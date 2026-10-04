from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app.auth import AuthenticatedUser
from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import Case, CaseApplication, InspectionOutcome, InspectionPeriodSegment, InspectionPlan, Site
from backend.app.read_models import CaseApplicationUpsertRequest, InspectionPeriodSegmentsUpsertRequest
from backend.app.services.workflow import CaseWorkflowService


def _user() -> AuthenticatedUser:
    return AuthenticatedUser(
        username="a3.operator",
        auth_mode="header_stub",
        role_codes=("manager",),
        permissions=frozenset({"case.edit", "inspection.edit", "capa.edit", "capa.assess"}),
    )


def _case(session: Session) -> str:
    site = Site(company_id="company-a3", site_name="A3 Site")
    session.add(site)
    session.flush()
    row = Case(site_id=site.id, gxp_type="GMP", state=CaseState.DRAFT)
    session.add(row)
    session.commit()
    return row.id


def test_plan_omission_preserves_canonical_decision_and_explicit_clear_is_distinct() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()
    with Session(engine) as session:
        case_id = _case(session)
        plan = InspectionPlan(case_id=case_id, decision_reference="QD-123", decision_date=date(2026, 10, 1))
        session.add(plan)
        session.commit()
        service.upsert_inspection_plan(
            session, case_id=case_id, expected_version=plan.row_version,
            plan_start_on=date(2026, 10, 2), plan_end_on=None, planning_sheet_name=None,
            decision_document_hint=None, decision_reference=None, decision_date=None,
            reason=None, user=_user(), fields_set={"plan_start_on"},
        )
        session.commit()
    with Session(engine) as session:
        plan = session.scalar(select(InspectionPlan))
        assert plan is not None
        assert (plan.decision_reference, plan.decision_date) == ("QD-123", date(2026, 10, 1))
        service.upsert_inspection_plan(
            session, case_id=case_id, expected_version=plan.row_version,
            plan_start_on=None, plan_end_on=None, planning_sheet_name=None,
            decision_document_hint=None, decision_reference=None, decision_date=None,
            reason=None, user=_user(), fields_set={"decision_reference", "decision_date"},
        )
        assert plan.decision_reference is None and plan.decision_date is None


def test_http_contract_rejects_compatibility_fields_and_outcome_omission_preserves_typed_values() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()
    with Session(engine) as session:
        case_id = _case(session)
        outcome = InspectionOutcome(
            case_id=case_id,
            minutes_recorded_on=date(2026, 10, 2),
            compliance_due_on=date(2026, 11, 2),
        )
        session.add(outcome)
        session.commit()
        with pytest.raises(HTTPException, match="read-only compatibility"):
            service.upsert_inspection_outcome(
                session, case_id=case_id, expected_version=outcome.row_version,
                inspected_on=None, inspected_to_on=None, decision_reference=None, bbkt_reference=None,
                outcome_result=None, reason=None, user=_user(), fields_set={"bbkt_reference"},
            )
        service.upsert_inspection_outcome(
            session, case_id=case_id, expected_version=outcome.row_version,
            inspected_on=None, inspected_to_on=None, decision_reference=None, bbkt_reference=None,
            outcome_result="Đạt", reason=None, user=_user(), fields_set={"outcome_result"},
        )
        assert outcome.minutes_recorded_on == date(2026, 10, 2)
        assert outcome.compliance_due_on == date(2026, 11, 2)


def test_direct_application_compatibility_omission_preserves_historical_reference() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()
    with Session(engine) as session:
        case_id = _case(session)
        session.add(CaseApplication(case_id=case_id, dossier_code="OLD", dossier_reference="LEGACY-KEEP"))
        session.commit()
        result = service.upsert_case_application(
            session, case_id=case_id, submitted_on=None, dossier_code="NEW", dossier_reference=None,
            applicant_name=None, reason=None, user=_user(), fields_set=None,
        )
        assert result["dossier_reference"] == "LEGACY-KEEP"
        with pytest.raises(HTTPException, match="read-only compatibility"):
            service.upsert_case_application(
                session, case_id=case_id, expected_version=result["row_version"], submitted_on=None,
                dossier_code=None, dossier_reference="NEW-COMPAT", applicant_name=None,
                reason=None, user=_user(), fields_set=None,
            )
        with pytest.raises(HTTPException, match="read-only compatibility"):
            service.upsert_case_application(
                session, case_id=case_id, expected_version=result["row_version"], submitted_on=None,
                dossier_code=None, dossier_reference=None, applicant_name=None,
                reason=None, user=_user(), fields_set={"dossier_reference"},
            )


