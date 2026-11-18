"""PCT/CT creation admission: never flush/discard an unrelated operator draft.

Synthetic SQLite, separate committed writer for Case/PCT canonical revalidation.
"""
from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import (
    AuditEvent, Case, Company, InspectionApprovalSubmission, Site,
)
from backend.app.services.workflow import CaseWorkflowService

USER = build_authenticated_user(
    "synthetic-ct-parent-admission", "manager", permissions={"inspection.edit"},
)


@pytest.fixture
def seeded(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'approval-create-admission.sqlite').as_posix()}",
        future=True,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        company = Company(legal_name="Committed company")
        db.add(company)
        db.flush()
        site = Site(company_id=company.id, site_name="Committed site")
        db.add(site)
        db.flush()
        owner = Case(site_id=site.id, gxp_type="GMP", state=CaseState.INSPECTION_COMPLETED)
        other = Case(site_id=site.id, gxp_type="GLP", state=CaseState.INSPECTION_COMPLETED)
        db.add_all((owner, other))
        db.flush()
        pct = InspectionApprovalSubmission(
            case_id=owner.id, stage="PCT", round_no=1,
            reference="Committed PCT", completed_on=date(2026, 11, 15),
        )
        db.add(pct)
        db.commit()
        ids = (owner.id, other.id, pct.id)
    try:
        yield engine, ids
    finally:
        engine.dispose()


def create(db, case_id, parent_id, stage="CT"):
    return CaseWorkflowService().create_approval_submission(
        db, case_id=case_id, stage=stage,
        reference="Synthetic new submission", submitted_on=None, submitted_time=None,
        pct_submission_id=parent_id if stage == "CT" else None,
        reason="Synthetic creation admission regression", user=USER,
    )


def attach_guards(engine, db):
    sql, flushes = [], []

    def on_sql(_conn, _cursor, statement, _params, _ctx, _many):
        sql.append(statement.lstrip().split(None, 1)[0].upper())

    def reject_flush(*_args):
        flushes.append(True)
        raise AssertionError("Creation admission unexpectedly flushed an operator draft")

    event.listen(engine, "before_cursor_execute", on_sql)
    event.listen(db, "before_flush", reject_flush)
    return sql, flushes, on_sql, reject_flush


def detach_guards(engine, db, on_sql, reject_flush):
    event.remove(engine, "before_cursor_execute", on_sql)
    event.remove(db, "before_flush", reject_flush)


@pytest.mark.parametrize("dirty_kind", ["pct_reference", "pct_completed_on", "case_state"])
def test_uncommitted_owner_draft_fails_closed_without_flushing(seeded, dirty_kind):
    engine, (case_id, _, pct_id) = seeded
    with Session(engine, autoflush=True, expire_on_commit=False) as db:
        pct = db.get(InspectionApprovalSubmission, pct_id)
        case = db.get(Case, case_id)
        if dirty_kind == "pct_reference":
            pct.reference = "Uncommitted parent text"
        elif dirty_kind == "pct_completed_on":
            pct.completed_on = None
        else:
            case.state = CaseState.CLOSED
        pending = Company(legal_name="Unrelated draft Company")
        db.add(pending)
        sql, flushes, sql_cb, flush_cb = attach_guards(engine, db)
        try:
            with pytest.raises(HTTPException) as exc:
                create(db, case_id, pct_id)
        finally:
            detach_guards(engine, db, sql_cb, flush_cb)
        assert exc.value.status_code == 409
        assert not flushes and set(sql) <= {"SELECT"}
        assert pending in db.new
        assert (pct if dirty_kind.startswith("pct") else case) in db.dirty
        if dirty_kind == "pct_reference":
            assert pct.reference == "Uncommitted parent text"
        elif dirty_kind == "pct_completed_on":
            assert pct.completed_on is None
        else:
            assert case.state == CaseState.CLOSED
        db.rollback()

    with Session(engine) as db:
        assert db.scalar(select(func.count(InspectionApprovalSubmission.id))) == 1
        assert db.get(InspectionApprovalSubmission, pct_id).completed_on == date(2026, 11, 15)
        assert db.scalar(select(func.count(AuditEvent.id))) == 0
        assert db.scalar(select(func.count(Company.id))) == 1


@pytest.mark.parametrize("kind", ["missing_pct", "pct_not_completed"])
def test_rejected_ct_does_not_autoflush_pending_draft(seeded, kind):
    engine, (case_id, _, pct_id) = seeded
    if kind == "pct_not_completed":
        with Session(engine) as writer:
            writer.get(InspectionApprovalSubmission, pct_id).completed_on = None
            writer.commit()
    with Session(engine, autoflush=True) as db:
        pending = Company(legal_name="Pending unrelated Company")
        db.add(pending)
        sql, flushes, sql_cb, flush_cb = attach_guards(engine, db)
        try:
            with pytest.raises(HTTPException) as exc:
                create(db, case_id, str(uuid4()) if kind == "missing_pct" else pct_id)
        finally:
            detach_guards(engine, db, sql_cb, flush_cb)
        assert exc.value.status_code == (404 if kind == "missing_pct" else 422)
        assert not flushes and sql and set(sql) == {"SELECT"}
        assert pending in db.new
        db.rollback()
    with Session(engine) as db:
        assert db.scalar(select(func.count(InspectionApprovalSubmission.id))) == 1
        assert db.scalar(select(func.count(AuditEvent.id))) == 0



