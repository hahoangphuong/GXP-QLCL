"""First Case registration in a new canonical Site/GxP/line context.

Tests use only disposable SQLite. Creation must not pretend a new physical
line or Site is a legacy GxP certificate or reassessment source.
"""
from __future__ import annotations

from uuid import uuid4
from datetime import date

import pytest
from fastapi import FastAPI, HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from pydantic import ValidationError

from backend.app.api.routers.workflow import register_workflow_routes
from backend.app.api.routers.catalog import register_catalog_routes, _build_facility_action_readiness
from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import (
    Company, Site, ProductionLine, Case, Certificate, CaseApplication,
    CaseEvaluationScope, InspectionPlan, AuditEvent,
)
from backend.app.read_models import InitialInspectionCaseCreateRequest
from backend.app.services.workflow import CaseWorkflowService


@pytest.fixture
def blank():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        company = Company(legal_name="Synthetic first registration")
        inactive = Company(legal_name="Inactive synthetic", is_inactive=True)
        db.add_all([company, inactive])
        db.flush()
        site = Site(company_id=company.id, site_name="New factory")
        site_2 = Site(company_id=company.id, site_name="Other factory")
        bad_site = Site(company_id=inactive.id, site_name="Inactive factory")
        db.add_all([site, site_2, bad_site])
        db.flush()
        line = ProductionLine(
            site_id=site.id, code="A", effective_from=date(2026, 1, 1),
        )
        unrelated_line = ProductionLine(
            site_id=site_2.id, code="A", effective_from=date(2026, 1, 1),
        )
        db.add_all([line, unrelated_line])
        db.flush()
        ids = site.id, site_2.id, bad_site.id, line.id, unrelated_line.id
        db.commit()
    yield engine, ids
    engine.dispose()


def editor():
    return build_authenticated_user("initial-case-editor", permissions={"case.edit"})


def inputs(site_id, **updates):
    return {
        "site_id": site_id, "case_id": str(uuid4()), "gxp_type": "GMP",
        "production_line_id": None, "inspection_type": "Mới",
        "applicable_standard": "WHO-GMP",
        "reason": "New dossier confirmed by operator; no earlier Case",
        "user": editor(), **updates,
    }


def totals(db):
    models = [Case, Certificate, CaseApplication, CaseEvaluationScope, InspectionPlan, AuditEvent]
    return tuple(db.scalar(select(func.count()).select_from(model)) for model in models)


def test_first_case_for_new_site_without_gxp_context(blank):
    engine, (site_id, _, _, _, _) = blank
    svc = CaseWorkflowService()
    identity = str(uuid4())
    with Session(engine) as db:
        assert svc.get_create_initial_case_action_readiness(
            db, site_id=site_id, gxp_type="GMP", line_code=None,
            production_line_id=None, user=editor(),
        )["readiness_status"] == "available"
        before = totals(db)
        result = svc.create_initial_inspection_case(
            db, **inputs(site_id, case_id=identity),
        )
        assert result["case_id"] == identity
        assert result["inspection_type"] == "Mới"
        assert result["line_code"] is None and result["production_line_id"] is None
        assert result["state"] == "draft" and result["row_version"] == 1
        assert result["legacy_inspection_id"] is None
        db.commit()
    with Session(engine) as db:
        row = db.get(Case, identity)
        assert row.site_id == site_id and row.gxp_type == "GMP"
        assert row.inspection_type == "Mới" and row.scope_code is None
        assert row.state == CaseState.DRAFT
        assert totals(db) == (before[0] + 1, before[1], before[2], before[3], before[4], before[5] + 1)
        assert db.scalar(select(AuditEvent.action)) == "case.create_initial_case"
        assert svc.get_create_initial_case_action_readiness(
            db, site_id=site_id, gxp_type="GMP", line_code=None,
            production_line_id=None, user=editor(),
        )["readiness_status"] == "conflict"
        assert svc.get_create_reassessment_case_action_readiness(
            db, site_id=site_id, gxp_type="GMP", line_code=None,
            production_line_id=None, user=editor(),
        )["readiness_status"] == "conflict"


def test_first_case_for_explicit_physical_line_not_legacy_code(blank):
    engine, (site_id, other_site, _, line_id, other_line) = blank
    with Session(engine) as db:
        a = CaseWorkflowService().create_initial_inspection_case(
            db, **inputs(site_id, production_line_id=line_id),
        )
        assert a["production_line_id"] == line_id
        assert a["line_code"] == "A"
        db.commit()
    with Session(engine) as db:
        row = db.get(Case, a["case_id"])
        assert row.production_line_id == line_id
        assert row.site_id == site_id
        assert not db.scalars(select(Case).where(Case.site_id == other_site)).all()
        assert db.get(ProductionLine, other_line).site_id == other_site


