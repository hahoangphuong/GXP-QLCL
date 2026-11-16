"""Canonical GET after uncertain master POST must read committed SQL, not ORM cache.

GET must not flush or overwrite dirty draft objects from a reused Session.
The resulting snapshot is read-only evidence; 404 never licenses POST replay.
Synthetic SQLite only; no production/rehearsal access.
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
from backend.app.db.models.phase1 import (
    AuditEvent, Company, ProductionLine, Site,
)
from backend.app.services.catalog import CatalogReadService


@pytest.fixture
def db(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'master-readback.sqlite').as_posix()}",
        future=True,
    )
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as seed:
        company = Company(legal_name="Committed Company", legal_address="Committed address")
        seed.add(company)
        seed.flush()
        site = Site(
            company_id=company.id, site_name="Committed Site",
            site_address="Committed Site address",
        )
        seed.add(site)
        seed.flush()
        line = ProductionLine(
            site_id=site.id, code="COMMITTED",
            effective_from=date(2026, 11, 1),
        )
        seed.add(line)
        seed.commit()
        ids = company.id, site.id, line.id
    try:
        yield engine, ids
    finally:
        engine.dispose()


@pytest.mark.parametrize("kind", ["company", "site", "line"])
def test_master_get_reads_persisted_without_flushing_dirty_or_pending_objects(db, kind):
    engine, (company_id, site_id, line_id) = db
    models = {
        "company": (Company, company_id, "legal_name", "Draft Company", "Committed Company"),
        "site": (Site, site_id, "site_name", "Draft Site", "Committed Site"),
        "line": (ProductionLine, line_id, "code", "DRAFT", "COMMITTED"),
    }
    model, identity, field, draft_value, persisted = models[kind]
    getters = {
        "company": ("get_company_master_persisted", company_id),
        "site": ("get_site_master_persisted", site_id),
        "line": ("get_production_line_master_persisted", line_id),
    }
    method, target_id = getters[kind]
    with Session(engine, autoflush=True, expire_on_commit=False) as session:
        cached = session.get(model, identity)
        setattr(cached, field, draft_value)
        # An unrelated pending identity must never be committed by a GET.
        pending = Company(legal_name="Uncommitted extra Company")
        session.add(pending)
        statements, flushes = [], []

        def sql(_connection, _cursor, statement, _params, _context, _many):
            statements.append(statement.lstrip().split(None, 1)[0].upper())

        def flush(*_args):
            flushes.append(True)
            raise AssertionError("Canonical GET flushed a pending operator draft")

        event.listen(engine, "before_cursor_execute", sql)
        event.listen(session, "before_flush", flush)
        try:
            snap = getattr(CatalogReadService(), method)(session, target_id)
        finally:
            event.remove(engine, "before_cursor_execute", sql)
            event.remove(session, "before_flush", flush)
        assert getattr(snap, field) == persisted
        assert getattr(cached, field) == draft_value
        assert cached in session.dirty
        assert pending in session.new
        assert statements and set(statements) == {"SELECT"}
        assert flushes == []
        session.rollback()

    with Session(engine) as verify:
        assert verify.scalar(select(func.count(Company.id))) == 1
        assert verify.scalar(select(func.count(AuditEvent.id))) == 0


@pytest.mark.parametrize("kind", ["company", "site", "line"])
def test_canonical_get_bypasses_stale_orm_identity_after_independent_commit(db, kind):
    engine, (company_id, site_id, line_id) = db
    model, identity, field, updated = {
        "company": (Company, company_id, "legal_name", "Company changed by writer"),
        "site": (Site, site_id, "site_name", "Site changed by writer"),
        "line": (ProductionLine, line_id, "code", "WRITER-NEW"),
    }[kind]
    method = {
        "company": "get_company_master_persisted",
        "site": "get_site_master_persisted",
        "line": "get_production_line_master_persisted",
    }[kind]
    with Session(engine, expire_on_commit=False) as cached_session:
        cached = cached_session.get(model, identity)
        old = getattr(cached, field)
        with Session(engine) as writer:
            setattr(writer.get(model, identity), field, updated)
            writer.commit()
        assert getattr(cached, field) == old
        snapshot = getattr(CatalogReadService(), method)(cached_session, identity)
        assert getattr(snapshot, field) == updated
        assert getattr(cached, field) == old
        assert not cached_session.new and not cached_session.dirty


def test_canonical_master_api_get_paths_preserve_response_contract_and_role(db):
    engine, (company_id, site_id, line_id) = db
    app = FastAPI()
    register_catalog_routes(app, lambda: None)
    routes = {getattr(r, "path", ""): r for r in app.routes}
    reader = build_authenticated_user("canonical-master-reader", "reader")
    company_endpoint = routes["/companies/{company_id}"].endpoint
    site_endpoint = routes["/sites/{site_id}"].endpoint
    line_endpoint = routes["/production-lines/{production_line_id}"].endpoint
    with Session(engine, autoflush=True, expire_on_commit=False) as session:
        company = session.get(Company, company_id)
        site = session.get(Site, site_id)
        line = session.get(ProductionLine, line_id)
        company.legal_name = "Locally altered"
        site.site_name = "Locally altered"
        line.code = "LOCALLY-ALTERED"
        flushes = []

        def forbidden(*_args):
            flushes.append(True)
            raise AssertionError("GET response triggered autoflush")

        event.listen(session, "before_flush", forbidden)
        try:
            company_result = company_endpoint(company_id=company_id, session=session, user=reader)
            site_result = site_endpoint(site_id=site_id, session=session, user=reader)
            line_result = line_endpoint(production_line_id=line_id, session=session, user=reader)
        finally:
            event.remove(session, "before_flush", forbidden)
        assert company_result.id == company_id
        assert company_result.legal_name == "Committed Company"
        assert site_result.id == site_id
        assert site_result.site_name == "Committed Site"
        assert line_result.id == line_id
        assert line_result.code == "COMMITTED"
        assert flushes == []
        assert company.legal_name == site.site_name == "Locally altered"
        assert line.code == "LOCALLY-ALTERED"
        session.rollback()


@pytest.mark.parametrize("kind", ["company", "site", "line"])
def test_missing_master_readback_is_404_not_authorization_to_replay(db, kind):
    engine, _ = db
    method = {
        "company": "get_company_master_persisted",
        "site": "get_site_master_persisted",
        "line": "get_production_line_master_persisted",
    }[kind]
    with Session(engine) as session:
        with pytest.raises(HTTPException) as missing:
            getattr(CatalogReadService(), method)(session, str(uuid4()))
        assert missing.value.status_code == 404
        assert not session.new and not session.dirty
