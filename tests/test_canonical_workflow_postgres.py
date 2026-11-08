"""Real service-level workflow on an isolated, migrated PostgreSQL schema.

Opt in only against the named loopback disposable databases. No rehearsal DB.
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from backend.app.auth import ROLE_PERMISSIONS, build_authenticated_user, get_authenticated_user
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import AuditEvent, CapaCycle, Case, Certificate, CertificateVersion, Company, InspectionApprovalSubmission, Site
from backend.app.services.catalog import CatalogReadService
from backend.app.services.workflow import CaseWorkflowService
from backend.app.main import create_app


@pytest.fixture(scope="module")
def pg_engine():
    if os.environ.get("GXP_CANONICAL_WORKFLOW_POSTGRES") != "1":
        pytest.skip("explicit disposable PostgreSQL workflow gate required")
    url = make_url(os.environ["DATABASE_URL"])
    if (url.get_backend_name() != "postgresql" or url.host not in {"127.0.0.1", "localhost"}
            or url.database not in {"gxp_qlcl_test", "gxp_workflow_disposable"}):
        pytest.fail("Refusing non-disposable PostgreSQL database")
    schema = "workflow_it_" + uuid4().hex
    admin = create_engine(url)
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    scoped = url.update_query_dict({"options": f"-csearch_path={schema}"})
    try:
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True,
                       env={**os.environ, "DATABASE_URL": scoped.render_as_string(hide_password=False)})
        engine = create_engine(scoped)
        try:
            yield engine
        finally:
            engine.dispose()
    finally:
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


USER = build_authenticated_user("workflow-integration", "admin", permissions=ROLE_PERMISSIONS["admin"])
DAY = date(2026, 10, 1)
SERVICE = CaseWorkflowService()
CATALOG = CatalogReadService()


def write(engine, fn, **kwargs):
    with Session(engine) as session:
        result = fn(session, user=USER, **kwargs)
        session.commit()
        return result


def seed(engine):
    with Session(engine) as session:
        company = Company(legal_name=f"Synthetic {uuid4()}")
        session.add(company); session.flush()
        site = Site(company_id=company.id, site_name="Synthetic workflow site")
        session.add(site); session.flush()
        case = Case(site_id=site.id, gxp_type="GMP", state=CaseState.INSPECTION_IN_PROGRESS)
        session.add(case); session.flush()
        ids = case.id, site.id
        session.commit()
        return ids


def transition(engine, case_id, state, version=None):
    return write(engine, SERVICE.transition_case, case_id=case_id, target_state=state,
                 expected_version=version, reason="synthetic transition")


def create_cycle(engine, case_id):
    return write(engine, SERVICE.create_capa_cycle, case_id=case_id, requested_on=DAY,
                 incoming_reference="initial", notes="draft", reason="synthetic CAPA")


def assess_cycle(engine, cycle, result):
    submitted = write(engine, SERVICE.submit_capa_cycle, capa_cycle_id=cycle["capa_cycle_id"],
                      expected_version=cycle["row_version"], submitted_on=DAY, notes="received", reason=None)
    return write(engine, SERVICE.assess_capa_cycle, capa_cycle_id=cycle["capa_cycle_id"],
                 expected_version=submitted["row_version"], assessed_on=DAY, assessor_name=None,
                 result=result, notes="assessed", reason=None)


def approval(engine, case_id, stage, parent=None):
    return write(engine, SERVICE.create_approval_submission, case_id=case_id, stage=stage,
                 reference=f"{stage}-synthetic", submitted_on=DAY, submitted_time=None,
                 pct_submission_id=parent, reason=None)


def complete(engine, submission):
    return write(engine, SERVICE.complete_approval_submission,
                 approval_submission_id=submission["approval_submission_id"],
                 expected_version=submission["row_version"], completed_on=DAY, completed_time=None, reason=None)


def issue(engine, case_id, site_id):
    return write(engine, SERVICE.issue_certificate, site_id=site_id, case_id=case_id,
                 certificate_type="GMP", issuance_basis="inspection_case", certificate_number="SYNTH-1",
                 issue_date=DAY, expiry_date=date(2027, 10, 1),
                 scopes=[{"scope_key": "s1", "scope_text": "Synthetic scope", "language_code": "vi", "sort_order": 1}],
                 reason="synthetic issue")


@pytest.mark.parametrize("reject_first", [False, True], ids=["accepted-first", "rejected-then-accepted"])
def test_capa_approval_certificate_through_closed_case(pg_engine, reject_first):
    case_id, site_id = seed(pg_engine)
    write(pg_engine, SERVICE.upsert_inspection_outcome, case_id=case_id, inspected_on=DAY,
          inspected_to_on=DAY, decision_reference=None, bbkt_reference=None,
          outcome_result="synthetic inspection", reason=None)
    transition(pg_engine, case_id, "inspection_completed")
    first = create_cycle(pg_engine, case_id)
    first = write(pg_engine, SERVICE.update_capa_cycle, capa_cycle_id=first["capa_cycle_id"],
                  expected_version=first["row_version"], requested_on=DAY, incoming_reference="CAPA-1",
                  notes="updated", reason=None)
    first = assess_cycle(pg_engine, first, "rejected" if reject_first else "accepted")
    if reject_first:
        with pytest.raises(HTTPException) as blocked:
            transition(pg_engine, case_id, "awaiting_certificate_decision")
        assert blocked.value.status_code == 409
        with pytest.raises(HTTPException) as blocked_issue:
            issue(pg_engine, case_id, site_id)
        assert blocked_issue.value.status_code == 409
        second = create_cycle(pg_engine, case_id)
        assert second["round_no"] == 2 and second["capa_cycle_id"] != first["capa_cycle_id"]
        assess_cycle(pg_engine, second, "accepted")
        with Session(pg_engine) as session:
            rounds = SERVICE.list_capa_cycles(session, case_id=case_id)
            assert [row["status"] for row in rounds] == ["rejected", "accepted"]
    transition(pg_engine, case_id, "awaiting_certificate_decision")
    with Session(pg_engine) as session:
        assert SERVICE.get_case_certificate_issue_readiness(session, case_id=case_id, user=USER)["available"]
    pct = complete(pg_engine, approval(pg_engine, case_id, "PCT"))
    ct = complete(pg_engine, approval(pg_engine, case_id, "CT", pct["approval_submission_id"]))
    assert ct["pct_submission_id"] == pct["approval_submission_id"]
    cert = issue(pg_engine, case_id, site_id)
    assert cert["latest_flag"] is False and cert["case_id"] == case_id
    with Session(pg_engine) as session:
        detail = CATALOG.get_gxp_certificate_detail(session, certificate_id=cert["certificate_id"])
        assert detail["certificate_id"] == cert["certificate_id"] and detail["site_id"] == site_id
        assert detail["latest_flag"] is False
        history = CATALOG.get_gxp_certificate_version_history(session, certificate_id=cert["certificate_id"])
        assert history["case_id"] == case_id and history["site_id"] == site_id
        assert history["latest_version_id"] == cert["latest_version_id"]
        assert history["versions"][0]["scopes"][0]["scope_text"] == "Synthetic scope"
        actions = SERVICE.get_certificate_action_readiness(session, certificate_id=cert["certificate_id"], user=USER)
        assert next(x for x in actions if x["action_key"] == "promote_current")["available"]
    write(pg_engine, SERVICE.promote_certificate_current, certificate_id=cert["certificate_id"],
          expected_version=cert["row_version"], reason="synthetic promotion")
    transition(pg_engine, case_id, "certified")
    transition(pg_engine, case_id, "closed")
    with Session(pg_engine) as session:
        workspace = CATALOG.get_case_workspace(session, case_id=case_id, user=USER)
        assert workspace["case_summary"]["state"] == "closed"
        assert session.get(Certificate, cert["certificate_id"]).latest_flag is True
        assert session.scalar(select(func.count()).select_from(CertificateVersion).where(CertificateVersion.certificate_id == cert["certificate_id"])) == 1
        assert session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.entity_id == cert["certificate_id"], AuditEvent.action == "certificate.issue")) == 1


def test_approval_parent_identity_and_terminal_guard(pg_engine):
    case_id, _ = seed(pg_engine)
    other_case, _ = seed(pg_engine)
    first = complete(pg_engine, approval(pg_engine, case_id, "PCT"))
    second = complete(pg_engine, approval(pg_engine, case_id, "PCT"))
    unfinished = approval(pg_engine, case_id, "PCT")
    other = complete(pg_engine, approval(pg_engine, other_case, "PCT"))
    ct1 = approval(pg_engine, case_id, "CT", first["approval_submission_id"])
    ct2 = approval(pg_engine, case_id, "CT", second["approval_submission_id"])
    assert ct1["pct_submission_id"] != ct2["pct_submission_id"]
    with Session(pg_engine) as session:
        audit_before = session.scalar(select(func.count()).select_from(AuditEvent))
    for parent in (unfinished, other, ct1):
        with pytest.raises(HTTPException) as blocked:
            approval(pg_engine, case_id, "CT", parent["approval_submission_id"])
        assert blocked.value.status_code == 422
    with Session(pg_engine) as session:
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == audit_before
    transition(pg_engine, case_id, "cancelled")
    with pytest.raises(HTTPException) as blocked:
        complete(pg_engine, ct1)
    assert blocked.value.status_code == 409


def test_competing_capa_creation_serializes_and_leaves_one_audit(pg_engine):
    case_id, _ = seed(pg_engine)
    transition(pg_engine, case_id, "inspection_completed")
    gate = Barrier(2)
    def attempt():
        gate.wait()
        try:
            return ("ok", create_cycle(pg_engine, case_id))
        except HTTPException as exc:
            return ("rejected", exc.status_code)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: attempt(), range(2)))
    assert sorted(x[0] for x in results) == ["ok", "rejected"]
    assert next(x[1] for x in results if x[0] == "rejected") == 409
    with Session(pg_engine) as session:
        rows = list(session.scalars(select(CapaCycle).where(CapaCycle.case_id == case_id)))
        assert len(rows) == 1 and rows[0].round_no == 1
        assert session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.entity_id == rows[0].id, AuditEvent.action == "capa_cycle.create")) == 1


def test_stale_versions_and_competing_approval_completion(pg_engine):
    case_id, _ = seed(pg_engine)
    transition(pg_engine, case_id, "inspection_completed")
    cycle = create_cycle(pg_engine, case_id)
    updated = write(pg_engine, SERVICE.update_capa_cycle, capa_cycle_id=cycle["capa_cycle_id"],
                    expected_version=cycle["row_version"], requested_on=DAY, incoming_reference="new",
                    notes="preserved", reason=None)
    with pytest.raises(HTTPException) as stale_update:
        write(pg_engine, SERVICE.update_capa_cycle, capa_cycle_id=cycle["capa_cycle_id"],
              expected_version=cycle["row_version"], requested_on=DAY, incoming_reference="stale",
              notes=None, reason=None)
    assert stale_update.value.status_code == 409
    submitted = write(pg_engine, SERVICE.submit_capa_cycle, capa_cycle_id=updated["capa_cycle_id"],
                      expected_version=updated["row_version"], submitted_on=DAY, notes=None, reason=None)
    with pytest.raises(HTTPException) as stale_assess:
        write(pg_engine, SERVICE.assess_capa_cycle, capa_cycle_id=cycle["capa_cycle_id"],
              expected_version=updated["row_version"], assessed_on=DAY, assessor_name=None,
              result="accepted", notes=None, reason=None)
    assert stale_assess.value.status_code == 409
    write(pg_engine, SERVICE.assess_capa_cycle, capa_cycle_id=cycle["capa_cycle_id"],
          expected_version=submitted["row_version"], assessed_on=DAY, assessor_name=None,
          result="accepted", notes=None, reason=None)
    with Session(pg_engine) as session:
        case_version = session.get(Case, case_id).row_version
    with pytest.raises(HTTPException) as stale_case:
        transition(pg_engine, case_id, "awaiting_certificate_decision", case_version + 1)
    assert stale_case.value.status_code == 409
    with Session(pg_engine) as session:
        for action in ("capa_cycle.update", "capa_cycle.assess"):
            assert session.scalar(select(func.count()).select_from(AuditEvent).where(
                AuditEvent.entity_id == cycle["capa_cycle_id"], AuditEvent.action == action)) == 1
    submission = approval(pg_engine, case_id, "PCT")
    gate = Barrier(2)
    def attempt():
        gate.wait()
        try:
            return ("ok", complete(pg_engine, submission))
        except HTTPException as exc:
            return ("rejected", exc.status_code)
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: attempt(), range(2)))
    assert sorted(x[0] for x in outcomes) == ["ok", "rejected"]
    assert next(x[1] for x in outcomes if x[0] == "rejected") == 409
    with Session(pg_engine) as session:
        assert session.scalar(select(func.count()).select_from(AuditEvent).where(
            AuditEvent.entity_id == submission["approval_submission_id"],
            AuditEvent.action == "inspection_approval_submission.complete")) == 1


def test_competing_gmp_issuance_is_unique_and_rollback_leaves_no_audit(pg_engine):
    case_id, site_id = seed(pg_engine)
    transition(pg_engine, case_id, "inspection_completed")
    cycle = create_cycle(pg_engine, case_id)
    with pytest.raises(HTTPException) as blocked:
        issue(pg_engine, case_id, site_id)
    assert blocked.value.status_code == 409
    with Session(pg_engine) as session:
        assert session.scalar(select(func.count()).select_from(Certificate).where(Certificate.case_id == case_id)) == 0
    assess_cycle(pg_engine, cycle, "accepted")
    transition(pg_engine, case_id, "awaiting_certificate_decision")
    gate = Barrier(2)
    def attempt():
        gate.wait()
        try:
            return ("ok", issue(pg_engine, case_id, site_id))
        except HTTPException as exc:
            return ("rejected", exc.status_code)
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: attempt(), range(2)))
    assert sorted(x[0] for x in outcomes) == ["ok", "rejected"]
    assert next(x[1] for x in outcomes if x[0] == "rejected") == 409
    with Session(pg_engine) as session:
        certs = list(session.scalars(select(Certificate).where(Certificate.case_id == case_id)))
        assert len(certs) == 1
        assert session.scalar(select(func.count()).select_from(CertificateVersion).where(CertificateVersion.certificate_id == certs[0].id)) == 1
        assert session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.entity_id == certs[0].id, AuditEvent.action == "certificate.issue")) == 1


def test_incomplete_candidate_requires_edit_before_current_promotion(pg_engine):
    case_id, site_id = seed(pg_engine)
    transition(pg_engine, case_id, "inspection_completed")
    transition(pg_engine, case_id, "awaiting_certificate_decision")
    candidate = write(pg_engine, SERVICE.issue_certificate, site_id=site_id, case_id=case_id,
                      certificate_type="GMP", issuance_basis="inspection_case", certificate_number=None,
                      issue_date=None, expiry_date=None, scopes=[], reason=None)
    with Session(pg_engine) as session:
        action = next(x for x in SERVICE.get_certificate_action_readiness(session,
                      certificate_id=candidate["certificate_id"], user=USER) if x["action_key"] == "promote_current")
        assert action["reason_code"] == "certificate_data_incomplete" and not action["available"]
    with pytest.raises(HTTPException) as blocked:
        write(pg_engine, SERVICE.promote_certificate_current, certificate_id=candidate["certificate_id"],
              expected_version=candidate["row_version"], reason=None)
    assert blocked.value.status_code == 409
    revised = write(pg_engine, SERVICE.upsert_certificate_latest_version, certificate_id=candidate["certificate_id"],
                    expected_version=candidate["row_version"], certificate_number="SYNTH-READY", issue_date=DAY,
                    expiry_date=date(2027, 10, 1), scopes=[], reason="complete candidate")
    assert revised["row_version"] > candidate["row_version"]
    write(pg_engine, SERVICE.promote_certificate_current, certificate_id=candidate["certificate_id"],
          expected_version=revised["row_version"], reason=None)


def test_approval_timestamp_defaults_survive_migration_round_trip(pg_engine):
    def defaults():
        with pg_engine.connect() as conn:
            return dict(conn.execute(text("SELECT column_name, column_default FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name = 'inspection_approval_submission' "
                "AND column_name IN ('created_at', 'updated_at')")).all())
    assert all(defaults().values())
    env = {**os.environ, "DATABASE_URL": pg_engine.url.render_as_string(hide_password=False)}
    subprocess.run([sys.executable, "-m", "alembic", "downgrade", "20261101_0027"], check=True, env=env)
    assert all(value is None for value in defaults().values())
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True, env=env)
    assert all(defaults().values())


@pytest.mark.parametrize("operation", ["issue", "approval"])
def test_terminal_transition_serializes_against_writes(pg_engine, operation):
    case_id, site_id = seed(pg_engine)
    transition(pg_engine, case_id, "inspection_completed")
    transition(pg_engine, case_id, "awaiting_certificate_decision")
    gate = Barrier(2)
    def cancel():
        gate.wait()
        return transition(pg_engine, case_id, "cancelled")
    def competing_write():
        gate.wait()
        try:
            result = issue(pg_engine, case_id, site_id) if operation == "issue" else approval(pg_engine, case_id, "PCT")
            return ("ok", result)
        except HTTPException as exc:
            return ("rejected", exc.status_code)
    with ThreadPoolExecutor(max_workers=2) as pool:
        cancel_future = pool.submit(cancel)
        write_future = pool.submit(competing_write)
        assert cancel_future.result()["current_state"] == "cancelled"
        outcome = write_future.result()
    assert outcome[0] == "ok" or outcome == ("rejected", 409)
    with Session(pg_engine) as session:
        assert session.get(Case, case_id).state == CaseState.CANCELLED
        certificates = session.scalar(select(func.count()).select_from(Certificate).where(Certificate.case_id == case_id))
        if operation == "issue":
            assert certificates == (1 if outcome[0] == "ok" else 0)
        else:
            approvals = session.scalar(select(func.count()).select_from(InspectionApprovalSubmission).where(InspectionApprovalSubmission.case_id == case_id))
            assert approvals == (1 if outcome[0] == "ok" else 0)
    with pytest.raises(HTTPException) as blocked:
        if operation == "issue":
            issue(pg_engine, case_id, site_id)
        else:
            approval(pg_engine, case_id, "PCT")
    assert blocked.value.status_code == 409


def test_http_approval_write_and_workspace_read_use_same_canonical_identity(pg_engine):
    case_id, _ = seed(pg_engine)
    app = create_app(pg_engine.url.render_as_string(hide_password=False))
    app.dependency_overrides[get_authenticated_user] = lambda: USER
    async def request(method, path, payload=None):
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
                   "method": method, "scheme": "http", "path": path, "raw_path": path.encode(),
                   "query_string": b"", "headers": [(b"content-type", b"application/json")],
                   "client": ("127.0.0.1", 12345), "server": ("localhost", 80), "root_path": ""}, receive, send)
        status = next(x["status"] for x in messages if x["type"] == "http.response.start")
        response_body = b"".join(x.get("body", b"") for x in messages if x["type"] == "http.response.body")
        return status, json.loads(response_body)
    async def scenario():
        status, submission = await request("POST", f"/cases/{case_id}/approval-submissions/PCT", {
            "reference": "HTTP-PCT", "submitted_on": "2026-10-01", "submitted_time": None,
            "pct_submission_id": None, "reason": "synthetic HTTP test",
        })
        assert status == 200, submission
        status, completed = await request("POST", f"/approval-submissions/{submission['approval_submission_id']}/complete", {
            "expected_version": submission["row_version"], "completed_on": "2026-10-01",
            "completed_time": None, "reason": None,
        })
        assert status == 200, completed
        status, workspace = await request("GET", f"/cases/{case_id}/workspace")
        assert status == 200, workspace
        records = workspace["inspection"]["approval_submissions"]
        assert [(x["approval_submission_id"], x["completed_on"]) for x in records] == [
            (submission["approval_submission_id"], "2026-10-01")]
        app.dependency_overrides[get_authenticated_user] = lambda: build_authenticated_user("reader-test", "reader", permissions=ROLE_PERMISSIONS["reader"])
        status, denied = await request("POST", f"/cases/{case_id}/approval-submissions/PCT", {
            "reference": "not-authorized", "submitted_on": "2026-10-01",
            "submitted_time": None, "pct_submission_id": None, "reason": None,
        })
        assert status == 403, denied
    asyncio.run(scenario())
    with Session(pg_engine) as session:
        assert session.scalar(select(func.count()).select_from(InspectionApprovalSubmission).where(InspectionApprovalSubmission.case_id == case_id)) == 1
