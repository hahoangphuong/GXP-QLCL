"""Two-session PostgreSQL regression for canonical CAPA owner and latest status.

Only runs against disposable loopback gxp_qlcl_test with its own ephemeral schema.
"""
from __future__ import annotations

import os
from datetime import date
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import sessionmaker

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import AuditEvent, CapaCycle, Case, Company, Site
from backend.app.services.workflow import CaseWorkflowService

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL.startswith("postgresql"):
    pytest.skip("requires disposable PostgreSQL", allow_module_level=True)


@pytest.mark.parametrize("scenario", [
    "cached_owner_reassigned",
    "cached_rejected_became_accepted",
    "cached_accepted_became_rejected",
])
def test_capa_mutations_revalidate_latest_committed_owner_and_status(scenario):
    url = make_url(DATABASE_URL)
    if url.host not in {"localhost", "127.0.0.1"} or url.database != "gxp_qlcl_test" or url.port != 5432:
        pytest.fail("Only loopback disposable gxp_qlcl_test: no mutations performed")

    schema = "capa_owner_latest_" + uuid4().hex
    admin = create_engine(DATABASE_URL, future=True)
    engine = contender = writer = None
    created = False
    try:
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        engine = create_engine(DATABASE_URL, connect_args={"options": f"-csearch_path={schema}"}, future=True)
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
        with factory() as setup:
            company = Company(legal_name="CAPA canonical owner/status " + schema)
            setup.add(company)
            setup.flush()
            site = Site(company_id=company.id, site_name="CAPA canonical site")
            setup.add(site)
            setup.flush()
            first = Case(site_id=site.id, gxp_type="GMP", state=CaseState.INSPECTION_COMPLETED)
            other = Case(site_id=site.id, gxp_type="GMP", state=CaseState.INSPECTION_COMPLETED)
            setup.add_all([first, other])
            setup.flush()
            status = "accepted" if scenario == "cached_accepted_became_rejected" else "rejected"
            cycle = CapaCycle(
                case_id=first.id, round_no=1, status=status, result=status,
                requested_on=date(2026, 11, 12), submitted_on=date(2026, 11, 12),
                assessed_on=date(2026, 11, 12),
            )
            setup.add(cycle)
            setup.commit()
            case_id, other_id, cycle_id = first.id, other.id, cycle.id

        contender = factory()
        cached = contender.get(CapaCycle, cycle_id)
        assert cached.case_id == case_id
        assert cached.status == status

        writer = factory()
        canonical = writer.get(CapaCycle, cycle_id)
        if scenario == "cached_owner_reassigned":
            canonical.case_id = other_id
        elif scenario == "cached_rejected_became_accepted":
            canonical.status = "accepted"
            canonical.result = "accepted"
        else:
            canonical.status = "rejected"
            canonical.result = "rejected"
        writer.commit()
        expected_version = canonical.row_version

        service = CaseWorkflowService()
        user = build_authenticated_user("ci-capa-owner", "manager")
        with pytest.raises(HTTPException) as denied:
            if scenario == "cached_owner_reassigned":
                service.submit_capa_cycle(
                    contender, capa_cycle_id=cycle_id,
                    expected_version=expected_version, submitted_on=date(2026, 11, 12),
                    notes="must not submit with stale owner", reason="owner regression", user=user,
                )
            elif scenario == "cached_rejected_became_accepted":
                service.create_capa_cycle(
                    contender, case_id=case_id, expected_case_version=None,
                    requested_on=date(2026, 11, 12),
                    incoming_reference="forbidden-second-round", notes=None,
                    reason="latest CAPA regression", user=user,
                )
            else:
                service.transition_case(
                    contender, case_id=case_id,
                    target_state=CaseState.AWAITING_CERTIFICATE_DECISION.value,
                    expected_version=None, reason="CAPA transition regression", user=user,
                )
        assert denied.value.status_code == 409
        contender.rollback()

        with factory() as verify:
            persisted = verify.get(CapaCycle, cycle_id)
            assert persisted.case_id == (other_id if scenario == "cached_owner_reassigned" else case_id)
            assert persisted.status == (
                "accepted" if scenario == "cached_rejected_became_accepted" else "rejected"
            )
            assert verify.get(Case, case_id).state == CaseState.INSPECTION_COMPLETED
            assert verify.scalar(select(func.count(CapaCycle.id))) == 1
            assert verify.scalar(select(func.count(AuditEvent.id))) == 0
    finally:
        for session in (contender, writer):
            if session is not None:
                session.rollback()
                session.close()
        if engine is not None:
            engine.dispose()
        if created:
            with admin.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
