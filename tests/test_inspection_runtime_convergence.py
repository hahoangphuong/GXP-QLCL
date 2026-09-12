from datetime import date, time

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app.auth import AuthenticatedUser
from backend.app.db.enums import CaseState
from backend.app.db.models import Base
from backend.app.db.models.phase1 import CapaCycle, Case, InspectionOutcome, InspectionPlan
from backend.app.services.workflow import CaseWorkflowService
from tests.test_phase10_workflow_mutation import build_authenticated_user, seed_case


def test_typed_plan_and_outcome_metadata_reject_compatibility_writes_and_preserve_history():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()
    with Session(engine) as session:
        case_id = seed_case(session)
    with Session(engine) as session:
        user = build_authenticated_user("manager01", "manager")
        with pytest.raises(HTTPException, match="read-only compatibility"):
            service.upsert_inspection_plan(session, case_id=case_id, plan_start_on=None, plan_end_on=None, planning_sheet_name=None, decision_document_hint="legacy hint", decision_reference="QD-12", decision_date=date(2026, 9, 1), reason="compatibility", user=user)
        plan = service.upsert_inspection_plan(session, case_id=case_id, plan_start_on=None, plan_end_on=None, planning_sheet_name=None, decision_document_hint=None, decision_reference="QD-12", decision_date=date(2026, 9, 1), reason="typed", user=user)
        assert plan["decision_reference"] == "QD-12"
        persisted_plan = session.scalars(select(InspectionPlan).where(InspectionPlan.case_id == case_id)).one()
        assert persisted_plan is not None
        persisted_plan.decision_document_hint = "historical hint"
        session.flush()
        plan = service.upsert_inspection_plan(session, case_id=case_id, expected_version=persisted_plan.row_version, plan_start_on=None, plan_end_on=None, planning_sheet_name=None, decision_document_hint=None, decision_reference="QD-13", decision_date=date(2026, 9, 3), reason="typed update", user=user)
        assert plan["decision_document_hint"] == "historical hint"
        with pytest.raises(HTTPException, match="read-only compatibility"):
            service.upsert_inspection_outcome(session, case_id=case_id, inspected_on=None, inspected_to_on=None, decision_reference="legacy decision", bbkt_reference=None, outcome_result="Dat", reason="compatibility", user=user)
        outcome = service.upsert_inspection_outcome(session, case_id=case_id, inspected_on=None, inspected_to_on=None, decision_reference=None, bbkt_reference=None, outcome_result="Dat", minutes_recorded_on=date(2026, 9, 2), minutes_recorded_time=time(9, 30), compliance_due_on=date(2026, 10, 1), reason="metadata", user=user)
        assert outcome["inspection_period_state"] is None
        persisted_outcome = session.scalars(select(InspectionOutcome).where(InspectionOutcome.case_id == case_id)).one()
        assert persisted_outcome is not None
        persisted_outcome.decision_reference = "historical decision"
        persisted_outcome.bbkt_reference = "historical bbkt"
        session.flush()
        outcome = service.upsert_inspection_outcome(session, case_id=case_id, expected_version=persisted_outcome.row_version, inspected_on=None, inspected_to_on=None, decision_reference=None, bbkt_reference=None, outcome_result="Dat", minutes_recorded_on=date(2026, 9, 2), minutes_recorded_time=time(9, 30), compliance_due_on=date(2026, 10, 1), reason="metadata no overwrite", user=user)
        assert (outcome["decision_reference"], outcome["bbkt_reference"]) == ("historical decision", "historical bbkt")
        with pytest.raises(HTTPException, match="requires a date"):
            service.upsert_inspection_outcome(session, case_id=case_id, expected_version=outcome["row_version"], inspected_on=None, inspected_to_on=None, decision_reference=None, bbkt_reference=None, outcome_result="Dat", minutes_recorded_on=None, minutes_recorded_time=time(9, 30), compliance_due_on=None, reason="bad", user=user)


def test_finalization_and_approval_parent_contracts():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()
    with Session(engine) as session:
        case_id = seed_case(session)
    with Session(engine) as session:
        user = build_authenticated_user("manager01", "manager")
        outcome = service.upsert_inspection_outcome(session, case_id=case_id, inspected_on=None, inspected_to_on=None, decision_reference=None, bbkt_reference=None, outcome_result="Dat", reason="outcome", user=user)
        session.add(CapaCycle(case_id=case_id, round_no=1, status="submitted"))
        session.flush()
        with pytest.raises(HTTPException, match="Latest CAPA cycle must be accepted"):
            service.finalize_inspection_outcome(session, case_id=case_id, expected_version=outcome["row_version"], final_evaluation="Dat sau CAPA", reason="blocked", user=user)
        session.scalars(select(CapaCycle).where(CapaCycle.case_id == case_id)).one().status = "accepted"
        session.flush()
        final = service.finalize_inspection_outcome(session, case_id=case_id, expected_version=outcome["row_version"], final_evaluation="Dat sau CAPA", reason="final", user=user)
        assert final["outcome_result"] == "Dat" and final["final_evaluation"] == "Dat sau CAPA"
        assert service.finalize_inspection_outcome(session, case_id=case_id, expected_version=final["row_version"], final_evaluation="Dat sau CAPA", reason="repeat", user=user)["row_version"] == final["row_version"]
        with pytest.raises(HTTPException, match="Stale inspection_outcome update"):
            service.finalize_inspection_outcome(session, case_id=case_id, expected_version=final["row_version"] - 1, final_evaluation="Dat sau CAPA", reason="stale", user=user)
        with pytest.raises(HTTPException, match="immutable"):
            service.finalize_inspection_outcome(session, case_id=case_id, expected_version=final["row_version"], final_evaluation="Khong dat", reason="different", user=user)
        pct = service.create_approval_submission(session, case_id=case_id, stage="PCT", reference=None, submitted_on=None, submitted_time=None, pct_submission_id=None, reason="pct", user=user)
        completed = service.complete_approval_submission(session, approval_submission_id=pct["approval_submission_id"], expected_version=pct["row_version"], completed_on=date(2026, 9, 3), completed_time=None, reason="complete", user=user)
        ct = service.create_approval_submission(session, case_id=case_id, stage="CT", reference=None, submitted_on=None, submitted_time=None, pct_submission_id=completed["approval_submission_id"], reason="ct", user=user)
        assert (pct["round_no"], ct["round_no"], ct["pct_submission_id"]) == (1, 1, pct["approval_submission_id"])
        with pytest.raises(HTTPException, match="immutable"):
            service.complete_approval_submission(session, approval_submission_id=pct["approval_submission_id"], expected_version=completed["row_version"], completed_on=date(2026, 9, 4), completed_time=None, reason="again", user=user)
        pending = service.create_approval_submission(session, case_id=case_id, stage="PCT", reference=None, submitted_on=None, submitted_time=None, pct_submission_id=None, reason="terminal", user=user)
        case = session.get(Case, case_id)
        assert case is not None
        case.state = CaseState.CLOSED
        session.flush()
        with pytest.raises(HTTPException, match="terminal state closed"):
            service.complete_approval_submission(session, approval_submission_id=pending["approval_submission_id"], expected_version=pending["row_version"], completed_on=date(2026, 9, 4), completed_time=None, reason="blocked", user=user)
