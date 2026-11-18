"""Fail-closed CAPA mutation admission for dirty owning Case and sibling rounds.

Synthetic disposable SQLite. No real database or deployment mutation.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import AuditEvent, CapaCycle, Case, Company, Site
from backend.app.services.workflow import CaseWorkflowService


@pytest.fixture
def seeded(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'capa-dirty-parent.sqlite'}", future=True)
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
        cycle = CapaCycle(case_id=case.id, round_no=1, status="requested")
        db.add(cycle)
        db.commit()
        ids = case.id, cycle.id, cycle.row_version
    try:
        yield engine, ids
    finally:
        engine.dispose()


def guarded(engine, db):
    sql, flushes = [], []

    def record(_conn, _cursor, statement, _params, _ctx, _many):
        sql.append(statement.lstrip().split(None, 1)[0].upper())

    def reject(*_args):
        flushes.append(True)
        raise AssertionError("CAPA admission unexpectedly flushed a draft")

    event.listen(engine, "before_cursor_execute", record)
    event.listen(db, "before_flush", reject)
    return sql, flushes, record, reject


def stop_guard(engine, db, record, reject):
    event.remove(engine, "before_cursor_execute", record)
    event.remove(db, "before_flush", reject)


@pytest.mark.parametrize("operation", ["CAPA update", "CAPA submit", "CAPA assess"])
def test_dirty_case_parent_rejected_before_refresh_without_draft_loss(seeded, operation):
    engine, (case_id, cycle_id, _) = seeded
    with Session(engine, autoflush=True, expire_on_commit=False) as db:
        parent = db.get(Case, case_id)
        parent.state = CaseState.CLOSED
        pending = Company(legal_name="Pending Company")
        db.add(pending)
        sql, flushes, record, reject = guarded(engine, db)
        try:
            with pytest.raises(HTTPException) as error:
                CaseWorkflowService()._lock_capa_parent_then_refresh(
                    db, capa_cycle_id=cycle_id, operation=operation,
                )
        finally:
            stop_guard(engine, db, record, reject)
        assert error.value.status_code == 409
        assert "Case has uncommitted changes" in str(error.value.detail)
        assert not flushes and set(sql) <= {"SELECT"}
        assert parent.state == CaseState.CLOSED and parent in db.dirty
        assert pending in db.new
        db.rollback()
    with Session(engine) as check:
        assert check.get(Case, case_id).state == CaseState.INSPECTION_COMPLETED
        assert check.scalar(select(func.count(Company.id))) == 1
        assert check.scalar(select(func.count(AuditEvent.id))) == 0


def test_dirty_latest_round_rejected_before_historical_target_refresh(seeded):
    engine, (case_id, old_id, _) = seeded
    with Session(engine) as seed:
        old = seed.get(CapaCycle, old_id)
        old.status = "rejected"
        old.result = "rejected"
        latest = CapaCycle(case_id=case_id, round_no=2, status="requested")
        seed.add(latest)
        seed.commit()
        latest_id = latest.id

    with Session(engine, autoflush=True, expire_on_commit=False) as db:
        latest = db.get(CapaCycle, latest_id)
        latest.notes = "Latest round uncommitted operator draft"
        pending = Company(legal_name="Another pending Company")
        db.add(pending)
        sql, flushes, record, reject = guarded(engine, db)
        try:
            with pytest.raises(HTTPException) as error:
                # An attempt to mutate an older round must not discard
                # the newer cached round by populate_existing refresh.
                CaseWorkflowService()._lock_capa_parent_then_refresh(
                    db, capa_cycle_id=old_id, operation="CAPA update",
                )
        finally:
            stop_guard(engine, db, record, reject)
        assert error.value.status_code == 409
        assert "CAPA cycle has uncommitted changes" in str(error.value.detail)
        assert not flushes and set(sql) <= {"SELECT"}
        assert latest in db.dirty
        assert latest.notes == "Latest round uncommitted operator draft"
        assert pending in db.new
        db.rollback()
    with Session(engine) as verify:
        assert verify.get(CapaCycle, latest_id).notes is None
        assert verify.scalar(select(func.count(AuditEvent.id))) == 0


def test_clean_request_update_submit_assess_still_progresses(seeded):
    engine, (_, cycle_id, version) = seeded
    edit_user = build_authenticated_user(
        "synthetic-capa-editor", "manager", permissions={"capa.edit"},
    )
    assessor = build_authenticated_user(
        "synthetic-capa-assessor", "manager", permissions={"capa.assess"},
    )
    service = CaseWorkflowService()

    with Session(engine) as db:
        changed = service.update_capa_cycle(
            db, capa_cycle_id=cycle_id, expected_version=version,
            requested_on=None, incoming_reference="Incoming", notes="Draft",
            reason="Synthetic update", user=edit_user,
            fields_set={"incoming_reference", "notes"},
        )
        db.commit()
    with Session(engine) as db:
        submitted = service.submit_capa_cycle(
            db, capa_cycle_id=cycle_id, expected_version=changed["row_version"],
            submitted_on=date(2026, 11, 18), notes="Submitted",
            reason="Synthetic submit", user=edit_user,
        )
        db.commit()
    with Session(engine) as db:
        assessed = service.assess_capa_cycle(
            db, capa_cycle_id=cycle_id, expected_version=submitted["row_version"],
            assessed_on=date(2026, 11, 18),
            assessor_name="Untrusted client assessor", result="accepted",
            notes="Accepted", reason="Synthetic assess", user=assessor,
        )
        db.commit()
    with Session(engine) as db:
        persisted = db.get(CapaCycle, cycle_id)
        assert assessed["status"] == "accepted"
        assert persisted.status == "accepted"
        assert persisted.assessor_name != "Untrusted client assessor"
        assert db.scalar(select(func.count(AuditEvent.id))) == 3
