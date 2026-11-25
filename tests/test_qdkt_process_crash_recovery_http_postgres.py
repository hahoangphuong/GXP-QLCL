"""Prove QĐKT recovery after an actual Uvicorn process exits at COMMIT.

Both phases use loopback HTTP, isolated migrated PostgreSQL and a freshly
started server process. Not a DB crash, real OIDC or multi-node failover.
"""
from __future__ import annotations

import http.client
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from time import monotonic, sleep
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.db.enums import InspectionEventType
from backend.app.db.models.phase1 import (
    AuditEvent, InspectionDecision, InspectionEvent, InspectionPlan,
    QdKtIssuedRoster, QdKtIssuedRosterMember,
)
from test_canonical_workflow_postgres import DAY, SERVICE, pg_engine, seed, write


def _http(port, method, path, body=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=8)
    headers = {"X-Auth-Role": "admin", "X-Auth-User": "qdkt-crash-synthetic"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    try:
        connection.request(
            method, path,
            body=None if body is None else json.dumps(body).encode(),
            headers=headers,
        )
        response = connection.getresponse()
        raw = response.read()
        return response.status, json.loads(raw) if raw else None
    finally:
        connection.close()


def _start_worker(engine, mode):
    # This helper never connects to or serves a user-supplied remote database.
    # pg_engine itself is restricted to a disposable local migrated schema.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as available:
        available.bind(("127.0.0.1", 0))
        port = available.getsockname()[1]
    env = {
        **os.environ,
        "DATABASE_URL": engine.url.render_as_string(hide_password=False),
        "GXP_CANONICAL_WORKFLOW_POSTGRES": "1",
        "GXP_QDKT_CRASH_TEST": "1",
        "GXP_QDKT_CRASH_MODE": mode,
        "AUTH_MODE": "header_stub",
        "APP_ENV": "development",
        "PYTHONUNBUFFERED": "1",
    }
    worker = subprocess.Popen(
        [sys.executable, "-m", "uvicorn",
         "tools.qdkt_process_crash_fixture_app:app", "--host", "127.0.0.1",
         "--port", str(port), "--log-level", "error"],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = monotonic() + 20
        while monotonic() < deadline:
            assert worker.poll() is None, f"Uvicorn worker exited early: {worker.returncode}"
            try:
                status, _ = _http(port, "GET", "/openapi.json")
                if status == 200:
                    return worker, port
            except (ConnectionError, OSError, TimeoutError):
                sleep(0.05)
        raise AssertionError("Uvicorn process did not become ready")
    except BaseException:
        _stop_worker(worker)
        raise


def _stop_worker(worker):
    if worker.poll() is None:
        worker.terminate()
        try:
            worker.wait(timeout=8)
        except subprocess.TimeoutExpired:
            worker.kill()
            worker.wait(timeout=8)


@pytest.mark.parametrize("crash_phase,expected_exit", [
    ("precommit", 74),
    ("postcommit", 73),
])
def test_qdkt_process_crash_at_commit_boundary_exact_recovery(
    pg_engine, crash_phase, expected_exit,
):
    case_id, _ = seed(pg_engine)
    plan = write(
        pg_engine, SERVICE.upsert_inspection_plan,
        case_id=case_id, plan_start_on=DAY, plan_end_on=DAY,
        planning_sheet_name="Disposable process death probe",
        decision_document_hint=None, reason="Synthetic plan",
    )
    decision_id = str(uuid4())
    request = {
        "decision_id": decision_id,
        "expected_plan_version": plan["row_version"],
        "reference": "SYNTH-CRASH-" + crash_phase,
        "decision_on": DAY.isoformat(),
        "source_text": "Synthetic externally approved QDKT text",
        "relation_type": "INITIAL",
        "related_decision_id": None,
        "external_approval_confirmed": True,
        "approval_basis": "Synthetic external decision approval",
        "team_confirmed": True,
        "roster_source": "USER_ENTERED",
        "members": [{
            "source_member_id": str(uuid4()),
            "display_name": "Synthetic inspector",
            "role_code": "LEADER",
            "job_title": "Inspector",
        }],
        "reason": "Synthetic QDKT attestation",
    }
    post = f"/cases/{case_id}/qdkt-issued-decisions"
    get = f"{post}/{decision_id}"

    def rows():
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
                db.scalar(select(InspectionPlan.row_version)
                    .where(InspectionPlan.case_id == case_id)),
            )

    before = rows()
    assert before[:5] == (0, 0, 0, 0, 0)
    worker, port = _start_worker(pg_engine, crash_phase)
    try:
        # The worker terminates with a known exit code inside the HTTP
        # transaction handler; the client must not receive a success body.
        with pytest.raises((http.client.RemoteDisconnected, ConnectionResetError,
                            ConnectionAbortedError, BrokenPipeError)):
            _http(port, "POST", post, request)
        assert worker.wait(timeout=10) == expected_exit
    finally:
        _stop_worker(worker)

    after_crash = rows()
    if crash_phase == "precommit":
        assert after_crash == before
    else:
        assert after_crash[:5] == (1, 1, 1, 1, 1)
        assert after_crash[5] > before[5]

    # A *different real Uvicorn process* owns canonical recovery.
    recovery_worker, recovery_port = _start_worker(pg_engine, "recovery")
    try:
        status, recovered = _http(recovery_port, "GET", get)
        if crash_phase == "precommit":
            assert status == 404
            assert rows() == before
            response, accepted = _http(recovery_port, "POST", post, request)
            assert response == 200, accepted
            assert accepted["decision_id"] == decision_id
            assert accepted["relation_type"] == "INITIAL"
        else:
            assert status == 200, recovered
            assert recovered["decision_id"] == decision_id
            assert recovered["case_id"] == case_id
            assert recovered["relation_type"] == "INITIAL"
            assert recovered["reference"] == request["reference"]
            assert recovered["source_text"] == request["source_text"]
            assert recovered["operator_attestation_recorded"] is True
            assert recovered["members"][0]["display_name"] == "Synthetic inspector"
            assert recovered["legal_issuance_verified"] is False
            assert recovered["ready_to_render"] is False
            # A retry of the original UUID cannot make another decision even
            # if the operator substitutes the latest plan row_version.
            status, _ = _http(recovery_port, "POST", post, {
                **request, "expected_plan_version": after_crash[5],
            })
            assert status == 409

        final = rows()
        assert final[:5] == (1, 1, 1, 1, 1)
        assert final[5] > before[5]
        status, final_read = _http(recovery_port, "GET", get)
        assert status == 200, final_read
        assert final_read["decision_id"] == decision_id
        assert final_read["relation_type"] == "INITIAL"
    finally:
        _stop_worker(recovery_worker)
