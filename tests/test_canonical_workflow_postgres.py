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
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from backend.app.auth import ROLE_PERMISSIONS, build_authenticated_user, get_authenticated_user
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import AuditEvent, CapaCycle, Case, CaseCertificateNonissuanceDecision, Certificate, CertificateScope, CertificateVersion, Company, InspectionApprovalSubmission, InspectionApprovalDocumentLink, InspectionOutcome, Document, Site, ChangeRequestAffectedArtifact, ChangeRequestIssuedArtifact, BusinessEligibilityCertificate, BusinessEligibilityVersion
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
        workspace = CATALOG.get_case_workspace(session, case_id=case_id, user=USER)
        records = list(reversed(workspace["inspection"]["approval_submissions"]))
        parents = {row["approval_submission_id"]: row["pct_submission_id"] for row in records if row["stage"] == "CT"}
        assert parents == {ct1["approval_submission_id"]: first["approval_submission_id"],
                           ct2["approval_submission_id"]: second["approval_submission_id"]}
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


def test_readiness_rejects_unaccepted_capa_even_on_imported_eligible_case(pg_engine):
    # A legacy snapshot may already be in the decision state with an unaccepted
    # CAPA; current transitions never create this combination. Keep it
    # synthetic and verify the persisted policy without repairing history.
    case_id, site_id = seed(pg_engine)
    with Session(pg_engine) as session:
        session.get(Case, case_id).state = CaseState.AWAITING_CERTIFICATE_DECISION
        session.add(CapaCycle(case_id=case_id, round_no=1, status="rejected", result="rejected"))
        session.commit()
    with Session(pg_engine) as session:
        ready = SERVICE.get_case_certificate_issue_readiness(session, case_id=case_id, user=USER)
        assert not ready["available"] and ready["reason_code"] == "latest_capa_not_accepted"
    with pytest.raises(HTTPException) as blocked:
        issue(pg_engine, case_id, site_id)
    assert blocked.value.status_code == 409
    with Session(pg_engine) as session:
        assert session.scalar(select(func.count()).select_from(Certificate).where(Certificate.case_id == case_id)) == 0


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


@pytest.mark.parametrize("issuance_basis", [
    "administrative_no_inspection", "inspection_case",
])
def test_certificate_link_rejects_cross_gxp_case_for_every_issuance_basis(
    pg_engine, issuance_basis,
):
    """A linked Certificate must use the Case's canonical GxP, not merely its Site.

    Administrative issuance cannot create a cross-GxP Case/Certificate link
    that the read model immediately rejects as corrupt historical ownership.
    Failed admission must not create a Certificate or an audit event.
    """
    case_id, site_id = seed(pg_engine)
    with Session(pg_engine) as setup:
        case = setup.get(Case, case_id)
        case.state = CaseState.AWAITING_CERTIFICATE_DECISION
        setup.commit()

    with Session(pg_engine) as session:
        before_certs = session.scalar(
            select(func.count()).select_from(Certificate).where(
                Certificate.case_id == case_id,
            )
        )
        before_events = session.scalar(
            select(func.count()).select_from(AuditEvent)
        )
        with pytest.raises(HTTPException) as blocked:
            SERVICE.issue_certificate(
                session, site_id=site_id, case_id=case_id,
                certificate_type="GLP", issuance_basis=issuance_basis,
                certificate_number="SYNTH-CROSS-GXP",
                issue_date=DAY, expiry_date=date(2027, 10, 1),
                scopes=[], reason="cross-gxp synthetic guard", user=USER,
            )
        assert blocked.value.status_code == 422
        assert session.scalar(
            select(func.count()).select_from(Certificate).where(
                Certificate.case_id == case_id,
            )
        ) == before_certs
        assert session.scalar(
            select(func.count()).select_from(AuditEvent)
        ) == before_events
        session.rollback()


def test_certificate_issue_rejects_expiry_before_issue_date_without_writes(pg_engine):
    """An issued certificate candidate cannot expire before its issue date."""
    _case_id, site_id = seed(pg_engine)
    with Session(pg_engine) as session:
        certs_before = session.scalar(select(func.count()).select_from(Certificate))
        events_before = session.scalar(select(func.count()).select_from(AuditEvent))
        with pytest.raises(HTTPException) as blocked:
            SERVICE.issue_certificate(
                session, site_id=site_id, case_id=None,
                certificate_type="GMP",
                issuance_basis="administrative_no_inspection",
                certificate_number="INVALID-DATE-ORDER-ISSUE",
                issue_date=date(2028, 1, 1),
                expiry_date=date(2027, 12, 31),
                scopes=[], reason="synthetic date-order guard", user=USER,
            )
        assert blocked.value.status_code == 422
        assert session.scalar(select(func.count()).select_from(Certificate)) == certs_before
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == events_before
        session.rollback()


def test_certificate_version_edit_rejects_expiry_before_issue_date_without_writes(pg_engine):
    """Editing a latest Version cannot turn a coherent date pair backwards."""
    _case_id, site_id = seed(pg_engine)
    issued = write(
        pg_engine, SERVICE.issue_certificate, site_id=site_id, case_id=None,
        certificate_type="GMP",
        issuance_basis="administrative_no_inspection",
        certificate_number="VALID-DATE-ORDER-ISSUE",
        issue_date=date(2027, 1, 1),
        expiry_date=date(2028, 1, 1),
        scopes=[], reason="synthetic candidate", 
    )
    with Session(pg_engine) as session:
        events_before = session.scalar(select(func.count()).select_from(AuditEvent))
        version_before = session.get(CertificateVersion, issued["latest_version_id"])
        original_dates = (version_before.issue_date, version_before.expiry_date)
        with pytest.raises(HTTPException) as blocked:
            SERVICE.upsert_certificate_latest_version(
                session, certificate_id=issued["certificate_id"],
                expected_version=issued["row_version"],
                certificate_number="INVALID-DATE-ORDER-EDIT",
                issue_date=date(2029, 1, 1),
                expiry_date=date(2028, 12, 31),
                scopes=[], reason="synthetic invalid date edit", user=USER,
            )
        assert blocked.value.status_code == 422
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == events_before
        persisted = session.execute(select(
            CertificateVersion.issue_date, CertificateVersion.expiry_date
        ).where(CertificateVersion.id == issued["latest_version_id"])).one()
        assert tuple(persisted) == original_dates
        session.rollback()


def test_nonissuance_rejects_dirty_cached_case_before_refresh_or_audit(pg_engine):
    """Non-issuance admission must not autoflush or discard an operator Case draft."""
    case_id, _site_id = seed(pg_engine)
    with Session(pg_engine) as setup:
        case = setup.get(Case, case_id)
        case.state = CaseState.AWAITING_CERTIFICATE_DECISION
        setup.add(InspectionOutcome(
            case_id=case_id, final_evaluation="Synthetic final evaluation"
        ))
        setup.commit()

    with Session(pg_engine) as session:
        case = session.get(Case, case_id)
        expected_version = case.row_version
        original_scope = case.scope_code
        audit_before = session.scalar(select(func.count()).select_from(AuditEvent))
        case.scope_code = "UNSAVED-NONISSUANCE-CASE-DRAFT"
        flushes = []

        def forbid_flush(*_args):
            flushes.append(True)
            raise AssertionError("Non-issuance admission autoflushed a Case draft")

        event.listen(session, "before_flush", forbid_flush)
        try:
            with pytest.raises(HTTPException) as blocked:
                SERVICE.record_case_nonissuance_decision(
                    session, case_id=case_id,
                    expected_case_version=expected_version,
                    decided_on=DAY, decision_reference="SYNTH-NONISSUANCE",
                    explanation="Synthetic decision",
                    reason="synthetic dirty Case guard", user=USER,
                )
            assert blocked.value.status_code == 409
            assert "uncommitted" in str(blocked.value.detail).lower()
            assert not flushes
            assert case.scope_code == "UNSAVED-NONISSUANCE-CASE-DRAFT"
            assert case in session.dirty
            with session.no_autoflush:
                assert session.scalar(select(func.count()).select_from(AuditEvent)) == audit_before
                assert session.scalar(
                    select(Case.scope_code).where(Case.id == case_id)
                ) == original_scope
        finally:
            event.remove(session, "before_flush", forbid_flush)
            session.rollback()


def test_transition_case_rejects_dirty_owner_without_autoflush_or_audit(pg_engine):
    """Changing Case state must not commit an independent operator Case draft."""
    case_id, _site_id = seed(pg_engine)
    with Session(pg_engine) as session:
        case = session.get(Case, case_id)
        original_state = case.state
        original_scope = case.scope_code
        expected_version = case.row_version
        audit_before = session.scalar(select(func.count()).select_from(AuditEvent))
        case.scope_code = "UNSAVED-TRANSITION-CASE-DRAFT"
        flushes = []

        def forbid_flush(*_args):
            flushes.append(True)
            raise AssertionError("Case transition autoflushed an operator draft")

        event.listen(session, "before_flush", forbid_flush)
        try:
            with pytest.raises(HTTPException) as blocked:
                SERVICE.transition_case(
                    session, case_id=case_id,
                    target_state=CaseState.INSPECTION_COMPLETED.value,
                    expected_version=expected_version,
                    reason="synthetic transition draft guard", user=USER,
                )
            assert blocked.value.status_code == 409
            assert "uncommitted" in str(blocked.value.detail).lower()
            assert not flushes
            assert case.scope_code == "UNSAVED-TRANSITION-CASE-DRAFT"
            assert case.state == original_state
            assert case in session.dirty
            with session.no_autoflush:
                assert session.scalar(select(func.count()).select_from(AuditEvent)) == audit_before
                assert session.execute(
                    select(Case.scope_code, Case.state).where(Case.id == case_id)
                ).one() == (original_scope, original_state)
        finally:
            event.remove(session, "before_flush", forbid_flush)
            session.rollback()


def test_capa_create_rejects_pending_round_without_flushing_operator_draft(pg_engine):
    """A second CAPA create must not persist another in-memory unsubmitted round."""
    case_id, _site_id = seed(pg_engine)
    transition(pg_engine, case_id, "inspection_completed")
    with Session(pg_engine) as session:
        audits_before = session.scalar(select(func.count()).select_from(AuditEvent))
        staged = CapaCycle(
            case_id=case_id, round_no=1, status="requested",
            requested_on=DAY, incoming_reference="UNSAVED-CAPA-ROUND",
        )
        session.add(staged)
        flushes = []

        def forbid_flush(*_args):
            flushes.append(True)
            raise AssertionError("CAPA creation autoflushed a pending cycle")

        event.listen(session, "before_flush", forbid_flush)
        try:
            with pytest.raises(HTTPException) as blocked:
                SERVICE.create_capa_cycle(
                    session, case_id=case_id, requested_on=DAY,
                    incoming_reference="SECOND-REQUEST", notes=None,
                    reason="synthetic pending-CAPA guard", user=USER,
                )
            assert blocked.value.status_code == 409
            assert "uncommitted" in str(blocked.value.detail).lower()
            assert not flushes
            assert staged in session.new
            assert staged.incoming_reference == "UNSAVED-CAPA-ROUND"
            with session.no_autoflush:
                assert session.scalar(
                    select(func.count()).select_from(CapaCycle)
                    .where(CapaCycle.case_id == case_id)
                ) == 0
                assert session.scalar(
                    select(func.count()).select_from(AuditEvent)
                ) == audits_before
        finally:
            event.remove(session, "before_flush", forbid_flush)
            session.rollback()


def test_final_evaluation_rejects_pending_capa_round_before_audit_or_flush(pg_engine):
    """An unsaved CAPA request cannot disappear from final-evaluation eligibility."""
    case_id, _site_id = seed(pg_engine)
    with Session(pg_engine) as setup:
        stage = InspectionOutcome(
            case_id=case_id, outcome_result="Synthetic inspection result",
        )
        setup.add(stage)
        setup.commit()
        outcome_id = stage.id
    with Session(pg_engine) as session:
        outcome = session.get(InspectionOutcome, outcome_id)
        token = outcome.row_version
        audit_before = session.scalar(select(func.count()).select_from(AuditEvent))
        staged = CapaCycle(
            case_id=case_id, round_no=1, requested_on=DAY,
            incoming_reference="UNSAVED-REMEDIATION",
            status="requested",
        )
        session.add(staged)
        flushes = []

        def forbid_flush(*_args):
            flushes.append(True)
            raise AssertionError("Final evaluation autoflushed an unaccepted CAPA draft")

        event.listen(session, "before_flush", forbid_flush)
        try:
            with pytest.raises(HTTPException) as blocked:
                SERVICE.finalize_inspection_outcome(
                    session, case_id=case_id, expected_version=token,
                    final_evaluation="Synthetic final determination",
                    reason="synthetic pending CAPA guard", user=USER,
                )
            assert blocked.value.status_code == 409
            assert "capa" in str(blocked.value.detail).lower()
            assert not flushes
            assert staged in session.new
            assert outcome.final_evaluation is None
            with session.no_autoflush:
                assert session.scalar(select(func.count()).select_from(AuditEvent)) == audit_before
                assert session.scalar(
                    select(InspectionOutcome.final_evaluation)
                    .where(InspectionOutcome.id == outcome_id)
                ) is None
                assert session.scalar(
                    select(func.count()).select_from(CapaCycle)
                    .where(CapaCycle.case_id == case_id)
                ) == 0
        finally:
            event.remove(session, "before_flush", forbid_flush)
            session.rollback()


def test_case_transition_rejects_pending_capa_without_flushing_or_transitioning(pg_engine):
    """CAPA pending in the caller Session cannot be implicitly saved by transition."""
    case_id, _site_id = seed(pg_engine)
    transition(pg_engine, case_id, "inspection_completed")
    with Session(pg_engine) as session:
        case = session.get(Case, case_id)
        token = case.row_version
        audits_before = session.scalar(select(func.count()).select_from(AuditEvent))
        pending = CapaCycle(
            case_id=case_id, round_no=1, status="requested",
            requested_on=DAY, incoming_reference="UNSAVED-TRANSITION-CAPA",
        )
        session.add(pending)
        flushes = []

        def forbid_flush(*_args):
            flushes.append(True)
            raise AssertionError("Case transition autoflushed an unaccepted CAPA")

        event.listen(session, "before_flush", forbid_flush)
        try:
            with pytest.raises(HTTPException) as blocked:
                SERVICE.transition_case(
                    session, case_id=case_id,
                    target_state=CaseState.AWAITING_CERTIFICATE_DECISION.value,
                    expected_version=token, reason="synthetic pending CAPA", user=USER,
                )
            assert blocked.value.status_code == 409
            assert "capa" in str(blocked.value.detail).lower()
            assert not flushes
            assert pending in session.new
            assert case.state == CaseState.INSPECTION_COMPLETED
            with session.no_autoflush:
                assert session.scalar(
                    select(Case.state).where(Case.id == case_id)
                ) == CaseState.INSPECTION_COMPLETED
                assert session.scalar(
                    select(func.count()).select_from(CapaCycle)
                    .where(CapaCycle.case_id == case_id)
                ) == 0
                assert session.scalar(select(func.count()).select_from(AuditEvent)) == audits_before
        finally:
            event.remove(session, "before_flush", forbid_flush)
            session.rollback()


@pytest.mark.parametrize("issuance_basis", ["inspection_case", "administrative_no_inspection"])
def test_case_linked_issuance_refuses_pending_capa_without_autoflush(pg_engine, issuance_basis):
    """A staged, unaccepted CAPA cannot be inserted as an issuance side effect."""
    case_id, site_id = seed(pg_engine)
    with Session(pg_engine) as setup:
        case = setup.get(Case, case_id)
        case.state = CaseState.AWAITING_CERTIFICATE_DECISION
        setup.commit()
    with Session(pg_engine) as session:
        audit_before = session.scalar(select(func.count()).select_from(AuditEvent))
        certificate_before = session.scalar(select(func.count()).select_from(Certificate))
        pending = CapaCycle(
            case_id=case_id, round_no=1, status="requested",
            requested_on=DAY, incoming_reference="UNSAVED-ISSUANCE-CAPA",
        )
        session.add(pending)
        flushes = []

        def forbid_flush(*_args):
            flushes.append(True)
            raise AssertionError("Certificate issuance autoflushed an unaccepted CAPA")

        event.listen(session, "before_flush", forbid_flush)
        try:
            with pytest.raises(HTTPException) as blocked:
                SERVICE.issue_certificate(
                    session, site_id=site_id, case_id=case_id,
                    certificate_type="GMP", issuance_basis=issuance_basis,
                    certificate_number="SYNTH-ISSUANCE-PENDING-CAPA",
                    issue_date=DAY, expiry_date=date(2027, 10, 1),
                    scopes=[], reason="synthetic pending CAPA admission", user=USER,
                )
            assert blocked.value.status_code == 409
            assert "capa" in str(blocked.value.detail).lower()
            assert not flushes
            assert pending in session.new
            with session.no_autoflush:
                assert session.scalar(select(func.count()).select_from(Certificate)) == certificate_before
                assert session.scalar(select(func.count()).select_from(AuditEvent)) == audit_before
                assert session.scalar(
                    select(func.count()).select_from(CapaCycle).where(CapaCycle.case_id == case_id)
                ) == 0
        finally:
            event.remove(session, "before_flush", forbid_flush)
            session.rollback()


def test_nonissuance_refuses_pending_capa_before_decision_or_audit(pg_engine):
    """An in-memory requested CAPA must not accompany an explicit non-issuance decision."""
    case_id, _site_id = seed(pg_engine)
    with Session(pg_engine) as setup:
        case = setup.get(Case, case_id)
        case.state = CaseState.AWAITING_CERTIFICATE_DECISION
        setup.add(InspectionOutcome(
            case_id=case_id, final_evaluation="Synthetic final non-issuance evaluation",
        ))
        setup.commit()

    with Session(pg_engine) as session:
        version = session.get(Case, case_id).row_version
        audit_before = session.scalar(select(func.count()).select_from(AuditEvent))
        pending = CapaCycle(
            case_id=case_id, round_no=1, status="requested",
            requested_on=DAY, incoming_reference="UNSAVED-NONISSUANCE-CAPA",
        )
        session.add(pending)
        flushes = []

        def forbid_flush(*_args):
            flushes.append(True)
            raise AssertionError("Non-issuance decision autoflushed an unaccepted CAPA")

        event.listen(session, "before_flush", forbid_flush)
        try:
            with pytest.raises(HTTPException) as blocked:
                SERVICE.record_case_nonissuance_decision(
                    session, case_id=case_id, expected_case_version=version,
                    decided_on=DAY, decision_reference="SYNTH-NONISSUANCE-PENDING",
                    explanation="Synthetic explicit refusal",
                    reason="synthetic pending CAPA guard", user=USER,
                )
            assert blocked.value.status_code == 409
            assert "capa" in str(blocked.value.detail).lower()
            assert not flushes
            assert pending in session.new
            with session.no_autoflush:
                assert SERVICE.get_case_nonissuance_decision(
                    session, case_id=case_id,
                )["decision"] is None
                assert session.scalar(
                    select(func.count()).select_from(CapaCycle).where(CapaCycle.case_id == case_id)
                ) == 0
                assert session.scalar(select(func.count()).select_from(AuditEvent)) == audit_before
        finally:
            event.remove(session, "before_flush", forbid_flush)
            session.rollback()


@pytest.mark.parametrize("operation", ["create", "complete"])
def test_approval_mutation_refuses_pending_capa_without_autoflush(pg_engine, operation):
    """A PCT creation/completion must never persist a separate unsaved CAPA."""
    case_id, _site_id = seed(pg_engine)
    transition(pg_engine, case_id, "inspection_completed")
    existing = approval(pg_engine, case_id, "PCT") if operation == "complete" else None

    with Session(pg_engine) as session:
        audit_before = session.scalar(select(func.count()).select_from(AuditEvent))
        approval_before = session.scalar(
            select(func.count()).select_from(InspectionApprovalSubmission)
            .where(InspectionApprovalSubmission.case_id == case_id)
        )
        pending = CapaCycle(
            case_id=case_id, round_no=1, status="requested",
            requested_on=DAY, incoming_reference="UNSAVED-PCT-CAPA",
        )
        session.add(pending)
        flushes = []

        def forbid_flush(*_args):
            flushes.append(True)
            raise AssertionError("Approval operation autoflushed an unaccepted CAPA")

        event.listen(session, "before_flush", forbid_flush)
        try:
            with pytest.raises(HTTPException) as blocked:
                if operation == "create":
                    SERVICE.create_approval_submission(
                        session, case_id=case_id, stage="PCT",
                        reference="SYNTH-PCT-PENDING-CAPA",
                        submitted_on=DAY, submitted_time=None,
                        pct_submission_id=None, reason="pending CAPA admission",
                        user=USER,
                    )
                else:
                    SERVICE.complete_approval_submission(
                        session,
                        approval_submission_id=existing["approval_submission_id"],
                        expected_version=existing["row_version"],
                        completed_on=DAY, completed_time=None,
                        reason="pending CAPA admission", user=USER,
                    )
            assert blocked.value.status_code == 409
            assert "capa" in str(blocked.value.detail).lower()
            assert not flushes
            assert pending in session.new
            with session.no_autoflush:
                assert session.scalar(
                    select(func.count()).select_from(CapaCycle).where(CapaCycle.case_id == case_id)
                ) == 0
                assert session.scalar(
                    select(func.count()).select_from(InspectionApprovalSubmission)
                    .where(InspectionApprovalSubmission.case_id == case_id)
                ) == approval_before
                if existing is not None:
                    assert session.scalar(
                        select(InspectionApprovalSubmission.completed_on)
                        .where(InspectionApprovalSubmission.id == existing["approval_submission_id"])
                    ) is None
                assert session.scalar(select(func.count()).select_from(AuditEvent)) == audit_before
        finally:
            event.remove(session, "before_flush", forbid_flush)
            session.rollback()


