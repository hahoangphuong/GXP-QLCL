"""Canonical Initial Case GET resolves committed Case/Line, not ORM draft.

The client supplies Case UUID before POST. After a lost response the readback
must project SQL rows under no_autoflush; GET 404 never authorizes replay.
Disposable synthetic SQLite only.
"""
from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from backend.app.api.routers.catalog import register_catalog_routes
from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import (
    AuditEvent, Case, Company, ProductionLine, Site,
)
from backend.app.services.catalog import CatalogReadService


@pytest.fixture
def case_db(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'case-get-persisted.sqlite').as_posix()}",
        future=True,
    )
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        company = Company(legal_name="Canonical fixture Company")
        db.add(company)
        db.flush()
        site = Site(company_id=company.id, site_name="Canonical fixture Site")
        other = Site(company_id=company.id, site_name="Other Site")
        db.add_all([site, other])
        db.flush()
        line = ProductionLine(site_id=site.id, code="COMMITTED-LINE", effective_from=date(2026, 11, 16))
        db.add(line)
        db.flush()
        case = Case(
            site_id=site.id, gxp_type="GMP", production_line_id=line.id,
            inspection_type="Committed inspection", state=CaseState.DRAFT,
            scope_code="COMMITTED-LINE",
        )
        db.add(case)
        db.commit()
        ids = case.id, line.id, site.id, other.id, company.id
    try:
        yield engine, ids
    finally:
        engine.dispose()


def endpoint():
    app = FastAPI()
    register_catalog_routes(app, lambda: None)
    return next(
        route.endpoint for route in app.routes
        if getattr(route, "path", None) == "/cases/{case_id}"
        and route.methods == {"GET"}
    )


READER = build_authenticated_user("initial-case-readback", "reader")


def test_case_get_uses_persisted_case_and_line_without_flushing_drafts(case_db):
    engine, (case_id, line_id, site_id, _, _) = case_db
    with Session(engine, autoflush=True, expire_on_commit=False) as session:
        cached_case = session.get(Case, case_id)
        cached_line = session.get(ProductionLine, line_id)
        cached_case.inspection_type = "Uncommitted Case draft"
        cached_line.code = "UNCOMMITTED-LINE"
        extra = Company(legal_name="Pending unrelated Company draft")
        session.add(extra)
        statements, flushes = [], []

        def observe(_conn, _cursor, sql, _params, _context, _many):
            statements.append(sql.lstrip().split(None, 1)[0].upper())

        def forbidden_flush(*_args):
            flushes.append(True)
            raise AssertionError("Case canonical GET must not autoflush")

        event.listen(engine, "before_cursor_execute", observe)
        event.listen(session, "before_flush", forbidden_flush)
        try:
            result = endpoint()(case_id=case_id, session=session, user=READER)
        finally:
            event.remove(engine, "before_cursor_execute", observe)
            event.remove(session, "before_flush", forbidden_flush)
        assert result.id == case_id and result.site_id == site_id
        assert result.inspection_type == "Committed inspection"
        assert result.production_line_id == line_id
        assert result.production_line_code == "COMMITTED-LINE"
        assert result.production_line_identity_state == "canonical"
        assert result.state == CaseState.DRAFT.value
        assert statements and set(statements) == {"SELECT"}
        assert flushes == []
        assert cached_case.inspection_type == "Uncommitted Case draft"
        assert cached_line.code == "UNCOMMITTED-LINE"
        assert cached_case in session.dirty and cached_line in session.dirty
        assert extra in session.new
        session.rollback()
    with Session(engine) as verify:
        assert verify.scalar(select(func.count(Company.id))) == 1
        assert verify.scalar(select(func.count(AuditEvent.id))) == 0


def test_case_get_bypasses_stale_identity_after_writer_commits(case_db):
    engine, (case_id, line_id, _, _, _) = case_db
    with Session(engine, expire_on_commit=False) as cached:
        old_case = cached.get(Case, case_id)
        old_line = cached.get(ProductionLine, line_id)
        with Session(engine) as writer:
            writer.get(Case, case_id).inspection_type = "Committed by writer"
            writer.get(ProductionLine, line_id).code = "WRITER-LINE"
            writer.commit()
        assert old_case.inspection_type == "Committed inspection"
        assert old_line.code == "COMMITTED-LINE"
        result = endpoint()(case_id=case_id, session=cached, user=READER)
        assert result.inspection_type == "Committed by writer"
        assert result.production_line_code == "WRITER-LINE"
        assert old_case.inspection_type == "Committed inspection"
        assert old_line.code == "COMMITTED-LINE"


def test_case_get_rejects_line_committed_under_different_site(case_db):
    engine, (case_id, line_id, _, other_site_id, _) = case_db
    with Session(engine, expire_on_commit=False) as cached:
        old_line = cached.get(ProductionLine, line_id)
        assert old_line.site_id != other_site_id
        with Session(engine) as writer:
            writer.get(ProductionLine, line_id).site_id = other_site_id
            writer.commit()
        with pytest.raises(HTTPException) as mismatch:
            endpoint()(case_id=case_id, session=cached, user=READER)
        assert mismatch.value.status_code == 409
        assert old_line.site_id != other_site_id


def test_missing_case_uuid_returns_404_without_side_effects(case_db):
    engine, _ = case_db
    with Session(engine) as session:
        with pytest.raises(HTTPException) as missing:
            endpoint()(case_id=str(uuid4()), session=session, user=READER)
        assert missing.value.status_code == 404
        assert not session.new and not session.dirty
        with pytest.raises(HTTPException) as missing_service:
            CatalogReadService().get_case_master_persisted(session, str(uuid4()))
        assert missing_service.value.status_code == 404
