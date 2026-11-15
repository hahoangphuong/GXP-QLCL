"""QĐKT current-team revision must come from persisted Case team owner.

The current-team diagnostic is not a draft snapshot or issued roster. This
suite uses a disposable SQLite database and asserts the reader never flushes,
refreshes or discards pending ORM drafts.
"""
from __future__ import annotations

from sqlalchemy import create_engine, event, select, update
from sqlalchemy.orm import Session

from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import (
    Case, Company, Site, InspectionTeam, InspectionTeamMember,
)
from backend.app.document.inspection_qd_kt_current_case_team import (
    read_qdkt_current_case_team,
)


def _seed(engine):
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        company = Company(legal_name="Synthetic QDKT revision company")
        session.add(company)
        session.flush()
        site = Site(company_id=company.id, site_name="Synthetic Site")
        session.add(site)
        session.flush()
        case = Case(site_id=site.id, gxp_type="GMP", state=CaseState.DRAFT)
        session.add(case)
        session.flush()
        team = InspectionTeam(case_id=case.id)
        session.add(team)
        session.flush()
        session.add(InspectionTeamMember(
            team_id=team.id, sort_order=1, role_code="LEADER",
            identity_kind="LEGACY_PERSON", display_name="Synthetic Inspector",
        ))
        session.commit()
        return case.id, team.id, team.row_version


def test_current_team_revision_ignores_pending_cached_orm_changes(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'team-draft.sqlite').as_posix()}")
    case_id, team_id, persisted_version = _seed(engine)
    try:
        with Session(engine, autoflush=True, expire_on_commit=False) as session:
            cached = session.get(InspectionTeam, team_id)
            cached.row_version = persisted_version + 70
            cached.display_text = "Uncommitted operator draft"
            assert cached in session.dirty
            statements = []

            def observe(conn, cursor, statement, params, context, many):
                statements.append(statement.strip().upper())

            event.listen(engine, "before_cursor_execute", observe)
            try:
                result = read_qdkt_current_case_team(session, case_id=case_id)
            finally:
                event.remove(engine, "before_cursor_execute", observe)

            assert result["team_revision"] == persisted_version
            assert result["team_id"] == team_id
            assert result["members"][0]["display_name"] == "Synthetic Inspector"
            assert result["draft_snapshot_available"] is False
            assert result["issued_team_confirmed"] is False
            assert cached.row_version == persisted_version + 70
            assert cached.display_text == "Uncommitted operator draft"
            assert cached in session.dirty
            assert statements and all(x.startswith("SELECT") for x in statements)
            session.rollback()
        with Session(engine) as verify:
            persisted = verify.scalar(
                select(InspectionTeam.row_version).where(InspectionTeam.id == team_id)
            )
            assert persisted == persisted_version
    finally:
        engine.dispose()


def test_current_team_revision_ignores_stale_identity_map_after_other_commit(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'team-stale.sqlite').as_posix()}")
    case_id, team_id, initial_version = _seed(engine)
    try:
        with Session(engine, autoflush=False, expire_on_commit=False) as reader:
            cached = reader.get(InspectionTeam, team_id)
            assert cached.row_version == initial_version
            with Session(engine) as writer:
                writer.execute(
                    update(InspectionTeam)
                    .where(InspectionTeam.id == team_id)
                    .values(row_version=initial_version + 1)
                )
                writer.commit()

            result = read_qdkt_current_case_team(reader, case_id=case_id)
            assert result["case_id"] == case_id
            assert result["team_revision"] == initial_version + 1
            assert result["members"][0]["display_name"] == "Synthetic Inspector"
            assert cached.row_version == initial_version  # no refresh/expire
            assert not reader.new and not reader.dirty
            reader.rollback()
    finally:
        engine.dispose()
