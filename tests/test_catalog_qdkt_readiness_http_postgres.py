"""Real HTTP/PostgreSQL QĐKT preflight from a new canonical Initial Case.

These tests must not manufacture legal issuance or enable Word rendering.
InspectionDecision inserts below are deliberately labeled synthetic *source
fixtures*, not executed approvals. The actual runtime API stays read-only.
"""
from datetime import date
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.db.models.phase1 import (
    AuditEvent, Case, Company, Document,
    InspectionDecision, InspectionPlan, ProductionLine, Site,
)
from test_canonical_http_workflow_postgres import api, ok
from test_canonical_workflow_postgres import pg_engine


def _uuid():
    return str(uuid4())


def _create_catalog_case(api):
    company_id, site_id, line_id, case_id = (_uuid() for _ in range(4))
    ok(api, "POST", "/companies", {
        "company_id": company_id, "legal_name": "Synthetic QDKT source Company",
        "legal_address": "Synthetic legal address", "reason": "Isolated preflight",
    })
    ok(api, "POST", f"/companies/{company_id}/sites", {
        "site_id": site_id, "site_name": "Synthetic QDKT Site",
        "site_address": "Synthetic registered site", "reason": "Isolated preflight",
    })
    ok(api, "POST", f"/sites/{site_id}/production-lines", {
        "production_line_id": line_id, "code": "L1",
        "effective_from": "2026-01-01",
        "physical_identity_evidence_reference": "SYNTHETIC-QDKT-OWNER",
        "reason": "Independent physical identity",
    })
    created = ok(api, "POST", f"/sites/{site_id}/inspection-cases/initial", {
        "case_id": case_id, "gxp_type": "GMP",
        "production_line_id": line_id, "inspection_type": "Mới",
        "applicable_standard": "WHO-GMP", "reason": "Source-owned draft Case",
    })
    assert created["state"] == "draft"
    return company_id, site_id, line_id, case_id


def _counts(engine, case_id):
    with Session(engine) as db:
        return {
            name: db.scalar(select(func.count()).select_from(model).where(where))
            for name, model, where in (
                ("audit", AuditEvent, AuditEvent.entity_id == case_id),
                ("documents", Document, Document.case_id == case_id),
                ("decisions", InspectionDecision, InspectionDecision.inspection_plan_id.in_(
                    select(InspectionPlan.id).where(InspectionPlan.case_id == case_id))),
            )
        }


def _readiness(api, case_id, purpose=None):
    path = f"/cases/{case_id}/documents/inspection-qd-kt/readiness"
    if purpose is not None:
        path += "?purpose=" + purpose
    return ok(api, "GET", path)


def test_new_case_qdkt_draft_never_promotes_plan_scalar_to_issued_reference(pg_engine, api):
    """Draft is independent of source decision; scalar dates are never legal proof."""
    company_id, site_id, line_id, case_id = _create_catalog_case(api)
    before = _counts(pg_engine, case_id)
    draft = _readiness(api, case_id, "DRAFT_QDKT")
    approved = _readiness(api, case_id)
    for result in (draft, approved):
        assert result["case_id"] == case_id
        assert result["family_code"] == "INSPECTION_QD_KT"
        assert result["ready_to_render"] is False
        assert result["decision_source_id"] is None
        assert result["registered_site_id"] == site_id
        assert "QDKT_TYPED_RENDER_CONTRACT_MISSING" in result["blocked_reasons"]
        assert "BLANK_ISSUANCE_DATE_BOOKMARK_UNVERIFIED" in result["blocked_reasons"]
    assert "QDKT_LEGAL_ISSUANCE_EVIDENCE_UNPROVEN" not in draft["blocked_reasons"]
    assert "SOURCE_DECISION_CARDINALITY_UNPROVEN" not in draft["blocked_reasons"]
    assert "QDKT_LEGAL_ISSUANCE_EVIDENCE_UNPROVEN" in approved["blocked_reasons"]
    assert _counts(pg_engine, case_id) == before

    # Plan compatibility metadata is NOT an InspectionDecision source record.
    plan = ok(api, "PUT", f"/cases/{case_id}/plan", {
        "planning_sheet_name": "Synthetic KHKT - draft",
        "decision_reference": "SYNTHETIC-PLAN-PROJECTION",
        "decision_date": "2026-11-10",
        "reason": "Source-independent compatibility metadata",
    })
    assert plan["decision_reference"] == "SYNTHETIC-PLAN-PROJECTION"
    assert plan["decision_date"] == "2026-11-10"
    before_reads = _counts(pg_engine, case_id)
    assert before_reads["decisions"] == 0
    after_scalar = _readiness(api, case_id)
    assert after_scalar["decision_source_id"] is None
    assert "SOURCE_DECISION_CARDINALITY_UNPROVEN" in after_scalar["blocked_reasons"]
    assert not after_scalar["ready_to_render"]
    assert _readiness(api, case_id, "DRAFT_QDKT")["decision_source_id"] is None
    assert _counts(pg_engine, case_id) == before_reads

    # Source rows are inserted only as synthetic private-PG fixture atoms;
    # no public API creates, approves, signs or issues a QĐKT in this test.
    with Session(pg_engine) as db:
        plan_row = db.scalar(select(InspectionPlan).where(InspectionPlan.case_id == case_id))
        assert plan_row is not None
        first = InspectionDecision(
            inspection_plan_id=plan_row.id, ordinal=1,
            reference="SYNTHETIC-DECISION-1",
            decision_on=date(2026, 11, 10), legacy_raw="synthetic source 1",
        )
        db.add(first)
        db.commit()
        first_id = first.id
        plan_id = plan_row.id
    source_only = _readiness(api, case_id)
    assert source_only["decision_source_id"] == first_id
    assert "QDKT_LEGAL_ISSUANCE_EVIDENCE_UNPROVEN" in source_only["blocked_reasons"]
    assert not source_only["ready_to_render"]
    # Process A must not borrow the issued-branch source, regardless of its existence.
    assert _readiness(api, case_id, "DRAFT_QDKT")["decision_source_id"] is None

    with Session(pg_engine) as db:
        plan_row = db.scalar(select(InspectionPlan).where(InspectionPlan.case_id == case_id))
        replacement = InspectionDecision(
            inspection_plan_id=plan_row.id, ordinal=2,
            reference="SYNTHETIC-DECISION-REPLACEMENT",
            decision_on=date(2026, 11, 12),
            legacy_raw="synthetic replacement atom",
            relation_type="REPLACES", related_decision_id=first_id,
        )
        db.add(replacement)
        db.commit()
        replacement_id = replacement.id
    latest = _readiness(api, case_id)
    assert latest["decision_source_id"] == replacement_id
    assert "QDKT_LEGAL_ISSUANCE_EVIDENCE_UNPROVEN" in latest["blocked_reasons"]
    assert not latest["ready_to_render"]
    assert _readiness(api, case_id, "DRAFT_QDKT")["decision_source_id"] is None
    # No unexpected document artifact or legally issued QĐKT is fabricated.
    with Session(pg_engine) as db:
        assert db.get(Case, case_id).site_id == site_id
        assert db.get(Case, case_id).production_line_id == line_id
        assert db.scalar(select(func.count()).select_from(Document)
                         .where(Document.case_id == case_id)) == 0
        assert db.scalar(select(func.count()).select_from(InspectionDecision)
                         .where(InspectionDecision.inspection_plan_id == plan_id)) == 2


