"""Canonical Initial Case operator milestone boundaries on isolated PostgreSQL.

These HTTP mutations persist genuine application, assessment and plan rows.
They do NOT generate actual signed source documents or an approved QĐKT.
"""
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.db.enums import InspectionEventType
from backend.app.db.models.phase1 import (
    AuditEvent, Case, CaseApplication, CaseAssessment, Company,
    InspectionEvent, InspectionPlan, ProductionLine, Site,
)
from test_canonical_http_workflow_postgres import api, ok, transition, workspace
from test_canonical_workflow_postgres import pg_engine


def events(engine, case_id):
    with Session(engine) as db:
        return list(db.scalars(
            select(InspectionEvent.event_type)
            .where(InspectionEvent.case_id == case_id)
            .order_by(InspectionEvent.created_at, InspectionEvent.id)
        ))


def stage_counts(engine, case_id):
    with Session(engine) as db:
        return {
            model.__tablename__: db.scalar(
                select(func.count()).select_from(model)
                .where(model.case_id == case_id)
            )
            for model in (CaseApplication, CaseAssessment, InspectionPlan, InspectionEvent)
        } | {
            "case_audits": db.scalar(select(func.count()).select_from(AuditEvent)
                                     .where(AuditEvent.entity_id == case_id))
        }


