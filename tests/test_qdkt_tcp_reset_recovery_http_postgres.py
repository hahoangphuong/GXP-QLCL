"""Real loopback TCP loss-after-commit recovery for QĐKT Process B.

No production environment, network proxy, or external DB. Uses the isolated
migrated PostgreSQL schema guarded by pg_engine and actual Uvicorn sockets.
This does not simulate a database crash or distributed network failover.
"""
from __future__ import annotations

import http.client
import json
import socket
import struct
from threading import Event, Thread
from time import monotonic, sleep
from uuid import uuid4

import pytest
import uvicorn
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import backend.app.api.routers.workflow as workflow_router
from backend.app.db.enums import InspectionEventType
from backend.app.db.models.phase1 import (
    AuditEvent, InspectionDecision, InspectionEvent, InspectionPlan,
    QdKtIssuedRoster, QdKtIssuedRosterMember,
)
from backend.app.main import create_app
from test_canonical_workflow_postgres import DAY, SERVICE, pg_engine, seed, write


def _json_http(port: int, method: str, path: str, body: dict | None = None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=15)
    try:
        headers = {"X-Auth-User": "synthetic-tcp", "X-Auth-Role": "admin"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        conn.request(method, path, body=None if body is None else json.dumps(body).encode(), headers=headers)
        response = conn.getresponse()
        payload = response.read()
        return response.status, json.loads(payload) if payload else None
    finally:
        conn.close()


def test_qdkt_committed_tcp_reset_recovers_exact_case_uuid_once(pg_engine, monkeypatch):
    case_id, _ = seed(pg_engine)
    plan = write(
        pg_engine, SERVICE.upsert_inspection_plan, case_id=case_id,
        plan_start_on=DAY, plan_end_on=DAY,
        planning_sheet_name="Loopback TCP fault injection",
        decision_document_hint=None, reason="Synthetic QDKT plan",
    )
    decision_id = str(uuid4())
    payload = {
        "decision_id": decision_id,
        "expected_plan_version": plan["row_version"],
        "reference": "SYNTH-TCP-RESET-QDKT",
        "decision_on": DAY.isoformat(),
        "source_text": "Synthetic approved source from operator",
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
        "reason": "Synthetic recorded external decision",
    }
    app = create_app(
        pg_engine.url.render_as_string(hide_password=False),
        app_env={"AUTH_MODE": "header_stub"},
    )
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(
        app, host="127.0.0.1", port=port, log_level="error", access_log=False,
    ))
    thread = Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    committed = Event()
    release_response = Event()
    actual_commit = workflow_router.commit_or_409

    def commit_then_pause(session):
        actual_commit(session)
        committed.set()
        if not release_response.wait(15):
            raise AssertionError("test did not release committed response")

    try:
        thread.start()
        deadline = monotonic() + 20
        while not server.started and thread.is_alive() and monotonic() < deadline:
            sleep(0.02)
        assert server.started, "loopback Uvicorn failed to start"
        with monkeypatch.context() as patch:
            patch.setattr(workflow_router, "commit_or_409", commit_then_pause)
            client = socket.create_connection(("127.0.0.1", port), timeout=15)
            try:
                body = json.dumps(payload).encode()
                path = f"/cases/{case_id}/qdkt-issued-decisions"
                raw = (
                    f"POST {path} HTTP/1.1\r\n"
                    f"Host: 127.0.0.1:{port}\r\n"
                    "X-Auth-User: synthetic-tcp\r\n"
                    "X-Auth-Role: admin\r\n"
                    "Content-Type: application/json\r\n"
                    f"Content-Length: {len(body)}\r\n"
                    "Connection: keep-alive\r\n\r\n"
                ).encode() + body
                client.sendall(raw)
                # Explicitly wait for the real PostgreSQL COMMIT to complete.
                assert committed.wait(15), "POST did not reach successful commit"
                # TCP RST, before application is permitted to send a reply.
                client.setsockopt(
                    socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0),
                )
            finally:
                client.close()
                release_response.set()

        exact = f"/cases/{case_id}/qdkt-issued-decisions/{decision_id}"
        status, recovered = _json_http(port, "GET", exact)
        assert status == 200, recovered
        assert recovered["case_id"] == case_id
        assert recovered["decision_id"] == decision_id
        assert recovered["relation_type"] == "INITIAL"
        assert recovered["reference"] == payload["reference"]
        assert recovered["source_text"] == payload["source_text"]
        assert recovered["operator_attestation_recorded"] is True
        assert recovered["members"][0]["display_name"] == "Synthetic leader"
        assert recovered["legal_issuance_verified"] is False
        assert recovered["ready_to_render"] is False

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
                    db.scalar(select(InspectionPlan.row_version)
                        .where(InspectionPlan.case_id == case_id)),
                )

        after_commit = state()
        assert after_commit[:5] == (1, 1, 1, 1, 1)
        assert after_commit[5] > plan["row_version"]
        # The same original UUID cannot be resubmitted despite the advanced
        # expected version, even through a new real TCP connection.
        replay, _ = _json_http(port, "POST", f"/cases/{case_id}/qdkt-issued-decisions", {
            **payload, "expected_plan_version": after_commit[5],
        })
        assert replay == 409
        assert state() == after_commit
        assert _json_http(port, "GET", exact) == (200, recovered)
    finally:
        release_response.set()
        server.should_exit = True
        if thread.is_alive():
            thread.join(timeout=15)
        listener.close()
        assert not thread.is_alive(), "loopback Uvicorn failed to stop"
