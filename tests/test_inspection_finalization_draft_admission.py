"""Inspection finalization must not flush or lose locally edited owner drafts.

Synthetic disposable SQLite only. Parent Case and InspectionOutcome are
versioned/locked by the existing canonical mutation owner.
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import (
    AuditEvent, Case, Company, InspectionOutcome, Site,
)
from backend.app.services.workflow import CaseWorkflowService


USER = build_authenticated_user(
    "inspection-finalize-admission", "manager", permissions={"inspection.edit"},
)


@pytest.fixture
def seeded(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'inspection-finalize-drafts.sqlite').as_posix()}",
        future=True,
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
        outcome = InspectionOutcome(case_id=case.id, outcome_result="Compliant")
        db.add(outcome)
        db.commit()
        ids = (case.id, outcome.id, outcome.row_version)
    try:
        yield engine, ids
    finally:
        engine.dispose()


def finalize(db, case_id, version, evaluation="Final evaluation"):
    return CaseWorkflowService().finalize_inspection_outcome(
        db, case_id=case_id, expected_version=version,
        final_evaluation=evaluation, reason="Synthetic finalization", user=USER,
    )


def guard(engine, db):
    sql, flushes = [], []

    def on_sql(_conn, _cursor, statement, _params, _context, _many):
        sql.append(statement.lstrip().split(None, 1)[0].upper())

    def fail(*_args):
        flushes.append(True)
        raise AssertionError("Finalization admission autoflushed operator drafts")

    event.listen(engine, "before_cursor_execute", on_sql)
    event.listen(db, "before_flush", fail)
    return sql, flushes, on_sql, fail


def unguard(engine, db, on_sql, on_flush):
    event.remove(engine, "before_cursor_execute", on_sql)
    event.remove(db, "before_flush", on_flush)


@pytest.mark.parametrize("dirty", ["case", "outcome"])
def test_dirty_owner_fails_closed_without_flush_or_draft_loss(seeded, dirty):
    engine, (case_id, outcome_id, version) = seeded
    with Session(engine, autoflush=True, expire_on_commit=False) as db:
        case = db.get(Case, case_id)
        outcome = db.get(InspectionOutcome, outcome_id)
        if dirty == "case":
            case.state = CaseState.CLOSED
        else:
            outcome.outcome_result = "Uncommitted draft result"
        pending = Company(legal_name="Unrelated pending Company")
        db.add(pending)
        statements, flushes, observe, fail = guard(engine, db)
        try:
            with pytest.raises(HTTPException) as error:
                finalize(db, case_id, version)
        finally:
            unguard(engine, db, observe, fail)
        assert error.value.status_code == 409
        assert not flushes and set(statements) <= {"SELECT"}
        assert pending in db.new
        assert (case if dirty == "case" else outcome) in db.dirty
        if dirty == "case":
            assert case.state == CaseState.CLOSED
        else:
            assert outcome.outcome_result == "Uncommitted draft result"
        db.rollback()
    with Session(engine) as db:
        assert db.get(Case, case_id).state == CaseState.INSPECTION_COMPLETED
        assert db.get(InspectionOutcome, outcome_id).final_evaluation is None
        assert db.scalar(select(func.count(Company.id))) == 1
        assert db.scalar(select(func.count(AuditEvent.id))) == 0


@pytest.mark.parametrize("reason", ["missing_case", "missing_outcome", "blank_evaluation"])
def test_rejected_finalization_does_not_autoflush_pending_draft(seeded, reason):
    engine, (case_id, outcome_id, version) = seeded
    if reason == "missing_outcome":
        with Session(engine) as writer:
            writer.delete(writer.get(InspectionOutcome, outcome_id))
            writer.commit()
    with Session(engine, autoflush=True) as db:
        pending = Company(legal_name="Uncommitted Company")
        db.add(pending)
        statements, flushes, observe, fail = guard(engine, db)
        try:
            with pytest.raises(HTTPException) as error:
                finalize(
                    db, str(uuid4()) if reason == "missing_case" else case_id,
                    version, " " if reason == "blank_evaluation" else "Final evaluation",
                )
        finally:
            unguard(engine, db, observe, fail)
        assert error.value.status_code == (404 if reason == "missing_case" else 422)
        assert not flushes and set(statements) <= {"SELECT"}
        assert pending in db.new
        db.rollback()
    with Session(engine) as db:
        assert db.scalar(select(func.count(Company.id))) == 1
        assert db.scalar(select(func.count(AuditEvent.id))) == 0


def test_clean_finalization_preserves_immutable_result_version_and_audit(seeded):
    engine, (case_id, outcome_id, version) = seeded
    with Session(engine) as db:
        result = finalize(db, case_id, version)
        assert result["final_evaluation"] == "Final evaluation"
        db.commit()
    with Session(engine) as db:
        outcome = db.get(InspectionOutcome, outcome_id)
        assert outcome.final_evaluation == "Final evaluation"
        assert outcome.row_version == version + 1
        assert db.scalar(select(func.count(AuditEvent.id))) == 1
        same = finalize(db, case_id, outcome.row_version)
        assert same["final_evaluation"] == "Final evaluation"
        db.commit()
        assert db.scalar(select(func.count(AuditEvent.id))) == 1