@pytest.mark.parametrize("operation", ["update", "submit", "assess"])
def test_capa_mutation_rejects_pending_sibling_round_without_autoflush(pg_engine, operation):
    """A separate pending CAPA round cannot be flushed by update/submit/assess."""
    case_id, _site_id = seed(pg_engine)
    transition(pg_engine, case_id, "inspection_completed")
    target = create_cycle(pg_engine, case_id)
    if operation == "assess":
        target = write(
            pg_engine, SERVICE.submit_capa_cycle,
            capa_cycle_id=target["capa_cycle_id"],
            expected_version=target["row_version"],
            submitted_on=DAY, notes="synthetic submission", reason=None,
        )
    with Session(pg_engine) as session:
        audits_before = session.scalar(select(func.count()).select_from(AuditEvent))
        pending = CapaCycle(
            case_id=case_id, round_no=2, status="requested",
            requested_on=DAY, incoming_reference="UNSAVED-SIBLING-CAPA",
        )
        session.add(pending)
        flushes = []

        def forbid_flush(*_args):
            flushes.append(True)
            raise AssertionError("CAPA mutation autoflushed a pending sibling")

        event.listen(session, "before_flush", forbid_flush)
        try:
            with pytest.raises(HTTPException) as blocked:
                if operation == "update":
                    SERVICE.update_capa_cycle(
                        session, capa_cycle_id=target["capa_cycle_id"],
                        expected_version=target["row_version"],
                        requested_on=DAY, incoming_reference="SYNTH-UPDATE",
                        notes="Synthetic update", reason=None, user=USER,
                    )
                elif operation == "submit":
                    SERVICE.submit_capa_cycle(
                        session, capa_cycle_id=target["capa_cycle_id"],
                        expected_version=target["row_version"],
                        submitted_on=DAY, notes="Synthetic submit",
                        reason=None, user=USER,
                    )
                else:
                    SERVICE.assess_capa_cycle(
                        session, capa_cycle_id=target["capa_cycle_id"],
                        expected_version=target["row_version"],
                        assessed_on=DAY, assessor_name=None,
                        result="accepted", notes="Synthetic accept",
                        reason=None, user=USER,
                    )
            assert blocked.value.status_code == 409
            assert "uncommitted" in str(blocked.value.detail).lower()
            assert not flushes
            assert pending in session.new
            with session.no_autoflush:
                assert session.scalar(
                    select(func.count()).select_from(CapaCycle)
                    .where(CapaCycle.case_id == case_id)
                ) == 1
                assert session.scalar(select(func.count()).select_from(AuditEvent)) == audits_before
                assert session.scalar(
                    select(CapaCycle.status).where(
                        CapaCycle.id == target["capa_cycle_id"]
                    )
                ) == ("submitted" if operation == "assess" else "requested")
        finally:
            event.remove(session, "before_flush", forbid_flush)
            session.rollback()


@pytest.mark.parametrize("operation", ["update", "submit", "assess"])
def test_capa_mutation_refuses_pending_delete_before_autoflush(pg_engine, operation):
    """A caller-staged CAPA deletion must not be committed by a separate mutation."""
    case_id, _site_id = seed(pg_engine)
    transition(pg_engine, case_id, "inspection_completed")
    target = create_cycle(pg_engine, case_id)
    if operation == "assess":
        target = write(
            pg_engine, SERVICE.submit_capa_cycle,
            capa_cycle_id=target["capa_cycle_id"],
            expected_version=target["row_version"],
            submitted_on=DAY, notes="synthetic submission", reason=None,
        )
    with Session(pg_engine) as session:
        cycle = session.get(CapaCycle, target["capa_cycle_id"])
        audit_before = session.scalar(select(func.count()).select_from(AuditEvent))
        session.delete(cycle)
        flushes = []

        def forbid_flush(*_args):
            flushes.append(True)
            raise AssertionError("CAPA mutation flushed a pending deletion")

        event.listen(session, "before_flush", forbid_flush)
        try:
            with pytest.raises(HTTPException) as blocked:
                if operation == "update":
                    SERVICE.update_capa_cycle(
                        session, capa_cycle_id=target["capa_cycle_id"],
                        expected_version=target["row_version"],
                        requested_on=DAY, incoming_reference="SYNTH-DELETE-GUARD",
                        notes="Synthetic update", reason=None, user=USER,
                    )
                elif operation == "submit":
                    SERVICE.submit_capa_cycle(
                        session, capa_cycle_id=target["capa_cycle_id"],
                        expected_version=target["row_version"],
                        submitted_on=DAY, notes="Synthetic submit",
                        reason=None, user=USER,
                    )
                else:
                    SERVICE.assess_capa_cycle(
                        session, capa_cycle_id=target["capa_cycle_id"],
                        expected_version=target["row_version"],
                        assessed_on=DAY, assessor_name=None, result="accepted",
                        notes="Synthetic assessment", reason=None, user=USER,
                    )
            assert blocked.value.status_code == 409
            assert "uncommitted" in str(blocked.value.detail).lower()
            assert not flushes
            assert cycle in session.deleted
            with session.no_autoflush:
                assert session.scalar(
                    select(func.count()).select_from(CapaCycle)
                    .where(CapaCycle.id == target["capa_cycle_id"])
                ) == 1
                assert session.scalar(select(func.count()).select_from(AuditEvent)) == audit_before
        finally:
            event.remove(session, "before_flush", forbid_flush)
            session.rollback()


@pytest.mark.parametrize("issuance_basis", ["inspection_case", "administrative_no_inspection"])
def test_case_issuance_refuses_pending_nonissuance_without_autoflush(pg_engine, issuance_basis):
    """A staged legal refusal must not be persisted by a certificate mutation."""
    case_id, site_id = seed(pg_engine)
    transition(pg_engine, case_id, "inspection_completed")
    with Session(pg_engine) as setup:
        case = setup.get(Case, case_id)
        case.state = CaseState.AWAITING_CERTIFICATE_DECISION
        setup.commit()
    with Session(pg_engine) as session:
        actor_id = session.scalar(
            select(AuditEvent.actor_user_id)
            .where(AuditEvent.actor_user_id.is_not(None)).limit(1)
        )
        assert actor_id is not None
        audit_before = session.scalar(select(func.count()).select_from(AuditEvent))
        certificates_before = session.scalar(select(func.count()).select_from(Certificate))
        pending = CaseCertificateNonissuanceDecision(
            case_id=case_id, decided_on=DAY,
            decision_reference="UNSAVED-LEGAL-REFUSAL",
            explanation="Synthetic unsubmitted non-issuance decision",
            recorded_by_user_id=actor_id,
        )
        session.add(pending)
        flushes = []

        def forbid_flush(*_args):
            flushes.append(True)
            raise AssertionError("Certificate issuance autoflushed a refusal draft")

        event.listen(session, "before_flush", forbid_flush)
        try:
            with pytest.raises(HTTPException) as blocked:
                SERVICE.issue_certificate(
                    session, site_id=site_id, case_id=case_id,
                    certificate_type="GMP", issuance_basis=issuance_basis,
                    certificate_number="SYNTH-REFUSAL-EXCLUSIVITY",
                    issue_date=DAY, expiry_date=date(2027, 10, 1),
                    scopes=[], reason="synthetic refusal draft guard", user=USER,
                )
            assert blocked.value.status_code == 409
            assert "uncommitted" in str(blocked.value.detail).lower()
            assert not flushes
            assert pending in session.new
            with session.no_autoflush:
                assert session.scalar(
                    select(func.count()).select_from(CaseCertificateNonissuanceDecision)
                    .where(CaseCertificateNonissuanceDecision.case_id == case_id)
                ) == 0
                assert session.scalar(select(func.count()).select_from(Certificate)) == certificates_before
                assert session.scalar(select(func.count()).select_from(AuditEvent)) == audit_before
        finally:
            event.remove(session, "before_flush", forbid_flush)
            session.rollback()


def test_nonissuance_rejects_pending_case_certificate_before_any_flush(pg_engine):
    """Refusal must not insert a separately staged same-Case certificate."""
    case_id, site_id = seed(pg_engine)
    with Session(pg_engine) as setup:
        case = setup.get(Case, case_id)
        case.state = CaseState.AWAITING_CERTIFICATE_DECISION
        setup.add(InspectionOutcome(
            case_id=case_id, final_evaluation="Synthetic final evaluation",
        ))
        setup.commit()
    with Session(pg_engine) as session:
        version = session.get(Case, case_id).row_version
        audits_before = session.scalar(select(func.count()).select_from(AuditEvent))
        staged = Certificate(
            case_id=case_id, site_id=site_id, certificate_type="GMP",
            issuance_basis="inspection_case", latest_flag=False,
        )
        session.add(staged)
        flushes = []

        def forbid_flush(*_args):
            flushes.append(True)
            raise AssertionError("Non-issuance autoflushed an unissued Certificate draft")

        event.listen(session, "before_flush", forbid_flush)
        try:
            with pytest.raises(HTTPException) as blocked:
                SERVICE.record_case_nonissuance_decision(
                    session, case_id=case_id, expected_case_version=version,
                    decided_on=DAY, decision_reference="SYNTH-NONISSUANCE-EXCLUSIVITY",
                    explanation="Synthetic refusal decision", reason=None, user=USER,
                )
            assert blocked.value.status_code == 409
            assert "uncommitted" in str(blocked.value.detail).lower()
            assert not flushes
            assert staged in session.new
            with session.no_autoflush:
                assert session.scalar(
                    select(func.count()).select_from(Certificate)
                    .where(Certificate.case_id == case_id)
                ) == 0
                assert SERVICE.get_case_nonissuance_decision(
                    session, case_id=case_id,
                )["decision"] is None
                assert session.scalar(select(func.count()).select_from(AuditEvent)) == audits_before
        finally:
            event.remove(session, "before_flush", forbid_flush)
            session.rollback()


def test_competing_case_issuance_and_nonissuance_leave_single_decision(pg_engine):
    """Two real transactions on the same Case cannot both issue and refuse."""
    case_id, site_id = seed(pg_engine)
    with Session(pg_engine) as setup:
        case = setup.get(Case, case_id)
        case.state = CaseState.AWAITING_CERTIFICATE_DECISION
        setup.add(InspectionOutcome(
            case_id=case_id, final_evaluation="Synthetic final evaluation",
        ))
        setup.commit()
        expected_version = case.row_version

    gate = Barrier(2)

    def attempt(kind):
        gate.wait()
        try:
            if kind == "issue":
                result = issue(pg_engine, case_id, site_id)
            else:
                result = write(
                    pg_engine, SERVICE.record_case_nonissuance_decision,
                    case_id=case_id, expected_case_version=expected_version,
                    decided_on=DAY, decision_reference="SYNTH-COMPETING-REFUSAL",
                    explanation="Synthetic competing decision", reason=None,
                )
            return "ok", kind, result
        except HTTPException as exc:
            return "rejected", kind, exc.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(attempt, ("issue", "refuse")))
    assert sorted(x[0] for x in outcomes) == ["ok", "rejected"]
    assert next(x[2] for x in outcomes if x[0] == "rejected") == 409
    with Session(pg_engine) as session:
        issued = session.scalar(
            select(func.count()).select_from(Certificate)
            .where(Certificate.case_id == case_id)
        )
        refused = session.scalar(
            select(func.count()).select_from(CaseCertificateNonissuanceDecision)
            .where(CaseCertificateNonissuanceDecision.case_id == case_id)
        )
        assert issued + refused == 1
        # Match audit IDs to exactly this Case's legal decision, not
        # other synthetic cases in the module's disposable schema.
        case_issue_ids = session.scalars(select(Certificate.id).where(Certificate.case_id == case_id)).all()
        case_refuse_ids = session.scalars(
            select(CaseCertificateNonissuanceDecision.id)
            .where(CaseCertificateNonissuanceDecision.case_id == case_id)
        ).all()
        assert session.scalar(
            select(func.count()).select_from(AuditEvent)
            .where(AuditEvent.action == "certificate.issue", AuditEvent.entity_id.in_(case_issue_ids))
        ) == issued
        assert session.scalar(
            select(func.count()).select_from(AuditEvent)
            .where(AuditEvent.action == "case_certificate_nonissuance_decision.record", AuditEvent.entity_id.in_(case_refuse_ids))
        ) == refused


def test_nonissuance_refuses_pending_same_case_decision_before_autoflush(pg_engine):
    """Duplicate refusal intent in one Session must not flush its first draft."""
    case_id, _site_id = seed(pg_engine)
    transition(pg_engine, case_id, "inspection_completed")
    with Session(pg_engine) as setup:
        case = setup.get(Case, case_id)
        case.state = CaseState.AWAITING_CERTIFICATE_DECISION
        setup.add(InspectionOutcome(
            case_id=case_id, final_evaluation="Synthetic final evaluation",
        ))
        setup.commit()
    with Session(pg_engine) as session:
        version = session.get(Case, case_id).row_version
        actor_id = session.scalar(
            select(AuditEvent.actor_user_id)
            .where(AuditEvent.actor_user_id.is_not(None))
            .limit(1)
        )
        assert actor_id is not None
        audits_before = session.scalar(select(func.count()).select_from(AuditEvent))
        pending = CaseCertificateNonissuanceDecision(
            case_id=case_id, decided_on=DAY,
            decision_reference="PENDING-REFUSAL-DRAFT",
            explanation="Unsubmitted legal decision",
            recorded_by_user_id=actor_id,
        )
        session.add(pending)
        flushes = []

        def forbid_flush(*_args):
            flushes.append(True)
            raise AssertionError("Second non-issuance operation flushed a first draft")

        event.listen(session, "before_flush", forbid_flush)
        try:
            with pytest.raises(HTTPException) as blocked:
                SERVICE.record_case_nonissuance_decision(
                    session, case_id=case_id, expected_case_version=version,
                    decided_on=DAY, decision_reference="SECOND-REFUSAL-INTENT",
                    explanation="Second legal decision intent",
                    reason="synthetic duplicate draft", user=USER,
                )
            assert blocked.value.status_code == 409
            assert "uncommitted" in str(blocked.value.detail).lower()
            assert not flushes
            assert pending in session.new
            assert pending.decision_reference == "PENDING-REFUSAL-DRAFT"
            with session.no_autoflush:
                assert SERVICE.get_case_nonissuance_decision(
                    session, case_id=case_id,
                )["decision"] is None
                assert session.scalar(
                    select(func.count()).select_from(CaseCertificateNonissuanceDecision)
                    .where(CaseCertificateNonissuanceDecision.case_id == case_id)
                ) == 0
                assert session.scalar(select(func.count()).select_from(AuditEvent)) == audits_before
        finally:
            event.remove(session, "before_flush", forbid_flush)
            session.rollback()


@pytest.mark.parametrize("operation", ["create", "complete"])
def test_approval_mutation_refuses_pending_nonissuance_without_autoflush(pg_engine, operation):
    """PCT creation/completion must not persist a separate unsigned legal refusal."""
    case_id, _site_id = seed(pg_engine)
    transition(pg_engine, case_id, "inspection_completed")
    existing = approval(pg_engine, case_id, "PCT") if operation == "complete" else None
    with Session(pg_engine) as session:
        actor_id = session.scalar(
            select(AuditEvent.actor_user_id)
            .where(AuditEvent.actor_user_id.is_not(None)).limit(1)
        )
        assert actor_id is not None
        audit_before = session.scalar(select(func.count()).select_from(AuditEvent))
        approvals_before = session.scalar(
            select(func.count()).select_from(InspectionApprovalSubmission)
            .where(InspectionApprovalSubmission.case_id == case_id)
        )
        pending = CaseCertificateNonissuanceDecision(
            case_id=case_id, decided_on=DAY,
            decision_reference="UNSAVED-PCT-LEGAL-REFUSAL",
            explanation="Separate operator draft not approved for recording",
            recorded_by_user_id=actor_id,
        )
        session.add(pending)
        flushes = []

        def forbid_flush(*_args):
            flushes.append(True)
            raise AssertionError("PCT mutation autoflushed a separate legal refusal draft")

        event.listen(session, "before_flush", forbid_flush)
        try:
            with pytest.raises(HTTPException) as blocked:
                if operation == "create":
                    SERVICE.create_approval_submission(
                        session, case_id=case_id, stage="PCT",
                        reference="SYNTH-PCT-REFUSAL", submitted_on=DAY,
                        submitted_time=None, pct_submission_id=None,
                        reason="pending refusal admission", user=USER,
                    )
                else:
                    SERVICE.complete_approval_submission(
                        session, approval_submission_id=existing["approval_submission_id"],
                        expected_version=existing["row_version"],
                        completed_on=DAY, completed_time=None,
                        reason="pending refusal admission", user=USER,
                    )
            assert blocked.value.status_code == 409
            assert "uncommitted" in str(blocked.value.detail).lower()
            assert not flushes
            assert pending in session.new
            assert pending.decision_reference == "UNSAVED-PCT-LEGAL-REFUSAL"
            with session.no_autoflush:
                assert session.scalar(
                    select(func.count()).select_from(CaseCertificateNonissuanceDecision)
                    .where(CaseCertificateNonissuanceDecision.case_id == case_id)
                ) == 0
                assert session.scalar(
                    select(func.count()).select_from(InspectionApprovalSubmission)
                    .where(InspectionApprovalSubmission.case_id == case_id)
                ) == approvals_before
                if existing is not None:
                    assert session.scalar(
                        select(InspectionApprovalSubmission.completed_on)
                        .where(InspectionApprovalSubmission.id == existing["approval_submission_id"])
                    ) is None
                assert session.scalar(select(func.count()).select_from(AuditEvent)) == audit_before
        finally:
            event.remove(session, "before_flush", forbid_flush)
            session.rollback()


def test_concurrent_final_evaluation_commit_fences_later_capa_creation(pg_engine):
    """Two transactions: a finalized outcome must not admit a new CAPA round.

    The first writer holds the canonical Case lock until the other writer
    starts its operation. The second must revalidate the committed final
    evaluation after acquiring that lock, not rely only on Case state.
    No sleep, implicit retry, or shared SQLAlchemy Session is used.
    """
    from threading import Event

    case_id, _site_id = seed(pg_engine)
    write(
        pg_engine, SERVICE.upsert_inspection_outcome,
        case_id=case_id, inspected_on=DAY, inspected_to_on=DAY,
        decision_reference=None, bbkt_reference=None,
        outcome_result="Synthetic inspection complete", reason=None,
    )
    transition(pg_engine, case_id, "inspection_completed")
    with Session(pg_engine) as lookup:
        outcome_id, version = lookup.execute(
            select(InspectionOutcome.id, InspectionOutcome.row_version)
            .where(InspectionOutcome.case_id == case_id)
        ).one()
        audit_before = lookup.scalar(select(func.count()).select_from(AuditEvent))

    first_flushed = Event()
    second_started = Event()

    def final_writer():
        with Session(pg_engine) as session:
            try:
                SERVICE.finalize_inspection_outcome(
                    session, case_id=case_id, expected_version=version,
                    final_evaluation="Final evaluation explicitly committed",
                    reason="independent transaction", user=USER,
                )
                session.flush()
                first_flushed.set()
                assert second_started.wait(20), "Second independent writer did not start"
                session.commit()
                return "finalized"
            finally:
                first_flushed.set()

    def capa_writer():
        assert first_flushed.wait(20), "First independent writer did not flush"
        with Session(pg_engine) as session:
            second_started.set()
            try:
                SERVICE.create_capa_cycle(
                    session, case_id=case_id, requested_on=DAY,
                    incoming_reference="CONCURRENT-AFTER-FINAL",
                    notes="should be rejected", reason="separate request",
                    user=USER,
                )
                session.commit()
                return "incorrectly_created"
            except HTTPException as exc:
                session.rollback()
                return ("rejected", exc.status_code, str(exc.detail))

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(final_writer)
        second = pool.submit(capa_writer)
        assert first.result(timeout=40) == "finalized"
        outcome = second.result(timeout=40)

    assert outcome[0:2] == ("rejected", 409)
    assert "final" in outcome[2].lower()
    with Session(pg_engine) as session:
        assert session.scalar(
            select(InspectionOutcome.final_evaluation)
            .where(InspectionOutcome.id == outcome_id)
        ) == "Final evaluation explicitly committed"
        assert session.scalar(
            select(func.count()).select_from(CapaCycle)
            .where(CapaCycle.case_id == case_id)
        ) == 0
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == audit_before + 1


@pytest.mark.parametrize("draft_mode", ["new", "dirty"])
def test_capa_creation_refuses_uncommitted_inspection_outcome_draft(pg_engine, draft_mode):
    """A separate outcome draft must not be persisted by CAPA creation."""
    case_id, _site_id = seed(pg_engine)
    transition(pg_engine, case_id, "inspection_completed")
    if draft_mode == "dirty":
        write(
            pg_engine, SERVICE.upsert_inspection_outcome,
            case_id=case_id, inspected_on=DAY, inspected_to_on=DAY,
            decision_reference=None, bbkt_reference=None,
            outcome_result="Committed observation", reason=None,
        )

    with Session(pg_engine) as session:
        audit_before = session.scalar(select(func.count()).select_from(AuditEvent))
        outcome_before = session.scalar(
            select(func.count()).select_from(InspectionOutcome)
            .where(InspectionOutcome.case_id == case_id)
        )
        if draft_mode == "new":
            pending = InspectionOutcome(
                case_id=case_id, outcome_result="Unsaved draft",
                final_evaluation="Unapproved final evaluation",
            )
            session.add(pending)
        else:
            pending = session.scalars(
                select(InspectionOutcome)
                .where(InspectionOutcome.case_id == case_id)
            ).one()
            pending.final_evaluation = "Unapproved final evaluation"
        flushes = []

        def forbid_flush(*_args):
            flushes.append(True)
            raise AssertionError("CAPA creation autoflushed an unrelated inspection outcome draft")

        event.listen(session, "before_flush", forbid_flush)
        try:
            with pytest.raises(HTTPException) as blocked:
                SERVICE.create_capa_cycle(
                    session, case_id=case_id, requested_on=DAY,
                    incoming_reference="UNSENT-OUTCOME-CAPA",
                    notes="separate mutation", reason=None, user=USER,
                )
            assert blocked.value.status_code == 409
            assert "uncommitted" in str(blocked.value.detail).lower()
            assert not flushes
            assert pending.final_evaluation == "Unapproved final evaluation"
            if draft_mode == "new":
                assert pending in session.new
            else:
                assert pending in session.dirty
            with session.no_autoflush:
                assert session.scalar(
                    select(func.count()).select_from(CapaCycle)
                    .where(CapaCycle.case_id == case_id)
                ) == 0
                assert session.scalar(
                    select(func.count()).select_from(InspectionOutcome)
                    .where(InspectionOutcome.case_id == case_id)
                ) == outcome_before
                assert session.scalar(
                    select(InspectionOutcome.final_evaluation)
                    .where(InspectionOutcome.case_id == case_id)
                ) is None
                assert session.scalar(select(func.count()).select_from(AuditEvent)) == audit_before
        finally:
            event.remove(session, "before_flush", forbid_flush)
            session.rollback()


