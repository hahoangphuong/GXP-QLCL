"""Operator Case report distinguishes explicit nonissuance from pending decisions."""
from datetime import date
import anyio
import pytest
from fastapi import FastAPI, HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from backend.app.api.routers.catalog import register_catalog_routes
from backend.app.auth import build_authenticated_user, get_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import AppUser, AuditEvent, Case, CaseCertificateNonissuanceDecision, Company, Site
from backend.app.services.catalog import CatalogReadService


@pytest.fixture
def seeded():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        actor = AppUser(username="decision-report-synthetic")
        a = Company(legal_name="Company with decisions")
        b = Company(legal_name="Unrelated company")
        db.add_all([actor, a, b])
        db.flush()
        sa = Site(company_id=a.id, site_name="Pharma facility")
        sb = Site(company_id=b.id, site_name="Another facility")
        db.add_all([sa, sb])
        db.flush()
        explicit = Case(site_id=sa.id, gxp_type="GMP", state=CaseState.AWAITING_CERTIFICATE_DECISION)
        pending = Case(site_id=sa.id, gxp_type="GMP", state=CaseState.AWAITING_CERTIFICATE_DECISION)
        earlier = Case(site_id=sa.id, gxp_type="GMP", state=CaseState.PLANNED)
        unrelated = Case(site_id=sb.id, gxp_type="GLP", state=CaseState.AWAITING_CERTIFICATE_DECISION)
        db.add_all([explicit, pending, earlier, unrelated])
        db.flush()
        db.add_all([
            CaseCertificateNonissuanceDecision(
                case_id=explicit.id, decided_on=date(2026, 11, 13),
                decision_reference="DEC-EXPLICIT-001", explanation="Synthetic explicit decision",
                recorded_by_user_id=actor.id,
            ),
            CaseCertificateNonissuanceDecision(
                case_id=unrelated.id, decided_on=date(2026, 11, 11),
                decision_reference="DEC-OTHER-002", explanation="Different Site and Case",
                recorded_by_user_id=actor.id,
            ),
        ])
        ids = dict(explicit=explicit.id, pending=pending.id, earlier=earlier.id, unrelated=unrelated.id)
        db.commit()
    try:
        yield engine, ids
    finally:
        engine.dispose()


def report(db, **changes):
    opts = dict(gxp_type=None, state=None, q=None, opened_year=None,
                inspection_queue=False, export=False, offset=0, limit=100,
                certificate_decision_status=None)
    return CatalogReadService().get_case_report(db, **(opts | changes))


def test_explicit_nonissuance_is_never_inferred_from_absent_gcn(seeded):
    engine, ids = seeded
    with Session(engine) as db:
        before = db.scalar(select(func.count(AuditEvent.id)))
        page = report(db)
        assert page["total_count"] == 4
        rows = {row["case_id"]: row for row in page["items"]}
        assert rows[ids["explicit"]]["certificate_decision_status"] == "nonissuance_recorded"
        assert rows[ids["explicit"]]["nonissuance_decision_reference"] == "DEC-EXPLICIT-001"
        assert rows[ids["explicit"]]["nonissuance_decided_on"] == date(2026, 11, 13)
        assert rows[ids["explicit"]]["nonissuance_decision_id"] is not None
        assert rows[ids["pending"]]["certificate_decision_status"] == "awaiting_decision"
        assert rows[ids["pending"]]["nonissuance_decision_id"] is None
        assert rows[ids["earlier"]]["certificate_decision_status"] == "not_at_decision_stage"
        assert rows[ids["earlier"]]["nonissuance_decision_reference"] is None
        assert rows[ids["unrelated"]]["nonissuance_decision_reference"] == "DEC-OTHER-002"
        assert db.scalar(select(func.count(AuditEvent.id))) == before
        assert not db.new and not db.dirty


def test_filters_counts_pagination_export_and_case_ownership(seeded):
    engine, ids = seeded
    with Session(engine) as db:
        page = report(db, certificate_decision_status="nonissuance_recorded")
        assert page["total_count"] == 2
        assert {row["case_id"] for row in page["items"]} == {ids["explicit"], ids["unrelated"]}
        first = report(db, certificate_decision_status="nonissuance_recorded", limit=1)
        second = report(db, certificate_decision_status="nonissuance_recorded", limit=1, offset=1)
        assert first["total_count"] == second["total_count"] == 2
        assert {row["case_id"] for row in first["items"] + second["items"]} == {ids["explicit"], ids["unrelated"]}
        assert {row["case_id"] for row in report(db, certificate_decision_status="nonissuance_recorded", export=True)["items"]} == {ids["explicit"], ids["unrelated"]}
        assert {row["case_id"] for row in report(db, certificate_decision_status="awaiting_decision")["items"]} == {ids["pending"]}
        assert {row["case_id"] for row in report(db, certificate_decision_status="not_at_decision_stage")["items"]} == {ids["earlier"]}
        assert {row["case_id"] for row in report(db, certificate_decision_status="nonissuance_recorded", gxp_type="GMP")["items"]} == {ids["explicit"]}
        assert report(db, certificate_decision_status="awaiting_decision", state="planned")["total_count"] == 0
        assert {row["case_id"] for row in report(db, certificate_decision_status="nonissuance_recorded", q="Pharma")["items"]} == {ids["explicit"]}


@pytest.mark.parametrize("wrong", ["", "refused", "issued", "nonissuance", "pending", "other"])
def test_invalid_status_is_rejected_by_service(seeded, wrong):
    engine, _ = seeded
    with Session(engine) as db:
        with pytest.raises(HTTPException) as exc:
            report(db, certificate_decision_status=wrong)
        assert exc.value.status_code == 422


def test_route_permission_readback_and_query(seeded):
    engine, ids = seeded
    app = FastAPI()
    register_catalog_routes(app, sessionmaker(bind=engine))
    endpoint = next(r.endpoint for r in app.routes if getattr(r, "path", "") == "/reports/cases")
    params = dict(gxp_type=None, state=None, q=None, opened_year=None, inspection_queue=False,
                  certificate_decision_status="nonissuance_recorded", export=False, offset=0, limit=100)
    with Session(engine) as db:
        result = endpoint(session=db, user=build_authenticated_user("reader", "reader"), **params)
        assert result.total_count == 2
        assert {row.case_id for row in result.items} == {ids["explicit"], ids["unrelated"]}
        with pytest.raises(HTTPException) as denied:
            endpoint(session=db, user=build_authenticated_user("viewer", "viewer"), **params)
        assert denied.value.status_code == 403
        with pytest.raises(HTTPException) as invalid:
            endpoint(session=db, user=build_authenticated_user("reader", "reader"), **(params | {"certificate_decision_status": "issued"}))
        assert invalid.value.status_code == 422
    app.dependency_overrides[get_authenticated_user] = lambda: build_authenticated_user("reader", "reader")
    def http_status(query):
        messages = []
        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}
        async def send(msg):
            messages.append(msg)
        scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET",
                 "scheme": "http", "path": "/reports/cases", "raw_path": b"/reports/cases",
                 "query_string": query, "headers": [(b"host", b"testserver")],
                 "client": ("testclient", 50000), "server": ("testserver", 80), "root_path": ""}
        anyio.run(app, scope, receive, send)
        return next(m["status"] for m in messages if m["type"] == "http.response.start")
    assert http_status(b"certificate_decision_status=nonissuance_recorded") == 200
    assert http_status(b"certificate_decision_status=awaiting_decision") == 200
    assert http_status(b"certificate_decision_status=refused") == 422
