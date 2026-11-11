"""HTTP/ASGI workflow against an isolated migrated PostgreSQL schema.

Identity is the real development header-stub adapter, not Google OIDC.
Only initial synthetic entity setup uses the ORM; all workflow steps use HTTP.
"""
import asyncio
import json
from urllib.parse import urlsplit
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.db.models.phase1 import AuditEvent, Certificate
from backend.app.main import create_app
from test_canonical_workflow_postgres import pg_engine, seed  # shared isolated-schema fixture


@pytest.fixture
def api(pg_engine):
    app = create_app(pg_engine.url.render_as_string(hide_password=False), app_env={"AUTH_MODE": "header_stub"})

    def call(method, path, payload=None, role="admin"):
        target = urlsplit(path)
        async def invoke():
            body = b"" if payload is None else json.dumps(payload).encode()
            messages = []
            received = False
            async def receive():
                nonlocal received
                if not received:
                    received = True
                    return {"type": "http.request", "body": body, "more_body": False}
                await asyncio.Future()
            async def send(message):
                messages.append(message)
            await app({"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
                       "method": method, "scheme": "http", "path": target.path, "raw_path": target.path.encode(),
                       "query_string": target.query.encode(), "headers": [(b"content-type", b"application/json"),
                           (b"x-auth-user", b"synthetic-http"), (b"x-auth-role", role.encode())],
                       "client": ("127.0.0.1", 12345), "server": ("localhost", 80), "root_path": ""}, receive, send)
            status = next(x["status"] for x in messages if x["type"] == "http.response.start")
            data = b"".join(x.get("body", b"") for x in messages if x["type"] == "http.response.body")
            return status, json.loads(data) if data else None
        return asyncio.run(invoke())
    return call


def ok(api, method, path, payload=None):
    status, body = api(method, path, payload)
    assert status == 200, (method, path, status, body)
    return body


def workspace(api, case_id):
    return ok(api, "GET", f"/cases/{case_id}/workspace")


def transition(api, case_id, target):
    ws = workspace(api, case_id)
    action = next(x for x in ws["transition_actions"] if x["target_state"] == target)
    assert action["available"]
    return ok(api, "POST", f"/cases/{case_id}/transition", {
        "target_state": target, "expected_version": action["expected_version"], "reason": "synthetic HTTP",
    })


def new_cycle(api, case_id):
    ws = workspace(api, case_id)
    action = next(x for x in ws["remediation"]["actions"] if x["action_key"] == "create_capa_cycle")
    assert action["available"]
    return ok(api, "POST", f"/cases/{case_id}/capa-cycles", {"expected_case_version": action["expected_version"],
        "requested_on": "2026-10-01", "incoming_reference": "HTTP-CAPA", "notes": "synthetic"})


def cycle_read(api, case_id, cycle_id):
    return next(x for x in workspace(api, case_id)["remediation"]["cycles"] if x["capa_cycle_id"] == cycle_id)


def submit_assess(api, case_id, cycle, result):
    cycle_id = cycle["capa_cycle_id"]
    current = cycle_read(api, case_id, cycle_id)
    ok(api, "POST", f"/capa-cycles/{cycle_id}/submit", {"expected_version": current["row_version"], "submitted_on": "2026-10-02"})
    current = cycle_read(api, case_id, cycle_id)
    return ok(api, "POST", f"/capa-cycles/{cycle_id}/assess", {"expected_version": current["row_version"],
        "assessed_on": "2026-10-03", "result": result})


def create_approval(api, case_id, stage, parent=None):
    return ok(api, "POST", f"/cases/{case_id}/approval-submissions/{stage}", {
        "reference": f"HTTP-{stage}", "submitted_on": "2026-10-04", "pct_submission_id": parent})


def complete_approval(api, case_id, item):
    submission_id = item["approval_submission_id"]
    current = next(x for x in workspace(api, case_id)["inspection"]["approval_submissions"] if x["approval_submission_id"] == submission_id)
    return ok(api, "POST", f"/approval-submissions/{submission_id}/complete", {
        "expected_version": current["row_version"], "completed_on": "2026-10-05"})


