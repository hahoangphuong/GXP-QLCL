"""Two-session PostgreSQL regression: Case issuance readiness must see committed Case state.

A cached eligible Case may be cancelled by another transaction. Readiness
must not advertise issuance after that committed cancellation. The mutation
itself already revalidates under the Case owner lock; this only tests projection.
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
from backend.app.db.models.phase1 import AuditEvent, Case, Certificate, Company, Site
from backend.app.services.workflow import CaseWorkflowService

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL.startswith("postgresql"):
    pytest.skip("requires disposable PostgreSQL", allow_module_level=True)


def test_case_certificate_readiness_rejects_cached_pre_cancellation_case():
    if make_url(DATABASE_URL).database != "gxp_qlcl_test":
        pytest.fail("Only disposable PostgreSQL gxp_qlcl_test is permitted.")
    schema = "case_issue_stale_" + uuid4().hex
    admin = create_engine(DATABASE_URL, future=True)
    engine = None
    cached_session = None
    created = False
    try:
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        engine = create_engine(
            DATABASE_URL,
            connect_args={"options": f"-csearch_path={schema}"},
            future=True,
        )
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
        with factory() as seed:
            company = Company(legal_name="Synthetic Case readiness " + schema)
            seed.add(company)
            seed.flush()
            site = Site(company_id=company.id, site_name="Synthetic issuance readiness")
            seed.add(site)
            seed.flush()
            case = Case(
                site_id=site.id,
                gxp_type="GMP",
                state=CaseState.AWAITING_CERTIFICATE_DECISION,
            )
            seed.add(case)
            seed.commit()
            case_id, site_id, token = case.id, site.id, case.row_version

        service = CaseWorkflowService()
        actor = build_authenticated_user("synthetic-case-readiness", "admin",
                                         permissions=["certificate.issue", "case.edit"])
        cached_session = factory()
        cached = cached_session.get(Case, case_id)
        assert cached.state == CaseState.AWAITING_CERTIFICATE_DECISION
        before = service.get_case_certificate_issue_readiness(
            cached_session, case_id=case_id, user=actor,
        )
        assert before["available"] is True
        assert before["reason_code"] is None

        with factory() as writer:
            changed = service.transition_case(
                writer, case_id=case_id, target_state=CaseState.CANCELLED.value,
                expected_version=token,
                reason="Synthetic cancellation after readiness was cached", user=actor,
            )
            assert changed["current_state"] == CaseState.CANCELLED.value
            writer.commit()
        assert cached.state == CaseState.AWAITING_CERTIFICATE_DECISION, (
            "Precondition: Session A retains stale ORM Case state"
        )

        after = service.get_case_certificate_issue_readiness(
            cached_session, case_id=case_id, user=actor,
        )
        assert after["available"] is False
        assert after["reason_code"] == "case_state_not_eligible"
        # The owning issue mutation must already fail closed even if a caller
        # used old readiness; no new Certificate or success issuance audit.
        with factory() as attempting:
            with pytest.raises(HTTPException) as denied:
                service.issue_certificate(
                    attempting, site_id=site_id, case_id=case_id,
                    certificate_type="GMP", issuance_basis="inspection_case",
                    certificate_number="SYNTHETIC-NOT-ISSUED",
                    issue_date=date(2026, 11, 5),
                    expiry_date=date(2027, 11, 5),
                    scopes=[], reason="Must not issue for cancelled Case", user=actor,
                )
            assert denied.value.status_code == 409
            attempting.rollback()

        with factory() as verify:
            assert verify.get(Case, case_id).state == CaseState.CANCELLED
            assert verify.scalar(select(func.count(Certificate.id))) == 0
            assert verify.scalar(select(func.count(AuditEvent.id))) == 1
    finally:
        if cached_session is not None:
            cached_session.rollback()
            cached_session.close()
        if engine is not None:
            engine.dispose()
        if created:
            with admin.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
