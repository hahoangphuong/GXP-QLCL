"""Inspection team replace-all admission preserves drafts and has no DML on reject.

Synthetic SQLite. Canonical identity and roster replacement contracts are unchanged.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import (
    AuditEvent, Case, Company, InspectionTeam, InspectionTeamMember, Person, Site,
)
from backend.app.services.workflow import CaseWorkflowService


USER = build_authenticated_user(
    "synthetic-inspection-team", "manager", permissions={"inspection.edit"},
)


@pytest.fixture
def seeded(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'inspection-team-draft.sqlite').as_posix()}",
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
        team = InspectionTeam(case_id=case.id)
        db.add(team)
        db.flush()
        person = Person(full_name="Committed member", display_name="Committed member")
        db.add(person)
        db.flush()
        member = InspectionTeamMember(
            team_id=team.id, sort_order=1, identity_kind=None,
            role_code="LEADER", person_id=person.id,
            display_name="Committed member",
        )
        db.add(member)
        db.commit()
        ids = (case.id, team.id, member.id, team.row_version)
    try:
        yield engine, ids
    finally:
        engine.dispose()


def replace(db, case_id, version, *, members=None, display_text=None):
    return CaseWorkflowService().upsert_inspection_team(
        db, case_id=case_id,
        members=[] if members is None else members,
        reason="Synthetic owner admission",
        user=USER, expected_version=version, display_text=display_text,
    )


def install_guards(engine, db):
    statements, flushes = [], []

    def on_sql(_conn, _cur, statement, _params, _ctx, _many):
        statements.append(statement.lstrip().split(None, 1)[0].upper())

    def fail_flush(*_args):
        flushes.append(True)
        raise AssertionError("Inspection team admission autoflushed operator draft")

    event.listen(engine, "before_cursor_execute", on_sql)
    event.listen(db, "before_flush", fail_flush)
    return statements, flushes, on_sql, fail_flush


def release_guards(engine, db, sql_cb, flush_cb):
    event.remove(engine, "before_cursor_execute", sql_cb)
    event.remove(db, "before_flush", flush_cb)


@pytest.mark.parametrize(("reason", "expected"), [
    ("legacy_display_text", 422),
    ("invalid_member_list", 422),
])
def test_rejected_team_request_does_not_flush_unrelated_pending_draft(seeded, reason, expected):
    engine, (case_id, _, _, version) = seeded
    with Session(engine, autoflush=True) as db:
        pending = Company(legal_name="Operator draft company")
        db.add(pending)
        sql, flushes, sql_cb, flush_cb = install_guards(engine, db)
        try:
            with pytest.raises(HTTPException) as exc:
                replace(
                    db, case_id, version,
                    display_text="Not editable" if reason == "legacy_display_text" else None,
                )
        finally:
            release_guards(engine, db, sql_cb, flush_cb)
        assert exc.value.status_code == expected
        assert not flushes and set(sql) <= {"SELECT"}
        assert pending in db.new
        db.rollback()
    with Session(engine) as db:
        assert db.scalar(select(func.count(Company.id))) == 1
        assert db.scalar(select(func.count(AuditEvent.id))) == 0


@pytest.mark.parametrize("dirty_kind", ["case", "team", "member"])
def test_dirty_owned_row_rejects_without_overwriting_cached_draft(seeded, dirty_kind):
    engine, (case_id, team_id, member_id, version) = seeded
    with Session(engine, autoflush=True, expire_on_commit=False) as db:
        case = db.get(Case, case_id)
        team = db.get(InspectionTeam, team_id)
        member = db.get(InspectionTeamMember, member_id)
        if dirty_kind == "case":
            case.state = CaseState.CLOSED
        elif dirty_kind == "team":
            team.display_text = "Operator team draft"
        else:
            member.display_name = "Operator member draft"
        pending = Company(legal_name="Unrelated pending company")
        db.add(pending)
        sql, flushes, sql_cb, flush_cb = install_guards(engine, db)
        try:
            with pytest.raises(HTTPException) as exc:
                replace(db, case_id, version)
        finally:
            release_guards(engine, db, sql_cb, flush_cb)
        assert exc.value.status_code == 409
        assert not flushes and set(sql) <= {"SELECT"}
        assert pending in db.new
        owned = {"case": case, "team": team, "member": member}[dirty_kind]
        assert owned in db.dirty
        if dirty_kind == "case":
            assert case.state == CaseState.CLOSED
        elif dirty_kind == "team":
            assert team.display_text == "Operator team draft"
        else:
            assert member.display_name == "Operator member draft"
        db.rollback()

    with Session(engine) as db:
        assert db.get(Case, case_id).state == CaseState.INSPECTION_COMPLETED
        assert db.get(InspectionTeamMember, member_id).display_name == "Committed member"
        assert db.scalar(select(func.count(AuditEvent.id))) == 0
        assert db.scalar(select(func.count(Company.id))) == 1