@pytest.mark.parametrize("reject_first", [False, True], ids=["accepted", "rejected-then-accepted"])
def test_http_end_to_end_capa_approval_certificate_close(pg_engine, api, reject_first):
    case_id, site_id = seed(pg_engine)
    assert workspace(api, case_id)["case_summary"]["id"] == case_id
    ok(api, "PUT", f"/cases/{case_id}/outcome", {"inspected_on": "2026-10-01", "inspected_to_on": "2026-10-01", "outcome_result": "synthetic"})
    transition(api, case_id, "inspection_completed")
    first = new_cycle(api, case_id)
    first_id = first["capa_cycle_id"]
    current = cycle_read(api, case_id, first_id)
    ok(api, "PUT", f"/capa-cycles/{first_id}", {"expected_version": current["row_version"], "incoming_reference": "HTTP-UPDATED"})
    submit_assess(api, case_id, first, "rejected" if reject_first else "accepted")
    if reject_first:
        ws = workspace(api, case_id)
        action = next(x for x in ws["transition_actions"] if x["target_state"] == "awaiting_certificate_decision")
        assert not action["available"]
        status, _ = api("POST", f"/cases/{case_id}/transition", {"target_state": "awaiting_certificate_decision", "expected_version": action["expected_version"]})
        assert status == 409
        second = new_cycle(api, case_id)
        assert second["round_no"] == 2 and second["capa_cycle_id"] != first_id
        submit_assess(api, case_id, second, "accepted")
        assert [x["status"] for x in workspace(api, case_id)["remediation"]["cycles"]] == ["rejected", "accepted"]
    ws = workspace(api, case_id)
    ready = ws["inspection"]["final_evaluation_readiness"]
    assert ready["available"]
    ok(api, "POST", f"/cases/{case_id}/outcome/final-evaluation", {"expected_version": ready["expected_version"], "final_evaluation": "Đạt"})
    assert workspace(api, case_id)["inspection"]["final_evaluation"] == "Đạt"
    transition(api, case_id, "awaiting_certificate_decision")
    pct = complete_approval(api, case_id, create_approval(api, case_id, "PCT"))
    ct = complete_approval(api, case_id, create_approval(api, case_id, "CT", pct["approval_submission_id"]))
    assert ct["pct_submission_id"] == pct["approval_submission_id"]
    assert workspace(api, case_id)["certificate_issue_readiness"]["available"]
    cert = ok(api, "POST", f"/sites/{site_id}/certificates", {"case_id": case_id, "certificate_type": "GMP", "issuance_basis": "inspection_case", "certificate_number": "HTTP-GMP", "issue_date": "2026-10-06", "expiry_date": "2027-10-06", "scopes": []})
    cert_id = cert["certificate_id"]
    detail = ok(api, "GET", f"/certificates/{cert_id}")
    assert detail["certificate_id"] == cert_id and detail["site_id"] == site_id and not detail["latest_flag"]
    edit = next(x for x in detail["action_readiness"] if x["action_key"] == "edit_latest_version")
    status, _ = api("PUT", f"/certificates/{cert_id}/latest-version", {"expected_version": edit["expected_version"] + 1, "scopes": []})
    assert status == 409
    status, _ = api("POST", f"/sites/{site_id}/certificates", {"case_id": case_id, "certificate_type": "GMP", "issuance_basis": "inspection_case", "scopes": []})
    assert status == 409
    ok(api, "PUT", f"/certificates/{cert_id}/latest-version", {"expected_version": edit["expected_version"],
        "certificate_number": "HTTP-GMP-UPDATED", "issue_date": "2026-10-06", "expiry_date": "2027-10-06",
        "scopes": [{"scope_key": "synthetic", "scope_text": "Synthetic scope", "language_code": "vi", "sort_order": 1}]})
    detail = ok(api, "GET", f"/certificates/{cert_id}")
    assert detail["certificate_number"] == "HTTP-GMP-UPDATED" and detail["scopes"][0]["scope_text"] == "Synthetic scope"
    # The read-only report must not advertise a Certificate that is merely
    # issued but has not been promoted to canonical Current.
    before_current = ok(api, "GET", "/reports/certificates?gxp_type=GMP&number=HTTP-GMP-UPDATED")
    assert all(row["certificate_id"] != cert_id for row in before_current["items"])
    action = next(x for x in detail["action_readiness"] if x["action_key"] == "promote_current")
    assert action["available"]
    status, _ = api("POST", f"/certificates/{cert_id}/promote-current", {"expected_version": action["expected_version"] + 1})
    assert status == 409
    ok(api, "POST", f"/certificates/{cert_id}/promote-current", {"expected_version": action["expected_version"]})
    assert ok(api, "GET", f"/certificates/{cert_id}")["latest_flag"]
    current = ok(api, "GET", "/reports/certificates?gxp_type=GMP&number=HTTP-GMP-UPDATED")
    assert any(row["certificate_id"] == cert_id and row["site_id"] == site_id
               and row["certificate_number"] == "HTTP-GMP-UPDATED" for row in current["items"])
    active_cases = ok(api, "GET", "/reports/cases?gxp_type=GMP")
    assert any(row["case_id"] == case_id for row in active_cases["items"])
    transition(api, case_id, "certified")
    transition(api, case_id, "closed")
    ws = workspace(api, case_id)
    assert ws["case_summary"]["state"] == "closed"
    assert any(x["certificate_id"] == cert_id for x in ws["linked_gxp_certificates"])
    after_close = ok(api, "GET", "/reports/cases?gxp_type=GMP")
    assert all(row["case_id"] != case_id for row in after_close["items"])
    after_close_certs = ok(api, "GET", "/reports/certificates?gxp_type=GMP&number=HTTP-GMP-UPDATED")
    assert any(row["certificate_id"] == cert_id for row in after_close_certs["items"])
    with Session(pg_engine) as session:
        assert session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.entity_id == cert_id, AuditEvent.action == "certificate.issue")) == 1