@pytest.mark.parametrize("operation", ["update", "submit", "assess"])
@pytest.mark.parametrize("draft_mode", ["new", "dirty"])
def test_capa_mutation_refuses_pending_inspection_outcome_draft(pg_engine, operation, draft_mode):
    """CAPA mutation cannot flush a different, unsubmitted outcome intent."""
    case_id, _site_id = seed(pg_engine)
    transition(pg_engine, case_id, "inspection_completed")
    target = create_cycle(pg_engine, case_id)
    if operation == "assess":
        target = write(
            pg_engine, SERVICE.submit_capa_cycle,
            capa_cycle_id=target["capa_cycle_id"],
            expected_version=target["row_version"],
            submitted_on=DAY, notes="synthetic submission", reason=None,
        )
    if draft_mode == "dirty":
        write(
            pg_engine, SERVICE.upsert_inspection_outcome,
            case_id=case_id, inspected_on=DAY, inspected_to_on=DAY,
            decision_reference=None, bbkt_reference=None,
            outcome_result="Committed inspection observation", reason=None,
        )
    with Session(pg_engine) as session:
        audits_before = session.scalar(select(func.count()).select_from(AuditEvent))
        if draft_mode == "new":
            pending = InspectionOutcome(
                case_id=case_id,
                outcome_result="Unsubmitted outcome draft",
                final_evaluation="Unsubmitted evaluation",
            )
            session.add(pending)
        else:
            pending = session.scalars(
                select(InspectionOutcome).where(InspectionOutcome.case_id == case_id)
            ).one()
            pending.final_evaluation = "Unsubmitted evaluation"
        flushes = []

        def forbid_flush(*_args):
            flushes.append(True)
            raise AssertionError("CAPA mutation autoflushed a separate inspection outcome draft")

        event.listen(session, "before_flush", forbid_flush)
        try:
            with pytest.raises(HTTPException) as blocked:
                if operation == "update":
                    SERVICE.update_capa_cycle(
                        session, capa_cycle_id=target["capa_cycle_id"],
                        expected_version=target["row_version"],
                        requested_on=DAY, incoming_reference="NEW-CAPA-REFERENCE",
                        notes="synthetic edit", reason=None, user=USER,
                    )
                elif operation == "submit":
                    SERVICE.submit_capa_cycle(
                        session, capa_cycle_id=target["capa_cycle_id"],
                        expected_version=target["row_version"], submitted_on=DAY,
                        notes="synthetic submit", reason=None, user=USER,
                    )
                else:
                    SERVICE.assess_capa_cycle(
                        session, capa_cycle_id=target["capa_cycle_id"],
                        expected_version=target["row_version"], assessed_on=DAY,
                        assessor_name=None, result="accepted", notes="synthetic assess",
                        reason=None, user=USER,
                    )
            assert blocked.value.status_code == 409
            assert "uncommitted" in str(blocked.value.detail).lower()
            assert not flushes
            assert pending.final_evaluation == "Unsubmitted evaluation"
            if draft_mode == "new":
                assert pending in session.new
            else:
                assert pending in session.dirty
            with session.no_autoflush:
                assert session.scalar(
                    select(InspectionOutcome.final_evaluation)
                    .where(InspectionOutcome.case_id == case_id)
                ) is None
                assert session.scalar(
                    select(CapaCycle.status).where(CapaCycle.id == target["capa_cycle_id"])
                ) == ("submitted" if operation == "assess" else "requested")
                assert session.scalar(select(func.count()).select_from(AuditEvent)) == audits_before
        finally:
            event.remove(session, "before_flush", forbid_flush)
            session.rollback()


@pytest.mark.parametrize("operation", ["update", "submit", "assess"])
def test_capa_mutation_refuses_pending_nonissuance_decision(pg_engine, operation):
    """An unsubmitted legal refusal is not a side effect of CAPA mutation."""
    case_id, _site_id = seed(pg_engine)
    transition(pg_engine, case_id, "inspection_completed")
    target = create_cycle(pg_engine, case_id)
    if operation == "assess":
        target = write(
            pg_engine, SERVICE.submit_capa_cycle,
            capa_cycle_id=target["capa_cycle_id"],
            expected_version=target["row_version"],
            submitted_on=DAY, notes="synthetic submission", reason=None,
        )
    with Session(pg_engine) as session:
        actor_id = session.scalar(
            select(AuditEvent.actor_user_id)
            .where(AuditEvent.actor_user_id.is_not(None)).limit(1)
        )
        assert actor_id is not None
        audit_before = session.scalar(select(func.count()).select_from(AuditEvent))
        pending = CaseCertificateNonissuanceDecision(
            case_id=case_id, decided_on=DAY,
            decision_reference="UNSUBMITTED-REFUSAL-DURING-CAPA",
            explanation="Separate legal intent not yet approved",
            recorded_by_user_id=actor_id,
        )
        session.add(pending)
        flushes = []

        def forbid_flush(*_args):
            flushes.append(True)
            raise AssertionError("CAPA mutation autoflushed a separate legal refusal")

        event.listen(session, "before_flush", forbid_flush)
        try:
            with pytest.raises(HTTPException) as blocked:
                if operation == "update":
                    SERVICE.update_capa_cycle(
                        session, capa_cycle_id=target["capa_cycle_id"],
                        expected_version=target["row_version"], requested_on=DAY,
                        incoming_reference="UPDATED-CAPA", notes="updated",
                        reason=None, user=USER,
                    )
                elif operation == "submit":
                    SERVICE.submit_capa_cycle(
                        session, capa_cycle_id=target["capa_cycle_id"],
                        expected_version=target["row_version"], submitted_on=DAY,
                        notes="submitted", reason=None, user=USER,
                    )
                else:
                    SERVICE.assess_capa_cycle(
                        session, capa_cycle_id=target["capa_cycle_id"],
                        expected_version=target["row_version"], assessed_on=DAY,
                        assessor_name=None, result="accepted",
                        notes="assessed", reason=None, user=USER,
                    )
            assert blocked.value.status_code == 409
            assert "uncommitted" in str(blocked.value.detail).lower()
            assert not flushes
            assert pending in session.new
            with session.no_autoflush:
                assert session.scalar(
                    select(func.count()).select_from(CaseCertificateNonissuanceDecision)
                    .where(CaseCertificateNonissuanceDecision.case_id == case_id)
                ) == 0
                assert session.scalar(
                    select(CapaCycle.status).where(CapaCycle.id == target["capa_cycle_id"])
                ) == ("submitted" if operation == "assess" else "requested")
                assert session.scalar(select(func.count()).select_from(AuditEvent)) == audit_before
        finally:
            event.remove(session, "before_flush", forbid_flush)
            session.rollback()


@pytest.mark.parametrize("operation", ["update", "submit", "assess"])
def test_capa_mutation_refuses_pending_certificate_draft(pg_engine, operation):
    """CAPA action must not flush an independent certificate candidate intent."""
    case_id, site_id = seed(pg_engine)
    transition(pg_engine, case_id, "inspection_completed")
    target = create_cycle(pg_engine, case_id)
    if operation == "assess":
        target = write(
            pg_engine, SERVICE.submit_capa_cycle,
            capa_cycle_id=target["capa_cycle_id"],
            expected_version=target["row_version"], submitted_on=DAY,
            notes="synthetic submission", reason=None,
        )
    with Session(pg_engine) as session:
        audit_before = session.scalar(select(func.count()).select_from(AuditEvent))
        pending = Certificate(
            case_id=case_id, site_id=site_id, certificate_type="GMP",
            issuance_basis="inspection_case", latest_flag=False,
        )
        session.add(pending)
        flushes = []

        def forbid_flush(*_args):
            flushes.append(True)
            raise AssertionError("CAPA mutation autoflushed a certificate draft")

        event.listen(session, "before_flush", forbid_flush)
        try:
            with pytest.raises(HTTPException) as blocked:
                if operation == "update":
                    SERVICE.update_capa_cycle(
                        session, capa_cycle_id=target["capa_cycle_id"],
                        expected_version=target["row_version"],
                        requested_on=DAY, incoming_reference="CAPA-CERT-TEST",
                        notes="updated", reason=None, user=USER,
                    )
                elif operation == "submit":
                    SERVICE.submit_capa_cycle(
                        session, capa_cycle_id=target["capa_cycle_id"],
                        expected_version=target["row_version"],
                        submitted_on=DAY, notes="submitted",
                        reason=None, user=USER,
                    )
                else:
                    SERVICE.assess_capa_cycle(
                        session, capa_cycle_id=target["capa_cycle_id"],
                        expected_version=target["row_version"],
                        assessed_on=DAY, assessor_name=None, result="accepted",
                        notes="assessed", reason=None, user=USER,
                    )
            assert blocked.value.status_code == 409
            assert "uncommitted" in str(blocked.value.detail).lower()
            assert not flushes
            assert pending in session.new
            with session.no_autoflush:
                assert session.scalar(
                    select(func.count()).select_from(Certificate)
                    .where(Certificate.case_id == case_id)
                ) == 0
                assert session.scalar(
                    select(CapaCycle.status).where(CapaCycle.id == target["capa_cycle_id"])
                ) == ("submitted" if operation == "assess" else "requested")
                assert session.scalar(select(func.count()).select_from(AuditEvent)) == audit_before
        finally:
            event.remove(session, "before_flush", forbid_flush)
            session.rollback()


@pytest.mark.parametrize("stage", ["PCT", "CT"])
@pytest.mark.parametrize("operation", ["create", "complete"])
@pytest.mark.parametrize("draft_mode", ["new", "dirty"])
def test_approval_mutation_refuses_pending_inspection_outcome(pg_engine, stage, operation, draft_mode):
    """PCT/CT cannot accidentally persist an unsubmitted inspection outcome."""
    case_id, _site_id = seed(pg_engine)
    transition(pg_engine, case_id, "inspection_completed")
    parent = None
    if stage == "CT":
        parent = complete(pg_engine, approval(pg_engine, case_id, "PCT"))
    existing = approval(
        pg_engine, case_id, stage,
        parent["approval_submission_id"] if parent else None,
    ) if operation == "complete" else None
    if draft_mode == "dirty":
        write(
            pg_engine, SERVICE.upsert_inspection_outcome,
            case_id=case_id, inspected_on=DAY, inspected_to_on=DAY,
            decision_reference=None, bbkt_reference=None,
            outcome_result="Committed inspection observation", reason=None,
        )
    with Session(pg_engine) as session:
        audit_before = session.scalar(select(func.count()).select_from(AuditEvent))
        approval_before = session.scalar(
            select(func.count()).select_from(InspectionApprovalSubmission)
            .where(InspectionApprovalSubmission.case_id == case_id)
        )
        if draft_mode == "new":
            pending = InspectionOutcome(
                case_id=case_id,
                outcome_result="Unsubmitted inspection outcome",
                final_evaluation="Unsubmitted final evaluation",
            )
            session.add(pending)
        else:
            pending = session.scalars(
                select(InspectionOutcome).where(InspectionOutcome.case_id == case_id)
            ).one()
            pending.final_evaluation = "Unsubmitted final evaluation"
        flushes = []

        def forbid_flush(*_args):
            flushes.append(True)
            raise AssertionError("PCT/CT mutation autoflushed a separate inspection outcome")

        event.listen(session, "before_flush", forbid_flush)
        try:
            with pytest.raises(HTTPException) as blocked:
                if operation == "create":
                    SERVICE.create_approval_submission(
                        session, case_id=case_id, stage=stage,
                        reference=f"SYNTH-{stage}-OUTCOME-DRAFT",
                        submitted_on=DAY, submitted_time=None,
                        pct_submission_id=parent["approval_submission_id"] if parent else None,
                        reason="synthetic draft guard", user=USER,
                    )
                else:
                    SERVICE.complete_approval_submission(
                        session, approval_submission_id=existing["approval_submission_id"],
                        expected_version=existing["row_version"],
                        completed_on=DAY, completed_time=None,
                        reason="synthetic draft guard", user=USER,
                    )
            assert blocked.value.status_code == 409
            assert "uncommitted" in str(blocked.value.detail).lower()
            assert not flushes
            assert pending.final_evaluation == "Unsubmitted final evaluation"
            if draft_mode == "new":
                assert pending in session.new
            else:
                assert pending in session.dirty
            with session.no_autoflush:
                assert session.scalar(
                    select(InspectionOutcome.final_evaluation)
                    .where(InspectionOutcome.case_id == case_id)
                ) is None
                assert session.scalar(
                    select(func.count()).select_from(InspectionApprovalSubmission)
                    .where(InspectionApprovalSubmission.case_id == case_id)
                ) == approval_before
                if existing is not None:
                    assert session.scalar(
                        select(InspectionApprovalSubmission.completed_on)
                        .where(InspectionApprovalSubmission.id == existing["approval_submission_id"])
                    ) is None
                assert session.scalar(select(func.count()).select_from(AuditEvent)) == audit_before
        finally:
            event.remove(session, "before_flush", forbid_flush)
            session.rollback()


@pytest.mark.parametrize("stage", ["PCT", "CT"])
@pytest.mark.parametrize("operation", ["create", "complete"])
def test_approval_mutation_refuses_pending_certificate_draft(pg_engine, stage, operation):
    """PCT/CT cannot issue a staged certificate as an unrelated flush side effect."""
    case_id, site_id = seed(pg_engine)
    transition(pg_engine, case_id, "inspection_completed")
    parent = complete(pg_engine, approval(pg_engine, case_id, "PCT")) if stage == "CT" else None
    existing = approval(
        pg_engine, case_id, stage,
        parent["approval_submission_id"] if parent else None,
    ) if operation == "complete" else None
    with Session(pg_engine) as session:
        audit_before = session.scalar(select(func.count()).select_from(AuditEvent))
        approval_before = session.scalar(
            select(func.count()).select_from(InspectionApprovalSubmission)
            .where(InspectionApprovalSubmission.case_id == case_id)
        )
        pending = Certificate(
            case_id=case_id, site_id=site_id,
            certificate_type="GMP", issuance_basis="inspection_case",
            latest_flag=False,
        )
        session.add(pending)
        flushes = []

        def forbid_flush(*_args):
            flushes.append(True)
            raise AssertionError("PCT/CT mutation autoflushed a separate Certificate draft")

        event.listen(session, "before_flush", forbid_flush)
        try:
            with pytest.raises(HTTPException) as blocked:
                if operation == "create":
                    SERVICE.create_approval_submission(
                        session, case_id=case_id, stage=stage,
                        reference=f"SYNTH-{stage}-PENDING-CERT",
                        submitted_on=DAY, submitted_time=None,
                        pct_submission_id=parent["approval_submission_id"] if parent else None,
                        reason="synthetic pending Certificate guard", user=USER,
                    )
                else:
                    SERVICE.complete_approval_submission(
                        session, approval_submission_id=existing["approval_submission_id"],
                        expected_version=existing["row_version"],
                        completed_on=DAY, completed_time=None,
                        reason="synthetic pending Certificate guard", user=USER,
                    )
            assert blocked.value.status_code == 409
            assert "uncommitted" in str(blocked.value.detail).lower()
            assert not flushes
            assert pending in session.new
            with session.no_autoflush:
                assert session.scalar(
                    select(func.count()).select_from(Certificate)
                    .where(Certificate.case_id == case_id)
                ) == 0
                assert session.scalar(
                    select(func.count()).select_from(InspectionApprovalSubmission)
                    .where(InspectionApprovalSubmission.case_id == case_id)
                ) == approval_before
                if existing is not None:
                    assert session.scalar(
                        select(InspectionApprovalSubmission.completed_on)
                        .where(InspectionApprovalSubmission.id == existing["approval_submission_id"])
                    ) is None
                assert session.scalar(select(func.count()).select_from(AuditEvent)) == audit_before
        finally:
            event.remove(session, "before_flush", forbid_flush)
            session.rollback()


@pytest.mark.parametrize("stage", ["PCT", "CT"])
@pytest.mark.parametrize("operation", ["update", "submit", "assess"])
@pytest.mark.parametrize("draft_mode", ["new", "dirty"])
def test_capa_mutation_refuses_unsubmitted_approval_draft(pg_engine, stage, operation, draft_mode):
    """CAPA mutation cannot flush or overwrite a separate same-Case PCT/CT intent."""
    case_id, _site_id = seed(pg_engine)
    transition(pg_engine, case_id, "inspection_completed")
    cycle = create_cycle(pg_engine, case_id)
    if operation == "assess":
        cycle = write(
            pg_engine, SERVICE.submit_capa_cycle,
            capa_cycle_id=cycle["capa_cycle_id"],
            expected_version=cycle["row_version"],
            submitted_on=DAY, notes="received", reason=None,
        )
    parent = complete(pg_engine, approval(pg_engine, case_id, "PCT")) if stage == "CT" else None
    saved = approval(
        pg_engine, case_id, stage,
        parent["approval_submission_id"] if parent else None,
    ) if draft_mode == "dirty" else None
    with Session(pg_engine) as session:
        audit_before = session.scalar(select(func.count()).select_from(AuditEvent))
        approval_before = session.scalar(
            select(func.count()).select_from(InspectionApprovalSubmission)
            .where(InspectionApprovalSubmission.case_id == case_id)
        )
        if draft_mode == "new":
            pending = InspectionApprovalSubmission(
                case_id=case_id, stage=stage, round_no=1,
                reference="UNSUBMITTED-APPROVAL-INTENT",
                submitted_on=DAY,
                pct_submission_id=parent["approval_submission_id"] if parent else None,
            )
            session.add(pending)
        else:
            pending = session.get(
                InspectionApprovalSubmission, saved["approval_submission_id"]
            )
            pending.reference = "UNSUBMITTED-APPROVAL-EDIT"
        flushes = []

        def forbid_flush(*_args):
            flushes.append(True)
            raise AssertionError("CAPA mutation autoflushed an independent PCT/CT draft")

        event.listen(session, "before_flush", forbid_flush)
        try:
            with pytest.raises(HTTPException) as blocked:
                if operation == "update":
                    SERVICE.update_capa_cycle(
                        session, capa_cycle_id=cycle["capa_cycle_id"],
                        expected_version=cycle["row_version"], requested_on=DAY,
                        incoming_reference="CAPA-EDIT", notes="edited",
                        reason=None, user=USER,
                    )
                elif operation == "submit":
                    SERVICE.submit_capa_cycle(
                        session, capa_cycle_id=cycle["capa_cycle_id"],
                        expected_version=cycle["row_version"],
                        submitted_on=DAY, notes="received",
                        reason=None, user=USER,
                    )
                else:
                    SERVICE.assess_capa_cycle(
                        session, capa_cycle_id=cycle["capa_cycle_id"],
                        expected_version=cycle["row_version"], assessed_on=DAY,
                        assessor_name=None, result="accepted", notes="assessed",
                        reason=None, user=USER,
                    )
            assert blocked.value.status_code == 409
            assert "uncommitted" in str(blocked.value.detail).lower()
            assert not flushes
            if draft_mode == "new":
                assert pending in session.new
            else:
                assert pending in session.dirty
                assert pending.reference == "UNSUBMITTED-APPROVAL-EDIT"
            with session.no_autoflush:
                assert session.scalar(
                    select(func.count()).select_from(InspectionApprovalSubmission)
                    .where(InspectionApprovalSubmission.case_id == case_id)
                ) == approval_before
                if saved is not None:
                    assert session.scalar(
                        select(InspectionApprovalSubmission.reference).where(
                            InspectionApprovalSubmission.id == saved["approval_submission_id"]
                        )
                    ) == saved["reference"]
                assert session.scalar(
                    select(CapaCycle.status).where(
                        CapaCycle.id == cycle["capa_cycle_id"]
                    )
                ) == ("submitted" if operation == "assess" else "requested")
                assert session.scalar(select(func.count()).select_from(AuditEvent)) == audit_before
        finally:
            event.remove(session, "before_flush", forbid_flush)
            session.rollback()


