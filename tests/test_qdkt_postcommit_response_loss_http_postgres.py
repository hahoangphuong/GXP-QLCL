"""Process B recovery after a lost HTTP response *after* committed POST.

Disposable migrated PostgreSQL + real ASGI router. No real TCP/network chaos
or Google OIDC claim: failure is injected at the ASGI response send boundary.
"""
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.db.enums import InspectionEventType
from backend.app.db.models.phase1 import (
    AuditEvent, InspectionDecision, InspectionEvent, InspectionPlan,
    QdKtIssuedRoster, QdKtIssuedRosterMember,
)
from test_canonical_http_workflow_postgres import api, ok
from test_canonical_workflow_postgres import (
    DAY, SERVICE, pg_engine, seed, write,
)


def test_qdkt_issued_post_commit_response_loss_recovers_exactly_once(pg_engine, api):
    case_id, _ = seed(pg_engine)
    plan = write(
        pg_engine, SERVICE.upsert_inspection_plan, case_id=case_id,
        plan_start_on=DAY, plan_end_on=DAY,
        planning_sheet_name="Synthetic unknown-outcome recovery",
        decision_document_hint=None, reason="Prepare synthetic QDKT plan",
    )
    decision_id = str(uuid4())
    payload = {
        "decision_id": decision_id,
        "expected_plan_version": plan["row_version"],
        "reference": "POSTCOMMIT-DISCONNECT-QDKT",
        "decision_on": DAY.isoformat(),
        "source_text": "Synthetic externally approved source text",
        "relation_type": "INITIAL",
        "related_decision_id": None,
        "external_approval_confirmed": True,
        "approval_basis": "Synthetic external operator approval",
        "team_confirmed": True,
        "roster_source": "USER_ENTERED",
        "members": [{
            "source_member_id": str(uuid4()),
            "display_name": "Synthetic inspector",
            "role_code": "LEADER",
            "job_title": "Inspector",
        }],
        "reason": "Synthetic recorded source",
    }
    path = f"/cases/{case_id}/qdkt-issued-decisions"
    exact_get = f"{path}/{decision_id}"

    # POST commits before the ASGI reply is sent. Simulate a lost reply, not
    # a failed mutation; caller sees no acknowledged success.
    with pytest.raises(ConnectionError, match="after commit"):
        api("POST", path, payload, disconnect_on_response=True)

    # Recover with exact Case+UUID, without initiating another write.
    recovered = ok(api, "GET", exact_get)
    assert recovered["case_id"] == case_id
    assert recovered["decision_id"] == decision_id
    assert recovered["reference"] == payload["reference"]
    assert recovered["source_text"] == payload["source_text"]
    assert recovered["relation_type"] == "INITIAL"
    assert recovered["related_decision_id"] is None
    assert recovered["operator_attestation_recorded"] is True
    assert len(recovered["members"]) == 1
    assert recovered["members"][0]["display_name"] == payload["members"][0]["display_name"]
    assert recovered["legal_issuance_verified"] is False
    assert recovered["ready_to_render"] is False

    def counts_and_version():
        with Session(pg_engine) as session:
            return (
                session.scalar(select(func.count()).select_from(InspectionDecision)
                    .join(InspectionPlan, InspectionDecision.inspection_plan_id == InspectionPlan.id)
                    .where(InspectionPlan.case_id == case_id)),
                session.scalar(select(func.count()).select_from(QdKtIssuedRoster)
                    .where(QdKtIssuedRoster.inspection_decision_id == decision_id)),
                session.scalar(select(func.count()).select_from(QdKtIssuedRosterMember)
                    .join(QdKtIssuedRoster, QdKtIssuedRosterMember.issued_roster_id == QdKtIssuedRoster.id)
                    .where(QdKtIssuedRoster.inspection_decision_id == decision_id)),
                session.scalar(select(func.count()).select_from(InspectionEvent)
                    .where(InspectionEvent.case_id == case_id,
                           InspectionEvent.event_type == InspectionEventType.DECISION_ISSUED)),
                session.scalar(select(func.count()).select_from(AuditEvent)
                    .where(AuditEvent.entity_type == "inspection_decision",
                           AuditEvent.entity_id == decision_id,
                           AuditEvent.action == "qdkt_issued_decision.record")),
                session.scalar(select(InspectionPlan.row_version).where(InspectionPlan.case_id == case_id)),
            )

    before = counts_and_version()
    assert before[:5] == (1, 1, 1, 1, 1)
    assert before[5] > payload["expected_plan_version"]
    # Same id and *current* plan version is still a conflict. This is a
    # readback locator, not permission for another issuing event.
    status, _ = api("POST", path, {**payload, "expected_plan_version": before[5]})
    assert status == 409
    assert counts_and_version() == before
    assert ok(api, "GET", exact_get) == recovered