@pytest.mark.parametrize("kind", [
    "same_uuid", "history_case", "history_certificate", "history_nonlatest_certificate", "wrong_line",
    "unknown_site", "inactive_parent", "unsupported_gxp", "reassessment_type",
    "blank_reason", "blank_inspection_type",
])
def test_fail_closed_with_no_partial_writes(blank, kind):
    engine, (site_id, other_site, inactive_site, line_id, other_line) = blank
    svc = CaseWorkflowService()
    ident = str(uuid4())
    with Session(engine) as db:
        if kind == "same_uuid":
            db.add(Case(
                id=ident, site_id=site_id, gxp_type="GLP",
                inspection_type="Mới", state=CaseState.DRAFT,
            ))
        if kind == "history_case":
            db.add(Case(
                site_id=site_id, gxp_type="GMP",
                state=CaseState.CLOSED, inspection_type="Định kỳ",
            ))
        if kind == "history_certificate":
            db.add(Certificate(
                site_id=site_id, certificate_type="GMP",
                latest_flag=True,
            ))
        if kind == "history_nonlatest_certificate":
            db.add(Certificate(
                site_id=site_id, certificate_type="GMP",
                latest_flag=False,
            ))
        db.commit()
    args = inputs(site_id, case_id=ident)
    if kind == "wrong_line": args["production_line_id"] = other_line
    if kind == "unknown_site": args["site_id"] = str(uuid4())
    if kind == "inactive_parent": args["site_id"] = inactive_site
    if kind == "unsupported_gxp": args["gxp_type"] = "GSP"
    if kind == "reassessment_type": args["inspection_type"] = "Tái"
    if kind == "blank_reason": args["reason"] = " "
    if kind == "blank_inspection_type": args["inspection_type"] = " "
    with Session(engine) as db:
        before = totals(db)
        with pytest.raises(HTTPException) as err:
            svc.create_initial_inspection_case(db, **args)
        assert err.value.status_code in (409, 404, 422)
        db.rollback()
        assert totals(db) == before


def test_nonlatest_historical_certificate_blocks_first_case_readiness(blank):
    engine, (site_id, _, _, _, _) = blank
    with Session(engine) as db:
        db.add(Certificate(site_id=site_id, certificate_type="GMP", latest_flag=False))
        db.commit()
    with Session(engine) as db:
        ready = CaseWorkflowService().get_create_initial_case_action_readiness(
            db, site_id=site_id, gxp_type="GMP", line_code=None,
            production_line_id=None, user=editor(),
        )
        assert ready["readiness_status"] == "conflict"


def test_unknown_post_replay_409_get_owner_then_compare(blank):
    engine, (site_id, _, _, _, _) = blank
    svc = CaseWorkflowService()
    identity = str(uuid4())
    with Session(engine) as db:
        svc.create_initial_inspection_case(db, **inputs(site_id, case_id=identity))
        db.commit()
    with Session(engine) as db:
        before = totals(db)
        with pytest.raises(HTTPException) as error:
            svc.create_initial_inspection_case(
                db, **inputs(site_id, case_id=identity, inspection_type="Different replay"),
            )
        assert error.value.status_code == 409
        db.rollback()
        assert totals(db) == before
        canonical = db.get(Case, identity)
        assert canonical.site_id == site_id
        assert canonical.inspection_type == "Mới"


def test_auth_uuid_contract_and_workspace_readiness(blank):
    engine, (site_id, _, _, line_id, _) = blank
    app = FastAPI()
    register_workflow_routes(app, lambda: None)
    register_catalog_routes(app, lambda: None)
    route = next(
        r.endpoint for r in app.routes
        if getattr(r, "path", "") == "/sites/{site_id}/inspection-cases/initial"
    )
    readonly = build_authenticated_user("readonly", "reader")
    with pytest.raises(ValidationError):
        InitialInspectionCaseCreateRequest(
            case_id="not-uuid", gxp_type="GMP", inspection_type="Mới", reason="R",
        )
    payload = InitialInspectionCaseCreateRequest(
        case_id=uuid4(), gxp_type="GMP", production_line_id=None,
        inspection_type="Mới", reason="Valid new applicant",
    )
    with Session(engine) as db:
        with pytest.raises(HTTPException) as err:
            route(site_id=site_id, payload=payload, session=db, user=readonly)
        assert err.value.status_code == 403
        assert totals(db)[0] == 0
    with Session(engine) as db:
        result = route(site_id=site_id, payload=payload, session=db, user=editor())
        assert result.case_id == str(payload.case_id)
    with Session(engine) as db:
        line_context = _build_facility_action_readiness(
            workflow_service=CaseWorkflowService(), session=db, site_id=site_id,
            selected_gxp_type="GMP", selected_line_code="A",
            selected_production_line_id=line_id, user=editor(),
        )
        action = {row["action_key"]: row for row in line_context}
        assert action["create_initial_case"]["readiness_status"] == "available"
        assert action["create_initial_case"]["required_permissions"] == ["case.edit"]
        readonly_actions = _build_facility_action_readiness(
            workflow_service=CaseWorkflowService(), session=db, site_id=site_id,
            selected_gxp_type="GMP", selected_line_code="A",
            selected_production_line_id=line_id, user=readonly,
        )
        assert {row["action_key"]: row for row in readonly_actions}["create_initial_case"]["readiness_status"] == "forbidden"


def test_long_canonical_line_code_does_not_overflow_case_legacy_scope_code(blank):
    engine, (site_id, _, _, _, _) = blank
    long_code = "LONG-PHYSICAL-LINE-CODE-" + ("Z" * 20)
    assert len(long_code) > 32
    with Session(engine) as db:
        physical = ProductionLine(
            site_id=site_id, code=long_code, effective_from=date(2026, 1, 1),
        )
        db.add(physical)
        db.flush()
        line_id = physical.id
        db.commit()
    with Session(engine) as db:
        created = CaseWorkflowService().create_initial_inspection_case(
            db, **inputs(site_id, production_line_id=line_id),
        )
        assert created["production_line_id"] == line_id
        assert created["line_code"] == long_code
        db.commit()
    with Session(engine) as db:
        row = db.get(Case, created["case_id"])
        assert row.production_line_id == line_id
        assert row.scope_code is None  # no invalid truncation or fake legacy code