@pytest.mark.parametrize("stage", ["PCT", "CT"])
@pytest.mark.parametrize("first_writer", ["capa_assess", "approval_complete"])
def test_independent_capa_assessment_and_approval_completion_serialize(pg_engine, stage, first_writer):
    """Two independent PostgreSQL writers serialize on Case and preserve both audits."""
    from threading import Event

    case_id, _site_id = seed(pg_engine)
    transition(pg_engine, case_id, "inspection_completed")
    cycle = create_cycle(pg_engine, case_id)
    cycle = write(
        pg_engine, SERVICE.submit_capa_cycle,
        capa_cycle_id=cycle["capa_cycle_id"],
        expected_version=cycle["row_version"],
        submitted_on=DAY, notes="synthetic submission", reason=None,
    )
    parent = complete(pg_engine, approval(pg_engine, case_id, "PCT")) if stage == "CT" else None
    submission = approval(
        pg_engine, case_id, stage,
        parent["approval_submission_id"] if parent else None,
    )
    with Session(pg_engine) as lookup:
        audit_before = lookup.scalar(select(func.count()).select_from(AuditEvent))
    first_flushed, second_started = Event(), Event()

    def first():
        with Session(pg_engine) as session:
            if first_writer == "capa_assess":
                SERVICE.assess_capa_cycle(
                    session, capa_cycle_id=cycle["capa_cycle_id"],
                    expected_version=cycle["row_version"], assessed_on=DAY,
                    assessor_name=None, result="accepted", notes="first assess",
                    reason="concurrent assess", user=USER,
                )
            else:
                SERVICE.complete_approval_submission(
                    session, approval_submission_id=submission["approval_submission_id"],
                    expected_version=submission["row_version"],
                    completed_on=DAY, completed_time=None,
                    reason="concurrent completion", user=USER,
                )
            session.flush()
            first_flushed.set()
            assert second_started.wait(20), "Second independent writer did not start"
            session.commit()
            return first_writer

    def second():
        assert first_flushed.wait(20), "First independent writer did not flush"
        second_started.set()
        other = "approval_complete" if first_writer == "capa_assess" else "capa_assess"
        with Session(pg_engine) as session:
            if other == "capa_assess":
                SERVICE.assess_capa_cycle(
                    session, capa_cycle_id=cycle["capa_cycle_id"],
                    expected_version=cycle["row_version"], assessed_on=DAY,
                    assessor_name=None, result="accepted", notes="second assess",
                    reason="concurrent assess", user=USER,
                )
            else:
                SERVICE.complete_approval_submission(
                    session, approval_submission_id=submission["approval_submission_id"],
                    expected_version=submission["row_version"], completed_on=DAY,
                    completed_time=None, reason="concurrent completion", user=USER,
                )
            session.commit()
            return other

    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(first)
        b = pool.submit(second)
        assert a.result(timeout=40) == first_writer
        assert b.result(timeout=40) != first_writer
    with Session(pg_engine) as session:
        assert session.scalar(
            select(CapaCycle.status).where(CapaCycle.id == cycle["capa_cycle_id"])
        ) == "accepted"
        assert session.scalar(
            select(InspectionApprovalSubmission.completed_on).where(
                InspectionApprovalSubmission.id == submission["approval_submission_id"]
            )
        ) == DAY
        assert session.scalar(
            select(func.count()).select_from(AuditEvent)
            .where(
                AuditEvent.entity_id == cycle["capa_cycle_id"],
                AuditEvent.action == "capa_cycle.assess",
            )
        ) == 1
        assert session.scalar(
            select(func.count()).select_from(AuditEvent)
            .where(
                AuditEvent.entity_id == submission["approval_submission_id"],
                AuditEvent.action == "inspection_approval_submission.complete",
            )
        ) == 1
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == audit_before + 2


@pytest.mark.parametrize("stage", ["PCT", "CT"])
@pytest.mark.parametrize("draft_mode", ["new", "dirty"])
def test_capa_creation_refuses_unsubmitted_approval_draft(pg_engine, stage, draft_mode):
    """A new CAPA round must not persist a staged PCT/CT intent."""
    case_id, _site_id = seed(pg_engine)
    transition(pg_engine, case_id, "inspection_completed")
    parent = complete(pg_engine, approval(pg_engine, case_id, "PCT")) if stage == "CT" else None
    existing = approval(
        pg_engine, case_id, stage,
        parent["approval_submission_id"] if parent else None,
    ) if draft_mode == "dirty" else None
    with Session(pg_engine) as session:
        case_version = session.get(Case, case_id).row_version
        audit_before = session.scalar(select(func.count()).select_from(AuditEvent))
        approval_before = session.scalar(
            select(func.count()).select_from(InspectionApprovalSubmission)
            .where(InspectionApprovalSubmission.case_id == case_id)
        )
        if draft_mode == "new":
            pending = InspectionApprovalSubmission(
                case_id=case_id, stage=stage, round_no=1,
                reference="UNSUBMITTED-APPROVAL-CAPA-CREATE",
                submitted_on=DAY,
                pct_submission_id=parent["approval_submission_id"] if parent else None,
            )
            session.add(pending)
        else:
            pending = session.get(
                InspectionApprovalSubmission, existing["approval_submission_id"]
            )
            pending.reference = "UNSUBMITTED-APPROVAL-EDIT-BEFORE-CAPA"
        flushes = []

        def forbid_flush(*_args):
            flushes.append(True)
            raise AssertionError("CAPA creation autoflushed a staged PCT/CT intent")

        event.listen(session, "before_flush", forbid_flush)
        try:
            with pytest.raises(HTTPException) as blocked:
                SERVICE.create_capa_cycle(
                    session, case_id=case_id, expected_case_version=case_version,
                    requested_on=DAY, incoming_reference="CAPA-CREATE-REF",
                    notes="new CAPA", reason="independent intent", user=USER,
                )
            assert blocked.value.status_code == 409
            assert "uncommitted" in str(blocked.value.detail).lower()
            assert not flushes
            if draft_mode == "new":
                assert pending in session.new
            else:
                assert pending in session.dirty
                assert pending.reference == "UNSUBMITTED-APPROVAL-EDIT-BEFORE-CAPA"
            with session.no_autoflush:
                assert session.scalar(
                    select(func.count()).select_from(InspectionApprovalSubmission)
                    .where(InspectionApprovalSubmission.case_id == case_id)
                ) == approval_before
                if existing is not None:
                    assert session.scalar(
                        select(InspectionApprovalSubmission.reference).where(
                            InspectionApprovalSubmission.id == existing["approval_submission_id"]
                        )
                    ) == existing["reference"]
                assert session.scalar(
                    select(func.count()).select_from(CapaCycle)
                    .where(CapaCycle.case_id == case_id)
                ) == 0
                assert session.scalar(select(func.count()).select_from(AuditEvent)) == audit_before
        finally:
            event.remove(session, "before_flush", forbid_flush)
            session.rollback()


@pytest.mark.parametrize("intent", ["legal_refusal", "certificate"])
@pytest.mark.parametrize("prior_round", ["none", "rejected"])
def test_capa_creation_refuses_pending_legal_intent(pg_engine, intent, prior_round):
    """CAPA create cannot commit an unsubmitted legal decision or certificate."""
    case_id, site_id = seed(pg_engine)
    transition(pg_engine, case_id, "inspection_completed")
    if prior_round == "rejected":
        assess_cycle(pg_engine, create_cycle(pg_engine, case_id), "rejected")
    with Session(pg_engine) as session:
        case_version = session.get(Case, case_id).row_version
        audit_before = session.scalar(select(func.count()).select_from(AuditEvent))
        cycles_before = session.scalar(
            select(func.count()).select_from(CapaCycle).where(CapaCycle.case_id == case_id)
        )
        if intent == "legal_refusal":
            actor_id = session.scalar(
                select(AuditEvent.actor_user_id)
                .where(AuditEvent.actor_user_id.is_not(None)).limit(1)
            )
            assert actor_id is not None
            pending = CaseCertificateNonissuanceDecision(
                case_id=case_id, decided_on=DAY,
                decision_reference="UNSUBMITTED-LEGAL-REFUSAL-CAPA-CREATE",
                explanation="A separate unapproved refusal intent",
                recorded_by_user_id=actor_id,
            )
            model = CaseCertificateNonissuanceDecision
        else:
            pending = Certificate(
                case_id=case_id, site_id=site_id, certificate_type="GMP",
                issuance_basis="inspection_case", latest_flag=False,
            )
            model = Certificate
        session.add(pending)
        flushes = []

        def forbid_flush(*_args):
            flushes.append(True)
            raise AssertionError("CAPA creation autoflushed a separate legal intent")

        event.listen(session, "before_flush", forbid_flush)
        try:
            with pytest.raises(HTTPException) as blocked:
                SERVICE.create_capa_cycle(
                    session, case_id=case_id, expected_case_version=case_version,
                    requested_on=DAY, incoming_reference="ANOTHER-CAPA-ROUND",
                    notes="new CAPA independent of legal decision", reason=None, user=USER,
                )
            assert blocked.value.status_code == 409
            assert "uncommitted" in str(blocked.value.detail).lower()
            assert not flushes
            assert pending in session.new
            with session.no_autoflush:
                assert session.scalar(
                    select(func.count()).select_from(model).where(model.case_id == case_id)
                ) == 0
                assert session.scalar(
                    select(func.count()).select_from(CapaCycle)
                    .where(CapaCycle.case_id == case_id)
                ) == cycles_before
                assert session.scalar(select(func.count()).select_from(AuditEvent)) == audit_before
        finally:
            event.remove(session, "before_flush", forbid_flush)
            session.rollback()


@pytest.mark.parametrize("intent", ["legal_refusal", "certificate"])
@pytest.mark.parametrize("operation", ["create", "update", "submit", "assess"])
def test_capa_mutation_refuses_dirty_legal_intent(pg_engine, intent, operation):
    """CAPA cannot persist an unsubmitted edit to an independent legal fact."""
    case_id, site_id = seed(pg_engine)
    transition(pg_engine, case_id, "inspection_completed")
    target = create_cycle(pg_engine, case_id) if operation != "create" else None
    if operation == "assess":
        target = write(
            pg_engine, SERVICE.submit_capa_cycle,
            capa_cycle_id=target["capa_cycle_id"],
            expected_version=target["row_version"],
            submitted_on=DAY, notes="submitted for assessment", reason=None,
        )
    with Session(pg_engine) as setup:
        if intent == "legal_refusal":
            actor_id = setup.scalar(
                select(AuditEvent.actor_user_id)
                .where(AuditEvent.actor_user_id.is_not(None)).limit(1)
            )
            assert actor_id is not None
            record = CaseCertificateNonissuanceDecision(
                case_id=case_id, decided_on=DAY,
                decision_reference="COMMITTED-LEGAL-REFUSAL",
                explanation="Original legally recorded explanation",
                recorded_by_user_id=actor_id,
            )
            column = CaseCertificateNonissuanceDecision.explanation
            original = "Original legally recorded explanation"
            modified = "Unsubmitted modified refusal explanation"
        else:
            record = Certificate(
                case_id=case_id, site_id=site_id, certificate_type="GMP",
                issuance_basis="inspection_case", latest_flag=False,
            )
            column = Certificate.latest_flag
            original = False
            modified = True
        setup.add(record)
        setup.commit()
        record_id = record.id
    with Session(pg_engine) as session:
        case_version = session.get(Case, case_id).row_version
        audit_before = session.scalar(select(func.count()).select_from(AuditEvent))
        cycles_before = session.scalar(
            select(func.count()).select_from(CapaCycle).where(CapaCycle.case_id == case_id)
        )
        cached = session.get(type(record), record_id)
        if intent == "legal_refusal":
            cached.explanation = modified
        else:
            cached.latest_flag = modified
        flushes = []

        def forbid_flush(*_args):
            flushes.append(True)
            raise AssertionError("CAPA mutation autoflushed an unsubmitted legal edit")

        event.listen(session, "before_flush", forbid_flush)
        try:
            with pytest.raises(HTTPException) as blocked:
                if operation == "create":
                    SERVICE.create_capa_cycle(
                        session, case_id=case_id, expected_case_version=case_version,
                        requested_on=DAY, incoming_reference="NEW-CAPA",
                        notes="not authorized to save legal edits", reason=None, user=USER,
                    )
                elif operation == "update":
                    SERVICE.update_capa_cycle(
                        session, capa_cycle_id=target["capa_cycle_id"],
                        expected_version=target["row_version"],
                        requested_on=DAY, incoming_reference="UPDATED-CAPA",
                        notes="updated", reason=None, user=USER,
                    )
                elif operation == "submit":
                    SERVICE.submit_capa_cycle(
                        session, capa_cycle_id=target["capa_cycle_id"],
                        expected_version=target["row_version"],
                        submitted_on=DAY, notes="submitted", reason=None, user=USER,
                    )
                else:
                    SERVICE.assess_capa_cycle(
                        session, capa_cycle_id=target["capa_cycle_id"],
                        expected_version=target["row_version"], assessed_on=DAY,
                        assessor_name=None, result="accepted", notes="assessed",
                        reason=None, user=USER,
                    )
            assert blocked.value.status_code == 409
            assert "uncommitted" in str(blocked.value.detail).lower()
            assert not flushes
            assert cached in session.dirty
            with session.no_autoflush:
                assert session.scalar(
                    select(column).where(type(record).id == record_id)
                ) == original
                assert session.scalar(
                    select(func.count()).select_from(CapaCycle)
                    .where(CapaCycle.case_id == case_id)
                ) == cycles_before
                if target is not None:
                    assert session.scalar(
                        select(CapaCycle.status).where(CapaCycle.id == target["capa_cycle_id"])
                    ) == ("submitted" if operation == "assess" else "requested")
                assert session.scalar(select(func.count()).select_from(AuditEvent)) == audit_before
        finally:
            event.remove(session, "before_flush", forbid_flush)
            session.rollback()


@pytest.mark.parametrize("operation", ["create", "update", "submit", "assess"])
@pytest.mark.parametrize("draft_mode", ["new", "dirty"])
def test_capa_mutation_refuses_pending_certificate_version(pg_engine, operation, draft_mode):
    """A CAPA transaction may not write an unrelated same-Case GCN version draft."""
    case_id, site_id = seed(pg_engine)
    transition(pg_engine, case_id, "inspection_completed")
    target = create_cycle(pg_engine, case_id) if operation != "create" else None
    if operation == "assess":
        target = write(
            pg_engine, SERVICE.submit_capa_cycle,
            capa_cycle_id=target["capa_cycle_id"],
            expected_version=target["row_version"],
            submitted_on=DAY, notes="ready for assessment", reason=None,
        )
    with Session(pg_engine) as setup:
        certificate = Certificate(
            case_id=case_id, site_id=site_id, certificate_type="GMP",
            issuance_basis="inspection_case", latest_flag=False,
        )
        setup.add(certificate)
        setup.flush()
        certificate_id = certificate.id
        if draft_mode == "dirty":
            version = CertificateVersion(
                certificate_id=certificate_id, version_no=1,
                certificate_number="GCN-COMMITTED-ORIGINAL",
                lifecycle_state="DRAFT", is_latest_version=False,
            )
            setup.add(version)
            setup.flush()
            version_id = version.id
        setup.commit()
    with Session(pg_engine) as session:
        case_version = session.get(Case, case_id).row_version
        audits_before = session.scalar(select(func.count()).select_from(AuditEvent))
        cycles_before = session.scalar(
            select(func.count()).select_from(CapaCycle)
            .where(CapaCycle.case_id == case_id)
        )
        if draft_mode == "new":
            staged = CertificateVersion(
                certificate_id=certificate_id, version_no=1,
                certificate_number="GCN-UNSUBMITTED-NEW",
                lifecycle_state="DRAFT", is_latest_version=False,
            )
            session.add(staged)
        else:
            staged = session.get(CertificateVersion, version_id)
            staged.certificate_number = "GCN-UNSUBMITTED-EDIT"
        flushes = []

        def forbid_flush(*_args):
            flushes.append(True)
            raise AssertionError("CAPA mutation autoflushed a separate CertificateVersion draft")

        event.listen(session, "before_flush", forbid_flush)
        try:
            with pytest.raises(HTTPException) as blocked:
                if operation == "create":
                    SERVICE.create_capa_cycle(
                        session, case_id=case_id, expected_case_version=case_version,
                        requested_on=DAY, incoming_reference="CAPA-VERSION",
                        notes="independent CAPA", reason=None, user=USER,
                    )
                elif operation == "update":
                    SERVICE.update_capa_cycle(
                        session, capa_cycle_id=target["capa_cycle_id"],
                        expected_version=target["row_version"],
                        requested_on=DAY, incoming_reference="CAPA-VERSION-EDIT",
                        notes="updated", reason=None, user=USER,
                    )
                elif operation == "submit":
                    SERVICE.submit_capa_cycle(
                        session, capa_cycle_id=target["capa_cycle_id"],
                        expected_version=target["row_version"],
                        submitted_on=DAY, notes="submitted", reason=None, user=USER,
                    )
                else:
                    SERVICE.assess_capa_cycle(
                        session, capa_cycle_id=target["capa_cycle_id"],
                        expected_version=target["row_version"], assessed_on=DAY,
                        assessor_name=None, result="accepted", notes="assessed",
                        reason=None, user=USER,
                    )
            assert blocked.value.status_code == 409
            assert "uncommitted" in str(blocked.value.detail).lower()
            assert not flushes
            if draft_mode == "new":
                assert staged in session.new
            else:
                assert staged in session.dirty
                assert staged.certificate_number == "GCN-UNSUBMITTED-EDIT"
            with session.no_autoflush:
                assert session.scalar(
                    select(func.count()).select_from(CertificateVersion)
                    .where(CertificateVersion.certificate_id == certificate_id)
                ) == (1 if draft_mode == "dirty" else 0)
                if draft_mode == "dirty":
                    assert session.scalar(
                        select(CertificateVersion.certificate_number)
                        .where(CertificateVersion.id == version_id)
                    ) == "GCN-COMMITTED-ORIGINAL"
                assert session.scalar(
                    select(func.count()).select_from(CapaCycle)
                    .where(CapaCycle.case_id == case_id)
                ) == cycles_before
                if target is not None:
                    assert session.scalar(
                        select(CapaCycle.status)
                        .where(CapaCycle.id == target["capa_cycle_id"])
                    ) == ("submitted" if operation == "assess" else "requested")
                assert session.scalar(select(func.count()).select_from(AuditEvent)) == audits_before
        finally:
            event.remove(session, "before_flush", forbid_flush)
            session.rollback()


@pytest.mark.parametrize("operation", ["create", "update", "submit", "assess"])
@pytest.mark.parametrize("draft_mode", ["new", "dirty"])
def test_capa_mutation_refuses_pending_certificate_scope(pg_engine, operation, draft_mode):
    """A CAPA flush cannot insert or edit a different legal GCN version scope."""
    case_id, site_id = seed(pg_engine)
    transition(pg_engine, case_id, "inspection_completed")
    target = create_cycle(pg_engine, case_id) if operation != "create" else None
    if operation == "assess":
        target = write(
            pg_engine, SERVICE.submit_capa_cycle,
            capa_cycle_id=target["capa_cycle_id"],
            expected_version=target["row_version"],
            submitted_on=DAY, notes="submitted for assessment", reason=None,
        )
    with Session(pg_engine) as setup:
        certificate = Certificate(
            case_id=case_id, site_id=site_id, certificate_type="GMP",
            issuance_basis="inspection_case", latest_flag=False,
        )
        setup.add(certificate)
        setup.flush()
        version = CertificateVersion(
            certificate_id=certificate.id, version_no=1,
            certificate_number="GCN-COMMITTED-ORIGINAL",
            lifecycle_state="DRAFT", is_latest_version=False,
        )
        setup.add(version)
        setup.flush()
        version_id = version.id
        if draft_mode == "dirty":
            scope = CertificateScope(
                certificate_version_id=version_id, scope_key="SCOPE-A",
                scope_text="Original approved source text",
                language_code="vi", sort_order=1,
            )
            setup.add(scope)
            setup.flush()
            scope_id = scope.id
        setup.commit()
    with Session(pg_engine) as session:
        case_version = session.get(Case, case_id).row_version
        audits_before = session.scalar(select(func.count()).select_from(AuditEvent))
        cycles_before = session.scalar(
            select(func.count()).select_from(CapaCycle)
            .where(CapaCycle.case_id == case_id)
        )
        if draft_mode == "new":
            staged = CertificateScope(
                certificate_version_id=version_id, scope_key="SCOPE-NEW",
                scope_text="Unsubmitted scope", language_code="vi", sort_order=1,
            )
            session.add(staged)
        else:
            staged = session.get(CertificateScope, scope_id)
            staged.scope_text = "Unsubmitted changed certificate scope"
        flushes = []

        def forbid_flush(*_args):
            flushes.append(True)
            raise AssertionError("CAPA mutation autoflushed separate CertificateScope content")

        event.listen(session, "before_flush", forbid_flush)
        try:
            with pytest.raises(HTTPException) as blocked:
                if operation == "create":
                    SERVICE.create_capa_cycle(
                        session, case_id=case_id, expected_case_version=case_version,
                        requested_on=DAY, incoming_reference="CAPA-SCOPE",
                        notes="independent CAPA", reason=None, user=USER,
                    )
                elif operation == "update":
                    SERVICE.update_capa_cycle(
                        session, capa_cycle_id=target["capa_cycle_id"],
                        expected_version=target["row_version"],
                        requested_on=DAY, incoming_reference="CAPA-SCOPE-EDIT",
                        notes="updated", reason=None, user=USER,
                    )
                elif operation == "submit":
                    SERVICE.submit_capa_cycle(
                        session, capa_cycle_id=target["capa_cycle_id"],
                        expected_version=target["row_version"],
                        submitted_on=DAY, notes="submitted", reason=None, user=USER,
                    )
                else:
                    SERVICE.assess_capa_cycle(
                        session, capa_cycle_id=target["capa_cycle_id"],
                        expected_version=target["row_version"], assessed_on=DAY,
                        assessor_name=None, result="accepted", notes="assessed",
                        reason=None, user=USER,
                    )
            assert blocked.value.status_code == 409
            assert "uncommitted" in str(blocked.value.detail).lower()
            assert not flushes
            if draft_mode == "new":
                assert staged in session.new
            else:
                assert staged in session.dirty
            with session.no_autoflush:
                assert session.scalar(
                    select(func.count()).select_from(CertificateScope)
                    .where(CertificateScope.certificate_version_id == version_id)
                ) == (1 if draft_mode == "dirty" else 0)
                if draft_mode == "dirty":
                    assert session.scalar(
                        select(CertificateScope.scope_text).where(CertificateScope.id == scope_id)
                    ) == "Original approved source text"
                assert session.scalar(
                    select(func.count()).select_from(CapaCycle)
                    .where(CapaCycle.case_id == case_id)
                ) == cycles_before
                if target is not None:
                    assert session.scalar(
                        select(CapaCycle.status).where(CapaCycle.id == target["capa_cycle_id"])
                    ) == ("submitted" if operation == "assess" else "requested")
                assert session.scalar(select(func.count()).select_from(AuditEvent)) == audits_before
        finally:
            event.remove(session, "before_flush", forbid_flush)
            session.rollback()


