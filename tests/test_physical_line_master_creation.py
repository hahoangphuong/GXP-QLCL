"""Explicit physical ProductionLine master: no legacy code inference or relinking."""
from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from backend.app.api.routers.catalog import register_catalog_routes, _build_facility_action_readiness
from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.models.phase1 import (
    AppUser, AuditEvent, Case, Certificate, Company, ProductionLine,
    ProductionLineTransformation, Site,
)
from backend.app.read_models import ProductionLineMasterCreateRequest
from backend.app.services.workflow import CaseWorkflowService


@pytest.fixture
def setup_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        primary = Company(legal_name="Direct physical identity owner")
        inactive = Company(legal_name="Inactive owner", is_inactive=True)
        db.add_all([primary, inactive])
        db.flush()
        site = Site(company_id=primary.id, site_name="Factory 1")
        site_other = Site(company_id=inactive.id, site_name="Factory 2")
        db.add_all([site, site_other])
        db.flush()
        ids = site.id, site_other.id
        db.commit()
    try:
        yield engine, ids
    finally:
        engine.dispose()


def actor():
    return build_authenticated_user("line-master-editor", permissions={"case.edit"})


def params(site_id, line_id=None, **changes):
    return {
        "site_id": site_id,
        "production_line_id": line_id or str(uuid4()),
        "code": " A ",
        "effective_from": date(2026, 11, 13),
        "effective_to": None,
        "physical_identity_evidence_reference": " SOURCE-PHYSICAL-LINE-001 ",
        "reason": "Reviewed physical line inventory signed by owner",
        "user": actor(),
        **changes,
    }


def totals(db):
    return {
        "lines": db.scalar(select(func.count(ProductionLine.id))),
        "audit": db.scalar(select(func.count(AuditEvent.id))),
        "cases": db.scalar(select(func.count(Case.id))),
        "certificates": db.scalar(select(func.count(Certificate.id))),
        "transformations": db.scalar(select(func.count(ProductionLineTransformation.id))),
    }


def test_new_identity_is_distinct_from_code_and_does_not_infer_any_gxp(setup_db):
    engine, (site_id, _) = setup_db
    svc = CaseWorkflowService()
    a, b = str(uuid4()), str(uuid4())
    with Session(engine) as db:
        first = svc.create_production_line_master(db, **params(site_id, a))
        second = svc.create_production_line_master(db, **params(site_id, b))
        assert first["id"] == a and second["id"] == b
        assert first["code"] == second["code"] == "A"
        assert first["row_version"] == second["row_version"] == 1
        db.commit()
    with Session(engine) as db:
        assert db.get(ProductionLine, a).site_id == site_id
        assert db.get(ProductionLine, b).site_id == site_id
        assert totals(db) == {"lines": 2, "audit": 2, "cases": 0, "certificates": 0, "transformations": 0}
        events = db.scalars(select(AuditEvent)).all()
        assert {event.action for event in events} == {"production_line.create"}
        assert all("SOURCE-PHYSICAL-LINE-001" in event.payload_redacted for event in events)


def test_readback_after_unknown_post_no_replay_and_no_side_effects(setup_db):
    engine, (site_id, _) = setup_db
    line_id = str(uuid4())
    with Session(engine) as db:
        CaseWorkflowService().create_production_line_master(db, **params(site_id, line_id))
        db.commit()
    with Session(engine) as db:
        old = totals(db)
        with pytest.raises(HTTPException) as err:
            CaseWorkflowService().create_production_line_master(
                db, **params(site_id, line_id, code="REPLAY-CODE")
            )
        assert err.value.status_code == 409
        db.rollback()
        assert totals(db) == old
        original = db.get(ProductionLine, line_id)
        assert original.code == "A"


