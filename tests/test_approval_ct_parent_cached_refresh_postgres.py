"""Two-session PostgreSQL gate: CT may use only the current canonical PCT parent."""
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
from backend.app.db.models.phase1 import (
    AuditEvent, Case, Company, InspectionApprovalSubmission, Site,
)
from backend.app.services.workflow import CaseWorkflowService

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL.startswith("postgresql"):
    pytest.skip("requires disposable PostgreSQL", allow_module_level=True)


@pytest.mark.parametrize(
    "change,allow_ct",
    [("complete_cached_parent", True), ("move_cached_parent_to_other_case", False)],
)
def test_ct_parent_uses_fresh_authoritative_snapshot_after_case_lock(change, allow_ct):
    url = make_url(DATABASE_URL)
    if url.host not in {"127.0.0.1", "localhost"} or url.database != "gxp_qlcl_test":
        pytest.fail("Only loopback disposable gxp_qlcl_test is allowed; no mutations performed.")

    schema = "pct_parent_refresh_" + uuid4().hex
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
            company = Company(legal_name="PCT parent refresh " + schema)
            setup.add(company)
            setup.flush()
            site = Site(company_id=company.id, site_name="PCT parent refresh site")
            setup.add(site)
            setup.flush()
            first = Case(site_id=site.id, gxp_type="GMP", state=CaseState.INSPECTION_COMPLETED)
            other = Case(site_id=site.id, gxp_type="GMP", state=CaseState.INSPECTION_COMPLETED)
            setup.add_all([first, other])
            setup.flush()
            pct = InspectionApprovalSubmission(
                case_id=first.id, stage="PCT", round_no=1,
                completed_on=date(2026, 11, 11) if not allow_ct else None,
            )
            setup.add(pct)
            setup.commit()
            case_id, other_case_id, pct_id = first.id, other.id, pct.id

        contender = factory()
        cached = contender.get(InspectionApprovalSubmission, pct_id)
        assert cached is not None
        assert (cached.completed_on is None) == allow_ct
        assert cached.case_id == case_id

        # The writer changes committed PCT truth after another Session has
        # cached its identity, but before that Session acquires the Case lock.
        writer = factory()
        current = writer.get(InspectionApprovalSubmission, pct_id)
        if change == "complete_cached_parent":
            current.completed_on = date(2026, 11, 11)
        else:
            current.case_id = other_case_id
        writer.commit()

        service = CaseWorkflowService()
        user = build_authenticated_user("pct-parent-refresh", "manager")
        args = dict(
            case_id=case_id, stage="CT", reference="Synthetic CT",
            submitted_on=None, submitted_time=None, pct_submission_id=pct_id,
            reason="two-session PCT parent readback", user=user,
        )
        if allow_ct:
            created_ct = service.create_approval_submission(contender, **args)
            assert created_ct["stage"] == "CT"
            assert created_ct["pct_submission_id"] == pct_id
            contender.commit()
        else:
            with pytest.raises(HTTPException) as denied:
                service.create_approval_submission(contender, **args)
            assert denied.value.status_code == 422
            contender.rollback()

        with factory() as verify:
            rows = list(verify.scalars(select(InspectionApprovalSubmission).where(
                InspectionApprovalSubmission.case_id == case_id,
                InspectionApprovalSubmission.stage == "CT",
            )))
            assert len(rows) == (1 if allow_ct else 0)
            assert verify.scalar(select(func.count(AuditEvent.id))) == (1 if allow_ct else 0)
            persisted_pct = verify.get(InspectionApprovalSubmission, pct_id)
            assert persisted_pct.case_id == (case_id if allow_ct else other_case_id)
            assert persisted_pct.completed_on == date(2026, 11, 11)
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


def test_completion_refuses_submission_reassigned_away_from_cached_case_owner():
    url = make_url(DATABASE_URL)
    if url.host not in {"127.0.0.1", "localhost"} or url.database != "gxp_qlcl_test":
        pytest.fail("Only loopback disposable gxp_qlcl_test is allowed; no mutations performed.")
    schema = "approval_owner_refresh_" + uuid4().hex
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
            company = Company(legal_name="Approval completion owner " + schema)
            setup.add(company)
            setup.flush()
            site = Site(company_id=company.id, site_name="Approval completion owner site")
            setup.add(site)
            setup.flush()
            old_case = Case(site_id=site.id, gxp_type="GMP", state=CaseState.INSPECTION_COMPLETED)
            new_case = Case(site_id=site.id, gxp_type="GMP", state=CaseState.INSPECTION_COMPLETED)
            setup.add_all([old_case, new_case])
            setup.flush()
            submission = InspectionApprovalSubmission(case_id=old_case.id, stage="PCT", round_no=1)
            setup.add(submission)
            setup.commit()
            original_case_id, next_case_id, submission_id = old_case.id, new_case.id, submission.id

        contender = factory()
        cached = contender.get(InspectionApprovalSubmission, submission_id)
        assert cached.case_id == original_case_id

        writer = factory()
        current = writer.get(InspectionApprovalSubmission, submission_id)
        current.case_id = next_case_id
        writer.commit()
        new_version = current.row_version

        with pytest.raises(HTTPException) as denied:
            CaseWorkflowService().complete_approval_submission(
                contender, approval_submission_id=submission_id,
                expected_version=new_version,
                completed_on=date(2026, 11, 11), completed_time=None,
                reason="stale owner lock probe",
                user=build_authenticated_user("approval-owner-refresh", "manager"),
            )
        assert denied.value.status_code == 409
        assert "owner changed" in str(denied.value.detail)
        contender.rollback()

        with factory() as verify:
            persisted = verify.get(InspectionApprovalSubmission, submission_id)
            assert persisted.case_id == next_case_id
            assert persisted.completed_on is None
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