@pytest.mark.parametrize("operation", ["issue", "edit_version"])
@pytest.mark.parametrize("stage", ["PCT", "CT"])
@pytest.mark.parametrize("draft_mode", ["new", "dirty"])
def test_certificate_mutation_refuses_pending_approval_round(
    pg_engine, operation, stage, draft_mode,
):
    """GCN issuance/edit must not persist an independent PCT/CT operator draft."""
    case_id, site_id = seed(pg_engine)
    transition(pg_engine, case_id, "inspection_completed")
    transition(pg_engine, case_id, "awaiting_certificate_decision")
    pct = complete(pg_engine, approval(pg_engine, case_id, "PCT"))
    ct = complete(pg_engine, approval(pg_engine, case_id, "CT", pct["approval_submission_id"]))
    candidate = issue(pg_engine, case_id, site_id) if operation == "edit_version" else None
    existing = pct if stage == "PCT" else ct

    with Session(pg_engine) as session:
        audits_before = session.scalar(select(func.count()).select_from(AuditEvent))
        certificates_before = session.scalar(
            select(func.count()).select_from(Certificate)
            .where(Certificate.case_id == case_id)
        )
        if draft_mode == "new":
            pending = InspectionApprovalSubmission(
                case_id=case_id, stage=stage, round_no=2,
                reference="UNSUBMITTED-APPROVAL-DURING-GCN",
                submitted_on=DAY,
                pct_submission_id=pct["approval_submission_id"] if stage == "CT" else None,
            )
            session.add(pending)
        else:
            pending = session.get(
                InspectionApprovalSubmission, existing["approval_submission_id"]
            )
            pending.reference = "UNSUBMITTED-PCT-CT-EDIT-DURING-GCN"
        flushes = []

        def forbid_flush(*_args):
            flushes.append(True)
            raise AssertionError("GCN mutation autoflushed an unsubmitted approval draft")

        event.listen(session, "before_flush", forbid_flush)
        try:
            with pytest.raises(HTTPException) as blocked:
                if operation == "issue":
                    SERVICE.issue_certificate(
                        session, site_id=site_id, case_id=case_id,
                        certificate_type="GMP", issuance_basis="inspection_case",
                        certificate_number="UNRELATED-GCN-ISSUE", issue_date=DAY,
                        expiry_date=date(2027, 10, 1),
                        scopes=[], reason="synthetic approval draft guard", user=USER,
                    )
                else:
                    SERVICE.upsert_certificate_latest_version(
                        session, certificate_id=candidate["certificate_id"],
                        expected_version=candidate["row_version"],
                        certificate_number="UNRELATED-GCN-VERSION-EDIT",
                        issue_date=DAY, expiry_date=date(2027, 10, 1),
                        scopes=[], reason="synthetic approval draft guard", user=USER,
                    )
            assert blocked.value.status_code == 409
            assert "uncommitted" in str(blocked.value.detail).lower()
            assert not flushes
            if draft_mode == "new":
                assert pending in session.new
            else:
                assert pending in session.dirty
                assert pending.reference == "UNSUBMITTED-PCT-CT-EDIT-DURING-GCN"
            with session.no_autoflush:
                assert session.scalar(
                    select(func.count()).select_from(Certificate)
                    .where(Certificate.case_id == case_id)
                ) == certificates_before
                assert session.scalar(
                    select(func.count()).select_from(InspectionApprovalSubmission)
                    .where(InspectionApprovalSubmission.case_id == case_id)
                ) == 2
                if draft_mode == "dirty":
                    assert session.scalar(
                        select(InspectionApprovalSubmission.reference).where(
                            InspectionApprovalSubmission.id == existing["approval_submission_id"]
                        )
                    ) == existing["reference"]
                if candidate is not None:
                    assert session.scalar(
                        select(CertificateVersion.certificate_number).where(
                            CertificateVersion.id == candidate["latest_version_id"]
                        )
                    ) == candidate["certificate_number"]
                assert session.scalar(select(func.count()).select_from(AuditEvent)) == audits_before
        finally:
            event.remove(session, "before_flush", forbid_flush)
            session.rollback()


@pytest.mark.parametrize("operation", ["issue", "edit_version"])
@pytest.mark.parametrize("draft_mode", ["new", "dirty", "deleted"])
def test_certificate_mutation_refuses_pending_capa_draft(
    pg_engine, operation, draft_mode,
):
    """A GCN mutation cannot flush a second CAPA round, local edit or deletion."""
    case_id, site_id = seed(pg_engine)
    transition(pg_engine, case_id, "inspection_completed")
    cycle = create_cycle(pg_engine, case_id)
    assessed = assess_cycle(pg_engine, cycle, "accepted")
    transition(pg_engine, case_id, "awaiting_certificate_decision")
    pct = complete(pg_engine, approval(pg_engine, case_id, "PCT"))
    complete(pg_engine, approval(pg_engine, case_id, "CT", pct["approval_submission_id"]))
    candidate = issue(pg_engine, case_id, site_id) if operation == "edit_version" else None
    with Session(pg_engine) as session:
        audit_before = session.scalar(select(func.count()).select_from(AuditEvent))
        certificates_before = session.scalar(
            select(func.count()).select_from(Certificate)
            .where(Certificate.case_id == case_id)
        )
        rounds_before = session.scalar(
            select(func.count()).select_from(CapaCycle).where(CapaCycle.case_id == case_id)
        )
        if draft_mode == "new":
            pending = CapaCycle(
                case_id=case_id, round_no=2,
                requested_on=DAY, incoming_reference="UNSUBMITTED-CAPA-GCN",
                notes="second round is not yet requested",
            )
            session.add(pending)
        else:
            pending = session.get(CapaCycle, assessed["capa_cycle_id"])
            if draft_mode == "dirty":
                pending.notes = "UNSUBMITTED-CAPA-EDIT-DURING-GCN"
            else:
                session.delete(pending)
        flushes = []

        def forbid_flush(*_args):
            flushes.append(True)
            raise AssertionError("GCN mutation autoflushed a separate CAPA draft")

        event.listen(session, "before_flush", forbid_flush)
        try:
            with pytest.raises(HTTPException) as blocked:
                if operation == "issue":
                    SERVICE.issue_certificate(
                        session, site_id=site_id, case_id=case_id,
                        certificate_type="GMP", issuance_basis="inspection_case",
                        certificate_number="GCN-DURING-CAPA-DRAFT",
                        issue_date=DAY, expiry_date=date(2027, 10, 1),
                        scopes=[], reason="synthetic CAPA draft guard", user=USER,
                    )
                else:
                    SERVICE.upsert_certificate_latest_version(
                        session, certificate_id=candidate["certificate_id"],
                        expected_version=candidate["row_version"],
                        certificate_number="EDIT-DURING-CAPA-DRAFT",
                        issue_date=DAY, expiry_date=date(2027, 10, 1),
                        scopes=[], reason="synthetic CAPA draft guard", user=USER,
                    )
            assert blocked.value.status_code == 409
            assert "uncommitted" in str(blocked.value.detail).lower()
            assert not flushes
            if draft_mode == "new":
                assert pending in session.new
            elif draft_mode == "dirty":
                assert pending in session.dirty
                assert pending.notes == "UNSUBMITTED-CAPA-EDIT-DURING-GCN"
            else:
                assert pending in session.deleted
            with session.no_autoflush:
                assert session.scalar(
                    select(func.count()).select_from(CapaCycle).where(CapaCycle.case_id == case_id)
                ) == rounds_before
                assert session.scalar(
                    select(CapaCycle.status).where(CapaCycle.id == assessed["capa_cycle_id"])
                ) == "accepted"
                assert session.scalar(
                    select(func.count()).select_from(Certificate)
                    .where(Certificate.case_id == case_id)
                ) == certificates_before
                if candidate is not None:
                    assert session.scalar(
                        select(CertificateVersion.certificate_number).where(
                            CertificateVersion.id == candidate["latest_version_id"]
                        )
                    ) == candidate["certificate_number"]
                assert session.scalar(select(func.count()).select_from(AuditEvent)) == audit_before
        finally:
            event.remove(session, "before_flush", forbid_flush)
            session.rollback()


def test_certificate_version_edit_refuses_pending_nonissuance_before_autoflush(pg_engine):
    """Editing a certificate version must not commit an independent legal refusal."""
    case_id, site_id = seed(pg_engine)
    transition(pg_engine, case_id, "inspection_completed")
    transition(pg_engine, case_id, "awaiting_certificate_decision")
    pct = complete(pg_engine, approval(pg_engine, case_id, "PCT"))
    complete(pg_engine, approval(pg_engine, case_id, "CT", pct["approval_submission_id"]))
    candidate = issue(pg_engine, case_id, site_id)
    with Session(pg_engine) as session:
        actor_id = session.scalar(
            select(AuditEvent.actor_user_id)
            .where(AuditEvent.actor_user_id.is_not(None)).limit(1)
        )
        assert actor_id is not None
        audit_before = session.scalar(select(func.count()).select_from(AuditEvent))
        pending = CaseCertificateNonissuanceDecision(
            case_id=case_id, decided_on=DAY,
            decision_reference="UNSUBMITTED-REFUSAL-DURING-VERSION-EDIT",
            explanation="Independent operator draft must survive",
            recorded_by_user_id=actor_id,
        )
        session.add(pending)
        flushes = []

        def forbid_flush(*_args):
            flushes.append(True)
            raise AssertionError("Certificate version edit autoflushed legal refusal draft")

        event.listen(session, "before_flush", forbid_flush)
        try:
            with pytest.raises(HTTPException) as blocked:
                SERVICE.upsert_certificate_latest_version(
                    session, certificate_id=candidate["certificate_id"],
                    expected_version=candidate["row_version"],
                    certificate_number="UNRELATED-VERSION-EDIT",
                    issue_date=DAY, expiry_date=date(2027, 10, 1),
                    scopes=[], reason="synthetic legal refusal draft guard", user=USER,
                )
            assert blocked.value.status_code == 409
            assert "uncommitted" in str(blocked.value.detail).lower()
            assert not flushes
            assert pending in session.new
            with session.no_autoflush:
                assert session.scalar(
                    select(func.count()).select_from(CaseCertificateNonissuanceDecision)
                    .where(CaseCertificateNonissuanceDecision.case_id == case_id)
                ) == 0
                assert session.scalar(
                    select(CertificateVersion.certificate_number)
                    .where(CertificateVersion.id == candidate["latest_version_id"])
                ) == candidate["certificate_number"]
                assert session.scalar(select(func.count()).select_from(AuditEvent)) == audit_before
        finally:
            event.remove(session, "before_flush", forbid_flush)
            session.rollback()


@pytest.mark.parametrize("intent", ["capa", "approval_pct", "approval_ct", "legal_refusal"])
def test_certificate_promotion_rejects_pending_same_case_workflow_intent(pg_engine, intent):
    """Promotion must not autoflush separately staged legal or workflow intents."""
    case_id, site_id = seed(pg_engine)
    transition(pg_engine, case_id, "inspection_completed")
    transition(pg_engine, case_id, "awaiting_certificate_decision")
    pct = complete(pg_engine, approval(pg_engine, case_id, "PCT"))
    complete(pg_engine, approval(pg_engine, case_id, "CT", pct["approval_submission_id"]))
    candidate = issue(pg_engine, case_id, site_id)

    with Session(pg_engine) as session:
        audit_before = session.scalar(select(func.count()).select_from(AuditEvent))
        if intent == "capa":
            pending = CapaCycle(
                case_id=case_id, round_no=1, requested_on=DAY,
                incoming_reference="UNSUBMITTED-CAPA-PROMOTION", notes="independent draft",
            )
            model = CapaCycle
        elif intent in {"approval_pct", "approval_ct"}:
            stage = "PCT" if intent == "approval_pct" else "CT"
            pending = InspectionApprovalSubmission(
                case_id=case_id, stage=stage, round_no=2,
                reference="UNSUBMITTED-APPROVAL-PROMOTION", submitted_on=DAY,
                pct_submission_id=pct["approval_submission_id"] if stage == "CT" else None,
            )
            model = InspectionApprovalSubmission
        else:
            actor_id = session.scalar(
                select(AuditEvent.actor_user_id)
                .where(AuditEvent.actor_user_id.is_not(None)).limit(1)
            )
            assert actor_id is not None
            pending = CaseCertificateNonissuanceDecision(
                case_id=case_id, decided_on=DAY,
                decision_reference="UNSUBMITTED-REFUSAL-PROMOTION",
                explanation="independent legal refusal draft",
                recorded_by_user_id=actor_id,
            )
            model = CaseCertificateNonissuanceDecision
        count_before = session.scalar(
            select(func.count()).select_from(model).where(model.case_id == case_id)
        )
        session.add(pending)
        flushes = []

        def forbid_flush(*_args):
            flushes.append(True)
            raise AssertionError("Certificate promotion autoflushed an independent Case draft")

        event.listen(session, "before_flush", forbid_flush)
        try:
            with pytest.raises(HTTPException) as blocked:
                SERVICE.promote_certificate_current(
                    session, certificate_id=candidate["certificate_id"],
                    expected_version=candidate["row_version"],
                    reason="synthetic pending intent guard", user=USER,
                )
            assert blocked.value.status_code == 409
            assert "uncommitted" in str(blocked.value.detail).lower()
            assert not flushes
            assert pending in session.new
            with session.no_autoflush:
                assert session.scalar(
                    select(func.count()).select_from(model).where(model.case_id == case_id)
                ) == count_before
                assert session.scalar(
                    select(Certificate.latest_flag).where(Certificate.id == candidate["certificate_id"])
                ) is False
                assert session.scalar(select(func.count()).select_from(AuditEvent)) == audit_before
        finally:
            event.remove(session, "before_flush", forbid_flush)
            session.rollback()


@pytest.mark.parametrize("draft_kind", ["capa_dirty", "pct_dirty", "ct_dirty", "capa_deleted"])
def test_certificate_promotion_refuses_dirty_or_deleted_case_workflow_draft(pg_engine, draft_kind):
    """Promotion must not flush changed persisted workflow rows or local CAPA delete."""
    case_id, site_id = seed(pg_engine)
    transition(pg_engine, case_id, "inspection_completed")
    cycle = create_cycle(pg_engine, case_id)
    assessed = assess_cycle(pg_engine, cycle, "accepted")
    transition(pg_engine, case_id, "awaiting_certificate_decision")
    pct = complete(pg_engine, approval(pg_engine, case_id, "PCT"))
    ct = complete(pg_engine, approval(pg_engine, case_id, "CT", pct["approval_submission_id"]))
    candidate = issue(pg_engine, case_id, site_id)
    with Session(pg_engine) as session:
        audit_before = session.scalar(select(func.count()).select_from(AuditEvent))
        if draft_kind.startswith("capa"):
            pending = session.get(CapaCycle, assessed["capa_cycle_id"])
            if draft_kind == "capa_deleted":
                session.delete(pending)
            else:
                pending.notes = "UNSUBMITTED-CAPA-DRAFT-DURING-PROMOTION"
        else:
            approval_id = pct["approval_submission_id"] if draft_kind == "pct_dirty" else ct["approval_submission_id"]
            pending = session.get(InspectionApprovalSubmission, approval_id)
            original_reference = pending.reference
            pending.reference = "UNSUBMITTED-APPROVAL-DRAFT-DURING-PROMOTION"

        flushes = []

        def forbid_flush(*_args):
            flushes.append(True)
            raise AssertionError("Certificate promotion autoflushed a dirty workflow row")

        event.listen(session, "before_flush", forbid_flush)
        try:
            with pytest.raises(HTTPException) as blocked:
                SERVICE.promote_certificate_current(
                    session, certificate_id=candidate["certificate_id"],
                    expected_version=candidate["row_version"],
                    reason="synthetic dirty workflow guard", user=USER,
                )
            assert blocked.value.status_code == 409
            assert "uncommitted" in str(blocked.value.detail).lower()
            assert not flushes
            if draft_kind == "capa_deleted":
                assert pending in session.deleted
            else:
                assert pending in session.dirty
            with session.no_autoflush:
                assert session.scalar(
                    select(Certificate.latest_flag).where(Certificate.id == candidate["certificate_id"])
                ) is False
                assert session.scalar(select(func.count()).select_from(AuditEvent)) == audit_before
                if draft_kind.startswith("capa"):
                    assert session.scalar(
                        select(CapaCycle.status).where(CapaCycle.id == assessed["capa_cycle_id"])
                    ) == "accepted"
                else:
                    assert session.scalar(
                        select(InspectionApprovalSubmission.reference)
                        .where(InspectionApprovalSubmission.id == pending.id)
                    ) == original_reference
        finally:
            event.remove(session, "before_flush", forbid_flush)
            session.rollback()


def test_certificate_promotion_refuses_unsubmitted_same_case_version(pg_engine):
    """Promotion must not autoflush a different unsubmitted GCN version."""
    case_id, site_id = seed(pg_engine)
    transition(pg_engine, case_id, "inspection_completed")
    transition(pg_engine, case_id, "awaiting_certificate_decision")
    candidate = issue(pg_engine, case_id, site_id)
    with Session(pg_engine) as session:
        audit_before = session.scalar(select(func.count()).select_from(AuditEvent))
        version_count = session.scalar(
            select(func.count()).select_from(CertificateVersion)
            .where(CertificateVersion.certificate_id == candidate["certificate_id"])
        )
        pending = CertificateVersion(
            certificate_id=candidate["certificate_id"], version_no=2,
            certificate_number="UNSUBMITTED-SECOND-VERSION",
            lifecycle_state="DRAFT", is_latest_version=False,
        )
        session.add(pending)
        flushes = []

        def forbid_flush(*_args):
            flushes.append(True)
            raise AssertionError("Certificate promotion autoflushed an unsubmitted version")

        event.listen(session, "before_flush", forbid_flush)
        try:
            with pytest.raises(HTTPException) as blocked:
                SERVICE.promote_certificate_current(
                    session, certificate_id=candidate["certificate_id"],
                    expected_version=candidate["row_version"],
                    reason="synthetic pending version guard", user=USER,
                )
            assert blocked.value.status_code == 409
            assert "uncommitted" in str(blocked.value.detail).lower()
            assert not flushes
            assert pending in session.new
            with session.no_autoflush:
                assert session.scalar(
                    select(func.count()).select_from(CertificateVersion)
                    .where(CertificateVersion.certificate_id == candidate["certificate_id"])
                ) == version_count
                assert session.scalar(
                    select(Certificate.latest_flag).where(Certificate.id == candidate["certificate_id"])
                ) is False
                assert session.scalar(select(func.count()).select_from(AuditEvent)) == audit_before
        finally:
            event.remove(session, "before_flush", forbid_flush)
            session.rollback()


@pytest.mark.parametrize("draft_mode", ["dirty", "deleted"])
def test_certificate_promotion_refuses_nonlatest_version_operator_draft(pg_engine, draft_mode):
    """A separate committed version's pending edit/delete cannot ride promotion."""
    case_id, site_id = seed(pg_engine)
    transition(pg_engine, case_id, "inspection_completed")
    transition(pg_engine, case_id, "awaiting_certificate_decision")
    candidate = issue(pg_engine, case_id, site_id)
    with Session(pg_engine) as setup:
        historical = CertificateVersion(
            certificate_id=candidate["certificate_id"], version_no=2,
            certificate_number="COMMITTED-NONLATEST-VERSION",
            lifecycle_state="DRAFT", is_latest_version=False,
        )
        setup.add(historical)
        setup.flush()
        historical_id = historical.id
        setup.commit()
    with Session(pg_engine) as session:
        audit_before = session.scalar(select(func.count()).select_from(AuditEvent))
        pending = session.get(CertificateVersion, historical_id)
        if draft_mode == "dirty":
            pending.certificate_number = "UNSUBMITTED-HISTORICAL-EDIT"
        else:
            session.delete(pending)
        flushes = []

        def forbid_flush(*_args):
            flushes.append(True)
            raise AssertionError("Promotion autoflushed another version draft")

        event.listen(session, "before_flush", forbid_flush)
        try:
            with pytest.raises(HTTPException) as blocked:
                SERVICE.promote_certificate_current(
                    session, certificate_id=candidate["certificate_id"],
                    expected_version=candidate["row_version"],
                    reason="synthetic historical version draft guard", user=USER,
                )
            assert blocked.value.status_code == 409
            assert "uncommitted" in str(blocked.value.detail).lower()
            assert not flushes
            assert pending in (session.dirty if draft_mode == "dirty" else session.deleted)
            with session.no_autoflush:
                assert session.scalar(
                    select(CertificateVersion.certificate_number)
                    .where(CertificateVersion.id == historical_id)
                ) == "COMMITTED-NONLATEST-VERSION"
                assert session.scalar(
                    select(Certificate.latest_flag).where(Certificate.id == candidate["certificate_id"])
                ) is False
                assert session.scalar(select(func.count()).select_from(AuditEvent)) == audit_before
        finally:
            event.remove(session, "before_flush", forbid_flush)
            session.rollback()


def test_competing_same_certificate_promotions_keep_single_audit(pg_engine):
    """Two independent PostgreSQL Sessions cannot both promote one GCN."""
    case_id, site_id = seed(pg_engine)
    transition(pg_engine, case_id, "inspection_completed")
    transition(pg_engine, case_id, "awaiting_certificate_decision")
    candidate = issue(pg_engine, case_id, site_id)
    gate = Barrier(2)

    def attempt():
        gate.wait()
        try:
            return ("ok", write(
                pg_engine, SERVICE.promote_certificate_current,
                certificate_id=candidate["certificate_id"],
                expected_version=candidate["row_version"],
                reason="synthetic parallel promotion",
            ))
        except HTTPException as exc:
            return ("rejected", exc.status_code)

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: attempt(), range(2)))
    assert sorted(x[0] for x in outcomes) == ["ok", "rejected"]
    assert next(x[1] for x in outcomes if x[0] == "rejected") == 409
    successful = next(x[1] for x in outcomes if x[0] == "ok")
    with Session(pg_engine) as session:
        row = session.get(Certificate, candidate["certificate_id"])
        assert row.latest_flag is True
        assert row.row_version == successful["row_version"]
        audits = list(session.scalars(
            select(AuditEvent).where(
                AuditEvent.entity_id == row.id,
                AuditEvent.action == "certificate.promote_current",
            )
        ))
        assert len(audits) == 1
        assert audits[0].id == successful["audit_event_id"]


