"""New facility master creation: explicit canonical identities and readback.

Synthetic only. No legacy mapping, GxP context, or auto-created Case/Certificate.
A lost POST response is resolved by the existing scoped resource GET, never retry.
"""
from __future__ import annotations

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
    AuditEvent, Case, Certificate, Company, ProductionLine, Site,
)
from backend.app.read_models import CompanyMasterCreateRequest, SiteMasterCreateRequest
from backend.app.services.catalog import CatalogReadService
from backend.app.services.workflow import CaseWorkflowService


@pytest.fixture
def seeded():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        previous = Company(legal_name="Legacy entity", legacy_company_id=42)
        db.add(previous)
        db.flush()
        legacy = Site(company_id=previous.id, site_name="Legacy site", legacy_site_id=77)
        db.add(legacy)
        db.flush()  # Primary keys are generated on flush, not at ORM construction.
        ids = (previous.id, legacy.id)
        db.commit()
    try:
        yield engine, ids
    finally:
        engine.dispose()


def editor():
    return build_authenticated_user("master-operator", permissions={"case.edit"})


def company_params(company_id, **patch):
    return {
        "company_id": company_id,
        "legal_name": " Synthetic Pharmaceutical Ltd ",
        "legal_address": " 1 Example Road, Hanoi ",
        "english_name": None,
        "short_name": "SYNTH",
        "legal_address_en": None,
        "reason": "Source-verified manual registration",
        "user": editor(),
        **patch,
    }


def site_params(company_id, site_id, **patch):
    return {
        "company_id": company_id, "site_id": site_id,
        "site_name": " Synthetic manufacturing site ",
        "site_address": " 6 Example Street ",
        "site_name_en": None, "site_address_en": None,
        "province_name": " Hanoi ", "short_name": None,
        "reason": "Explicit Company-selected facility",
        "user": editor(),
        **patch,
    }


def counts(db):
    return {
        "companies": db.scalar(select(func.count(Company.id))),
        "sites": db.scalar(select(func.count(Site.id))),
        "audits": db.scalar(select(func.count(AuditEvent.id))),
        "cases": db.scalar(select(func.count(Case.id))),
        "certificates": db.scalar(select(func.count(Certificate.id))),
        "production_lines": db.scalar(select(func.count(ProductionLine.id))),
    }


def test_create_company_and_site_canonical_get_and_no_inferred_gxp(seeded):
    engine, (legacy_company, legacy_site) = seeded
    company_id, site_id = str(uuid4()), str(uuid4())
    svc = CaseWorkflowService()
    with Session(engine) as db:
        before = counts(db)
        created_company = svc.create_company_master(db, **company_params(company_id))
        assert created_company["id"] == company_id
        assert created_company["legacy_company_id"] is None
        assert created_company["legal_name"] == "Synthetic Pharmaceutical Ltd"
        assert created_company["legal_address"] == "1 Example Road, Hanoi"
        assert created_company["is_inactive"] is False
        db.commit()
    with Session(engine) as db:
        canonical = CatalogReadService().get_company(db, company_id)
        assert canonical.legal_address == created_company["legal_address"]
        assert canonical.legacy_company_id is None
        created_site = svc.create_site_master(db, **site_params(company_id, site_id))
        assert created_site["id"] == site_id
        assert created_site["company_id"] == company_id
        assert created_site["legacy_site_id"] is None
        db.commit()
    with Session(engine) as db:
        canonical_site = CatalogReadService().get_site(db, site_id)
        assert canonical_site.company_id == company_id
        assert canonical_site.site_address == "6 Example Street"
        # The newly created Site must remain discoverable before any Case,
        # GxP registration, certificate or ProductionLine has been created.
        found = CatalogReadService().search_facilities(db, site_id=site_id)
        assert found["total_count"] == 1
        assert len(found["items"]) == 1
        item = found["items"][0]
        assert item["site_id"] == site_id
        assert item["result_grain"] == "facility"
        assert item["gxp_type"] is None
        assert item["production_line_id"] is None
        assert item["production_line_identity_state"] == "facility_wide"
        assert CatalogReadService().search_facilities(
            db, site_id=site_id, gxp_type="GMP",
        )["total_count"] == 0
        assert db.get(Company, legacy_company).legacy_company_id == 42
        assert db.get(Site, legacy_site).legacy_site_id == 77
        after = counts(db)
        assert after == {**before, "companies": before["companies"] + 1, "sites": before["sites"] + 1, "audits": before["audits"] + 2}
        audits = db.scalars(select(AuditEvent).order_by(AuditEvent.created_at, AuditEvent.id)).all()
        assert {a.action for a in audits} == {"company.create", "site.create"}
        assert not db.new and not db.dirty


@pytest.mark.parametrize("master", ["company", "site"])
def test_duplicate_uuid_post_does_not_retry_after_lost_response(seeded, master):
    engine, (existing_company, _) = seeded
    identity = str(uuid4())
    svc = CaseWorkflowService()
    with Session(engine) as db:
        if master == "company":
            svc.create_company_master(db, **company_params(identity))
        else:
            svc.create_site_master(db, **site_params(existing_company, identity))
        db.commit()
    with Session(engine) as db:
        before = counts(db)
        with pytest.raises(HTTPException) as error:
            if master == "company":
                svc.create_company_master(db, **company_params(identity, legal_name="Changed on replay"))
            else:
                svc.create_site_master(db, **site_params(existing_company, identity, site_name="Changed on replay"))
        assert error.value.status_code == 409
        db.rollback()
        assert counts(db) == before
        original = db.get(Company if master == "company" else Site, identity)
        assert original is not None