def test_qdkt_reference_ambiguous_replacements_and_permission_fail_closed(pg_engine, api):
    """Never borrow cross-Case decision or infer newest from malformed relation."""
    _, _, _, case_a = _create_catalog_case(api)
    _, _, _, case_b = _create_catalog_case(api)
    status, _ = api(
        "GET", f"/cases/{case_a}/documents/inspection-qd-kt/readiness",
        role="reader",
    )
    assert status == 403
    for case_id in (case_a, case_b):
        ok(api, "PUT", f"/cases/{case_id}/plan", {
            "planning_sheet_name": "Synthetic source plan",
        })
    with Session(pg_engine) as db:
        plan_b = db.scalar(select(InspectionPlan).where(InspectionPlan.case_id == case_b))
        other = InspectionDecision(
            inspection_plan_id=plan_b.id, ordinal=1,
            reference="OTHER-CASE-DECISION",
            decision_on=date(2026, 11, 10), legacy_raw="other case atom",
        )
        db.add(other)
        db.commit()
    before = _counts(pg_engine, case_a)
    assert _readiness(api, case_a)["decision_source_id"] is None
    assert _readiness(api, case_a, "DRAFT_QDKT")["decision_source_id"] is None
    assert _counts(pg_engine, case_a) == before

    with Session(pg_engine) as db:
        plan_a = db.scalar(select(InspectionPlan).where(InspectionPlan.case_id == case_a))
        first = InspectionDecision(
            inspection_plan_id=plan_a.id, ordinal=1,
            reference="CASE-A-ROOT", decision_on=date(2026, 11, 10),
            legacy_raw="case A root",
        )
        db.add(first)
        db.commit()
        first_id = first.id
    assert _readiness(api, case_a)["decision_source_id"] == first_id

    # Second entry without an explicit REPLACES predecessor cannot become
    # the authoritative latest Decision even if its ordinal and date are newer.
    with Session(pg_engine) as db:
        plan_a = db.scalar(select(InspectionPlan).where(InspectionPlan.case_id == case_a))
        db.add(InspectionDecision(
            inspection_plan_id=plan_a.id, ordinal=2,
            reference="AMBIGUOUS-FOLLOWUP", decision_on=date(2026, 11, 12),
            legacy_raw="no relation",
        ))
        db.commit()
    unresolved = _readiness(api, case_a)
    assert unresolved["decision_source_id"] is None
    assert "DECISION_REPLACEMENT_LINEAGE_AMBIGUOUS" in unresolved["blocked_reasons"]
    assert "QDKT_LEGAL_ISSUANCE_EVIDENCE_UNPROVEN" in unresolved["blocked_reasons"]
    assert unresolved["ready_to_render"] is False
    assert _readiness(api, case_a, "DRAFT_QDKT")["decision_source_id"] is None