def test_request_models_keep_explicit_compatibility_null_and_period_writes_id_free() -> None:
    explicit_null = CaseApplicationUpsertRequest.model_validate({"dossier_reference": None})
    assert explicit_null.model_fields_set == {"dossier_reference"}
    period = InspectionPeriodSegmentsUpsertRequest.model_validate({
        "expected_version": 4,
        "segments": [{"ordinal": 1, "started_on": "2026-10-01", "ended_on": "2026-10-02"}],
    })
    assert period.segments[0].model_dump() == {
        "ordinal": 1,
        "started_on": date(2026, 10, 1),
        "ended_on": date(2026, 10, 2),
    }


def test_period_segments_are_ordered_and_never_flatten_multiple_visits() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()
    with Session(engine) as session:
        case_id = _case(session)
        outcome = InspectionOutcome(case_id=case_id, inspection_period_state="KNOWN")
        session.add(outcome)
        session.commit()
        service.upsert_inspection_period_segments(
            session, case_id=case_id, expected_version=outcome.row_version, user=_user(), reason=None,
            segments=[
                {"ordinal": 1, "started_on": date(2026, 10, 1), "ended_on": date(2026, 10, 2)},
                {"ordinal": 2, "started_on": date(2026, 10, 10), "ended_on": date(2026, 10, 11)},
            ],
        )
        session.commit()
    with Session(engine) as session:
        outcome = session.scalar(select(InspectionOutcome))
        assert outcome is not None
        assert (outcome.inspected_on, outcome.inspected_to_on) == (None, None)
        assert [item.ordinal for item in session.scalars(select(InspectionPeriodSegment).order_by(InspectionPeriodSegment.ordinal))] == [1, 2]


def test_period_segments_reject_invalid_dates_and_source_owned_states() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()
    with Session(engine) as session:
        case_id = _case(session)
        outcome = InspectionOutcome(case_id=case_id, inspection_period_state="KNOWN")
        session.add(outcome)
        session.commit()
        with pytest.raises(HTTPException, match="start date"):
            service.upsert_inspection_period_segments(
                session, case_id=case_id, expected_version=outcome.row_version, user=_user(), reason=None,
                segments=[{"ordinal": 1, "started_on": date(2026, 10, 2), "ended_on": date(2026, 10, 1)}],
            )
        outcome.inspection_period_state = "UNRESOLVED"
        session.flush()
        with pytest.raises(HTTPException, match="source-owned"):
            service.upsert_inspection_period_segments(
                session, case_id=case_id, expected_version=outcome.row_version, user=_user(), reason=None,
                segments=[{"ordinal": 1, "started_on": date(2026, 10, 1), "ended_on": date(2026, 10, 2)}],
            )


def test_a3_frontend_mutation_owners_do_not_reintroduce_compatibility_or_readiness_logic() -> None:
    root = Path("frontend/src/features/search")
    application = (root / "CaseApplicationWorkspace.tsx").read_text(encoding="utf-8")
    inspection = (root / "CaseInspectionWorkspace.tsx").read_text(encoding="utf-8")
    remediation = (root / "CaseRemediationWorkspace.tsx").read_text(encoding="utf-8")
    approval = (root / "CaseApprovalWorkspace.tsx").read_text(encoding="utf-8")
    transitions = (root / "CaseLifecycleActions.tsx").read_text(encoding="utf-8")

    assert "dossier_reference" not in application
    assert 'setEditingField("decision_document_hint")' not in inspection
    assert "inspected_on" not in inspection and "inspected_to_on" not in inspection
    assert 'inspection_period_state !== "KNOWN"' in inspection
    assert "cycle.status ===" not in remediation
    assert "approval_actions ?? []" in approval
    assert 'stage === "CT" && !parentId' in approval
    assert "target_state: action.target_state" in transitions
    assert "ALLOWED_CASE_TRANSITIONS" not in transitions
    assert ".split(" not in transitions and ".replace(" not in transitions
