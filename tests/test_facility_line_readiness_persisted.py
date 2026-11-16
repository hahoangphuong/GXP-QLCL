"""Facility ProductionLine action readiness is an advisory committed SQL read.

The GET must not flush Site/Company drafts or trust stale cached owners.
Synthetic databases only; no rehearsal/production writes.
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from backend.app.api.routers.catalog import _build_facility_action_readiness
from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.models.phase1 import AuditEvent, Company, Site
from backend.app.services.workflow import CaseWorkflowService


EDITOR = build_authenticated_user("line-readiness-editor", permissions={"case.edit"})
READER = build_authenticated_user("line-readiness-reader", "reader")


@pytest.fixture
def owners(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'line-readiness.sqlite').as_posix()}",
        future=True,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        active = Company(legal_name="Active company", is_inactive=False)
        inactive = Company(legal_name="Inactive company", is_inactive=True)
        db.add_all([active, inactive])
        db.flush()
        site = Site(company_id=active.id, site_name="Committed site")
        db.add(site)
        db.commit()
        ids = (site.id, active.id, inactive.id)
    try:
        yield engine, ids
    finally:
        engine.dispose()


def status(db, site_id, user=EDITOR):
    actions = _build_facility_action_readiness(
        workflow_service=CaseWorkflowService(),
        session=db,
        site_id=site_id,
        selected_gxp_type=None,
        selected_line_code=None,
        selected_production_line_id=None,
        user=user,
    )
    return {action["action_key"]: action["readiness_status"] for action in actions}


def test_readiness_uses_committed_owner_without_flushing_operator_drafts(owners):
    engine, (site_id, active_company_id, inactive_company_id) = owners
    with Session(engine, autoflush=True, expire_on_commit=False) as db:
        site = db.get(Site, site_id)
        active = db.get(Company, active_company_id)
        site.company_id = inactive_company_id
        active.is_inactive = True
        pending = Company(legal_name="Uncommitted draft")
        db.add(pending)
        statements, flushes = [], []

        def sql(_conn, _cursor, statement, _params, _context, _many):
            statements.append(statement.lstrip().split(None, 1)[0].upper())

        def fail_flush(*_args):
            flushes.append(True)
            raise AssertionError("Facility readiness GET autoflushed operator draft")

        event.listen(engine, "before_cursor_execute", sql)
        event.listen(db, "before_flush", fail_flush)
        try:
            actions = status(db, site_id)
        finally:
            event.remove(engine, "before_cursor_execute", sql)
            event.remove(db, "before_flush", fail_flush)
        assert actions["create_production_line"] == "available"
        assert statements and set(statements) == {"SELECT"}
        assert not flushes
        assert site.company_id == inactive_company_id
        assert active.is_inactive is True
        assert site in db.dirty and active in db.dirty and pending in db.new
        db.rollback()
    with Session(engine) as verify:
        assert verify.scalar(select(func.count(Company.id))) == 2
        assert verify.scalar(select(func.count(AuditEvent.id))) == 0


def test_readiness_follows_independent_committed_writer_not_cached_identity(owners):
    engine, (site_id, active_company_id, inactive_company_id) = owners
    with Session(engine, expire_on_commit=False) as db:
        site = db.get(Site, site_id)
        active = db.get(Company, active_company_id)
        assert status(db, site_id)["create_production_line"] == "available"
        with Session(engine) as writer:
            writer.get(Site, site_id).company_id = inactive_company_id
            writer.commit()
        assert site.company_id == active_company_id
        assert status(db, site_id)["create_production_line"] == "unavailable"
        with Session(engine) as writer:
            writer.get(Site, site_id).company_id = active_company_id
            writer.get(Company, active_company_id).is_inactive = True
            writer.commit()
        assert active.is_inactive is False
        assert status(db, site_id)["create_production_line"] == "unavailable"
        with Session(engine) as writer:
            writer.get(Company, active_company_id).is_inactive = False
            writer.commit()
        assert status(db, site_id)["create_production_line"] == "available"
        assert site.company_id == active_company_id
        assert active.is_inactive is False


def test_missing_site_and_denied_permission_remain_unavailable_or_forbidden(owners):
    engine, (site_id, _, _) = owners
    with Session(engine) as db:
        assert status(db, str(uuid4()))["create_production_line"] == "unavailable"
        assert status(db, site_id, READER)["create_production_line"] == "forbidden"
        assert not db.new and not db.dirty
