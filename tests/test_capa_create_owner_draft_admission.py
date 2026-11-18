"""CAPA round creation must preserve Case drafts and reject without SQL writes.

Synthetic file-backed SQLite only. The existing PostgreSQL lock/race regression
continues to own the concurrent round-allocation guarantee.
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
from backend.app.db.models.phase1 import AuditEvent, CapaCycle, Case, Company, Site
from backend.app.services.workflow import CaseWorkflowService


USER = build_authenticated_user(
    "capa-create-owner-admission", "manager", permissions={"capa.edit"},
)


@pytest.fixture
def seeded(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'capa-create-admission.sqlite'}", future=True,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        company = Company(legal_name="Committed Company")
        db.add(company)
        db.flush()
        site = Site(company_id=company.id, site_name="Committed Site")
        db.add(site)
        db.flush()
        case = Case(
            site_id=site.id, gxp_type="GMP",
            state=CaseState.INSPECTION_COMPLETED,
        )
        db.add(case)
        db.commit()
        ids = (case.id, case.row_version)
    try:
        yield engine, ids
    finally:
        engine.dispose()


def create(db, case_id, version=None):
    return CaseWorkflowService().create_capa_cycle(
        db, case_id=case_id, expected_case_version=version,
        requested_on=None, incoming_reference="Synthetic CAPA request",
        notes="Synthetic", reason="Admission regression", user=USER,
    )


def guard(engine, db):
    sql, flushes = [], []

    def record(_conn, _cursor, statement, _params, _ctx, _many):
        sql.append(statement.lstrip().split(None, 1)[0].upper())

    def reject(*_args):
        flushes.append(True)
        raise AssertionError("Rejected CAPA create autoflushed operator draft")

    event.listen(engine, "before_cursor_execute", record)
    event.listen(db, "before_flush", reject)
    return sql, flushes, record, reject


def unguard(engine, db, record, reject):
    event.remove(engine, "before_cursor_execute", record)
    event.remove(db, "before_flush", reject)


def test_dirty_case_rejected_without_refresh_or_unrelated_flush(seeded):
    engine, (case_id, version) = seeded
    with Session(engine, autoflush=True, expire_on_commit=False) as db:
        case = db.get(Case, case_id)
        case.state = CaseState.CLOSED
        pending = Company(legal_name="Uncommitted Company")
        db.add(pending)
        statements, flushes, record, reject = guard(engine, db)
        try:
            with pytest.raises(HTTPException) as error:
                create(db, case_id, version)
        finally:
            unguard(engine, db, record, reject)
        assert error.value.status_code == 409
        assert not flushes and set(statements) <= {"SELECT"}
        assert case in db.dirty and case.state == CaseState.CLOSED
        assert pending in db.new
        db.rollback()
    with Session(engine) as check:
        assert check.get(Case, case_id).state == CaseState.INSPECTION_COMPLETED
        assert check.scalar(select(func.count(Company.id))) == 1
        assert check.scalar(select(func.count(CapaCycle.id))) == 0
        assert check.scalar(select(func.count(AuditEvent.id))) == 0


@pytest.mark.parametrize(("reason", "status"), [
    ("missing_case", 404), ("wrong_version", 409),
])
def test_rejected_create_does_not_autoflush_pending_company(seeded, reason, status):
    engine, (case_id, version) = seeded
    with Session(engine, autoflush=True) as db:
        pending = Company(legal_name="Pending operator draft")
        db.add(pending)
        statements, flushes, record, reject = guard(engine, db)
        try:
            with pytest.raises(HTTPException) as error:
                create(db, str(uuid4()) if reason == "missing_case" else case_id,
                       version + 5 if reason == "wrong_version" else version)
        finally:
            unguard(engine, db, record, reject)
        assert error.value.status_code == status
        assert not flushes and set(statements) <= {"SELECT"}
        assert pending in db.new
        db.rollback()
    with Session(engine) as check:
        assert check.scalar(select(func.count(Company.id))) == 1
        assert check.scalar(select(func.count(CapaCycle.id))) == 0
        assert check.scalar(select(func.count(AuditEvent.id))) == 0



def test_dirty_latest_rejected_round_keeps_draft_and_pending_company(seeded):
    engine, (case_id, version) = seeded
    with Session(engine) as seed:
        rejected = CapaCycle(
            case_id=case_id, round_no=1,
            status="rejected", result="rejected",
        )
        seed.add(rejected)
        seed.commit()
        rejected_id = rejected.id

    with Session(engine, autoflush=True, expire_on_commit=False) as db:
        cached = db.get(CapaCycle, rejected_id)
        cached.notes = "Operator edit not yet committed"
        pending = Company(legal_name="Unrelated pending Company")
        db.add(pending)
        statements, flushes, record, reject = guard(engine, db)
        try:
            with pytest.raises(HTTPException) as error:
                create(db, case_id, version)
        finally:
            unguard(engine, db, record, reject)
        assert error.value.status_code == 409
        assert not flushes and set(statements) <= {"SELECT"}
        assert cached in db.dirty and pending in db.new
        assert cached.notes == "Operator edit not yet committed"
        db.rollback()

    with Session(engine) as check:
        saved = check.get(CapaCycle, rejected_id)
        assert saved.status == "rejected"
        assert saved.notes is None
        assert check.scalar(select(func.count(CapaCycle.id))) == 1
        assert check.scalar(select(func.count(AuditEvent.id))) == 0
        assert check.scalar(select(func.count(Company.id))) == 1


def test_clean_new_round_after_rejection_keeps_round_allocation(seeded):
    engine, (case_id, version) = seeded
    with Session(engine) as seed:
        seed.add(CapaCycle(
            case_id=case_id, round_no=1,
            status="rejected", result="rejected",
        ))
        seed.commit()
    with Session(engine) as db:
        response = create(db, case_id, version)
        assert response["round_no"] == 2
        db.commit()
    with Session(engine) as verify:
        assert [cycle.round_no for cycle in verify.scalars(
            select(CapaCycle).where(CapaCycle.case_id == case_id)
            .order_by(CapaCycle.round_no)
        )] == [1, 2]
        assert verify.scalar(select(func.count(AuditEvent.id))) == 1


def test_clean_create_preserves_single_round_and_audit(seeded):
    engine, (case_id, version) = seeded
    with Session(engine) as db:
        response = create(db, case_id, version)
        assert response["round_no"] == 1
        assert response["status"] == "requested"
        db.commit()
    with Session(engine) as check:
        cycles = list(check.scalars(select(CapaCycle).where(CapaCycle.case_id == case_id)))
        assert len(cycles) == 1
        assert cycles[0].round_no == 1
        assert check.scalar(select(func.count(AuditEvent.id))) == 1
