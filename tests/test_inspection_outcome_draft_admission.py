"""Inspection outcome compatibility mutation must reject dirty cached owners.

Synthetic isolated SQLite; no rehearsal or production database access.
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
    AuditEvent, Case, Company, InspectionOutcome, InspectionPeriodSegment, Site,
)
from backend.app.services.workflow import CaseWorkflowService


USER = build_authenticated_user(
    "outcome-admission-regression", "manager", permissions={"inspection.edit"},
)


@pytest.fixture
def seeded(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'outcome-admission.sqlite').as_posix()}", future=True,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        company = Company(legal_name="Committed Company")
        db.add(company)
        db.flush()
        site = Site(company_id=company.id, site_name="Committed Site")
        db.add(site)
        db.flush()
        case = Case(site_id=site.id, gxp_type="GMP", state=CaseState.INSPECTION_COMPLETED)
        db.add(case)
        db.flush()
        outcome = InspectionOutcome(
            case_id=case.id, inspection_period_state="KNOWN",
            inspected_on=date(2026, 11, 11), inspected_to_on=date(2026, 11, 11),
        )
        db.add(outcome)
        db.flush()
        segment = InspectionPeriodSegment(
            inspection_outcome_id=outcome.id, ordinal=1,
            started_on=date(2026, 11, 11), ended_on=date(2026, 11, 11),
        )
        db.add(segment)
        db.commit()
        ids = (case.id, outcome.id, segment.id, outcome.row_version)
    try:
        yield engine, ids
    finally:
        engine.dispose()


def mutate(db, case_id, version, *, provided=None):
    fields = {"outcome_result"} if provided is None else provided
    return CaseWorkflowService().upsert_inspection_outcome(
        db, case_id=case_id, expected_version=version,
        inspected_on=date(2026, 11, 12) if "inspected_on" in fields else None,
        inspected_to_on=date(2026, 11, 12) if "inspected_to_on" in fields else None,
        decision_reference=None, bbkt_reference=None,
        outcome_result="Compliant" if "outcome_result" in fields else None,
        reason="Synthetic outcome admission", user=USER, fields_set=fields,
    )


def observe_admission(engine, db):
    statements = []
    flushes = []

    def track(_conn, _cursor, statement, _params, _context, _many):
        statements.append(statement.lstrip().split(None, 1)[0].upper())

    def reject_flush(*_args):
        flushes.append(True)
        raise AssertionError("Rejected outcome admission autoflushed an operator draft")

    event.listen(engine, "before_cursor_execute", track)
    event.listen(db, "before_flush", reject_flush)
    return statements, flushes, track, reject_flush


@pytest.mark.parametrize("dirty", ["case", "outcome", "segment"])
def test_dirty_owner_fails_closed_before_flush_and_keeps_draft(seeded, dirty):
    engine, (case_id, outcome_id, segment_id, version) = seeded
    with Session(engine, autoflush=True, expire_on_commit=False) as db:
        case = db.get(Case, case_id)
        outcome = db.get(InspectionOutcome, outcome_id)
        segment = db.get(InspectionPeriodSegment, segment_id)
        if dirty == "case":
            case.state = CaseState.CLOSED
        elif dirty == "outcome":
            outcome.outcome_result = "Local outcome draft"
        else:
            segment.started_on = date(2026, 11, 10)
        pending = Company(legal_name="Unrelated pending Company")
        db.add(pending)
        statements, flushes, track, reject_flush = observe_admission(engine, db)
        try:
            with pytest.raises(HTTPException) as error:
                mutate(db, case_id, version)
        finally:
            event.remove(engine, "before_cursor_execute", track)
            event.remove(db, "before_flush", reject_flush)
        assert error.value.status_code == 409
        assert not flushes and set(statements) <= {"SELECT"}
        owned = {"case": case, "outcome": outcome, "segment": segment}[dirty]
        assert owned in db.dirty and pending in db.new
        if dirty == "case":
            assert case.state == CaseState.CLOSED
        elif dirty == "outcome":
            assert outcome.outcome_result == "Local outcome draft"
        else:
            assert segment.started_on == date(2026, 11, 10)
        db.rollback()
    with Session(engine) as db:
        assert db.get(InspectionOutcome, outcome_id).row_version == version
        assert db.get(InspectionPeriodSegment, segment_id).started_on == date(2026, 11, 11)
        assert db.scalar(select(func.count(Company.id))) == 1
        assert db.scalar(select(func.count(AuditEvent.id))) == 0


def test_clean_outcome_update_preserves_version_and_audit(seeded):
    engine, (case_id, outcome_id, _, version) = seeded
    with Session(engine) as db:
        result = mutate(db, case_id, version, provided={"outcome_result"})
        assert result["outcome_result"] == "Compliant"
        db.commit()
    with Session(engine) as db:
        row = db.get(InspectionOutcome, outcome_id)
        assert row.outcome_result == "Compliant"
        assert row.row_version == version + 1
        assert db.scalar(select(func.count(AuditEvent.id))) == 1


def test_missing_case_with_pending_draft_does_not_flush(seeded):
    engine, (_, _, _, version) = seeded
    with Session(engine, autoflush=True) as db:
        pending = Company(legal_name="Pending operator Company")
        db.add(pending)
        statements, flushes, track, reject_flush = observe_admission(engine, db)
        try:
            with pytest.raises(HTTPException) as error:
                mutate(db, str(uuid4()), version)
        finally:
            event.remove(engine, "before_cursor_execute", track)
            event.remove(db, "before_flush", reject_flush)
        assert error.value.status_code == 404
        assert not flushes and set(statements) <= {"SELECT"}
        assert pending in db.new
        db.rollback()