@pytest.mark.parametrize("change", [
    "unknown_site", "inactive_company", "blank_code", "long_code",
    "missing_reference", "blank_reason", "backwards_interval",
])
def test_fail_closed_invalid_evidence_site_and_dates(setup_db, change):
    engine, (site_id, inactive_site) = setup_db
    args = params(site_id)
    if change == "unknown_site": args["site_id"] = str(uuid4())
    if change == "inactive_company": args["site_id"] = inactive_site
    if change == "blank_code": args["code"] = " "
    if change == "long_code": args["code"] = "L" * 65
    if change == "missing_reference": args["physical_identity_evidence_reference"] = " "
    if change == "blank_reason": args["reason"] = " "
    if change == "backwards_interval": args["effective_to"] = date(2026, 11, 13)
    with Session(engine) as db:
        before = totals(db)
        with pytest.raises(HTTPException) as err:
            CaseWorkflowService().create_production_line_master(db, **args)
        assert err.value.status_code in (404, 409, 422)
        db.rollback()
        assert totals(db) == before


def test_http_scoped_list_readback_roles_uuid4_contract(setup_db):
    engine, (site_id, other_id) = setup_db
    app = FastAPI()
    register_catalog_routes(app, lambda: None)
    routes = [
        route for route in app.routes
        if getattr(route, "path", "") in (
            "/sites/{site_id}/production-lines", "/production-lines/{production_line_id}"
        )
    ]
    create = next(r.endpoint for r in routes if r.path.endswith("/production-lines") and r.methods == {"POST"})
    listing = next(r.endpoint for r in routes if r.path.endswith("/production-lines") and r.methods == {"GET"})
    detail = next(r.endpoint for r in routes if r.path.startswith("/production-lines/"))
    viewer = build_authenticated_user("read-only", "reader")
    with pytest.raises(ValidationError):
        ProductionLineMasterCreateRequest(
            production_line_id="not-a-uuid", code="A", effective_from=date(2026, 1, 1),
            physical_identity_evidence_reference="REF", reason="R",
        )
    with Session(engine) as db:
        with pytest.raises(HTTPException) as err:
            create(
                site_id=site_id,
                payload=ProductionLineMasterCreateRequest(
                    production_line_id=uuid4(), code="A", effective_from=date(2026, 1, 1),
                    physical_identity_evidence_reference="REF", reason="R",
                ), session=db, user=viewer,
            )
        assert err.value.status_code == 403
        assert totals(db)["lines"] == 0
    line_id = uuid4()
    with Session(engine) as db:
        receipt = create(
            site_id=site_id,
            payload=ProductionLineMasterCreateRequest(
                production_line_id=line_id, code="A", effective_from=date(2026, 1, 1),
                physical_identity_evidence_reference="REF", reason="Evidence verified",
            ), session=db, user=actor(),
        )
        assert receipt.id == str(line_id)
    with Session(engine) as db:
        target = detail(production_line_id=str(line_id), session=db, user=viewer)
        assert target.site_id == site_id
        rows = listing(site_id=site_id, session=db, user=viewer)
        assert len(rows) == 1 and rows[0].id == str(line_id)
        assert listing(site_id=other_id, session=db, user=viewer) == []
        assert totals(db)["lines"] == 1


def test_workspace_readiness_uses_permission_and_line_identity_not_gxp(setup_db):
    engine, (site_id, _) = setup_db
    with Session(engine) as db:
        for user, expected in (
            (actor(), "available"),
            (build_authenticated_user("reader", "reader"), "forbidden"),
        ):
            actions = {
                v["action_key"]: v
                for v in _build_facility_action_readiness(
                    workflow_service=CaseWorkflowService(), session=db, site_id=site_id,
                    selected_gxp_type=None, selected_line_code=None,
                    selected_production_line_id=None, user=user,
                )
            }
            assert actions["create_production_line"]["readiness_status"] == expected
            assert actions["create_production_line"]["required_permissions"] == ["case.edit"]
            assert actions["create_reassessment_case"]["readiness_status"] == "unavailable"