def test_http_multiple_approvals_identity_permissions_and_stale_versions(pg_engine, api):
    case_id, site_id = seed(pg_engine)
    other_case, other_site = seed(pg_engine)
    pct1 = complete_approval(api, case_id, create_approval(api, case_id, "PCT"))
    pct2 = complete_approval(api, case_id, create_approval(api, case_id, "PCT"))
    pending = create_approval(api, case_id, "PCT")
    other = complete_approval(api, other_case, create_approval(api, other_case, "PCT"))
    ct = create_approval(api, case_id, "CT", pct1["approval_submission_id"])
    assert ct["pct_submission_id"] == pct1["approval_submission_id"] != pct2["approval_submission_id"]
    assert [pct1["round_no"], pct2["round_no"], pending["round_no"]] == [1, 2, 3]
    for invalid in (pending["approval_submission_id"], other["approval_submission_id"], ct["approval_submission_id"]):
        status, _ = api("POST", f"/cases/{case_id}/approval-submissions/CT", {"pct_submission_id": invalid})
        assert status == 422
    records = workspace(api, case_id)["inspection"]["approval_submissions"]
    assert next(x for x in records if x["approval_submission_id"] == ct["approval_submission_id"])["pct_submission_id"] == pct1["approval_submission_id"]
    status, _ = api("POST", f"/cases/{case_id}/approval-submissions/PCT", {}, role="reader")
    assert status == 403
    status, _ = api("POST", f"/sites/{other_site}/certificates", {"case_id": case_id, "certificate_type": "GMP", "issuance_basis": "inspection_case", "scopes": []})
    assert status in {409, 422}
    transition(api, case_id, "inspection_completed")
    cycle = new_cycle(api, case_id)
    current = cycle_read(api, case_id, cycle["capa_cycle_id"])
    status, _ = api("POST", f"/capa-cycles/{cycle['capa_cycle_id']}/submit", {"expected_version": current["row_version"] + 1, "submitted_on": "2026-10-02"})
    assert status == 409
    assert cycle_read(api, case_id, cycle["capa_cycle_id"])["status"] == "requested"
    with Session(pg_engine) as session:
        assert session.scalar(select(func.count()).select_from(Certificate).where(Certificate.case_id == case_id)) == 0
        assert session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.entity_id == cycle["capa_cycle_id"], AuditEvent.action == "capa_cycle.submit")) == 0


