"""Site physical-line list is a committed, read-only projection.

Never flush or overwrite unrelated operator drafts. A missing Site is 404;
the list does not establish POST recovery or authorize a blind retry.
Synthetic SQLite only; no rehearsal/production database.
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
from backend.app.db.models.phase1 import AuditEvent, Company, ProductionLine, Site


READER = build_authenticated_user("line-list-reader", "reader")


def endpoint():
    app = FastAPI()
    register_catalog_routes(app, lambda: None)
    return next(
        route.endpoint for route in app.routes
        if getattr(route, "path", None) == "/sites/{site_id}/production-lines"
        and route.methods == {"GET"}
    )


@pytest.fixture
def seeded(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'site-line-list.sqlite').as_posix()}",
        future=True,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        company = Company(legal_name="Committed company")
        db.add(company)
        db.flush()
        site = Site(company_id=company.id, site_name="Committed site")
        other_site = Site(company_id=company.id, site_name="Other site")
        db.add_all([site, other_site])
        db.flush()
        line = ProductionLine(
            site_id=site.id, code="COMMITTED-LINE",
            effective_from=date(2026, 11, 16),
        )
        other_line = ProductionLine(
            site_id=other_site.id, code="OTHER-LINE",
            effective_from=date(2026, 11, 16),
        )
        db.add_all([line, other_line])
        db.commit()
        ids = (company.id, site.id, other_site.id, line.id, other_line.id)
    try:
        yield engine, ids
    finally:
        engine.dispose()


def test_site_line_list_is_select_only_and_keeps_dirty_drafts(seeded):
    engine, (company_id, site_id, _, line_id, _) = seeded
    with Session(engine, autoflush=True, expire_on_commit=False) as db:
        cached_line = db.get(ProductionLine, line_id)
        cached_company = db.get(Company, company_id)
        cached_line.code = "UNCOMMITTED-LINE"
        cached_company.legal_name = "Uncommitted company draft"
        pending = Company(legal_name="Pending new company")
        db.add(pending)
        statements, flushes = [], []

        def observe(_conn, _cursor, sql, _params, _context, _many):
            statements.append(sql.lstrip().split(None, 1)[0].upper())

        def forbidden_flush(*_args):
            flushes.append(True)
            raise AssertionError("Site line list GET must not autoflush")

        event.listen(engine, "before_cursor_execute", observe)
        event.listen(db, "before_flush", forbidden_flush)
        try:
            result = endpoint()(site_id=site_id, session=db, user=READER)
        finally:
            event.remove(engine, "before_cursor_execute", observe)
            event.remove(db, "before_flush", forbidden_flush)
        assert len(result) == 1
        assert result[0].id == line_id
        assert result[0].site_id == site_id
        assert result[0].code == "COMMITTED-LINE"
        assert statements and set(statements) == {"SELECT"}
        assert not flushes
        assert cached_line.code == "UNCOMMITTED-LINE"
        assert cached_company.legal_name == "Uncommitted company draft"
        assert cached_line in db.dirty and cached_company in db.dirty
        assert pending in db.new
        db.rollback()

    with Session(engine) as verify:
        assert verify.scalar(select(func.count(Company.id))) == 1
        assert verify.scalar(select(func.count(AuditEvent.id))) == 0


def test_site_line_list_ignores_stale_identity_after_writer_commit(seeded):
    engine, (_, site_id, other_site_id, line_id, other_line_id) = seeded
    with Session(engine, expire_on_commit=False) as db:
        cached_line = db.get(ProductionLine, line_id)
        cached_other = db.get(ProductionLine, other_line_id)
        with Session(engine) as writer:
            writer.get(ProductionLine, line_id).site_id = other_site_id
            writer.get(ProductionLine, other_line_id).site_id = site_id
            writer.get(ProductionLine, other_line_id).code = "WRITER-LINE"
            writer.commit()
        result = endpoint()(site_id=site_id, session=db, user=READER)
        assert [(row.id, row.code) for row in result] == [
            (other_line_id, "WRITER-LINE")
        ]
        assert cached_line.site_id == site_id
        assert cached_other.site_id == other_site_id


def test_missing_and_empty_sites_are_distinguished_without_mutation(seeded):
    engine, (_, site_id, other_site_id, line_id, _) = seeded
    with Session(engine) as db:
        with pytest.raises(HTTPException) as missing:
            endpoint()(site_id=str(uuid4()), session=db, user=READER)
        assert missing.value.status_code == 404
        assert not db.new and not db.dirty
        db.query(ProductionLine).filter(
            ProductionLine.site_id == other_site_id
        ).delete(synchronize_session=False)
        db.commit()
        assert endpoint()(site_id=other_site_id, session=db, user=READER) == []
        assert [item.id for item in endpoint()(
            site_id=site_id, session=db, user=READER
        )] == [line_id]