def test_competing_peer_certificate_promotions_preserve_single_current(pg_engine):
    """Site owner lock linearizes two different candidate promotions in one context."""
    case_id, site_id = seed(pg_engine)
    transition(pg_engine, case_id, "inspection_completed")
    transition(pg_engine, case_id, "awaiting_certificate_decision")
    with Session(pg_engine) as setup:
        sibling = Case(
            site_id=site_id, gxp_type="GMP",
            state=CaseState.AWAITING_CERTIFICATE_DECISION,
        )
        setup.add(sibling)
        setup.flush()
        sibling_id = sibling.id
        setup.commit()
    first = issue(pg_engine, case_id, site_id)
    second = issue(pg_engine, sibling_id, site_id)
    ids = {first["certificate_id"], second["certificate_id"]}
    gate = Barrier(2)

    def attempt(candidate):
        gate.wait()
        try:
            result = write(
                pg_engine, SERVICE.promote_certificate_current,
                certificate_id=candidate["certificate_id"],
                expected_version=candidate["row_version"],
                reason="synthetic competing contextual promotion",
            )
            return ("ok", result)
        except HTTPException as exc:
            return ("rejected", exc.status_code)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(attempt, candidate) for candidate in (first, second)]
        outcomes = [future.result() for future in futures]
    assert all(result[0] in {"ok", "rejected"} for result in outcomes)
    assert all(result[0] == "ok" or result[1] == 409 for result in outcomes)
    assert any(result[0] == "ok" for result in outcomes)
    with Session(pg_engine) as session:
        rows = list(session.scalars(
            select(Certificate).where(Certificate.id.in_(ids))
        ))
        assert len(rows) == 2
        current = [row for row in rows if row.latest_flag]
        assert len(current) == 1
        audits = list(session.scalars(
            select(AuditEvent).where(
                AuditEvent.entity_id.in_(ids),
                AuditEvent.action == "certificate.promote_current",
            )
        ))
        successes = [result[1] for result in outcomes if result[0] == "ok"]
        assert len(audits) == len(successes)
        assert {audit.id for audit in audits} == {
            result["audit_event_id"] for result in successes
        }
        assert current[0].id in {result["certificate_id"] for result in successes}


@pytest.mark.parametrize("draft_mode", ["new", "dirty", "deleted"])
def test_certificate_promotion_refuses_nonlatest_scope_draft(pg_engine, draft_mode):
    """Promotion cannot flush scopes attached to nonlatest candidate versions."""
    case_id, site_id = seed(pg_engine)
    transition(pg_engine, case_id, "inspection_completed")
    transition(pg_engine, case_id, "awaiting_certificate_decision")
    candidate = issue(pg_engine, case_id, site_id)
    with Session(pg_engine) as setup:
        old_version = CertificateVersion(
            certificate_id=candidate["certificate_id"], version_no=2,
            certificate_number="HISTORICAL-NONLATEST",
            lifecycle_state="DRAFT", is_latest_version=False,
        )
        setup.add(old_version)
        setup.flush()
        old_version_id = old_version.id
        if draft_mode != "new":
            old_scope = CertificateScope(
                certificate_version_id=old_version_id, scope_key="SCOPE-OLD",
                scope_text="Committed historical scope", language_code="vi", sort_order=1,
            )
            setup.add(old_scope)
            setup.flush()
            old_scope_id = old_scope.id
        setup.commit()
    with Session(pg_engine) as session:
        audit_before = session.scalar(select(func.count()).select_from(AuditEvent))
        if draft_mode == "new":
            pending = CertificateScope(
                certificate_version_id=old_version_id, scope_key="SCOPE-NEW",
                scope_text="Unsubmitted historical scope", language_code="vi", sort_order=2,
            )
            session.add(pending)
        else:
            pending = session.get(CertificateScope, old_scope_id)
            if draft_mode == "dirty":
                pending.scope_text = "Unsubmitted historical scope edit"
            else:
                session.delete(pending)
        flushes = []

        def forbid_flush(*_args):
            flushes.append(True)
            raise AssertionError("Promotion autoflushed a historical scope draft")

        event.listen(session, "before_flush", forbid_flush)
        try:
            with pytest.raises(HTTPException) as blocked:
                SERVICE.promote_certificate_current(
                    session, certificate_id=candidate["certificate_id"],
                    expected_version=candidate["row_version"],
                    reason="synthetic nonlatest scope admission", user=USER,
                )
            assert blocked.value.status_code == 409
            assert "uncommitted" in str(blocked.value.detail).lower()
            assert not flushes
            assert pending in {
                "new": session.new, "dirty": session.dirty,
                "deleted": session.deleted,
            }[draft_mode]
            with session.no_autoflush:
                assert session.scalar(
                    select(Certificate.latest_flag)
                    .where(Certificate.id == candidate["certificate_id"])
                ) is False
                assert session.scalar(select(func.count()).select_from(AuditEvent)) == audit_before
                assert session.scalar(
                    select(func.count()).select_from(CertificateScope)
                    .where(CertificateScope.certificate_version_id == old_version_id)
                ) == (0 if draft_mode == "new" else 1)
                if draft_mode != "new":
                    assert session.scalar(
                        select(CertificateScope.scope_text)
                        .where(CertificateScope.id == old_scope_id)
                    ) == "Committed historical scope"
        finally:
            event.remove(session, "before_flush", forbid_flush)
            session.rollback()


@pytest.mark.parametrize(
    "draft_kind",
    ["other_case_capa", "other_case_pct", "other_case_refusal", "other_certificate_version", "other_certificate_scope"],
)
def test_certificate_promotion_never_autoflushes_foreign_case_operator_draft(pg_engine, draft_kind):
    """The Session flush is global even when the source draft belongs to another Case/Site."""
    case_id, site_id = seed(pg_engine)
    transition(pg_engine, case_id, "inspection_completed")
    transition(pg_engine, case_id, "awaiting_certificate_decision")
    candidate = issue(pg_engine, case_id, site_id)

    foreign_case_id, foreign_site_id = seed(pg_engine)
    transition(pg_engine, foreign_case_id, "inspection_completed")
    transition(pg_engine, foreign_case_id, "awaiting_certificate_decision")
    foreign_certificate = issue(pg_engine, foreign_case_id, foreign_site_id)

    with Session(pg_engine) as session:
        audit_before = session.scalar(select(func.count()).select_from(AuditEvent))
        if draft_kind == "other_case_capa":
            pending = CapaCycle(
                case_id=foreign_case_id, round_no=1, requested_on=DAY,
                incoming_reference="UNSUBMITTED-OTHER-CAPA", notes="independent operator draft",
            )
            model, owner_key, owner_id = CapaCycle, CapaCycle.case_id, foreign_case_id
        elif draft_kind == "other_case_pct":
            pending = InspectionApprovalSubmission(
                case_id=foreign_case_id, stage="PCT", round_no=1,
                submitted_on=DAY, reference="UNSUBMITTED-OTHER-PCT",
            )
            model, owner_key, owner_id = InspectionApprovalSubmission, InspectionApprovalSubmission.case_id, foreign_case_id
        elif draft_kind == "other_case_refusal":
            actor_id = session.scalar(
                select(AuditEvent.actor_user_id)
                .where(AuditEvent.actor_user_id.is_not(None)).limit(1)
            )
            assert actor_id is not None
            pending = CaseCertificateNonissuanceDecision(
                case_id=foreign_case_id, decided_on=DAY,
                decision_reference="UNSUBMITTED-OTHER-REFUSAL",
                explanation="separate case legal draft", recorded_by_user_id=actor_id,
            )
            model, owner_key, owner_id = CaseCertificateNonissuanceDecision, CaseCertificateNonissuanceDecision.case_id, foreign_case_id
        elif draft_kind == "other_certificate_version":
            pending = CertificateVersion(
                certificate_id=foreign_certificate["certificate_id"], version_no=2,
                certificate_number="UNSUBMITTED-OTHER-VERSION",
                lifecycle_state="DRAFT", is_latest_version=False,
            )
            model, owner_key, owner_id = CertificateVersion, CertificateVersion.certificate_id, foreign_certificate["certificate_id"]
        else:
            pending = CertificateScope(
                certificate_version_id=foreign_certificate["latest_version_id"],
                scope_key="FOREIGN-SCOPE", scope_text="unsubmitted foreign scope",
                language_code="vi", sort_order=22,
            )
            model, owner_key, owner_id = CertificateScope, CertificateScope.certificate_version_id, foreign_certificate["latest_version_id"]
        count_before = session.scalar(
            select(func.count()).select_from(model).where(owner_key == owner_id)
        )
        session.add(pending)
        flushes = []

        def forbid_flush(*_args):
            flushes.append(True)
            raise AssertionError("Promotion attempted a global Session flush of another Case draft")

        event.listen(session, "before_flush", forbid_flush)
        try:
            with pytest.raises(HTTPException) as blocked:
                SERVICE.promote_certificate_current(
                    session, certificate_id=candidate["certificate_id"],
                    expected_version=candidate["row_version"],
                    reason="synthetic other Case draft isolation", user=USER,
                )
            assert blocked.value.status_code == 409
            assert "uncommitted" in str(blocked.value.detail).lower()
            assert not flushes
            assert pending in session.new
            with session.no_autoflush:
                assert session.scalar(
                    select(func.count()).select_from(model).where(owner_key == owner_id)
                ) == count_before
                assert session.scalar(
                    select(Certificate.latest_flag).where(Certificate.id == candidate["certificate_id"])
                ) is False
                assert session.scalar(select(func.count()).select_from(AuditEvent)) == audit_before
        finally:
            event.remove(session, "before_flush", forbid_flush)
            session.rollback()


@pytest.mark.parametrize("draft_kind", ["other_case_dirty", "other_version_dirty", "other_scope_deleted"])
def test_certificate_promotion_preserves_foreign_dirty_or_deleted_draft(pg_engine, draft_kind):
    """A distinct Case/Site's changed or deleted record cannot ride promotion flush."""
    case_id, site_id = seed(pg_engine)
    transition(pg_engine, case_id, "inspection_completed")
    transition(pg_engine, case_id, "awaiting_certificate_decision")
    candidate = issue(pg_engine, case_id, site_id)
    foreign_case_id, foreign_site_id = seed(pg_engine)
    transition(pg_engine, foreign_case_id, "inspection_completed")
    transition(pg_engine, foreign_case_id, "awaiting_certificate_decision")
    foreign = issue(pg_engine, foreign_case_id, foreign_site_id)

    with Session(pg_engine) as session:
        audit_before = session.scalar(select(func.count()).select_from(AuditEvent))
        if draft_kind == "other_case_dirty":
            pending = session.get(Case, foreign_case_id)
            original = pending.scope_code
            pending.scope_code = "UNSUBMITTED-FOREIGN-CASE"
            column, owner_id = Case.scope_code, foreign_case_id
        elif draft_kind == "other_version_dirty":
            pending = session.get(CertificateVersion, foreign["latest_version_id"])
            original = pending.certificate_number
            pending.certificate_number = "UNSUBMITTED-FOREIGN-VERSION"
            column, owner_id = CertificateVersion.certificate_number, pending.id
        else:
            scope_id = session.scalar(
                select(CertificateScope.id).where(
                    CertificateScope.certificate_version_id == foreign["latest_version_id"]
                ).limit(1)
            )
            assert scope_id is not None
            pending = session.get(CertificateScope, scope_id)
            original = pending.scope_text
            session.delete(pending)
            column, owner_id = CertificateScope.scope_text, scope_id
        flushes = []

        def forbid_flush(*_args):
            flushes.append(True)
            raise AssertionError("Promotion attempted to save unrelated changed/deleted record")

        event.listen(session, "before_flush", forbid_flush)
        try:
            with pytest.raises(HTTPException) as blocked:
                SERVICE.promote_certificate_current(
                    session, certificate_id=candidate["certificate_id"],
                    expected_version=candidate["row_version"],
                    reason="synthetic foreign draft edit isolation", user=USER,
                )
            assert blocked.value.status_code == 409
            assert "uncommitted" in str(blocked.value.detail).lower()
            assert not flushes
            assert pending in (
                session.deleted if draft_kind == "other_scope_deleted" else session.dirty
            )
            with session.no_autoflush:
                assert session.scalar(
                    select(column).where(
                        (Case.id if draft_kind == "other_case_dirty"
                         else CertificateVersion.id if draft_kind == "other_version_dirty"
                         else CertificateScope.id) == owner_id
                    )
                ) == original
                assert session.scalar(
                    select(Certificate.latest_flag)
                    .where(Certificate.id == candidate["certificate_id"])
                ) is False
                assert session.scalar(select(func.count()).select_from(AuditEvent)) == audit_before
        finally:
            event.remove(session, "before_flush", forbid_flush)
            session.rollback()


def test_certificate_promotion_accepts_foreign_case_noop_dirty_identity(pg_engine):
    """A harmless ORM dirty marker is not a separately flushable operator change."""
    case_id, site_id = seed(pg_engine)
    transition(pg_engine, case_id, "inspection_completed")
    transition(pg_engine, case_id, "awaiting_certificate_decision")
    candidate = issue(pg_engine, case_id, site_id)
    foreign_case_id, _ = seed(pg_engine)

    with Session(pg_engine) as session:
        foreign_case = session.get(Case, foreign_case_id)
        foreign_case.scope_code = foreign_case.scope_code
        assert foreign_case in session.dirty
        assert not session.is_modified(foreign_case, include_collections=True)
        result = SERVICE.promote_certificate_current(
            session, certificate_id=candidate["certificate_id"],
            expected_version=candidate["row_version"],
            reason="synthetic no-op ORM marker", user=USER,
        )
        assert result["latest_flag"] is True
        session.commit()
    with Session(pg_engine) as verify:
        assert verify.get(Certificate, candidate["certificate_id"]).latest_flag is True
        assert verify.scalar(
            select(func.count()).select_from(AuditEvent).where(
                AuditEvent.entity_id == candidate["certificate_id"],
                AuditEvent.action == "certificate.promote_current",
            )
        ) == 1


@pytest.mark.parametrize("operation", ["issue", "edit"])
@pytest.mark.parametrize("foreign_draft", ["capa", "certificate_version"])
def test_certificate_issue_and_edit_preserve_foreign_case_operator_intent(pg_engine, operation, foreign_draft):
    """A different Case/Site's pending legal data must not ride issue/edit Session flush."""
    case_id, site_id = seed(pg_engine)
    transition(pg_engine, case_id, "inspection_completed")
    transition(pg_engine, case_id, "awaiting_certificate_decision")
    target = issue(pg_engine, case_id, site_id) if operation == "edit" else None
    foreign_case_id, foreign_site_id = seed(pg_engine)
    transition(pg_engine, foreign_case_id, "inspection_completed")
    transition(pg_engine, foreign_case_id, "awaiting_certificate_decision")
    foreign = issue(pg_engine, foreign_case_id, foreign_site_id)

    with Session(pg_engine) as session:
        audit_before = session.scalar(select(func.count()).select_from(AuditEvent))
        count_before = session.scalar(
            select(func.count()).select_from(Certificate).where(Certificate.case_id == case_id)
        )
        if foreign_draft == "capa":
            pending = CapaCycle(
                case_id=foreign_case_id, round_no=1, requested_on=DAY,
                incoming_reference="UNSUBMITTED-FOREIGN-CAPA-ISSUE-EDIT",
                notes="independent foreign Case intent",
            )
            model, owner, owner_id = CapaCycle, CapaCycle.case_id, foreign_case_id
        else:
            pending = CertificateVersion(
                certificate_id=foreign["certificate_id"], version_no=2,
                certificate_number="UNSUBMITTED-FOREIGN-GCN-ISSUE-EDIT",
                lifecycle_state="DRAFT", is_latest_version=False,
            )
            model, owner, owner_id = CertificateVersion, CertificateVersion.certificate_id, foreign["certificate_id"]
        foreign_count = session.scalar(
            select(func.count()).select_from(model).where(owner == owner_id)
        )
        session.add(pending)
        flushes = []

        def forbid_flush(*_args):
            flushes.append(True)
            raise AssertionError("Issue/edit autoflushed an independent foreign Case draft")

        event.listen(session, "before_flush", forbid_flush)
        try:
            with pytest.raises(HTTPException) as blocked:
                if operation == "issue":
                    SERVICE.issue_certificate(
                        session, site_id=site_id, case_id=case_id,
                        certificate_type="GMP", issuance_basis="inspection_case",
                        certificate_number="SYNTH-ISSUE-FOREIGN-DRAFT",
                        issue_date=DAY, expiry_date=date(2027, 10, 1),
                        scopes=[], reason="independent issuance", user=USER,
                    )
                else:
                    SERVICE.upsert_certificate_latest_version(
                        session, certificate_id=target["certificate_id"],
                        expected_version=target["row_version"],
                        certificate_number="SYNTH-EDIT-FOREIGN-DRAFT",
                        issue_date=DAY, expiry_date=date(2027, 10, 1),
                        scopes=[], reason="independent version edit", user=USER,
                    )
            assert blocked.value.status_code == 409
            assert "uncommitted" in str(blocked.value.detail).lower()
            assert not flushes
            assert pending in session.new
            with session.no_autoflush:
                assert session.scalar(
                    select(func.count()).select_from(model).where(owner == owner_id)
                ) == foreign_count
                assert session.scalar(
                    select(func.count()).select_from(Certificate).where(Certificate.case_id == case_id)
                ) == count_before
                assert session.scalar(select(func.count()).select_from(AuditEvent)) == audit_before
                if target is not None:
                    assert session.scalar(
                        select(CertificateVersion.certificate_number).where(
                            CertificateVersion.id == target["latest_version_id"]
                        )
                    ) == target["certificate_number"]
        finally:
            event.remove(session, "before_flush", forbid_flush)
            session.rollback()


@pytest.mark.parametrize("operation", ["issue", "edit"])
def test_certificate_issue_edit_allows_harmless_foreign_noop_marker(pg_engine, operation):
    """Do not reject a no-op ORM dirty identity as a separate draft."""
    case_id, site_id = seed(pg_engine)
    transition(pg_engine, case_id, "inspection_completed")
    transition(pg_engine, case_id, "awaiting_certificate_decision")
    target = issue(pg_engine, case_id, site_id) if operation == "edit" else None
    foreign_case_id, _ = seed(pg_engine)
    with Session(pg_engine) as session:
        foreign_case = session.get(Case, foreign_case_id)
        foreign_case.scope_code = foreign_case.scope_code
        assert foreign_case in session.dirty
        assert not session.is_modified(foreign_case, include_collections=True)
        if operation == "issue":
            result = SERVICE.issue_certificate(
                session, site_id=site_id, case_id=case_id,
                certificate_type="GMP", issuance_basis="inspection_case",
                certificate_number="SYNTH-NOOP-ISSUE", issue_date=DAY,
                expiry_date=date(2027, 10, 1), scopes=[],
                reason="positive no-op marker", user=USER,
            )
            audit_action = "certificate.issue"
            audit_owner = result["certificate_id"]
        else:
            result = SERVICE.upsert_certificate_latest_version(
                session, certificate_id=target["certificate_id"],
                expected_version=target["row_version"],
                certificate_number="SYNTH-NOOP-EDIT", issue_date=DAY,
                expiry_date=date(2027, 10, 1), scopes=[],
                reason="positive no-op marker", user=USER,
            )
            audit_action = "certificate.latest_version.upsert"
            audit_owner = result["latest_version_id"]
        session.commit()
    with Session(pg_engine) as verify:
        assert verify.scalar(
            select(func.count()).select_from(AuditEvent).where(
                AuditEvent.entity_id == audit_owner,
                AuditEvent.action == audit_action,
            )
        ) == 1


@pytest.mark.parametrize("operation", ["capa_create", "capa_update", "approval_create", "approval_complete"])
def test_capa_approval_mutations_refuse_foreign_case_session_drafts(pg_engine, operation):
    """Do not flush another Case's unsubmitted CAPA during a distinct owner's mutation."""
    case_id, _ = seed(pg_engine)
    transition(pg_engine, case_id, "inspection_completed")
    capa = create_cycle(pg_engine, case_id) if operation == "capa_update" else None
    submission = approval(pg_engine, case_id, "PCT") if operation == "approval_complete" else None
    foreign_case_id, _ = seed(pg_engine)

    with Session(pg_engine) as session:
        audit_before = session.scalar(select(func.count()).select_from(AuditEvent))
        target_count = session.scalar(
            select(func.count()).select_from(CapaCycle)
            .where(CapaCycle.case_id == case_id)
        )
        foreign_count = session.scalar(
            select(func.count()).select_from(CapaCycle)
            .where(CapaCycle.case_id == foreign_case_id)
        )
        pending = CapaCycle(
            case_id=foreign_case_id, round_no=1, requested_on=DAY,
            incoming_reference="UNSUBMITTED-FOREIGN-CAPA", notes="independent operator draft",
        )
        session.add(pending)
        flushes = []

        def forbid_flush(*_args):
            flushes.append(True)
            raise AssertionError("CAPA/approval mutation autoflushed foreign Case draft")

        event.listen(session, "before_flush", forbid_flush)
        try:
            with pytest.raises(HTTPException) as blocked:
                if operation == "capa_create":
                    SERVICE.create_capa_cycle(
                        session, case_id=case_id, requested_on=DAY,
                        incoming_reference="ISOLATION-CAPA", notes="target round",
                        reason="separate operation", user=USER,
                    )
                elif operation == "capa_update":
                    SERVICE.update_capa_cycle(
                        session, capa_cycle_id=capa["capa_cycle_id"],
                        expected_version=capa["row_version"],
                        requested_on=DAY, incoming_reference="ISOLATION-UPDATE",
                        notes="target update", reason="separate operation", user=USER,
                    )
                elif operation == "approval_create":
                    SERVICE.create_approval_submission(
                        session, case_id=case_id, stage="PCT", reference="ISOLATION-PCT",
                        submitted_on=DAY, submitted_time=None, pct_submission_id=None,
                        reason="separate operation", user=USER,
                    )
                else:
                    SERVICE.complete_approval_submission(
                        session, approval_submission_id=submission["approval_submission_id"],
                        expected_version=submission["row_version"], completed_on=DAY,
                        completed_time=None, reason="separate operation", user=USER,
                    )
            assert blocked.value.status_code == 409
            assert "uncommitted" in str(blocked.value.detail).lower()
            assert not flushes
            assert pending in session.new
            with session.no_autoflush:
                assert session.scalar(
                    select(func.count()).select_from(CapaCycle)
                    .where(CapaCycle.case_id == foreign_case_id)
                ) == foreign_count
                assert session.scalar(
                    select(func.count()).select_from(CapaCycle)
                    .where(CapaCycle.case_id == case_id)
                ) == target_count
                assert session.scalar(select(func.count()).select_from(AuditEvent)) == audit_before
        finally:
            event.remove(session, "before_flush", forbid_flush)
            session.rollback()


