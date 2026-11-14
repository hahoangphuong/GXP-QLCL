"""Real ASGI + disposable migrated PostgreSQL catalog-to-first-Case contract.

This suite extends the existing PostgreSQL HTTP fixture, not the intercepted
Chromium mock. It is deliberately gated by GXP_CANONICAL_WORKFLOW_POSTGRES.
No rehearsal or production database is permitted by the shared fixture.
"""
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.db.models.phase1 import (
    AuditEvent, Case, Certificate, Company, ProductionLine, Site,
)
from test_canonical_http_workflow_postgres import api, ok
from test_canonical_workflow_postgres import pg_engine


def new_uuid():
    return str(uuid4())


def counts(engine):
    with Session(engine) as db:
        return {
            model.__tablename__: db.scalar(select(func.count()).select_from(model))
            for model in (Company, Site, ProductionLine, Case, Certificate, AuditEvent)
        }


def test_real_http_company_site_line_initial_case_canonical_lineage(pg_engine, api):
    company_id, site_id, line_id, case_id = (new_uuid() for _ in range(4))
    start = counts(pg_engine)

    company = ok(api, "POST", "/companies", {
        "company_id": company_id, "legal_name": "Synthetic HTTP Company",
        "legal_address": "Synthetic address", "reason": "Operator confirmed",
    })
    assert company["id"] == company_id
    assert ok(api, "GET", f"/companies/{company_id}")["id"] == company_id

    site = ok(api, "POST", f"/companies/{company_id}/sites", {
        "site_id": site_id, "site_name": "Synthetic HTTP Site",
        "site_address": "Synthetic factory address", "reason": "Operator confirmed",
    })
    assert site["id"] == site_id and site["company_id"] == company_id
    assert ok(api, "GET", f"/sites/{site_id}")["company_id"] == company_id

    # A physical asset has its own UUID. Code alone is not identity.
    line = ok(api, "POST", f"/sites/{site_id}/production-lines", {
        "production_line_id": line_id, "code": "L1",
        "effective_from": "2026-01-01",
        "physical_identity_evidence_reference": "SYNTHETIC-REVIEW",
        "reason": "Operator confirmed physical asset",
    })
    assert line["id"] == line_id and line["site_id"] == site_id
    assert ok(api, "GET", f"/production-lines/{line_id}")["site_id"] == site_id

    before_case = counts(pg_engine)
    assert before_case[Certificate.__tablename__] == start[Certificate.__tablename__]
    case = ok(api, "POST", f"/sites/{site_id}/inspection-cases/initial", {
        "case_id": case_id, "gxp_type": "GMP",
        "production_line_id": line_id, "inspection_type": "Mới",
        "applicable_standard": "WHO-GMP",
        "reason": "Initial synthetic case",
    })
    assert case["case_id"] == case_id
    assert case["site_id"] == site_id
    assert case["production_line_id"] == line_id
    assert case["state"] == "draft"
    assert case["row_version"] == 1
    detail = ok(api, "GET", f"/cases/{case_id}")
    assert detail["id"] == case_id
    assert detail["site_id"] == site_id
    assert detail["gxp_type"] == "GMP"
    assert detail["production_line_id"] == line_id
    assert detail["row_version"] == 1
    assert detail["legacy_inspection_id"] is None

    workspace = ok(api, "GET", f"/cases/{case_id}/workspace")
    assert workspace["case_summary"]["id"] == case_id
    assert workspace["case_summary"]["site_id"] == site_id
    assert workspace["case_summary"]["state"] == "draft"

    after = counts(pg_engine)
    for model in (Company, Site, ProductionLine, Case):
        assert after[model.__tablename__] == start[model.__tablename__] + 1
    assert after[Certificate.__tablename__] == start[Certificate.__tablename__]
    assert after[AuditEvent.__tablename__] == start[AuditEvent.__tablename__] + 4

    # A lost POST response must be recovered through exact-UUID GET,
    # never by replaying the write.
    status, _ = api("POST", f"/sites/{site_id}/inspection-cases/initial", {
        "case_id": case_id, "gxp_type": "GMP",
        "production_line_id": line_id, "inspection_type": "Mới",
        "reason": "Ambiguous response replay must fail",
    })
    assert status == 409
    assert counts(pg_engine) == after
    assert ok(api, "GET", f"/cases/{case_id}")["production_line_id"] == line_id


def test_real_http_foreign_line_and_readonly_are_denied_without_writes(pg_engine, api):
    company_id, first_site_id, second_site_id, line_id, case_id = (
        new_uuid() for _ in range(5)
    )
    ok(api, "POST", "/companies", {
        "company_id": company_id, "legal_name": "Synthetic ownership boundary",
        "legal_address": "Synthetic address", "reason": "Test setup",
    })
    for site_id in (first_site_id, second_site_id):
        ok(api, "POST", f"/companies/{company_id}/sites", {
            "site_id": site_id, "site_name": f"Synthetic Site {site_id}",
            "site_address": "Synthetic address", "reason": "Test setup",
        })
    ok(api, "POST", f"/sites/{first_site_id}/production-lines", {
        "production_line_id": line_id, "code": "L1",
        "effective_from": "2026-01-01",
        "physical_identity_evidence_reference": "SYNTHETIC-REVIEW",
        "reason": "Physical source verified",
    })
    before = counts(pg_engine)
    payload = {
        "case_id": case_id, "gxp_type": "GMP",
        "production_line_id": line_id, "inspection_type": "Mới",
        "reason": "Foreign owner must fail",
    }
    status, _ = api(
        "POST", f"/sites/{second_site_id}/inspection-cases/initial", payload
    )
    assert status in (404, 409, 422)
    assert counts(pg_engine) == before
    status, _ = api(
        "POST", f"/sites/{first_site_id}/inspection-cases/initial",
        {**payload, "case_id": new_uuid()}, role="reader",
    )
    assert status == 403
    assert counts(pg_engine) == before
    status, _ = api("GET", f"/cases/{case_id}")
    assert status == 404
