"""PostgreSQL regression: GxP promotion compares against committed current version date.

A stale Session caches current GxP certificate version before a separate
editor commits a new issue date. Promotion of now-backdated candidate must fail.
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


def test_gxp_promotion_rejects_backdate_against_updated_cached_current_version():
    if make_url(DATABASE_URL).database != "gxp_qlcl_test":
        pytest.fail("Only disposable PostgreSQL gxp_qlcl_test is permitted.")
    schema = "gxp_current_version_" + uuid4().hex
    admin = create_engine(DATABASE_URL, future=True)
    engine = contender = editor = None
    created = False
    try:
        with admin.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        engine = create_engine(DATABASE_URL, connect_args={"options": f"-csearch_path={schema}"}, future=True)
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
        with factory() as seed:
            company = Company(legal_name="Synthetic GxP current-version " + schema)
            seed.add(company)
            seed.flush()
            site = Site(company_id=company.id, site_name="Synthetic GxP current-date site")
            seed.add(site)
            seed.flush()
            current = Certificate(site_id=site.id, certificate_type="GLP", latest_flag=True)
            candidate = Certificate(site_id=site.id, certificate_type="GLP", latest_flag=False)
            seed.add_all([current, candidate])
            seed.flush()
            current_version = CertificateVersion(
                certificate_id=current.id, version_no=1,
                certificate_number="CURRENT-B", issue_date=date(2026, 8, 1),
                expiry_date=date(2027, 8, 1), is_latest_version=True,
            )
            candidate_version = CertificateVersion(
                certificate_id=candidate.id, version_no=1,
                certificate_number="CANDIDATE-C", issue_date=date(2026, 9, 1),
                expiry_date=date(2027, 9, 1), is_latest_version=True,
            )
            seed.add_all([current_version, candidate_version])
            seed.add(AppUser(username="synthetic-gxp-current-date", display_name="Synthetic actor", is_active=True))
            seed.commit()
            site_id = site.id
            current_id, current_version_id, current_token = current.id, current_version.id, current.row_version
            candidate_id, candidate_token = candidate.id, candidate.row_version

        service = CaseWorkflowService()
        actor = build_authenticated_user("synthetic-gxp-current-date", "manager")
        contender = factory()
        cached_current_version = contender.get(CertificateVersion, current_version_id)
        assert cached_current_version.issue_date == date(2026, 8, 1)

        editor = factory()
        service.upsert_certificate_latest_version(
            editor, certificate_id=current_id, expected_version=current_token,
            certificate_number="CURRENT-B", issue_date=date(2026, 10, 1),
            expiry_date=date(2027, 10, 1), scopes=[],
            reason="Correct GxP current issue date", user=actor,
        )
        editor.commit()
        assert cached_current_version.issue_date == date(2026, 8, 1)

        with pytest.raises(HTTPException) as denied:
            service.promote_certificate_current(
                contender, certificate_id=candidate_id,
                expected_version=candidate_token,
                reason="Reject GxP candidate older than corrected current",
                user=actor,
            )
        assert denied.value.status_code == 409
        assert "older than the current" in str(denied.value.detail).lower()
        contender.rollback()

        with factory() as verify:
            current_rows = list(verify.scalars(select(Certificate).where(
                Certificate.site_id == site_id,
                Certificate.certificate_type == "GLP",
                Certificate.latest_flag.is_(True),
            )))
            assert [row.id for row in current_rows] == [current_id]
            assert verify.get(CertificateVersion, current_version_id).issue_date == date(2026, 10, 1)
            assert verify.scalar(select(func.count(AuditEvent.id))) == 1
    finally:
        for session in (contender, editor):
            if session is not None:
                session.rollback()
                session.close()
        if engine is not None:
            engine.dispose()
        if created:
            with admin.begin() as conn:
                conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