@pytest.mark.parametrize("operation", ["capa_create", "capa_update", "approval_create", "approval_complete"])
def test_capa_approval_allows_foreign_noop_dirty_marker(pg_engine, operation):
    """Session-wide admission must ignore an ORM identity with no real edit."""
    case_id, _ = seed(pg_engine)
    transition(pg_engine, case_id, "inspection_completed")
    target_capa = create_cycle(pg_engine, case_id) if operation == "capa_update" else None
    target_approval = approval(pg_engine, case_id, "PCT") if operation == "approval_complete" else None
    foreign_case_id, _ = seed(pg_engine)

    with Session(pg_engine) as session:
        foreign_case = session.get(Case, foreign_case_id)
        original_foreign_scope = foreign_case.scope_code
        foreign_case.scope_code = original_foreign_scope
        assert foreign_case in session.dirty
        assert not session.is_modified(foreign_case, include_collections=True)
        if operation == "capa_create":
            result = SERVICE.create_capa_cycle(
                session, case_id=case_id, requested_on=DAY,
                incoming_reference="POSITIVE-CAPA", notes="valid independent round",
                reason="no-op foreign Case", user=USER,
            )
        elif operation == "capa_update":
            result = SERVICE.update_capa_cycle(
                session, capa_cycle_id=target_capa["capa_cycle_id"],
                expected_version=target_capa["row_version"], requested_on=DAY,
                incoming_reference="POSITIVE-UPDATE", notes="valid update",
                reason="no-op foreign Case", user=USER,
            )
        elif operation == "approval_create":
            result = SERVICE.create_approval_submission(
                session, case_id=case_id, stage="PCT", reference="POSITIVE-PCT",
                submitted_on=DAY, submitted_time=None, pct_submission_id=None,
                reason="no-op foreign Case", user=USER,
            )
        else:
            result = SERVICE.complete_approval_submission(
                session, approval_submission_id=target_approval["approval_submission_id"],
                expected_version=target_approval["row_version"],
                completed_on=DAY, completed_time=None,
                reason="no-op foreign Case", user=USER,
            )
        assert result
        session.commit()
    with Session(pg_engine) as verify:
        assert verify.get(Case, foreign_case_id).scope_code == original_foreign_scope
        if operation.startswith("capa"):
            assert verify.scalar(
                select(func.count()).select_from(CapaCycle)
                .where(CapaCycle.case_id == case_id)
            ) == 1
        else:
            assert verify.scalar(
                select(func.count()).select_from(InspectionApprovalSubmission)
                .where(InspectionApprovalSubmission.case_id == case_id)
            ) == 1


@pytest.mark.parametrize("operation", ["application", "assessment"])
def test_case_intake_stage_mutation_rejects_foreign_pending_capa(pg_engine, operation):
    """A Case intake/assessment flush must not save another Case's CAPA draft."""
    case_id, _ = seed(pg_engine)
    foreign_case_id, _ = seed(pg_engine)
    with Session(pg_engine) as session:
        audit_before = session.scalar(select(func.count()).select_from(AuditEvent))
        foreign_before = session.scalar(select(func.count()).select_from(CapaCycle).where(
            CapaCycle.case_id == foreign_case_id
        ))
        pending = CapaCycle(
            case_id=foreign_case_id, round_no=1, requested_on=DAY,
            incoming_reference="FOREIGN-UNCOMMITTED-CAPA", notes="separate Case draft",
        )
        session.add(pending)
        flushes = []

        def forbid_flush(*_):
            flushes.append(True)
            raise AssertionError("Case application/assessment flushed a foreign CAPA draft")

        event.listen(session, "before_flush", forbid_flush)
        try:
            with pytest.raises(HTTPException) as blocked:
                if operation == "application":
                    SERVICE.upsert_case_application(
                        session, case_id=case_id, submitted_on=DAY,
                        dossier_code="INTAKE-CASE", dossier_reference=None,
                        applicant_name="Synthetic applicant", reason="intake",
                        user=USER,
                    )
                else:
                    SERVICE.upsert_case_assessment(
                        session, case_id=case_id, assessed_on=DAY,
                        assessor_name="Synthetic assessor", assessment_result="eligible",
                        notes="synthetic assessment", reason="assessment", user=USER,
                    )
            assert blocked.value.status_code == 409
            assert "uncommitted" in str(blocked.value.detail).lower()
            assert not flushes
            assert pending in session.new
            with session.no_autoflush:
                assert session.scalar(select(func.count()).select_from(CapaCycle).where(
                    CapaCycle.case_id == foreign_case_id
                )) == foreign_before
                assert session.scalar(select(func.count()).select_from(AuditEvent)) == audit_before
        finally:
            event.remove(session, "before_flush", forbid_flush)
            session.rollback()


@pytest.mark.parametrize("operation", ["application", "assessment"])
def test_case_intake_stage_accepts_foreign_noop_dirty_marker(pg_engine, operation):
    """A separate Case's no-op ORM dirty marker cannot block valid intake."""
    case_id, _ = seed(pg_engine)
    foreign_case_id, _ = seed(pg_engine)
    with Session(pg_engine) as session:
        foreign = session.get(Case, foreign_case_id)
        original_scope = foreign.scope_code
        foreign.scope_code = original_scope
        assert foreign in session.dirty
        assert not session.is_modified(foreign, include_collections=True)
        if operation == "application":
            result = SERVICE.upsert_case_application(
                session, case_id=case_id, submitted_on=DAY,
                dossier_code="NOOP-INTAKE", dossier_reference=None,
                applicant_name="Synthetic applicant", reason="no-op foreign Case",
                user=USER,
            )
            audit_action = "case_application.upsert"
        else:
            result = SERVICE.upsert_case_assessment(
                session, case_id=case_id, assessed_on=DAY,
                assessor_name="Synthetic assessor", assessment_result="eligible",
                notes="synthetic assessment", reason="no-op foreign Case",
                user=USER,
            )
            audit_action = "case_assessment.upsert"
        assert result["case_id"] == case_id
        session.commit()
    with Session(pg_engine) as verify:
        assert verify.get(Case, foreign_case_id).scope_code == original_scope
        assert verify.scalar(select(func.count()).select_from(AuditEvent).where(
            AuditEvent.entity_id == case_id, AuditEvent.action == audit_action
        )) == 1


@pytest.mark.parametrize("operation", ["plan", "outcome"])
def test_inspection_stage_refuses_foreign_capa_draft_without_flush(pg_engine, operation):
    """Inspection plan/outcome must not persist a pending CAPA of another Case."""
    case_id, _ = seed(pg_engine)
    foreign_case_id, _ = seed(pg_engine)
    with Session(pg_engine) as session:
        before_audit = session.scalar(select(func.count()).select_from(AuditEvent))
        before_foreign = session.scalar(select(func.count()).select_from(CapaCycle).where(
            CapaCycle.case_id == foreign_case_id
        ))
        pending = CapaCycle(
            case_id=foreign_case_id, round_no=1, requested_on=DAY,
            incoming_reference="UNCOMMITTED-OTHER-CAPA", notes="unsubmitted",
        )
        session.add(pending)
        flushes = []

        def forbid_flush(*_):
            flushes.append(True)
            raise AssertionError("Inspection stage attempted foreign CAPA autoflush")

        event.listen(session, "before_flush", forbid_flush)
        try:
            with pytest.raises(HTTPException) as ex:
                if operation == "plan":
                    SERVICE.upsert_inspection_plan(
                        session, case_id=case_id,
                        plan_start_on=DAY, plan_end_on=DAY,
                        planning_sheet_name="Synthetic schedule",
                        decision_document_hint=None, reason="synthetic plan",
                        user=USER,
                    )
                else:
                    SERVICE.upsert_inspection_outcome(
                        session, case_id=case_id,
                        inspected_on=DAY, inspected_to_on=DAY,
                        decision_reference=None, bbkt_reference=None,
                        outcome_result="Synthetic inspected result",
                        reason="synthetic outcome", user=USER,
                    )
            assert ex.value.status_code == 409
            assert "uncommitted" in str(ex.value.detail).lower()
            assert not flushes
            assert pending in session.new
            with session.no_autoflush:
                assert session.scalar(select(func.count()).select_from(CapaCycle).where(
                    CapaCycle.case_id == foreign_case_id
                )) == before_foreign
                assert session.scalar(select(func.count()).select_from(AuditEvent)) == before_audit
        finally:
            event.remove(session, "before_flush", forbid_flush)
            session.rollback()


@pytest.mark.parametrize("operation", ["plan", "outcome"])
def test_inspection_stage_allows_unmodified_foreign_dirty_marker(pg_engine, operation):
    """A harmless ORM dirty marker in a different Case cannot block a stage write."""
    case_id, _ = seed(pg_engine)
    foreign_case_id, _ = seed(pg_engine)
    with Session(pg_engine) as session:
        foreign = session.get(Case, foreign_case_id)
        original_scope = foreign.scope_code
        foreign.scope_code = original_scope
        assert foreign in session.dirty
        assert not session.is_modified(foreign, include_collections=True)
        if operation == "plan":
            result = SERVICE.upsert_inspection_plan(
                session, case_id=case_id, plan_start_on=DAY, plan_end_on=DAY,
                planning_sheet_name="Synthetic plan",
                decision_document_hint=None, reason="no-op foreign Case", user=USER,
            )
            audit_action = "inspection_plan.upsert"
        else:
            result = SERVICE.upsert_inspection_outcome(
                session, case_id=case_id,
                inspected_on=DAY, inspected_to_on=DAY,
                decision_reference=None, bbkt_reference=None,
                outcome_result="Synthetic outcome",
                reason="no-op foreign Case", user=USER,
            )
            audit_action = "inspection_outcome.upsert"
        assert result["case_id"] == case_id
        session.commit()
    with Session(pg_engine) as verify:
        assert verify.get(Case, foreign_case_id).scope_code == original_scope
        assert verify.scalar(select(func.count()).select_from(AuditEvent).where(
            AuditEvent.entity_id == case_id,
            AuditEvent.action == audit_action,
        )) == 1


@pytest.mark.parametrize("operation", ["finalize", "nonissuance"])
def test_legal_outcome_mutation_refuses_foreign_session_draft(pg_engine, operation):
    """A valid target mutation cannot implicitly persist another Case's CAPA."""
    case_id, _ = seed(pg_engine)
    foreign_case_id, _ = seed(pg_engine)
    with Session(pg_engine) as setup:
        if operation == "finalize":
            setup.add(InspectionOutcome(
                case_id=case_id, outcome_result="Synthetic completed inspection",
            ))
        else:
            case = setup.get(Case, case_id)
            case.state = CaseState.AWAITING_CERTIFICATE_DECISION
            setup.add(InspectionOutcome(
                case_id=case_id, final_evaluation="Synthetic legal determination",
            ))
        setup.commit()

    with Session(pg_engine) as session:
        target_case = session.get(Case, case_id)
        expected_case_version = target_case.row_version
        outcome = session.scalar(select(InspectionOutcome).where(InspectionOutcome.case_id == case_id))
        expected_outcome_version = outcome.row_version
        audit_before = session.scalar(select(func.count()).select_from(AuditEvent))
        pending = CapaCycle(
            case_id=foreign_case_id, round_no=1, requested_on=DAY,
            incoming_reference="UNSUBMITTED-FOREIGN-CAPA", notes="independent draft",
        )
        session.add(pending)
        flushes = []

        def forbid_flush(*_):
            flushes.append(True)
            raise AssertionError("Legal outcome mutation flushed a foreign Case draft")

        event.listen(session, "before_flush", forbid_flush)
        try:
            with pytest.raises(HTTPException) as blocked:
                if operation == "finalize":
                    SERVICE.finalize_inspection_outcome(
                        session, case_id=case_id,
                        expected_version=expected_outcome_version,
                        final_evaluation="Synthetic finalized",
                        reason="isolated finalization", user=USER,
                    )
                else:
                    SERVICE.record_case_nonissuance_decision(
                        session, case_id=case_id,
                        expected_case_version=expected_case_version,
                        decided_on=DAY, decision_reference="SYNTH-REFUSAL-ISOLATED",
                        explanation="Synthetic non-issuance rationale",
                        reason="isolated legal decision", user=USER,
                    )
            assert blocked.value.status_code == 409
            assert "uncommitted" in str(blocked.value.detail).lower()
            assert not flushes
            assert pending in session.new
            with session.no_autoflush:
                assert session.scalar(select(func.count()).select_from(CapaCycle).where(
                    CapaCycle.case_id == foreign_case_id
                )) == 0
                assert session.scalar(select(func.count()).select_from(AuditEvent)) == audit_before
                if operation == "finalize":
                    assert session.scalar(select(InspectionOutcome.final_evaluation).where(
                        InspectionOutcome.case_id == case_id
                    )) is None
                else:
                    assert session.scalar(select(func.count()).select_from(
                        CaseCertificateNonissuanceDecision
                    ).where(CaseCertificateNonissuanceDecision.case_id == case_id)) == 0
        finally:
            event.remove(session, "before_flush", forbid_flush)
            session.rollback()


@pytest.mark.parametrize("operation", ["finalize", "nonissuance"])
def test_legal_outcome_mutation_accepts_foreign_noop_dirty_marker(pg_engine, operation):
    """No-op foreign Case identity markers are not independent SQL writes."""
    case_id, _ = seed(pg_engine)
    foreign_case_id, _ = seed(pg_engine)
    with Session(pg_engine) as setup:
        if operation == "finalize":
            setup.add(InspectionOutcome(
                case_id=case_id, outcome_result="Synthetic completed inspection",
            ))
        else:
            setup.get(Case, case_id).state = CaseState.AWAITING_CERTIFICATE_DECISION
            setup.add(InspectionOutcome(
                case_id=case_id, final_evaluation="Synthetic final legal assessment",
            ))
        setup.commit()

    with Session(pg_engine) as session:
        foreign = session.get(Case, foreign_case_id)
        original_scope = foreign.scope_code
        foreign.scope_code = original_scope
        assert foreign in session.dirty
        assert not session.is_modified(foreign, include_collections=True)
        target = session.get(Case, case_id)
        if operation == "finalize":
            outcome = session.scalar(select(InspectionOutcome).where(
                InspectionOutcome.case_id == case_id
            ))
            result = SERVICE.finalize_inspection_outcome(
                session, case_id=case_id, expected_version=outcome.row_version,
                final_evaluation="Synthetic approved determination",
                reason="synthetic no-op control", user=USER,
            )
            assert result["final_evaluation"] == "Synthetic approved determination"
        else:
            result = SERVICE.record_case_nonissuance_decision(
                session, case_id=case_id, expected_case_version=target.row_version,
                decided_on=DAY, decision_reference="SYNTH-NONISSUANCE-NOOP",
                explanation="Synthetic legal rationale",
                reason="synthetic no-op control", user=USER,
            )
            assert result["decision"] is not None
        session.commit()

    with Session(pg_engine) as verify:
        assert verify.get(Case, foreign_case_id).scope_code == original_scope
        if operation == "finalize":
            assert verify.scalar(select(InspectionOutcome.final_evaluation).where(
                InspectionOutcome.case_id == case_id
            )) == "Synthetic approved determination"
            assert verify.scalar(select(func.count()).select_from(AuditEvent).where(
                AuditEvent.action == "inspection_outcome.finalize"
            )) >= 1
        else:
            assert verify.scalar(select(func.count()).select_from(
                CaseCertificateNonissuanceDecision
            ).where(CaseCertificateNonissuanceDecision.case_id == case_id)) == 1


def test_change_request_create_refuses_foreign_case_draft_before_flush(pg_engine):
    """A new Site Change Request cannot commit another Case's pending CAPA."""
    _, site_id = seed(pg_engine)
    foreign_case_id, _ = seed(pg_engine)
    with Session(pg_engine) as session:
        audits_before = session.scalar(select(func.count()).select_from(AuditEvent))
        pending = CapaCycle(
            case_id=foreign_case_id, round_no=1, requested_on=DAY,
            incoming_reference="UNCOMMITTED-FOREIGN-CR-CAPA", notes="independent draft",
        )
        session.add(pending)
        flushes = []

        def forbid_flush(*_):
            flushes.append(True)
            raise AssertionError("Change Request creation attempted a foreign CAPA flush")

        event.listen(session, "before_flush", forbid_flush)
        try:
            with pytest.raises(HTTPException) as blocked:
                SERVICE.create_change_request(
                    session, site_id=site_id, scope_label="Synthetic change",
                    description="Separate Site change request", submitted_on=DAY,
                    requester_name="Synthetic requester", reason="isolated change request",
                    user=USER,
                )
            assert blocked.value.status_code == 409
            assert "uncommitted" in str(blocked.value.detail).lower()
            assert not flushes
            assert pending in session.new
            with session.no_autoflush:
                assert session.scalar(select(func.count()).select_from(CapaCycle).where(
                    CapaCycle.case_id == foreign_case_id
                )) == 0
                assert session.scalar(select(func.count()).select_from(AuditEvent)) == audits_before
        finally:
            event.remove(session, "before_flush", forbid_flush)
            session.rollback()


def test_change_request_create_accepts_foreign_noop_dirty_marker(pg_engine):
    """Unchanged Case fields must not block an independent valid Site request."""
    _, site_id = seed(pg_engine)
    foreign_case_id, _ = seed(pg_engine)
    with Session(pg_engine) as session:
        foreign = session.get(Case, foreign_case_id)
        original_scope = foreign.scope_code
        foreign.scope_code = original_scope
        assert foreign in session.dirty
        assert not session.is_modified(foreign, include_collections=True)
        result = SERVICE.create_change_request(
            session, site_id=site_id, scope_label="Synthetic no-op control",
            description="Site change request unaffected by another Case marker",
            submitted_on=DAY, requester_name="Synthetic requester",
            reason="synthetic no-op control", user=USER,
        )
        assert result
        session.commit()
    with Session(pg_engine) as verify:
        assert verify.get(Case, foreign_case_id).scope_code == original_scope
        assert verify.scalar(select(func.count()).select_from(AuditEvent).where(
            AuditEvent.action == "change_request.create"
        )) >= 1


def _approval_binding_fixture(pg_engine):
    case_id, _ = seed(pg_engine)
    submission = approval(pg_engine, case_id, "PCT")
    with Session(pg_engine) as setup:
        doc = Document(
            case_id=case_id,
            family_code="INSPECTION_PT_PCT",
            document_type_code="SYNTHETIC_PCT",
            title="Synthetic PCT for binding",
        )
        setup.add(doc)
        setup.commit()
        return case_id, submission, doc.id


def test_bind_approval_document_rejects_foreign_pending_capa_before_flush(pg_engine):
    """Binding a PCT document cannot save another Case's unfinished CAPA."""
    case_id, submission, document_id = _approval_binding_fixture(pg_engine)
    foreign_case_id, _ = seed(pg_engine)
    with Session(pg_engine) as session:
        audit_before = session.scalar(select(func.count()).select_from(AuditEvent))
        binding_before = session.scalar(select(func.count()).select_from(InspectionApprovalDocumentLink))
        pending = CapaCycle(
            case_id=foreign_case_id, round_no=1, requested_on=DAY,
            incoming_reference="PENDING-FOREIGN-APPROVAL-BINDING-CAPA",
        )
        session.add(pending)
        flushes = []

        def forbid_flush(*_):
            flushes.append(True)
            raise AssertionError("Approval document binding attempted foreign CAPA flush")

        event.listen(session, "before_flush", forbid_flush)
        try:
            with pytest.raises(HTTPException) as blocked:
                SERVICE.bind_approval_document(
                    session,
                    approval_submission_id=submission["approval_submission_id"],
                    document_id=document_id,
                    expected_version=submission["row_version"],
                    reason="synthetic foreign Session isolation", user=USER,
                )
            assert blocked.value.status_code == 409
            assert "uncommitted" in str(blocked.value.detail).lower()
            assert not flushes
            assert pending in session.new
            with session.no_autoflush:
                assert session.scalar(select(func.count()).select_from(AuditEvent)) == audit_before
                assert session.scalar(select(func.count()).select_from(InspectionApprovalDocumentLink)) == binding_before
                assert session.scalar(select(func.count()).select_from(CapaCycle).where(
                    CapaCycle.case_id == foreign_case_id
                )) == 0
                assert session.scalar(select(InspectionApprovalSubmission.row_version).where(
                    InspectionApprovalSubmission.id == submission["approval_submission_id"]
                )) == submission["row_version"]
        finally:
            event.remove(session, "before_flush", forbid_flush)
            session.rollback()


