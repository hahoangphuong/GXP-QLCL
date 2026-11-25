"""QĐKT Process B: fail before commit, roll back; same UUID can then succeed.

Uses the actual ASGI endpoint and disposable migrated PostgreSQL. The
injected failure is at the API transaction boundary, not a network claim.
"""
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import backend.app.api.routers.workflow as workflow_router
from backend.app.db.enums import InspectionEventType
from backend.app.db.models.phase1 import (
    AuditEvent, InspectionDecision, InspectionEvent, InspectionPlan, QdKtIssuedRoster,
)
from test_canonical_http_workflow_postgres import api, ok
from test_canonical_workflow_postgres import DAY, SERVICE, pg_engine, seed, write


def test_qdkt_precommit_failure_rolls_back_and_allows_same_uuid_once(pg_engine, api, monkeypatch):
    case_id, _ = seed(pg_engine)
    plan = write(
        pg_engine, SERVICE.upsert_inspection_plan, case_id=case_id,
        plan_start_on=DAY, plan_end_on=DAY,
        planning_sheet_name="Synthetic precommit failure",
        decision_document_hint=None, reason="Synthetic QDKT plan",
    )
    decision_id = str(uuid4())
    request = {
        "decision_id": decision_id,
        "expected_plan_version": plan["row_version"],
        "reference": "PRECOMMIT-ROLLBACK-QDKT",
        "decision_on": DAY.isoformat(),
        "source_text": "Synthetic externally approved source",
        "relation_type": "INITIAL",
        "related_decision_id": None,
        "external_approval_confirmed": True,
        "approval_basis": "Synthetic external approval attestation",
        "team_confirmed": True,
        "roster_source": "USER_ENTERED",
        "members": [{
            "source_member_id": str(uuid4()), "display_name": "Synthetic leader",
            "role_code": "LEADER", "job_title": "Inspector",
        }],
        "reason": "Synthetic operator attestation",
    }

    def db_state():
        with Session(pg_engine) as db:
            return (
                db.scalar(select(func.count()).select_from(InspectionDecision)
                    .join(InspectionPlan, InspectionDecision.inspection_plan_id == InspectionPlan.id)
                    .where(InspectionPlan.case_id == case_id)),
                db.scalar(select(func.count()).select_from(QdKtIssuedRoster)
                    .where(QdKtIssuedRoster.inspection_decision_id == decision_id)),
                db.scalar(select(func.count()).select_from(AuditEvent)
                    .where(AuditEvent.entity_type == "inspection_decision",
                           AuditEvent.entity_id == decision_id,
                           AuditEvent.action == "qdkt_issued_decision.record")),
                db.scalar(select(func.count()).select_from(InspectionEvent)
                    .where(InspectionEvent.case_id == case_id,
                           InspectionEvent.event_type == InspectionEventType.DECISION_ISSUED)),
                db.scalar(select(InspectionPlan.row_version)
                    .where(InspectionPlan.case_id == case_id)),
            )

    before = db_state()
    assert before[:4] == (0, 0, 0, 0)
    path = f"/cases/{case_id}/qdkt-issued-decisions"
    original_commit = workflow_router.commit_or_409

    def fail_before_commit(session):
        assert session.in_transaction()
        raise RuntimeError("synthetic failure before transaction commit")

    # The service may flush inside its nested savepoint, but request teardown
    # must roll back the outer transaction after the commit boundary fails.
    with monkeypatch.context() as patch:
        patch.setattr(workflow_router, "commit_or_409", fail_before_commit)
        with pytest.raises(RuntimeError, match="before transaction commit"):
            api("POST", path, request)

    assert db_state() == before
    assert api("GET", f"{path}/{decision_id}")[0] == 404

    # The ID was not consumed by the failed transaction. A legitimate submit
    # with unchanged expected plan version commits exactly once.
    assert workflow_router.commit_or_409 is original_commit
    accepted = ok(api, "POST", path, request)
    assert accepted["decision_id"] == decision_id
    assert accepted["relation_type"] == "INITIAL"
    assert db_state()[:4] == (1, 1, 1, 1)
    assert db_state()[4] > before[4]
    recovered = ok(api, "GET", f"{path}/{decision_id}")
    assert recovered["relation_type"] == "INITIAL"
    assert recovered["operator_attestation_recorded"] is True
    assert recovered["legal_issuance_verified"] is False
    assert recovered["ready_to_render"] is False