@pytest.mark.parametrize("invalid", ["unknown_company", "inactive_company", "blank_name", "blank_address", "long_province"])
def test_site_validates_authoritative_parent_and_fields(seeded, invalid):
    engine, (company_id, _) = seeded
    with Session(engine) as db:
        if invalid == "inactive_company":
            db.get(Company, company_id).is_inactive = True
        db.commit()
    params = site_params(company_id, str(uuid4()))
    if invalid == "unknown_company": params["company_id"] = str(uuid4())
    if invalid == "blank_name": params["site_name"] = "  "
    if invalid == "blank_address": params["site_address"] = ""
    if invalid == "long_province": params["province_name"] = "x" * 256
    with Session(engine) as db:
        before = counts(db)
        with pytest.raises(HTTPException) as ex:
            CaseWorkflowService().create_site_master(db, **params)
        assert ex.value.status_code in {404, 409, 422}
        db.rollback()
        assert counts(db) == before


@pytest.mark.parametrize("invalid", ["blank_name", "blank_address", "oversize_name"])
def test_company_rejects_invalid_fields_without_writing(seeded, invalid):
    engine, _ = seeded
    params = company_params(str(uuid4()))
    if invalid == "blank_name": params["legal_name"] = "  "
    if invalid == "blank_address": params["legal_address"] = " "
    if invalid == "oversize_name": params["legal_name"] = "x" * 513
    with Session(engine) as db:
        before = counts(db)
        with pytest.raises(HTTPException) as error:
            CaseWorkflowService().create_company_master(db, **params)
        assert error.value.status_code == 422
        db.rollback()
        assert counts(db) == before


def test_route_permissions_and_client_uuid4_contract(seeded):
    engine, (company_id, _) = seeded
    app = FastAPI()
    register_catalog_routes(app, lambda: None)
    companies = next(r.endpoint for r in app.routes if getattr(r, "path", None) == "/companies" and r.methods == {"POST"})
    sites = next(r.endpoint for r in app.routes if getattr(r, "path", None) == "/companies/{company_id}/sites")
    get_company = next(r.endpoint for r in app.routes if getattr(r, "path", None) == "/companies/{company_id}" and r.methods == {"GET"})
    get_site = next(r.endpoint for r in app.routes if getattr(r, "path", None) == "/sites/{site_id}" and r.methods == {"GET"})
    with pytest.raises(ValidationError):
        CompanyMasterCreateRequest(company_id="not-a-uuid", legal_name="A", legal_address="B")
    with pytest.raises(ValidationError):
        SiteMasterCreateRequest(site_id="00000000-0000-0000-0000-000000000001", site_name="A", site_address="B")
    denied = build_authenticated_user("readonly", "reader")
    with Session(engine) as db:
        before = counts(db)
        with pytest.raises(HTTPException) as error:
            companies(
                payload=CompanyMasterCreateRequest(
                    company_id=uuid4(), legal_name="Forbidden", legal_address="Forbidden"
                ), session=db, user=denied,
            )
        assert error.value.status_code == 403
        with pytest.raises(HTTPException) as error:
            sites(
                company_id=company_id,
                payload=SiteMasterCreateRequest(
                    site_id=uuid4(), site_name="Forbidden", site_address="Forbidden"
                ), session=db, user=denied,
            )
        assert error.value.status_code == 403
        assert counts(db) == before
    fresh_id = uuid4()
    with Session(engine) as db:
        result = companies(
            payload=CompanyMasterCreateRequest(
                company_id=fresh_id, legal_name="New source company", legal_address="Source address"
            ), session=db, user=editor(),
        )
        assert result.id == str(fresh_id)
    with Session(engine) as db:
        read = get_company(company_id=str(fresh_id), session=db, user=denied)
        assert read.id == str(fresh_id)
    new_site_id = uuid4()
    with Session(engine) as db:
        result = sites(
            company_id=str(fresh_id),
            payload=SiteMasterCreateRequest(
                site_id=new_site_id, site_name="New source site", site_address="Site source address"
            ), session=db, user=editor(),
        )
        assert result.company_id == str(fresh_id)
    with Session(engine) as db:
        read = get_site(site_id=str(new_site_id), session=db, user=denied)
        assert read.company_id == str(fresh_id)


def test_facility_readiness_only_opens_implemented_master_actions(seeded):
    engine, (company_id, site_id) = seeded
    with Session(engine) as db:
        for user, expected in [(editor(), "available"), (build_authenticated_user("reader", "reader"), "forbidden")]:
            actions = {
                row["action_key"]: row
                for row in _build_facility_action_readiness(
                    workflow_service=CaseWorkflowService(), session=db,
                    site_id=site_id, selected_gxp_type=None,
                    selected_line_code=None, selected_production_line_id=None, user=user,
                )
            }
            assert actions["create_company"]["readiness_status"] == expected
            assert actions["create_site"]["readiness_status"] == expected
            assert actions["create_company"]["required_permissions"] == ["case.edit"]
            assert actions["create_production_line"]["readiness_status"] == "missing_contract"
