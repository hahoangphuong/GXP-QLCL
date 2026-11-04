"""Regression: a GxP certificate already current must not be promoted again.

Use a disposable PostgreSQL schema. A second promotion is not a state transition
and must not create a duplicate success audit (or an issuance inspection event).
"""
from __future__ import annotations

from datetime import date
import os
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import sessionmaker

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.models.phase1 import (
    AppUser, AuditEvent, Certificate, CertificateVersion, Company, Site,
)
from backend.app.services.workflow import CaseWorkflowService

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL.startswith("postgresql"):
    pytest.skip("requires disposable PostgreSQL", allow_module_level=True)


def test_repeated_gxp_current_promotion_rejected_without_duplicate_audit():
    if make_url(DATABASE_URL).database != "gxp_qlcl_test":
        pytest.fail("Only disposable PostgreSQL gxp_qlcl_test is permitted.")
    schema = "gxp_already_current_" + uuid4().hex
    admin = create_engine(DATABASE_URL, future=True)
    engine = None
    created = False
    try:
        with admin.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        engine = create_engine(
            DATABASE_URL,
            connect_args={"options": f"-csearch_path={schema}"},
            future=True,
        )
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
        with factory() as seed:
            company = Company(legal_name="Synthetic repeated GxP promotion " + schema)
            seed.add(company)
            seed.flush()
            site = Site(company_id=company.id, site_name="Synthetic GxP promotion")
            seed.add(site)
            seed.flush()
            certificate = Certificate(
                site_id=site.id, certificate_type="GLP", latest_flag=False,
            )
            seed.add(certificate)
            seed.flush()
            seed.add(CertificateVersion(
                certificate_id=certificate.id,
                version_no=1,
                certificate_number="SYNTHETIC-GLP-1",
                issue_date=date(2026, 9, 1),
                expiry_date=date(2027, 9, 1),
                is_latest_version=True,
            ))
            seed.add(AppUser(
                username="synthetic-repeated-promotion",
                display_name="Synthetic actor",
                is_active=True,
            ))
            seed.commit()
            certificate_id = certificate.id
            initial_token = certificate.row_version

        service = CaseWorkflowService()
        actor = build_authenticated_user("synthetic-repeated-promotion", "manager")
        with factory() as first:
            promoted = service.promote_certificate_current(
                first,
                certificate_id=certificate_id,
                expected_version=initial_token,
                reason="Initial current promotion",
                user=actor,
            )
            assert promoted["latest_flag"] is True
            first.commit()
            current_token = promoted["row_version"]

        with factory() as repeated:
            with pytest.raises(HTTPException) as denied:
                service.promote_certificate_current(
                    repeated,
                    certificate_id=certificate_id,
                    expected_version=current_token,
                    reason="Must reject redundant promotion",
                    user=actor,
                )
            assert denied.value.status_code == 409
            repeated.rollback()

        with factory() as verify:
            persisted = verify.get(Certificate, certificate_id)
            assert persisted.latest_flag is True
            assert persisted.row_version == current_token
            assert verify.scalar(select(func.count(AuditEvent.id))) == 1
    finally:
        if engine is not None:
            engine.dispose()
        if created:
            with admin.begin() as conn:
                conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
