"""QĐKT Process B recovery when its PostgreSQL session backend is killed.

This is isolated migrated PostgreSQL only (canonical fixture refuses remote
databases). We terminate the *specific* application connection, never restart
the database server or affect production. These two probes do NOT establish
atomicity of an ambiguous in-flight COMMIT or PostgreSQL HA failover.
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import backend.app.api.routers.workflow as workflow_router
from backend.app.db.enums import InspectionEventType
from backend.app.db.models.phase1 import (
    AuditEvent, InspectionDecision, InspectionEvent, InspectionPlan,
    QdKtIssuedRoster, QdKtIssuedRosterMember,
)
from test_canonical_http_workflow_postgres import api, ok
from test_canonical_workflow_postgres import DAY, SERVICE, pg_engine, seed, write


@pytest.mark.parametrize("phase", ["precommit", "postcommit"])
def test_qdkt_postgres_session_backend_termination_recovery(
    pg_engine, api, monkeypatch, phase,
):
    """Real PG backend death on the write connection; recover via new GET."""
    case_id, _ = seed(pg_engine)
    plan = write(
        pg_engine, SERVICE.upsert_inspection_plan,
        case_id=case_id, plan_start_on=DAY, plan_end_on=DAY,
        planning_sheet_name="Synthetic terminated PostgreSQL connection",
        decision_document_hint=None, reason="Synthetic QĐKT plan",
    )
    decision_id = str(uuid4())
    request = {
        "decision_id": decision_id,
        "expected_plan_version": plan["row_version"],
        "reference": "SYNTH-PG-BACKEND-LOSS-" + phase,
        "decision_on": DAY.isoformat(),
        "source_text": "Synthetic externally approved decision source",
        "relation_type": "INITIAL", "related_decision_id": None,
        "external_approval_confirmed": True,
        "approval_basis": "Synthetic external operator approval",
        "team_confirmed": True, "roster_source": "USER_ENTERED",
        "members": [{
            "source_member_id": str(uuid4()),
            "display_name": "Synthetic leader", "role_code": "LEADER",
            "job_title": "Inspector",
        }],
        "reason": "Synthetic approved-decision recording",
    }
    path = f"/cases/{case_id}/qdkt-issued-decisions"
    exact = f"{path}/{decision_id}"

    def state():
        with Session(pg_engine) as db:
            return (
                db.scalar(select(func.count()).select_from(InspectionDecision)
                    .where(InspectionDecision.id == decision_id)),
                db.scalar(select(func.count()).select_from(QdKtIssuedRoster)
                    .where(QdKtIssuedRoster.inspection_decision_id == decision_id)),
                db.scalar(select(func.count()).select_from(QdKtIssuedRosterMember)
                    .join(QdKtIssuedRoster,
                          QdKtIssuedRosterMember.issued_roster_id == QdKtIssuedRoster.id)
                    .where(QdKtIssuedRoster.inspection_decision_id == decision_id)),
                db.scalar(select(func.count()).select_from(AuditEvent)
                    .where(AuditEvent.entity_type == "inspection_decision",
                           AuditEvent.entity_id == decision_id,
                           AuditEvent.action == "qdkt_issued_decision.record")),
                db.scalar(select(func.count()).select_from(InspectionEvent)
                    .where(InspectionEvent.case_id == case_id,
                           InspectionEvent.event_type == InspectionEventType.DECISION_ISSUED)),
                db.scalar(select(InspectionPlan.row_version).where(InspectionPlan.case_id == case_id)),
            )

    def terminate_this_backend(session):
        # The target PID comes from the real application transaction. The
        # killer is an independent local connection using the disposable
        # schema's own test engine. No blanket backend termination is allowed.
        pid = session.connection().exec_driver_sql(
            "SELECT pg_backend_pid()"
        ).scalar_one()
        with pg_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as killer:
            own_pid = killer.exec_driver_sql("SELECT pg_backend_pid()").scalar_one()
            assert pid != own_pid
            assert killer.exec_driver_sql(
                "SELECT pg_terminate_backend(%s)", (pid,)
            ).scalar_one() is True

    original_commit = workflow_router.commit_or_409

    def terminate_at_commit(session):
        if phase == "precommit":
            # Service has already flushed decision/roster/audit under its
            # outer transaction. The real DB connection is then killed
            # before any COMMIT; PostgreSQL must roll it all back.
            terminate_this_backend(session)
            original_commit(session)  # raises: server closed connection
        else:
            # Distinct, acknowledged commit boundary: do NOT claim an
            # ambiguous in-flight commit race.
            original_commit(session)
            terminate_this_backend(session)
            # A lost handler response is an unknown outcome to the client.
            raise ConnectionError("committed but PostgreSQL backend lost")

    baseline = state()
    assert baseline[:5] == (0, 0, 0, 0, 0)
    with monkeypatch.context() as patch:
        patch.setattr(workflow_router, "commit_or_409", terminate_at_commit)
        try:
            status, response = api("POST", path, request)
        except Exception:
            # Failure may surface from SQLAlchemy, the dependency rollback,
            # or the ASGI middleware; none may acknowledge HTTP 200.
            pass
        else:
            assert status >= 500, response

    after = state()
    if phase == "precommit":
        assert after == baseline
        assert api("GET", exact)[0] == 404
        accepted = ok(api, "POST", path, request)
        assert accepted["decision_id"] == decision_id
        assert accepted["relation_type"] == "INITIAL"
    else:
        assert after[:5] == (1, 1, 1, 1, 1)
        assert after[5] > baseline[5]
        canonical = ok(api, "GET", exact)
        assert canonical["decision_id"] == decision_id
        assert canonical["case_id"] == case_id
        assert canonical["relation_type"] == "INITIAL"
        assert canonical["reference"] == request["reference"]
        assert canonical["source_text"] == request["source_text"]
        assert canonical["operator_attestation_recorded"] is True
        assert len(canonical["members"]) == 1
        assert canonical["legal_issuance_verified"] is False
        assert canonical["ready_to_render"] is False
        # An already-consumed request UUID may not append a second event.
        status, _ = api("POST", path, {
            **request, "expected_plan_version": after[5],
        })
        assert status == 409
        assert state() == after

    final = state()
    assert final[:5] == (1, 1, 1, 1, 1)
    assert final[5] > baseline[5]
    recovered = ok(api, "GET", exact)
    assert recovered["relation_type"] == "INITIAL"
    assert recovered["operator_attestation_recorded"] is True
