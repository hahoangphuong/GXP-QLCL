"""InspectionPlan admission never flushes or overwrites cached operator drafts.

Synthetic disposable SQLite; preserve Case lock, optimistic version and audit.
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
    AuditEvent, Case, Company, InspectionPlan, Site,
)
from backend.app.services.workflow import CaseWorkflowService


USER = build_authenticated_user(
    "inspection-plan-admission", "manager", permissions={"inspection.edit"},
)


@pytest.fixture
def seeded(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'plan-owner-draft-admission.sqlite'}", future=True,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        company = Company(legal_name="Committed Company")
        db.add(company)
        db.flush()
        site = Site(company_id=company.id, site_name="Committed Site")
        db.add(site)
        db.flush()
        case = Case(site_id=site.id, gxp_type="GMP", state=CaseState.DRAFT)
        db.add(case)
        db.flush()
        plan = InspectionPlan(
            case_id=case.id, plan_start_on=date(2026, 11, 11),
        )
        db.add(plan)
        db.commit()
        ids = (case.id, plan.id, plan.row_version)
    try:
        yield engine, ids
    finally:
        engine.dispose()


def save(db, case_id, version):
    return CaseWorkflowService().upsert_inspection_plan(
        db, case_id=case_id, expected_version=version,
        plan_start_on=None, plan_end_on=date(2026, 11, 12),
        planning_sheet_name=None, decision_document_hint=None,
        decision_reference=None, decision_date=None,
        reason="Synthetic plan update", user=USER,
        fields_set={"plan_end_on"},
    )


def guard(engine, db):
    statements, flushes = [], []

    def record(_conn, _cursor, statement, _params, _context, _many):
        statements.append(statement.lstrip().split(None, 1)[0].upper())

    def forbidden(*_args):
        flushes.append(True)
        raise AssertionError("Rejected plan admission autoflushed operator drafts")

    event.listen(engine, "before_cursor_execute", record)
    event.listen(db, "before_flush", forbidden)
    return statements, flushes, record, forbidden


@pytest.mark.parametrize("dirty", ["case", "plan"])
def test_dirty_owner_rejected_before_flush_without_draft_loss(seeded, dirty):
    engine, (case_id, plan_id, version) = seeded
    with Session(engine, autoflush=True, expire_on_commit=False) as db:
        case = db.get(Case, case_id)
        plan = db.get(InspectionPlan, plan_id)
        if dirty == "case":
            case.state = CaseState.CLOSED
        else:
            plan.planning_sheet_name = "Uncommitted draft"
        pending = Company(legal_name="Operator draft Company")
        db.add(pending)
        statements, flushes, observe, forbidden = guard(engine, db)
        try:
            with pytest.raises(HTTPException) as exc:
                save(db, case_id, version)
        finally:
            event.remove(engine, "before_cursor_execute", observe)
            event.remove(db, "before_flush", forbidden)
        assert exc.value.status_code == 409
        assert not flushes and set(statements) <= {"SELECT"}
        owner = case if dirty == "case" else plan
        assert owner in db.dirty and pending in db.new
        if dirty == "case":
            assert case.state == CaseState.CLOSED
        else:
            assert plan.planning_sheet_name == "Uncommitted draft"
        db.rollback()
    with Session(engine) as verify:
        assert verify.get(Case, case_id).state == CaseState.DRAFT
        assert verify.get(InspectionPlan, plan_id).planning_sheet_name is None
        assert verify.get(InspectionPlan, plan_id).row_version == version
        assert verify.scalar(select(func.count(AuditEvent.id))) == 0
        assert verify.scalar(select(func.count(Company.id))) == 1


@pytest.mark.parametrize(("failure", "status"), [
    ("missing_case", 404), ("version", 409), ("invalid_dates", 422),
])
def test_rejected_admission_does_not_autoflush_unrelated_pending_company(
    seeded, failure, status,
):
    engine, (case_id, _, version) = seeded
    with Session(engine, autoflush=True) as db:
        pending = Company(legal_name="Operator pending Company")
        db.add(pending)
        statements, flushes, observe, forbidden = guard(engine, db)
        try:
            with pytest.raises(HTTPException) as exc:
                if failure == "missing_case":
                    save(db, str(uuid4()), version)
                elif failure == "version":
                    save(db, case_id, version + 100)
                else:
                    CaseWorkflowService().upsert_inspection_plan(
                        db, case_id=case_id, expected_version=version,
                        plan_start_on=date(2026, 11, 13),
                        plan_end_on=date(2026, 11, 12),
                        planning_sheet_name=None, decision_document_hint=None,
                        decision_reference=None, decision_date=None,
                        reason="Synthetic invalid date", user=USER,
                        fields_set={"plan_start_on", "plan_end_on"},
                    )
        finally:
            event.remove(engine, "before_cursor_execute", observe)
            event.remove(db, "before_flush", forbidden)
        assert exc.value.status_code == status
        assert not flushes and set(statements) <= {"SELECT"}
        assert pending in db.new
        db.rollback()
    with Session(engine) as verify:
        assert verify.scalar(select(func.count(Company.id))) == 1
        assert verify.scalar(select(func.count(AuditEvent.id))) == 0


def test_clean_plan_update_preserves_version_and_audit(seeded):
    engine, (case_id, plan_id, version) = seeded
    with Session(engine) as db:
        result = save(db, case_id, version)
        assert result["plan_end_on"] == date(2026, 11, 12)
        db.commit()
    with Session(engine) as verify:
        plan = verify.get(InspectionPlan, plan_id)
        assert plan.plan_start_on == date(2026, 11, 11)
        assert plan.plan_end_on == date(2026, 11, 12)
        assert plan.row_version == version + 1
        assert verify.scalar(select(func.count(AuditEvent.id))) == 1
