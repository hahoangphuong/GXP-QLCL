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
from test_canonical_http_workflow_postgres import (
    api, ok, workspace, transition, new_cycle, submit_assess,
    create_approval, complete_approval,
)
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


def test_real_http_new_initial_case_continues_through_capa_pct_ct_and_close(pg_engine, api):
    """A *new* canonical Case, not an ORM-seeded in-progress Case, can complete.

    Lifecycle transitions are synthetic audit facts in this regression; they
    do not stand in for actual application, decision, or inspection documents.
    This verifies canonical IDs, optimistic versions and HTTP integration.
    """
    company_id, site_id, line_id, case_id = (new_uuid() for _ in range(4))
    start = counts(pg_engine)
    ok(api, "POST", "/companies", {
        "company_id": company_id, "legal_name": "Synthetic full-flow Company",
        "legal_address": "Synthetic legal address", "reason": "Isolated workflow",
    })
    ok(api, "POST", f"/companies/{company_id}/sites", {
        "site_id": site_id, "site_name": "Synthetic full-flow Site",
        "site_address": "Synthetic factory address", "reason": "Isolated workflow",
    })
    ok(api, "POST", f"/sites/{site_id}/production-lines", {
        "production_line_id": line_id, "code": "L1",
        "effective_from": "2026-01-01",
        "physical_identity_evidence_reference": "SYNTHETIC-OWNER-DOCUMENT",
        "reason": "Distinct physical identity",
    })
    created = ok(api, "POST", f"/sites/{site_id}/inspection-cases/initial", {
        "case_id": case_id, "gxp_type": "GMP", "production_line_id": line_id,
        "inspection_type": "Mới", "applicable_standard": "WHO-GMP",
        "reason": "Synthetic initial case",
    })
    assert created["case_id"] == case_id and created["row_version"] == 1
    first = workspace(api, case_id)
    assert first["case_summary"]["state"] == "draft"
    assert first["case_summary"]["site_id"] == site_id
    assert first["case_summary"]["production_line_id"] == line_id

    # Neither a premature Certificate nor a fabricated lifecycle skip may
    # become an alternative admission path after creating an Initial Case.
    premature = {
        "case_id": case_id, "certificate_type": "GMP",
        "issuance_basis": "inspection_case", "certificate_number": "SYNTHETIC-EARLY",
        "issue_date": "2026-10-06", "expiry_date": "2027-10-06", "scopes": [],
    }
    before_blocked = counts(pg_engine)
    status, _ = api("POST", f"/sites/{site_id}/certificates", premature)
    assert status == 409
    status, _ = api("POST", f"/cases/{case_id}/transition", {
        "target_state": "certified", "expected_version": created["row_version"],
        "reason": "Disallowed lifecycle skip",
    })
    assert status == 409
    assert counts(pg_engine) == before_blocked

    # Every next state is requested through the authoritative workspace
    # readiness/version; there are no inferred jumps or version rescues.
    steps = (
        "application_received", "under_assessment", "planned",
        "decision_issued", "inspection_in_progress",
    )
    for target in steps:
        changed = transition(api, case_id, target)
        assert changed["case_id"] == case_id and changed["current_state"] == target
        detail = ok(api, "GET", f"/cases/{case_id}")
        assert detail["site_id"] == site_id
        assert detail["production_line_id"] == line_id
        assert detail["gxp_type"] == "GMP"

    ok(api, "PUT", f"/cases/{case_id}/outcome", {
        "inspected_on": "2026-10-01", "inspected_to_on": "2026-10-01",
        "outcome_result": "synthetic inspection",
    })
    transition(api, case_id, "inspection_completed")
    cycle = new_cycle(api, case_id)
    submit_assess(api, case_id, cycle, "accepted")
    readiness = workspace(api, case_id)["inspection"]["final_evaluation_readiness"]
    assert readiness["available"]
    ok(api, "POST", f"/cases/{case_id}/outcome/final-evaluation", {
        "expected_version": readiness["expected_version"],
        "final_evaluation": "Đạt",
    })
    transition(api, case_id, "awaiting_certificate_decision")

    pct = complete_approval(api, case_id, create_approval(api, case_id, "PCT"))
    ct = complete_approval(
        api, case_id, create_approval(api, case_id, "CT", pct["approval_submission_id"]),
    )
    assert ct["pct_submission_id"] == pct["approval_submission_id"]
    assert workspace(api, case_id)["certificate_issue_readiness"]["available"]

    issued = ok(api, "POST", f"/sites/{site_id}/certificates", {
        **premature, "certificate_number": "SYNTHETIC-INITIAL-" + case_id[:8],
    })
    certificate_id = issued["certificate_id"]
    certificate = ok(api, "GET", f"/certificates/{certificate_id}")
    assert certificate["case_id"] == case_id and certificate["site_id"] == site_id
    assert not certificate["latest_flag"]
    promote = next(x for x in certificate["action_readiness"] if x["action_key"] == "promote_current")
    assert promote["available"]
    ok(api, "POST", f"/certificates/{certificate_id}/promote-current", {
        "expected_version": promote["expected_version"],
    })
    transition(api, case_id, "certified")
    transition(api, case_id, "closed")

    closed = workspace(api, case_id)
    assert closed["case_summary"]["state"] == "closed"
    assert closed["case_summary"]["id"] == case_id
    assert closed["case_summary"]["site_id"] == site_id
    assert closed["case_summary"]["production_line_id"] == line_id
    assert any(c["certificate_id"] == certificate_id for c in closed["linked_gxp_certificates"])
    assert ok(api, "GET", f"/certificates/{certificate_id}")["latest_flag"]

    after = counts(pg_engine)
    for model in (Company, Site, ProductionLine, Case, Certificate):
        assert after[model.__tablename__] == start[model.__tablename__] + 1
    # The one successful Initial Case creation must not be replaced or copied.
    assert ok(api, "GET", f"/cases/{case_id}")["legacy_inspection_id"] is None
    with Session(pg_engine) as db:
        assert db.scalar(select(func.count()).select_from(AuditEvent).where(
            AuditEvent.entity_id == case_id, AuditEvent.action == "case.create_initial_case",
        )) == 1
        assert db.scalar(select(func.count()).select_from(AuditEvent).where(
            AuditEvent.entity_id == certificate_id, AuditEvent.action == "certificate.issue",
        )) == 1
