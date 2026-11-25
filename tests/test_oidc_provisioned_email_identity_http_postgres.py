"""Google OIDC -> DB-provisioned RBAC -> real QĐKT Process B GET.

Google signature verification is deliberately mocked, not claimed as UAT;
the production auth/router/SQL owner and disposable migrated PostgreSQL are
real. Email case aliases must resolve one account or fail closed.
"""
from __future__ import annotations

import asyncio
import json
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

import backend.app.auth as auth
from backend.app.db.models.phase1 import AppUser, AppUserRole, RbacRole
from backend.app.main import create_app
from test_canonical_workflow_postgres import DAY, SERVICE, pg_engine, seed, write


def _oidc_http(app, path, *, token="synthetic-token"):
    async def invoke():
        messages = []
        received = False

        async def receive():
            nonlocal received
            if not received:
                received = True
                return {"type": "http.request", "body": b"", "more_body": False}
            await asyncio.Future()

        async def send(message):
            messages.append(message)

        headers = [(b"content-type", b"application/json")]
        if token is not None:
            headers.append((b"authorization", ("Bearer " + token).encode()))

        await app({
            "type": "http", "asgi": {"version": "3.0"},
            "http_version": "1.1", "method": "GET", "scheme": "http",
            "path": path, "raw_path": path.encode(), "query_string": b"",
            "headers": headers,
            "client": ("127.0.0.1", 12345), "server": ("localhost", 80),
            "root_path": "",
        }, receive, send)
        status = next(x["status"] for x in messages if x["type"] == "http.response.start")
        data = b"".join(x.get("body", b"") for x in messages if x["type"] == "http.response.body")
        return status, json.loads(data) if data else None

    return asyncio.run(invoke())


def _provision(pg_engine, *, username, email, subject, role_code="admin"):
    with Session(pg_engine) as db:
        role = db.scalar(select(RbacRole).where(RbacRole.role_code == role_code))
        if role is None:
            role = RbacRole(role_code=role_code)
            db.add(role)
            db.flush()
        user = AppUser(
            username=username, external_email=email,
            external_subject=subject, is_active=True,
        )
        db.add(user)
        db.flush()
        db.add(AppUserRole(app_user_id=user.id, rbac_role_id=role.id))
        db.commit()
        return user.id


def _app(pg_engine):
    return create_app(
        pg_engine.url.render_as_string(hide_password=False),
        app_env={
            "AUTH_MODE": "google_oidc",
            "AUTH_OIDC_CLIENT_ID": "synthetic-gxp-client",
            "AUTH_ROLE_SOURCE": "database",
            "AUTH_DEFAULT_ROLE": "reader",
            "APP_ENV": "development",
        },
    )


def _issued_decision(pg_engine):
    case_id, _ = seed(pg_engine)
    plan = write(
        pg_engine, SERVICE.upsert_inspection_plan,
        case_id=case_id, plan_start_on=DAY, plan_end_on=DAY,
        planning_sheet_name="Synthetic Google OIDC DB RBAC",
        decision_document_hint=None, reason="Synthetic plan",
    )
    decision_id = str(uuid4())
    write(
        pg_engine, SERVICE.record_qdkt_issued_decision,
        case_id=case_id, decision_id=decision_id,
        expected_plan_version=plan["row_version"],
        reference="SYNTH-OIDC-ROLE", decision_on=DAY,
        source_text="Synthetic approved external decision",
        relation_type="INITIAL", related_decision_id=None,
        external_approval_confirmed=True,
        approval_basis="Synthetic external confirmation",
        team_confirmed=True, roster_source="USER_ENTERED",
        draft_id=None, draft_team_id=None, draft_team_revision=None,
        acknowledged_changes=False,
        members=[{
            "source_member_id": str(uuid4()),
            "display_name": "Synthetic inspector",
            "role_code": "LEADER", "job_title": "Inspector",
        }],
        reason="Synthetic operator record",
    )
    return f"/cases/{case_id}/qdkt-issued-decisions/{decision_id}", case_id, decision_id


def test_verified_oidc_claim_resolves_mixed_case_provisioned_email_and_reads_qdkt(
    pg_engine, monkeypatch,
):
    path, case_id, decision_id = _issued_decision(pg_engine)
    email = "Operator." + uuid4().hex[:12] + "@Example.COM"
    subject = "google-oidc-" + uuid4().hex
    _provision(
        pg_engine, username="synthetic-oidc-" + uuid4().hex,
        email=email, subject=subject,
    )
    claims = {"email": email.lower(), "sub": subject, "email_verified": True}
    monkeypatch.setattr(
        auth, "_verify_google_oidc_assertion",
        lambda token, audience: claims,
    )
    app = _app(pg_engine)
    status, detail = _oidc_http(app, path)
    assert status == 200, detail
    assert detail["case_id"] == case_id
    assert detail["decision_id"] == decision_id
    assert detail["relation_type"] == "INITIAL"
    assert detail["operator_attestation_recorded"] is True
    assert detail["legal_issuance_verified"] is False

    # Signed-but-unverified email is never sufficient to select an RBAC user.
    claims["email_verified"] = False
    status, denied = _oidc_http(app, path)
    assert status == 403, denied
    assert "verified" in denied["detail"].lower()

    # Missing Google bearer never falls back to X-Auth-Role or header stub.
    status, denied = _oidc_http(app, path, token=None)
    assert status == 401, denied


def test_oidc_casefold_email_collision_rejects_ambiguous_rbac_owners(
    pg_engine, monkeypatch,
):
    path, _, _ = _issued_decision(pg_engine)
    unique = uuid4().hex[:16]
    email = f"Collision.{unique}@Example.COM"
    subject_a = "subject-a-" + uuid4().hex
    _provision(
        pg_engine, username="synthetic-a-" + uuid4().hex,
        email=email, subject=subject_a,
    )
    _provision(
        pg_engine, username="synthetic-b-" + uuid4().hex,
        email=email.lower(), subject="subject-b-" + uuid4().hex,
    )
    monkeypatch.setattr(
        auth, "_verify_google_oidc_assertion",
        lambda token, audience: {
            "email": email.lower(), "sub": subject_a, "email_verified": True,
        },
    )
    status, denied = _oidc_http(_app(pg_engine), path)
    assert status == 403, denied
    assert "ambiguously provisioned" in denied["detail"]


def test_oidc_matching_email_cannot_override_different_provisioned_subject(
    pg_engine, monkeypatch,
):
    path, _, _ = _issued_decision(pg_engine)
    email = "Subject." + uuid4().hex[:12] + "@Example.COM"
    _provision(
        pg_engine, username="synthetic-subject-" + uuid4().hex,
        email=email, subject="trusted-" + uuid4().hex,
    )
    monkeypatch.setattr(
        auth, "_verify_google_oidc_assertion",
        lambda token, audience: {
            "email": email.lower(), "sub": "different-" + uuid4().hex,
            "email_verified": True,
        },
    )
    status, denied = _oidc_http(_app(pg_engine), path)
    assert status == 403, denied
    assert "subject does not match" in denied["detail"]
