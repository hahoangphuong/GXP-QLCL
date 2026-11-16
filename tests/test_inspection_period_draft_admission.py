"""Actual inspection period replace-all admission preserves operator drafts.

Synthetic SQLite. Existing PostgreSQL concurrency/audit-source gates remain
the authority for committed Case, Outcome and Segment snapshots.
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
    "period-draft-admission", "manager", permissions={"inspection.edit"},
)


@pytest.fixture
def seeded(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'period-draft-admission.sqlite').as_posix()}",
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


VALID = [{"ordinal": 1, "started_on": date(2026, 11, 12), "ended_on": date(2026, 11, 13)}]


def replace(db, case_id, version, segments=None):
    return CaseWorkflowService().upsert_inspection_period_segments(
        db, case_id=case_id, expected_version=version,
        segments=VALID if segments is None else segments,
        reason="Synthetic period replacement", user=USER,
    )


def guard(engine, db):
    sql, flushes = [], []

    def on_sql(_conn, _cursor, statement, _params, _context, _many):
        sql.append(statement.lstrip().split(None, 1)[0].upper())

    def fail(*_args):
        flushes.append(True)
        raise AssertionError("Period admission autoflushed an operator draft")

    event.listen(engine, "before_cursor_execute", on_sql)
    event.listen(db, "before_flush", fail)
    return sql, flushes, on_sql, fail


def unguard(engine, db, on_sql, fail):
    event.remove(engine, "before_cursor_execute", on_sql)
    event.remove(db, "before_flush", fail)


@pytest.mark.parametrize("dirty", ["case", "outcome", "segment"])
def test_dirty_owner_is_rejected_without_overwriting_draft(seeded, dirty):
    engine, (case_id, outcome_id, segment_id, version) = seeded
    with Session(engine, autoflush=True, expire_on_commit=False) as db:
        case = db.get(Case, case_id)
        outcome = db.get(InspectionOutcome, outcome_id)
        segment = db.get(InspectionPeriodSegment, segment_id)
        if dirty == "case":
            case.state = CaseState.CLOSED
        elif dirty == "outcome":
            outcome.outcome_result = "Uncommitted outcome draft"
        else:
            segment.started_on = date(2026, 11, 10)
        pending = Company(legal_name="Uncommitted Company")
        db.add(pending)
        statements, flushes, on_sql, fail = guard(engine, db)
        try:
            with pytest.raises(HTTPException) as error:
                replace(db, case_id, version)
        finally:
            unguard(engine, db, on_sql, fail)
        assert error.value.status_code == 409
        assert not flushes and set(statements) <= {"SELECT"}
        owned = {"case": case, "outcome": outcome, "segment": segment}[dirty]
        assert owned in db.dirty and pending in db.new
        if dirty == "case":
            assert case.state == CaseState.CLOSED
        elif dirty == "outcome":
            assert outcome.outcome_result == "Uncommitted outcome draft"
        else:
            assert segment.started_on == date(2026, 11, 10)
        db.rollback()
    with Session(engine) as db:
        assert db.get(InspectionPeriodSegment, segment_id).started_on == date(2026, 11, 11)
        assert db.get(InspectionOutcome, outcome_id).row_version == version
        assert db.scalar(select(func.count(Company.id))) == 1
        assert db.scalar(select(func.count(AuditEvent.id))) == 0


@pytest.mark.parametrize(("kind", "status"), [
    ("missing_case", 404),
    ("empty", 422),
    ("ordinal_gap", 422),
    ("reverse_dates", 422),
])
def test_rejected_replace_does_not_flush_unrelated_pending_draft(seeded, kind, status):
    engine, (case_id, _, _, version) = seeded
    bad_segments = {
        "empty": [],
        "ordinal_gap": [{"ordinal": 2, "started_on": date(2026, 11, 12), "ended_on": date(2026, 11, 12)}],
        "reverse_dates": [{"ordinal": 1, "started_on": date(2026, 11, 13), "ended_on": date(2026, 11, 12)}],
    }
    with Session(engine, autoflush=True) as db:
        pending = Company(legal_name="Pending operator Company")
        db.add(pending)
        statements, flushes, on_sql, fail = guard(engine, db)
        try:
            with pytest.raises(HTTPException) as error:
                replace(
                    db, str(uuid4()) if kind == "missing_case" else case_id,
                    version, bad_segments.get(kind, VALID),
                )
        finally:
            unguard(engine, db, on_sql, fail)
        assert error.value.status_code == status
        assert not flushes and set(statements) <= {"SELECT"}
        assert pending in db.new
        db.rollback()
    with Session(engine) as db:
        assert db.scalar(select(func.count(Company.id))) == 1
        assert db.scalar(select(func.count(AuditEvent.id))) == 0


def test_clean_replace_preserves_version_period_and_single_audit(seeded):
    engine, (case_id, outcome_id, _, version) = seeded
    with Session(engine) as db:
        result = replace(db, case_id, version)
        assert result["row_version"] > version
        db.commit()
    with Session(engine) as db:
        segments = db.scalars(
            select(InspectionPeriodSegment)
            .where(InspectionPeriodSegment.inspection_outcome_id == outcome_id)
        ).all()
        assert len(segments) == 1
        assert segments[0].started_on == date(2026, 11, 12)
        assert segments[0].ended_on == date(2026, 11, 13)
        assert db.scalar(select(func.count(AuditEvent.id))) == 1
