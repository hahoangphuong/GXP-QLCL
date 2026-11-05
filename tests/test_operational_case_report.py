from __future__ import annotations

import pytest
import anyio
from fastapi import HTTPException
from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.auth import build_authenticated_user, get_authenticated_user
from backend.app.api.routers.catalog import register_catalog_routes
from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import Case, Company, Site
from backend.app.main import create_app
from backend.app.services.catalog import CatalogReadService


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        company = Company(legal_name="Công ty thử")
        db.add(company)
        db.flush()
        site = Site(company_id=company.id, site_name="Cơ sở thử")
        db.add(site)
        db.flush()
        for state, year in [(CaseState.PLANNED, 2025), (CaseState.DECISION_ISSUED, 2026),
                            (CaseState.INSPECTION_IN_PROGRESS, 2026), (CaseState.CLOSED, 2026)]:
            db.add(Case(site_id=site.id, gxp_type="GMP", state=state, opened_year=year))
        db.commit()
        yield db
    engine.dispose()


def report(session, **overrides):
    options = dict(gxp_type=None, state=None, q=None, opened_year=None, inspection_queue=False,
                   export=False, offset=0, limit=2)
    return CatalogReadService().get_case_report(session, **(options | overrides))


def test_case_report_filters_paginates_and_exports_all(session):
    first = report(session, q="Công ty", gxp_type="GMP", opened_year=2026)
    assert first["total_count"] == 2
    assert len(first["items"]) == 2
    assert {item["state"] for item in first["items"]} == {"decision_issued", "inspection_in_progress"}
    page1 = report(session)
    page2 = report(session, offset=2)
    exported = report(session, export=True)
    assert page1["total_count"] == 3
    assert len(page1["items"]) == 2 and len(page2["items"]) == 1
    assert {x["case_id"] for x in exported["items"]} == {x["case_id"] for x in page1["items"] + page2["items"]}
    assert all(x["result_key"].startswith(x["site_id"] + ":GMP:") for x in exported["items"])


def test_inspection_queue_and_invalid_state(session):
    assert report(session, inspection_queue=True)["total_count"] == 3
    assert report(session, inspection_queue=True, state="planned")["total_count"] == 1
    assert report(session, q="not found")["total_count"] == 0
    with pytest.raises(HTTPException) as invalid:
        report(session, inspection_queue=True, state="closed")
    assert invalid.value.status_code == 422
    with pytest.raises(HTTPException):
        report(session, export=True, offset=1)


def test_export_rejects_more_than_10000_without_partial_success(session):
    site_id = session.query(Site.id).first()[0]
    session.add_all(Case(site_id=site_id, gxp_type="GLP", state=CaseState.PLANNED) for _ in range(10001))
    session.flush()
    with pytest.raises(HTTPException) as overflow:
        report(session, gxp_type="GLP", export=True)
    assert overflow.value.status_code == 413


def test_report_route_enforces_existing_read_role(session):
    app = create_app("sqlite:///:memory:")
    endpoint = next(route.endpoint for route in app.routes if getattr(route, "path", "") == "/reports/cases")
    args = dict(gxp_type=None, state=None, q=None, opened_year=None, inspection_queue=False,
                export=False, offset=0, limit=100, session=session)
    assert endpoint(**args, user=build_authenticated_user("reader", "reader")).total_count == 3
    with pytest.raises(HTTPException) as forbidden:
        endpoint(**args, user=build_authenticated_user("viewer", "viewer"))
    assert forbidden.value.status_code == 403


def test_http_read_permission_and_query_validation():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    app = FastAPI()
    register_catalog_routes(app, factory)
    actor = build_authenticated_user("reader", "reader")
    app.dependency_overrides[get_authenticated_user] = lambda: actor
    def request(query):
        messages = []
        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}
        async def send(message):
            messages.append(message)
        scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET",
                 "scheme": "http", "path": "/reports/cases", "raw_path": b"/reports/cases",
                 "query_string": query, "headers": [(b"host", b"testserver")],
                 "client": ("testclient", 50000), "server": ("testserver", 80), "root_path": ""}
        anyio.run(app, scope, receive, send)
        return next(x["status"] for x in messages if x["type"] == "http.response.start")
    assert request(b"offset=-1") == 422
    assert request(b"state=closed") == 422
    assert request(b"") == 200
    actor = build_authenticated_user("viewer", "viewer")
    assert request(b"") == 403
    engine.dispose()