def test_bind_approval_document_allows_foreign_noop_dirty_marker(pg_engine):
    """A no-op cached foreign Case must not prevent a valid binding."""
    case_id, submission, document_id = _approval_binding_fixture(pg_engine)
    foreign_case_id, _ = seed(pg_engine)
    with Session(pg_engine) as session:
        foreign = session.get(Case, foreign_case_id)
        original_scope = foreign.scope_code
        foreign.scope_code = original_scope
        assert foreign in session.dirty
        assert not session.is_modified(foreign, include_collections=True)
        receipt = SERVICE.bind_approval_document(
            session,
            approval_submission_id=submission["approval_submission_id"],
            document_id=document_id,
            expected_version=submission["row_version"],
            reason="synthetic no-op dirty control", user=USER,
        )
        assert receipt["created"] is True
        assert receipt["document_id"] == document_id
        session.commit()
    with Session(pg_engine) as verify:
        assert verify.get(Case, foreign_case_id).scope_code == original_scope
        assert verify.scalar(select(func.count()).select_from(InspectionApprovalDocumentLink).where(
            InspectionApprovalDocumentLink.document_id == document_id
        )) == 1
        assert verify.scalar(select(func.count()).select_from(AuditEvent).where(
            AuditEvent.action == "inspection_approval_document_link.create",
        )) >= 1


@pytest.mark.parametrize("operation", ["header_update", "detail_create", "transition"])
def test_change_request_mutation_refuses_foreign_pending_capa(pg_engine, operation):
    """A Change Request mutation cannot save pending CAPA from a foreign Case."""
    _, site_id = seed(pg_engine)
    foreign_case_id, _ = seed(pg_engine)
    cr = write(
        pg_engine, SERVICE.create_change_request,
        site_id=site_id, scope_label="Synthetic scope",
        description="Target change", submitted_on=DAY,
        requester_name="Synthetic operator", reason="seed",
    )
    with Session(pg_engine) as session:
        audit_before = session.scalar(select(func.count()).select_from(AuditEvent))
        pending = CapaCycle(
            case_id=foreign_case_id, round_no=1, requested_on=DAY,
            incoming_reference="PENDING-FOREIGN-CR-EDIT",
        )
        session.add(pending)
        flushes = []
        def forbid_flush(*_):
            flushes.append(True)
            raise AssertionError("Change Request mutation attempted foreign CAPA flush")
        event.listen(session, "before_flush", forbid_flush)
        try:
            with pytest.raises(HTTPException) as blocked:
                if operation == "header_update":
                    SERVICE.update_change_request(
                        session, change_request_id=cr["change_request_id"],
                        expected_version=cr["row_version"],
                        scope_label="Updated synthetic scope", description=None,
                        submitted_on=None, requester_name=None,
                        fields_set={"scope_label"}, reason="synthetic update", user=USER,
                    )
                elif operation == "detail_create":
                    SERVICE.create_change_request_detail(
                        session, change_request_id=cr["change_request_id"],
                        expected_version=cr["row_version"],
                        classification_id=None, classification_label="Synthetic class",
                        approval_status=None, old_value="old", new_value="new",
                        note=None, reason="synthetic detail", user=USER,
                    )
                else:
                    SERVICE.transition_change_request(
                        session, change_request_id=cr["change_request_id"],
                        target_state="under_review", expected_version=cr["row_version"],
                        reason="synthetic transition", user=USER,
                    )
            assert blocked.value.status_code == 409
            assert "uncommitted" in str(blocked.value.detail).lower()
            assert not flushes
            assert pending in session.new
            with session.no_autoflush:
                assert session.scalar(select(func.count()).select_from(AuditEvent)) == audit_before
                assert session.scalar(select(func.count()).select_from(CapaCycle).where(
                    CapaCycle.case_id == foreign_case_id
                )) == 0
        finally:
            event.remove(session, "before_flush", forbid_flush)
            session.rollback()


@pytest.mark.parametrize("operation", ["header_update", "detail_create", "transition"])
def test_change_request_mutation_allows_foreign_noop_marker(pg_engine, operation):
    """No-op ORM dirty markers on unrelated Cases are not independent mutations."""
    _, site_id = seed(pg_engine)
    foreign_case_id, _ = seed(pg_engine)
    cr = write(
        pg_engine, SERVICE.create_change_request,
        site_id=site_id, scope_label="Synthetic original",
        description="Target change", submitted_on=DAY,
        requester_name="Synthetic operator", reason="seed",
    )
    with Session(pg_engine) as session:
        foreign = session.get(Case, foreign_case_id)
        original = foreign.scope_code
        foreign.scope_code = original
        assert foreign in session.dirty
        assert not session.is_modified(foreign, include_collections=True)
        if operation == "header_update":
            receipt = SERVICE.update_change_request(
                session, change_request_id=cr["change_request_id"],
                expected_version=cr["row_version"],
                scope_label="Updated synthetic scope", description=None,
                submitted_on=None, requester_name=None,
                fields_set={"scope_label"}, reason="no-op control", user=USER,
            )
            action = "change_request.update"
        elif operation == "detail_create":
            receipt = SERVICE.create_change_request_detail(
                session, change_request_id=cr["change_request_id"],
                expected_version=cr["row_version"],
                classification_id=None, classification_label="Synthetic class",
                approval_status=None, old_value="old", new_value="new",
                note=None, reason="no-op control", user=USER,
            )
            action = "change_request_detail.create"
        else:
            receipt = SERVICE.transition_change_request(
                session, change_request_id=cr["change_request_id"],
                target_state="under_review", expected_version=cr["row_version"],
                reason="no-op control", user=USER,
            )
            action = "change_request.transition"
        assert receipt["change_request_id"] == cr["change_request_id"]
        session.commit()
    with Session(pg_engine) as verify:
        assert verify.get(Case, foreign_case_id).scope_code == original
        assert verify.scalar(select(func.count()).select_from(AuditEvent).where(
            AuditEvent.action == action,
        )) >= 1


def _change_request_detail_update_fixture(pg_engine):
    _, site_id = seed(pg_engine)
    cr = write(
        pg_engine, SERVICE.create_change_request,
        site_id=site_id, scope_label="Synthetic detail update owner",
        description="Change request detail update", submitted_on=DAY,
        requester_name="Synthetic operator", reason="seed",
    )
    detail = write(
        pg_engine, SERVICE.create_change_request_detail,
        change_request_id=cr["change_request_id"], expected_version=cr["row_version"],
        classification_id=None, classification_label="Old synthetic classification",
        approval_status=None, old_value="original", new_value="changed",
        note="original note", reason="seed detail",
    )
    return detail


def test_change_request_detail_update_rejects_foreign_pending_capa_before_flush(pg_engine):
    """Updating one detail must not autoflush another Case's unfinished CAPA."""
    detail = _change_request_detail_update_fixture(pg_engine)
    foreign_case_id, _ = seed(pg_engine)
    with Session(pg_engine) as session:
        audit_before = session.scalar(select(func.count()).select_from(AuditEvent))
        pending = CapaCycle(
            case_id=foreign_case_id, round_no=1, requested_on=DAY,
            incoming_reference="PENDING-FOREIGN-CR-DETAIL-UPDATE",
        )
        session.add(pending)
        flushes = []

        def forbid_flush(*_):
            flushes.append(True)
            raise AssertionError("Change Request detail update attempted foreign CAPA flush")

        event.listen(session, "before_flush", forbid_flush)
        try:
            with pytest.raises(HTTPException) as blocked:
                SERVICE.update_change_request_detail(
                    session, change_detail_id=detail["change_detail_id"],
                    expected_version=detail["row_version"],
                    classification_id=None, classification_label="Updated synthetic class",
                    approval_status=None, old_value=None, new_value=None, note=None,
                    fields_set={"classification_label"}, reason="separate operator update", user=USER,
                )
            assert blocked.value.status_code == 409
            assert "uncommitted" in str(blocked.value.detail).lower()
            assert not flushes
            assert pending in session.new
            with session.no_autoflush:
                assert session.scalar(select(func.count()).select_from(AuditEvent)) == audit_before
                assert session.scalar(select(func.count()).select_from(CapaCycle).where(
                    CapaCycle.case_id == foreign_case_id
                )) == 0
        finally:
            event.remove(session, "before_flush", forbid_flush)
            session.rollback()


def test_change_request_detail_update_allows_foreign_noop_marker(pg_engine):
    """An unchanged Case identity is not a pending independent mutation."""
    detail = _change_request_detail_update_fixture(pg_engine)
    foreign_case_id, _ = seed(pg_engine)
    with Session(pg_engine) as session:
        foreign = session.get(Case, foreign_case_id)
        original = foreign.scope_code
        foreign.scope_code = original
        assert foreign in session.dirty
        assert not session.is_modified(foreign, include_collections=True)
        receipt = SERVICE.update_change_request_detail(
            session, change_detail_id=detail["change_detail_id"],
            expected_version=detail["row_version"],
            classification_id=None, classification_label="Updated synthetic class",
            approval_status=None, old_value=None, new_value=None, note=None,
            fields_set={"classification_label"}, reason="no-op foreign marker", user=USER,
        )
        assert receipt["change_detail_id"] == detail["change_detail_id"]
        session.commit()
    with Session(pg_engine) as verify:
        assert verify.get(Case, foreign_case_id).scope_code == original
        assert verify.scalar(select(func.count()).select_from(AuditEvent).where(
            AuditEvent.action == "change_request_detail.update",
        )) >= 1


def _change_approval_session_fixture(pg_engine, *, existing: bool):
    _, site_id = seed(pg_engine)
    cr = write(
        pg_engine, SERVICE.create_change_request,
        site_id=site_id, scope_label="Synthetic approval workflow",
        description="Approval mutation session test", submitted_on=DAY,
        requester_name="Synthetic operator", reason="seed",
    )
    cr = write(
        pg_engine, SERVICE.transition_change_request,
        change_request_id=cr["change_request_id"], target_state="under_review",
        expected_version=cr["row_version"], reason="open review",
    )
    if existing:
        cr = write(
            pg_engine, SERVICE.upsert_change_approval,
            change_request_id=cr["change_request_id"], expected_version=cr["row_version"],
            handled_on=DAY, handled_by_name="Synthetic approver",
            result_label="under consideration", effective_on=None,
            approval_reference="SYNTH-APPROVAL-EXISTING", reason="seed approval",
        )
    return cr


@pytest.mark.parametrize("existing", [False, True], ids=["create", "update"])
def test_change_approval_upsert_rejects_foreign_pending_capa(pg_engine, existing):
    """Approval insertion/update must not flush foreign pending Case drafts."""
    cr = _change_approval_session_fixture(pg_engine, existing=existing)
    foreign_case_id, _ = seed(pg_engine)
    with Session(pg_engine) as session:
        audit_before = session.scalar(select(func.count()).select_from(AuditEvent))
        pending = CapaCycle(
            case_id=foreign_case_id, round_no=1, requested_on=DAY,
            incoming_reference="UNCOMMITTED-FOREIGN-CHANGE-APPROVAL-CAPA",
        )
        session.add(pending)
        flushes = []

        def forbid_flush(*_):
            flushes.append(True)
            raise AssertionError("Change approval upsert attempted a foreign CAPA flush")

        event.listen(session, "before_flush", forbid_flush)
        try:
            with pytest.raises(HTTPException) as blocked:
                SERVICE.upsert_change_approval(
                    session, change_request_id=cr["change_request_id"],
                    expected_version=cr["row_version"],
                    handled_on=DAY, handled_by_name="Updated approver",
                    result_label="under consideration", effective_on=None,
                    approval_reference="SYNTH-FOREIGN-UPSET-REF",
                    fields_set={"handled_by_name", "approval_reference"},
                    reason="synthetic independent approval", user=USER,
                )
            assert blocked.value.status_code == 409
            assert "uncommitted" in str(blocked.value.detail).lower()
            assert not flushes
            assert pending in session.new
            with session.no_autoflush:
                assert session.scalar(select(func.count()).select_from(AuditEvent)) == audit_before
                assert session.scalar(select(func.count()).select_from(CapaCycle).where(
                    CapaCycle.case_id == foreign_case_id
                )) == 0
        finally:
            event.remove(session, "before_flush", forbid_flush)
            session.rollback()


@pytest.mark.parametrize("existing", [False, True], ids=["create", "update"])
def test_change_approval_upsert_allows_foreign_noop_marker(pg_engine, existing):
    """No-op foreign Case dirtiness does not block approval mutation."""
    cr = _change_approval_session_fixture(pg_engine, existing=existing)
    foreign_case_id, _ = seed(pg_engine)
    with Session(pg_engine) as session:
        foreign = session.get(Case, foreign_case_id)
        original = foreign.scope_code
        foreign.scope_code = original
        assert foreign in session.dirty
        assert not session.is_modified(foreign, include_collections=True)
        receipt = SERVICE.upsert_change_approval(
            session, change_request_id=cr["change_request_id"],
            expected_version=cr["row_version"],
            handled_on=DAY, handled_by_name="Updated approver",
            result_label="under consideration", effective_on=None,
            approval_reference="SYNTH-APPROVAL-NOOP",
            fields_set={"handled_by_name", "approval_reference"},
            reason="no-op marker control", user=USER,
        )
        assert receipt["change_request_id"] == cr["change_request_id"]
        assert receipt["change_approval_id"]
        session.commit()
    with Session(pg_engine) as verify:
        assert verify.get(Case, foreign_case_id).scope_code == original
        assert verify.scalar(select(func.count()).select_from(AuditEvent).where(
            AuditEvent.action == ("change_approval.update" if existing else "change_approval.create"),
        )) >= 1


def _change_successor_session_fixture(pg_engine, *, kind):
    """Create one current committed source, then let CR snapshot its identity."""
    with Session(pg_engine) as setup:
        company = Company(legal_name=f"Synthetic successor owner {uuid4()}")
        setup.add(company)
        setup.flush()
        site = Site(company_id=company.id, site_name="Successor session isolation")
        setup.add(site)
        setup.flush()
        if kind == "certificate":
            source = Certificate(
                site_id=site.id, certificate_type="GLP",
                issuance_basis="administrative_no_inspection", latest_flag=True,
            )
            setup.add(source)
            setup.flush()
            setup.add(CertificateVersion(
                certificate_id=source.id, version_no=1,
                certificate_number=f"SOURCE-{uuid4()}", is_latest_version=True,
            ))
        else:
            source = BusinessEligibilityCertificate(
                site_id=site.id, company_id=company.id, latest_flag=True,
            )
            setup.add(source)
            setup.flush()
            setup.add(BusinessEligibilityVersion(
                business_eligibility_certificate_id=source.id,
                version_no=1, certificate_number=f"DDK-SOURCE-{uuid4()}",
            ))
        setup.commit()
        site_id, source_id = site.id, source.id
    cr = write(
        pg_engine, SERVICE.create_change_request,
        site_id=site_id, scope_label="Synthetic successor approval",
        description="Foreign Session isolation", submitted_on=DAY,
        requester_name="Synthetic operator", reason="seed",
    )
    source_field = (
        ChangeRequestAffectedArtifact.certificate_id
        if kind == "certificate"
        else ChangeRequestAffectedArtifact.business_eligibility_certificate_id
    )
    with Session(pg_engine) as lookup:
        affected_id = lookup.scalars(select(ChangeRequestAffectedArtifact.id).where(
            ChangeRequestAffectedArtifact.change_request_id == cr["change_request_id"],
            source_field == source_id,
        )).one()
    return cr, affected_id


@pytest.mark.parametrize("kind", ["certificate", "business_eligibility"])
def test_change_successor_rejects_foreign_pending_capa_without_flush(pg_engine, kind):
    """Issuing a new legal artifact must not save unrelated Case CAPA drafts."""
    cr, affected_id = _change_successor_session_fixture(pg_engine, kind=kind)
    foreign_case_id, _ = seed(pg_engine)
    with Session(pg_engine) as session:
        audit_before = session.scalar(select(func.count()).select_from(AuditEvent))
        issued_before = session.scalar(select(func.count()).select_from(ChangeRequestIssuedArtifact))
        pending = CapaCycle(
            case_id=foreign_case_id, round_no=1, requested_on=DAY,
            incoming_reference=f"UNCOMMITTED-FOREIGN-{kind}-SUCCESSOR-CAPA",
        )
        session.add(pending)
        flushes = []

        def forbid_flush(*_):
            flushes.append(True)
            raise AssertionError(f"{kind} successor attempted foreign CAPA flush")

        event.listen(session, "before_flush", forbid_flush)
        try:
            with pytest.raises(HTTPException) as blocked:
                method = (
                    SERVICE.issue_change_request_certificate_successor
                    if kind == "certificate"
                    else SERVICE.issue_change_request_business_eligibility_successor
                )
                method(
                    session, change_request_id=cr["change_request_id"],
                    source_affected_artifact_id=affected_id,
                    expected_version=cr["row_version"],
                    reason="separate operator intent", user=USER,
                )
            assert blocked.value.status_code == 409
            assert "uncommitted" in str(blocked.value.detail).lower()
            assert not flushes
            assert pending in session.new
            with session.no_autoflush:
                assert session.scalar(select(func.count()).select_from(AuditEvent)) == audit_before
                assert session.scalar(select(func.count()).select_from(ChangeRequestIssuedArtifact)) == issued_before
                assert session.scalar(select(func.count()).select_from(CapaCycle).where(
                    CapaCycle.case_id == foreign_case_id
                )) == 0
        finally:
            event.remove(session, "before_flush", forbid_flush)
            session.rollback()


@pytest.mark.parametrize("kind", ["certificate", "business_eligibility"])
def test_change_successor_allows_foreign_noop_case_marker(pg_engine, kind):
    """No-op cached Case markers do not invalidate a lawful successor issue."""
    cr, affected_id = _change_successor_session_fixture(pg_engine, kind=kind)
    foreign_case_id, _ = seed(pg_engine)
    with Session(pg_engine) as session:
        foreign = session.get(Case, foreign_case_id)
        scope_before = foreign.scope_code
        foreign.scope_code = scope_before
        assert foreign in session.dirty
        assert not session.is_modified(foreign, include_collections=True)
        method = (
            SERVICE.issue_change_request_certificate_successor
            if kind == "certificate"
            else SERVICE.issue_change_request_business_eligibility_successor
        )
        issued = method(
            session, change_request_id=cr["change_request_id"],
            source_affected_artifact_id=affected_id,
            expected_version=cr["row_version"],
            reason="no-op Case marker control", user=USER,
        )
        assert issued["issued_artifact_link_id"]
        session.commit()
    with Session(pg_engine) as verify:
        assert verify.get(Case, foreign_case_id).scope_code == scope_before
        assert verify.scalar(select(func.count()).select_from(ChangeRequestIssuedArtifact).where(
            ChangeRequestIssuedArtifact.change_request_id == cr["change_request_id"],
        )) == 1
        audit_action = (
            "change_request.certificate_successor.issue"
            if kind == "certificate"
            else "change_request.business_eligibility_successor.issue"
        )
        assert verify.scalar(select(func.count()).select_from(AuditEvent).where(
            AuditEvent.action == audit_action,
        )) == 1


def test_business_eligibility_issue_refuses_foreign_pending_capa(pg_engine):
    """Direct DDK issuance must not implicitly commit another Case's CAPA."""
    _, site_id = seed(pg_engine)
    foreign_case_id, _ = seed(pg_engine)
    with Session(pg_engine) as session:
        audit_before = session.scalar(select(func.count()).select_from(AuditEvent))
        certificate_before = session.scalar(select(func.count()).select_from(BusinessEligibilityCertificate))
        pending = CapaCycle(
            case_id=foreign_case_id, round_no=1, requested_on=DAY,
            incoming_reference="UNCOMMITTED-FOREIGN-DIRECT-DDK-CAPA",
        )
        session.add(pending)
        flushes = []

        def forbid_flush(*_):
            flushes.append(True)
            raise AssertionError("Direct business eligibility issuance attempted foreign CAPA flush")

        event.listen(session, "before_flush", forbid_flush)
        try:
            with pytest.raises(HTTPException) as blocked:
                SERVICE.issue_business_eligibility(
                    session, site_id=site_id, certificate_number="SYNTH-DDK-FENCE",
                    issued_on=DAY, expires_on=None,
                    professional_responsible_person_name=None, notes=None,
                    linked_certificates=[], reason="foreign Session draft", user=USER,
                )
            assert blocked.value.status_code == 409
            assert "uncommitted" in str(blocked.value.detail).lower()
            assert not flushes
            assert pending in session.new
            with session.no_autoflush:
                assert session.scalar(select(func.count()).select_from(AuditEvent)) == audit_before
                assert session.scalar(select(func.count()).select_from(BusinessEligibilityCertificate)) == certificate_before
                assert session.scalar(select(func.count()).select_from(CapaCycle).where(
                    CapaCycle.case_id == foreign_case_id
                )) == 0
        finally:
            event.remove(session, "before_flush", forbid_flush)
            session.rollback()


def test_business_eligibility_issue_allows_foreign_noop_case_marker(pg_engine):
    """An unchanged cached foreign Case must not block direct DDK issuance."""
    _, site_id = seed(pg_engine)
    foreign_case_id, _ = seed(pg_engine)
    with Session(pg_engine) as session:
        foreign = session.get(Case, foreign_case_id)
        scope_before = foreign.scope_code
        foreign.scope_code = scope_before
        assert foreign in session.dirty
        assert not session.is_modified(foreign, include_collections=True)
        receipt = SERVICE.issue_business_eligibility(
            session, site_id=site_id, certificate_number="SYNTH-DDK-NOOP",
            issued_on=DAY, expires_on=None,
            professional_responsible_person_name=None, notes=None,
            linked_certificates=[], reason="no-op foreign marker", user=USER,
        )
        assert receipt["business_eligibility_certificate_id"]
        session.commit()
    with Session(pg_engine) as verify:
        assert verify.get(Case, foreign_case_id).scope_code == scope_before
        assert verify.scalar(select(func.count()).select_from(BusinessEligibilityCertificate).where(
            BusinessEligibilityCertificate.id == receipt["business_eligibility_certificate_id"]
        )) == 1
        assert verify.scalar(select(func.count()).select_from(AuditEvent).where(
            AuditEvent.action == "business_eligibility.issue"
        )) >= 1
