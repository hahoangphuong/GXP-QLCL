"""Rejected InspectionOutcome payloads cannot mutate an ORM Session before admission.

Only synthetic file-backed SQLite. The API transaction boundary is not a
substitute for fail-closed service ownership of drafts and audit rows.
"""
from __future__ import annotations

from datetime import date, time

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import AuditEvent, Case, Company, InspectionOutcome, Site
from backend.app.services.workflow import CaseWorkflowService


USER = build_authenticated_user("inspection-prewrite", "manager", permissions={"inspection.edit"})


@pytest.fixture
def seeded(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'prewrite.sqlite'}", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        company = Company(legal_name="Committed")
        db.add(company)
        db.flush()
        site = Site(company_id=company.id, site_name="Committed Site")
        db.add(site)
        db.flush()
        case = Case(site_id=site.id, gxp_type="GMP", state=CaseState.INSPECTION_COMPLETED)
        db.add(case)
        db.commit()
        case_id = case.id
    try:
        yield engine, case_id
    finally:
        engine.dispose()


def upsert(db, case_id, *, expected_version=None, fields=None, start=None,
           end=None, minutes_on=None, minutes_time=None):
    provided = fields or {"inspected_to_on"}
    return CaseWorkflowService().upsert_inspection_outcome(
        db, case_id=case_id, expected_version=expected_version,
        inspected_on=start, inspected_to_on=end,
        decision_reference=None, bbkt_reference=None, outcome_result=None,
        minutes_recorded_on=minutes_on, minutes_recorded_time=minutes_time,
        reason="Synthetic admission check", user=USER, fields_set=provided,
    )


@pytest.mark.parametrize("fields,values", [
    ({"inspected_to_on"}, {"end": date(2026, 11, 12)}),
    ({"minutes_recorded_time"}, {"minutes_time": time(10, 30)}),
])
def test_invalid_create_never_flushes_or_enqueues_outcome(seeded, fields, values):
    engine, case_id = seeded
    with Session(engine, autoflush=True, expire_on_commit=False) as db:
        unrelated = Company(legal_name="Uncommitted operator draft")
        db.add(unrelated)
        sql, flushes = [], []

        def track(_conn, _cursor, statement, *_args):
            sql.append(statement.lstrip().split(None, 1)[0].upper())

        def fail(*_args):
            flushes.append(True)
            raise AssertionError("Rejected InspectionOutcome request emitted a flush")

        event.listen(engine, "before_cursor_execute", track)
        event.listen(db, "before_flush", fail)
        try:
            with pytest.raises(HTTPException) as error:
                upsert(db, case_id, fields=fields, **values)
        finally:
            event.remove(engine, "before_cursor_execute", track)
            event.remove(db, "before_flush", fail)
        assert error.value.status_code == 422
        assert not flushes and set(sql) <= {"SELECT"}
        assert unrelated in db.new
        assert not any(isinstance(item, InspectionOutcome) for item in db.new)
        db.rollback()
    with Session(engine) as verify:
        assert verify.scalar(select(func.count(InspectionOutcome.id))) == 0
        assert verify.scalar(select(func.count(AuditEvent.id))) == 0
        assert verify.scalar(select(func.count(Company.id))) == 1


def test_invalid_existing_minutes_does_not_dirty_stage(seeded):
    engine, case_id = seeded
    with Session(engine) as db:
        stage = InspectionOutcome(case_id=case_id)
        db.add(stage)
        db.commit()
        stage_id, version = stage.id, stage.row_version
    with Session(engine, expire_on_commit=False) as db:
        cached = db.get(InspectionOutcome, stage_id)
        with pytest.raises(HTTPException) as error:
            upsert(
                db, case_id, expected_version=version,
                fields={"minutes_recorded_time"}, minutes_time=time(9, 15),
            )
        assert error.value.status_code == 422
        assert cached not in db.dirty
        assert cached.minutes_recorded_time is None
        assert not any(isinstance(item, AuditEvent) for item in db.new)
        db.rollback()
    with Session(engine) as verify:
        assert verify.scalar(select(func.count(AuditEvent.id))) == 0


@pytest.mark.parametrize("fields,kwargs", [
    ({"inspected_on", "inspected_to_on"}, {
        "start": date(2026, 11, 12), "end": date(2026, 11, 13),
    }),
    ({"minutes_recorded_on", "minutes_recorded_time"}, {
        "minutes_on": date(2026, 11, 12), "minutes_time": time(9, 30),
    }),
])
def test_valid_initial_outcome_still_commits_with_audit(seeded, fields, kwargs):
    engine, case_id = seeded
    with Session(engine) as db:
        result = upsert(db, case_id, fields=fields, **kwargs)
        assert result["case_id"] == case_id
        db.commit()
    with Session(engine) as verify:
        assert verify.scalar(select(func.count(InspectionOutcome.id))) == 1
        assert verify.scalar(select(func.count(AuditEvent.id))) == 1