def test_http_competing_approval_completion_is_single_commit(pg_engine, api):
    case_id, _ = seed(pg_engine)
    pct = create_approval(api, case_id, "PCT")
    submission_id = pct["approval_submission_id"]
    current = next(x for x in workspace(api, case_id)["inspection"]["approval_submissions"] if x["approval_submission_id"] == submission_id)
    gate = Barrier(2)
    def attempt():
        gate.wait()
        return api("POST", f"/approval-submissions/{submission_id}/complete", {"expected_version": current["row_version"], "completed_on": "2026-10-05"})[0]
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(lambda _: attempt(), range(2)))
    assert sorted(statuses) == [200, 409]
    records = workspace(api, case_id)["inspection"]["approval_submissions"]
    assert next(x for x in records if x["approval_submission_id"] == submission_id)["completed_on"] == "2026-10-05"
    with Session(pg_engine) as session:
        assert session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.entity_id == submission_id, AuditEvent.action == "inspection_approval_submission.complete")) == 1


def test_http_competing_capa_submit_and_assess_are_single_commit(pg_engine, api):
    case_id, _ = seed(pg_engine)
    transition(api, case_id, "inspection_completed")
    cycle = new_cycle(api, case_id)
    cycle_id = cycle["capa_cycle_id"]
    def race(path, payload):
        gate = Barrier(2)
        def attempt():
            gate.wait()
            return api("POST", path, payload)[0]
        with ThreadPoolExecutor(max_workers=2) as pool:
            return sorted(pool.map(lambda _: attempt(), range(2)))
    current = cycle_read(api, case_id, cycle_id)
    assert race(f"/capa-cycles/{cycle_id}/submit", {"expected_version": current["row_version"], "submitted_on": "2026-10-02"}) == [200, 409]
    current = cycle_read(api, case_id, cycle_id)
    assert current["status"] == "submitted"
    assert race(f"/capa-cycles/{cycle_id}/assess", {"expected_version": current["row_version"], "assessed_on": "2026-10-03", "result": "accepted"}) == [200, 409]
    assert cycle_read(api, case_id, cycle_id)["status"] == "accepted"
    with Session(pg_engine) as session:
        for action in ("capa_cycle.submit", "capa_cycle.assess"):
            assert session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.entity_id == cycle_id, AuditEvent.action == action)) == 1


def test_http_competing_gmp_issue_and_stale_transition(pg_engine, api):
    case_id, site_id = seed(pg_engine)
    transition(api, case_id, "inspection_completed")
    transition(api, case_id, "awaiting_certificate_decision")
    gate = Barrier(2)
    def attempt():
        gate.wait()
        return api("POST", f"/sites/{site_id}/certificates", {"case_id": case_id, "certificate_type": "GMP",
            "issuance_basis": "inspection_case", "certificate_number": "HTTP-RACE",
            "issue_date": "2026-10-06", "expiry_date": "2027-10-06", "scopes": []})
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: attempt(), range(2)))
    assert sorted(status for status, _ in results) == [200, 409]
    cert_id = next(body["certificate_id"] for status, body in results if status == 200)
    ws = workspace(api, case_id)
    action = next(x for x in ws["transition_actions"] if x["target_state"] == "certified")
    status, _ = api("POST", f"/cases/{case_id}/transition", {"target_state": "certified", "expected_version": action["expected_version"] + 1})
    assert status == 409
    assert workspace(api, case_id)["case_summary"]["state"] == "awaiting_certificate_decision"
    with Session(pg_engine) as session:
        assert session.scalar(select(func.count()).select_from(Certificate).where(Certificate.case_id == case_id)) == 1
        assert session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.entity_id == cert_id, AuditEvent.action == "certificate.issue")) == 1


def test_http_approval_create_has_no_implicit_idempotency(pg_engine, api):
    # Two independently accepted requests are distinct submissions. The UI
    # must fence uncertain outcomes; request IDs do not confer idempotency.
    case_id, _ = seed(pg_engine)
    gate = Barrier(2)
    def attempt():
        gate.wait()
        return api("POST", f"/cases/{case_id}/approval-submissions/PCT", {"reference": "same-reference"})
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: attempt(), range(2)))
    assert [status for status, _ in results] == [200, 200]
    ids = {body["approval_submission_id"] for _, body in results}
    assert len(ids) == 2
    records = workspace(api, case_id)["inspection"]["approval_submissions"]
    assert {row["approval_submission_id"] for row in records} == ids
    assert sorted(row["round_no"] for row in records) == [1, 2]
