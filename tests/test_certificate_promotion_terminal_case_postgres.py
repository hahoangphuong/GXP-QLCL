"""PostgreSQL: promotion must revalidate the linked Case after closure.

The promotion Session caches a previously eligible Case. Another Session
commits a legal AWAITING_CERTIFICATE_DECISION -> CANCELLED transition.
Promotion must refresh and lock that Case, not issue a certificate into the
cancelled Case using the earlier ORM identity.
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
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import (
    AppUser, AuditEvent, Case, Certificate, CertificateVersion, Company,
    InspectionEvent, Site,
)
from backend.app.services.workflow import CaseWorkflowService

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL.startswith("postgresql"):
    pytest.skip("requires disposable PostgreSQL", allow_module_level=True)


def test_certificate_promotion_rechecks_cached_case_after_committed_cancellation():
    if make_url(DATABASE_URL).database != "gxp_qlcl_test":
        pytest.fail("Only disposable PostgreSQL gxp_qlcl_test is permitted.")
    schema = "cert_promotion_case_terminal_" + uuid4().hex
    admin = create_engine(DATABASE_URL, future=True)
    engine = contender = terminal_writer = None
    created = False
    try:
        with admin.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        engine = create_engine(
            DATABASE_URL, connect_args={"options": f"-csearch_path={schema}"}, future=True,
        )
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
        with factory() as seed:
            company = Company(legal_name="Synthetic promotion Case " + schema)
            seed.add(company); seed.flush()
            site = Site(company_id=company.id, site_name="Synthetic Case site")
            seed.add(site); seed.flush()
            case = Case(
                site_id=site.id, gxp_type="GMP",
                state=CaseState.AWAITING_CERTIFICATE_DECISION,
            )
            seed.add(case); seed.flush()
            cert = Certificate(
                site_id=site.id, case_id=case.id,
                certificate_type="GMP", issuance_basis="inspection_case",
                latest_flag=False,
            )
            seed.add(cert); seed.flush()
            seed.add(CertificateVersion(
                certificate_id=cert.id, version_no=1,
                certificate_number="GMP-CANDIDATE",
                issue_date=date(2026, 10, 1),
                expiry_date=date(2027, 10, 1), is_latest_version=True,
            ))
            seed.add(AppUser(
                username="synthetic-promotion-case", display_name="Synthetic manager",
                is_active=True,
            ))
            seed.commit()
            case_id, cert_id = case.id, cert.id
            case_token, cert_token = case.row_version, cert.row_version

        service = CaseWorkflowService()
        actor = build_authenticated_user("synthetic-promotion-case", "manager")
        contender = factory()
        cached_case = contender.get(Case, case_id)
        assert cached_case.state == CaseState.AWAITING_CERTIFICATE_DECISION

        terminal_writer = factory()
        transition = service.transition_case(
            terminal_writer, case_id=case_id,
            target_state=CaseState.CANCELLED.value,
            expected_version=case_token,
            reason="synthetic terminal transition", user=actor,
        )
        assert transition["current_state"] == CaseState.CANCELLED.value
        terminal_writer.commit()

        with pytest.raises(HTTPException) as denied:
            service.promote_certificate_current(
                contender, certificate_id=cert_id,
                expected_version=cert_token,
                reason="must not promote after cancellation", user=actor,
            )
        assert denied.value.status_code == 409
        contender.rollback()

        with factory() as verify:
            assert verify.get(Case, case_id).state == CaseState.CANCELLED
            assert verify.get(Certificate, cert_id).latest_flag is False
            assert verify.scalar(select(func.count(AuditEvent.id))) == 1
            assert verify.scalar(select(func.count(InspectionEvent.id))) == 0
    finally:
        for sess in (contender, terminal_writer):
            if sess is not None:
                sess.rollback()
                sess.close()
        if engine is not None:
            engine.dispose()
        if created:
            with admin.begin() as conn:
                conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
