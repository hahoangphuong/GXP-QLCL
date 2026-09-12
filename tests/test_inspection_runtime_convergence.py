from datetime import date, time

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.auth import AuthenticatedUser
from backend.app.db.models import Base
from backend.app.services.workflow import CaseWorkflowService
from tests.test_phase10_workflow_mutation import build_authenticated_user, seed_case


def test_typed_plan_and_metadata_outcome_contracts_preserve_period_owner():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()
    with Session(engine) as session:
        case_id = seed_case(session)
    with Session(engine) as session:
        user = build_authenticated_user("manager01", "manager")
        plan = service.upsert_inspection_plan(session, case_id=case_id, plan_start_on=None, plan_end_on=None, planning_sheet_name=None, decision_document_hint="legacy hint", decision_reference="QD-12", decision_date=date(2026, 9, 1), reason="typed", user=user)
        assert plan["decision_reference"] == "QD-12"
        outcome = service.upsert_inspection_outcome(session, case_id=case_id, inspected_on=None, inspected_to_on=None, decision_reference=None, bbkt_reference=None, outcome_result="Dat", minutes_recorded_on=date(2026, 9, 2), minutes_recorded_time=time(9, 30), compliance_due_on=date(2026, 10, 1), reason="metadata", user=user)
        assert outcome["inspection_period_state"] is None
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
        final = service.finalize_inspection_outcome(session, case_id=case_id, expected_version=outcome["row_version"], final_evaluation="Dat sau CAPA", reason="final", user=user)
        assert final["outcome_result"] == "Dat" and final["final_evaluation"] == "Dat sau CAPA"
        pct = service.create_approval_submission(session, case_id=case_id, stage="PCT", reference=None, submitted_on=None, submitted_time=None, pct_submission_id=None, reason="pct", user=user)
        completed = service.complete_approval_submission(session, approval_submission_id=pct["approval_submission_id"], expected_version=pct["row_version"], completed_on=date(2026, 9, 3), completed_time=None, reason="complete", user=user)
        ct = service.create_approval_submission(session, case_id=case_id, stage="CT", reference=None, submitted_on=None, submitted_time=None, pct_submission_id=completed["approval_submission_id"], reason="ct", user=user)
        assert (pct["round_no"], ct["round_no"], ct["pct_submission_id"]) == (1, 1, pct["approval_submission_id"])
        with pytest.raises(HTTPException, match="immutable"):
            service.complete_approval_submission(session, approval_submission_id=pct["approval_submission_id"], expected_version=completed["row_version"], completed_on=date(2026, 9, 4), completed_time=None, reason="again", user=user)