def test_initial_case_real_application_assessment_plan_milestone_owners(pg_engine, api):
    """No milestone from metadata-only PUT or Case transition; owner facts only."""
    company_id, site_id, line_id, case_id = (str(uuid4()) for _ in range(4))
    ok(api, "POST", "/companies", {
        "company_id": company_id, "legal_name": "Synthetic operator milestone Company",
        "legal_address": "Synthetic legal address", "reason": "Test setup",
    })
    ok(api, "POST", f"/companies/{company_id}/sites", {
        "site_id": site_id, "site_name": "Synthetic milestone Site",
        "site_address": "Synthetic factory", "reason": "Test setup",
    })
    ok(api, "POST", f"/sites/{site_id}/production-lines", {
        "production_line_id": line_id, "code": "L1", "effective_from": "2026-01-01",
        "physical_identity_evidence_reference": "SYNTHETIC-MILESTONE-SOURCE",
        "reason": "Physical line verified",
    })
    created = ok(api, "POST", f"/sites/{site_id}/inspection-cases/initial", {
        "case_id": case_id, "gxp_type": "GMP", "production_line_id": line_id,
        "inspection_type": "Mới", "applicable_standard": "WHO-GMP",
        "reason": "Initial Case from catalog",
    })
    assert created["state"] == "draft" and created["row_version"] == 1
    assert events(pg_engine, case_id) == []

    # The dossier metadata does not constitute a submission.
    application = ok(api, "PUT", f"/cases/{case_id}/application", {
        "dossier_code": "SYNTH-REGISTRATION", "applicant_name": "Synthetic applicant",
        "reason": "Draft metadata",
    })
    assert application["case_id"] == case_id
    assert application["submitted_on"] is None
    assert application["inspection_event_id"] is None
    assert events(pg_engine, case_id) == []
    baseline = stage_counts(pg_engine, case_id)
    # A known stage requires the exact version, and a reader never mutates it.
    status, _ = api("PUT", f"/cases/{case_id}/application", {
        "dossier_code": "Replay without version",
    })
    assert status == 409
    status, _ = api("PUT", f"/cases/{case_id}/application", {
        "expected_version": application["row_version"] + 1,
        "dossier_code": "Stale applicant",
    })
    assert status == 409
    status, _ = api("PUT", f"/cases/{case_id}/application", {
        "expected_version": application["row_version"],
        "dossier_code": "Reader cannot mutate",
    }, role="reader")
    assert status == 403
    assert stage_counts(pg_engine, case_id) == baseline

    submitted = ok(api, "PUT", f"/cases/{case_id}/application", {
        "expected_version": application["row_version"],
        "submitted_on": "2026-10-01T08:00:00+07:00",
        "reason": "Explicit operator submission",
    })
    assert submitted["dossier_code"] == application["dossier_code"]
    assert submitted["inspection_event_id"] is not None
    assert events(pg_engine, case_id) == [InspectionEventType.APPLICATION_SUBMITTED]
    assert workspace(api, case_id)["application"]["dossier_code"] == "SYNTH-REGISTRATION"
    assert workspace(api, case_id)["case_summary"]["state"] == "draft"
    transition(api, case_id, "application_received")
    assert events(pg_engine, case_id) == [InspectionEventType.APPLICATION_SUBMITTED]

    # Assessment notes alone do not record the milestone.
    assessment = ok(api, "PUT", f"/cases/{case_id}/assessment", {
        "notes": "Assessment drafting, not completed",
    })
    assert assessment["inspection_event_id"] is None
    assert events(pg_engine, case_id) == [InspectionEventType.APPLICATION_SUBMITTED]
    final_assessment = ok(api, "PUT", f"/cases/{case_id}/assessment", {
        "expected_version": assessment["row_version"],
        "assessed_on": "2026-10-02T09:00:00+07:00",
        "assessor_name": "Synthetic assessor",
        "assessment_result": "Acceptable to plan",
        "reason": "Explicit assessment milestone",
    })
    assert final_assessment["inspection_event_id"] is not None
    assert final_assessment["notes"] == assessment["notes"]
    assert events(pg_engine, case_id) == [
        InspectionEventType.APPLICATION_SUBMITTED,
        InspectionEventType.ASSESSMENT_COMPLETED,
    ]
    with Session(pg_engine) as db:
        row = db.scalar(select(CaseAssessment).where(CaseAssessment.case_id == case_id))
        assert row is not None and row.assessor_name == "Synthetic assessor"
        assert row.notes == "Assessment drafting, not completed"
    transition(api, case_id, "under_assessment")

    # Plan drafting has blank QĐKT fields; scheduling creates the plan milestone
    # but not an approved / issued decision.
    plan = ok(api, "PUT", f"/cases/{case_id}/plan", {
        "planning_sheet_name": "Synthetic KHKT working draft",
    })
    assert plan["decision_reference"] is None
    assert plan["decision_date"] is None
    assert plan["inspection_event_id"] is None
    assert len(events(pg_engine, case_id)) == 2
    before_invalid = stage_counts(pg_engine, case_id)
    status, _ = api("PUT", f"/cases/{case_id}/plan", {
        "expected_version": plan["row_version"],
        "plan_end_on": "2026-10-01",
    })
    assert status == 422
    assert stage_counts(pg_engine, case_id) == before_invalid
    scheduled = ok(api, "PUT", f"/cases/{case_id}/plan", {
        "expected_version": plan["row_version"],
        "plan_start_on": "2026-10-05",
        "plan_end_on": "2026-10-06",
        "reason": "Explicit schedule recorded",
    })
    assert scheduled["inspection_event_id"] is not None
    assert scheduled["decision_reference"] is None
    assert scheduled["decision_date"] is None
    assert events(pg_engine, case_id)[-1] == InspectionEventType.PLAN_CREATED
    transition(api, case_id, "planned")
    assert workspace(api, case_id)["inspection"]["plan_decision_reference"] is None

    # Only explicit user-entered decision fields yield this compatibility
    # event. This does not create an approved QĐKT document.
    decided = ok(api, "PUT", f"/cases/{case_id}/plan", {
        "expected_version": scheduled["row_version"],
        "decision_reference": "SYNTHETIC-QDKT-REFERENCE",
        "decision_date": "2026-10-04",
        "reason": "Explicitly recorded source reference",
    })
    assert decided["inspection_event_id"] is not None
    assert decided["decision_reference"] == "SYNTHETIC-QDKT-REFERENCE"
    assert [item.value for item in events(pg_engine, case_id)] == [
        "application_submitted", "assessment_completed", "plan_created", "decision_issued",
    ]
    readback = workspace(api, case_id)
    assert readback["inspection"]["plan_decision_reference"] == decided["decision_reference"]
    assert str(readback["inspection"]["plan_decision_date"]) == "2026-10-04"
    transition(api, case_id, "decision_issued")
    assert len(events(pg_engine, case_id)) == 4

    with Session(pg_engine) as db:
        case = db.get(Case, case_id)
        assert case.site_id == site_id and case.production_line_id == line_id
        assert case.legacy_inspection_id is None
        assert db.scalar(select(func.count()).select_from(CaseApplication)
                         .where(CaseApplication.case_id == case_id)) == 1
        assert db.scalar(select(func.count()).select_from(CaseAssessment)
                         .where(CaseAssessment.case_id == case_id)) == 1
        assert db.scalar(select(func.count()).select_from(InspectionPlan)
                         .where(InspectionPlan.case_id == case_id)) == 1
        # Stage writes have separate audit records from synthetic transitions.
        for action in ("case_application.upsert", "case_assessment.upsert", "inspection_plan.upsert"):
            assert db.scalar(select(func.count()).select_from(AuditEvent)
                             .where(AuditEvent.entity_id == case_id,
                                    AuditEvent.action == action)) >= 2
