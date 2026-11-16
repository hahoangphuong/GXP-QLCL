"""CAPA owner admission is SELECT-only and does not discard cached CAPA drafts.

Synthetic SQLite only. No real database, HTTP writes, or bypass of Case locks.
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import AuditEvent, CapaCycle, Case, Company, Site
from backend.app.services.workflow import CaseWorkflowService


@pytest.fixture
def seeded(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'capa-parent-admission.sqlite').as_posix()}",
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
        case = Case(
            site_id=site.id, gxp_type="GMP",
            state=CaseState.INSPECTION_COMPLETED,
        )
        db.add(case)
        db.flush()
        cycle = CapaCycle(case_id=case.id, round_no=1, status="requested")
        db.add(cycle)
        db.commit()
        ids = (case.id, cycle.id)
    try:
        yield engine, ids
    finally:
        engine.dispose()


def admission(db, cycle_id):
    return CaseWorkflowService()._lock_capa_parent_then_refresh(
        db, capa_cycle_id=cycle_id, operation="CAPA update",
    )


def install_sql_guards(engine, db):
    statements, flushes = [], []

    def observe(_conn, _cursor, statement, _params, _context, _many):
        statements.append(statement.lstrip().split(None, 1)[0].upper())

    def reject_flush(*_args):
        flushes.append(True)
        raise AssertionError("CAPA owner admission triggered unintended autoflush")

    event.listen(engine, "before_cursor_execute", observe)
    event.listen(db, "before_flush", reject_flush)
    return statements, flushes, observe, reject_flush


def test_owner_admission_keeps_unrelated_drafts_and_never_autoflushes(seeded):
    engine, (_, cycle_id) = seeded
    with Session(engine, autoflush=True, expire_on_commit=False) as db:
        pending = Company(legal_name="Pending company")
        db.add(pending)
        statements, flushes, observe, reject_flush = install_sql_guards(engine, db)
        try:
            locked = admission(db, cycle_id)
        finally:
            event.remove(engine, "before_cursor_execute", observe)
            event.remove(db, "before_flush", reject_flush)
        assert locked.id == cycle_id
        assert locked.status == "requested"
        assert statements and set(statements) == {"SELECT"}
        assert not flushes
        assert pending in db.new
        db.rollback()
    with Session(engine) as check:
        assert check.scalar(select(func.count(Company.id))) == 1
        assert check.scalar(select(func.count(AuditEvent.id))) == 0


@pytest.mark.parametrize("draft_field,draft_value", [
    ("notes", "Operator CAPA draft"),
    ("case_id", "other-owner-draft"),
])
def test_cached_dirty_cycle_is_rejected_without_losing_draft_or_writes(
    seeded, draft_field, draft_value,
):
    engine, (case_id, cycle_id) = seeded
    with Session(engine, autoflush=True, expire_on_commit=False) as db:
        cycle = db.get(CapaCycle, cycle_id)
        draft = str(uuid4()) if draft_field == "case_id" else draft_value
        setattr(cycle, draft_field, draft)
        pending = Company(legal_name="Unrelated pending draft")
        db.add(pending)
        statements, flushes, observe, reject_flush = install_sql_guards(engine, db)
        try:
            with pytest.raises(HTTPException) as ex:
                admission(db, cycle_id)
        finally:
            event.remove(engine, "before_cursor_execute", observe)
            event.remove(db, "before_flush", reject_flush)
        assert ex.value.status_code == 409
        assert getattr(cycle, draft_field) == draft
        assert cycle in db.dirty and pending in db.new
        assert not flushes
        assert all(command == "SELECT" for command in statements)
        db.rollback()
    with Session(engine) as check:
        canonical = check.get(CapaCycle, cycle_id)
        assert canonical.case_id == case_id
        assert canonical.notes is None
        assert check.scalar(select(func.count(AuditEvent.id))) == 0


def test_missing_cycle_is_404_and_no_pending_draft_flushed(seeded):
    engine, _ = seeded
    with Session(engine, autoflush=True) as db:
        pending = Company(legal_name="Pending unrelated company")
        db.add(pending)
        statements, flushes, observe, reject_flush = install_sql_guards(engine, db)
        try:
            with pytest.raises(HTTPException) as ex:
                admission(db, str(uuid4()))
        finally:
            event.remove(engine, "before_cursor_execute", observe)
            event.remove(db, "before_flush", reject_flush)
        assert ex.value.status_code == 404
        assert pending in db.new and not flushes
        assert all(command == "SELECT" for command in statements)
        db.rollback()