@pytest.mark.parametrize("stage", ["PCT", "CT"])
def test_dirty_historical_round_rejected_before_new_round_flush(seeded, stage):
    engine, (case_id, _, pct_id) = seeded
    with Session(engine, autoflush=True, expire_on_commit=False) as db:
        cached = db.get(InspectionApprovalSubmission, pct_id)
        cached.reference = "Uncommitted historical approval draft"
        pending = Company(legal_name="Unrelated pending Company")
        db.add(pending)
        sql, flushes, sql_cb, flush_cb = attach_guards(engine, db)
        try:
            with pytest.raises(HTTPException) as error:
                # For PCT the cached row is an older round; for CT it is
                # the completed parent. Both must remain unmodified.
                create(db, case_id, pct_id, stage=stage)
        finally:
            detach_guards(engine, db, sql_cb, flush_cb)
        assert error.value.status_code == 409
        assert not flushes and set(sql) <= {"SELECT"}
        assert cached in db.dirty and pending in db.new
        assert cached.reference == "Uncommitted historical approval draft"
        db.rollback()
    with Session(engine) as verify:
        assert verify.get(InspectionApprovalSubmission, pct_id).reference == "Committed PCT"
        assert verify.scalar(select(func.count(InspectionApprovalSubmission.id))) == 1
        assert verify.scalar(select(func.count(AuditEvent.id))) == 0
        assert verify.scalar(select(func.count(Company.id))) == 1


def test_ct_creation_rejects_dirty_different_pct_round(seeded):
    engine, (case_id, _, canonical_parent_id) = seeded
    with Session(engine) as seed:
        second = InspectionApprovalSubmission(
            case_id=case_id, stage="PCT", round_no=2,
            reference="Second committed PCT", completed_on=date(2026, 11, 16),
        )
        seed.add(second)
        seed.commit()
        sibling_id = second.id

    with Session(engine, autoflush=True, expire_on_commit=False) as db:
        parent = db.get(InspectionApprovalSubmission, canonical_parent_id)
        assert parent.reference == "Committed PCT"
        sibling = db.get(InspectionApprovalSubmission, sibling_id)
        sibling.reference = "Uncommitted sibling PCT draft"
        pending = Company(legal_name="Pending Company draft")
        db.add(pending)
        sql, flushes, sql_cb, flush_cb = attach_guards(engine, db)
        try:
            with pytest.raises(HTTPException) as error:
                create(db, case_id, canonical_parent_id, stage="CT")
        finally:
            detach_guards(engine, db, sql_cb, flush_cb)
        assert error.value.status_code == 409
        assert "Approval submission has uncommitted changes" in str(error.value.detail)
        assert not flushes and set(sql) <= {"SELECT"}
        assert sibling in db.dirty and sibling.reference == "Uncommitted sibling PCT draft"
        assert pending in db.new
        db.rollback()

    with Session(engine) as verify:
        assert verify.get(InspectionApprovalSubmission, sibling_id).reference == "Second committed PCT"
        assert verify.scalar(select(func.count(InspectionApprovalSubmission.id))) == 2
        assert verify.scalar(select(func.count(AuditEvent.id))) == 0


def test_clean_second_pct_round_still_allocates_and_audits(seeded):
    engine, (case_id, _, pct_id) = seeded
    with Session(engine) as db:
        response = create(db, case_id, pct_id, stage="PCT")
        assert response["stage"] == "PCT"
        assert response["round_no"] == 2
        db.commit()
    with Session(engine) as verify:
        rounds = list(verify.scalars(
            select(InspectionApprovalSubmission)
            .where(InspectionApprovalSubmission.case_id == case_id)
            .order_by(InspectionApprovalSubmission.round_no)
        ))
        assert [row.round_no for row in rounds] == [1, 2]
        assert rounds[0].reference == "Committed PCT"
        assert verify.scalar(select(func.count(AuditEvent.id))) == 1


def test_clean_ct_creation_preserves_parent_identity_round_and_audit(seeded):
    engine, (case_id, _, pct_id) = seeded
    with Session(engine) as db:
        result = create(db, case_id, pct_id)
        assert result["stage"] == "CT"
        assert result["round_no"] == 1
        assert result["pct_submission_id"] == pct_id
        db.commit()
    with Session(engine) as db:
        ct = db.scalar(select(InspectionApprovalSubmission).where(
            InspectionApprovalSubmission.case_id == case_id,
            InspectionApprovalSubmission.stage == "CT",
        ))
        assert ct.pct_submission_id == pct_id
        assert db.scalar(select(func.count(AuditEvent.id))) == 1
