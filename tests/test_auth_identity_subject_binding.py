"""Adversarial database identity matching for both supported Google auth adapters."""

import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import backend.app.auth as auth_module
from backend.app.auth import authenticate_google_iap_request, authenticate_google_oidc_request, require_permissions
from backend.app.db.base import Base
from backend.app.db.models.phase1 import AppUser, AppUserRole, RbacRole
from backend.app.main import create_app


PROVIDERS = ("google_iap_jwt", "google_oidc")


def _provisioned_app(tmp_path, provider: str, *, bound_subject: str | None):
    database_url = f"sqlite:///{(tmp_path / 'identity-binding.sqlite').as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        role = RbacRole(role_code="reader", description="Read-only user")
        account = AppUser(
            username="account-owner",
            external_email="alice@example.com",
            external_subject=bound_subject,
            display_name="Account Owner",
            is_active=True,
        )
        session.add_all([role, account])
        session.flush()
        session.add(AppUserRole(app_user_id=account.id, rbac_role_id=role.id))
        session.commit()
    engine.dispose()

    return create_app(
        database_url,
        app_env={
            "AUTH_MODE": provider,
            "AUTH_ROLE_SOURCE": "database",
            "AUTH_IAP_EXPECTED_AUDIENCE": "/projects/123/global/backendServices/456",
            "AUTH_OIDC_CLIENT_ID": "expected-web-client-id",
            "AUTH_ALLOWED_EMAIL_DOMAIN": "example.com",
        },
    )


def _authenticate(app, provider: str, *, subject: str | None):
    claims = {"email": "alice@example.com", "email_verified": True}
    if subject is not None:
        claims["sub"] = subject

    if provider == "google_iap_jwt":
        request = SimpleNamespace(app=app, headers={"X-Goog-IAP-JWT-Assertion": "verified-assertion"})
        return authenticate_google_iap_request(request, verifier=lambda *_: claims)
    request = SimpleNamespace(app=app, headers={"Authorization": "Bearer verified-credential"})
    return authenticate_google_oidc_request(request, verifier=lambda *_: claims)


@pytest.mark.parametrize("provider", PROVIDERS)
@pytest.mark.parametrize("incoming_subject", ("different-google-account", None))
def test_email_match_cannot_override_bound_google_subject(tmp_path, provider, incoming_subject):
    app = _provisioned_app(tmp_path, provider, bound_subject="original-google-account")
    with pytest.raises(HTTPException) as exc:
        _authenticate(app, provider, subject=incoming_subject)
    assert exc.value.status_code == 403
    assert "subject" in exc.value.detail


@pytest.mark.parametrize("provider", PROVIDERS)
def test_matching_google_subject_preserves_database_authorization(tmp_path, provider):
    app = _provisioned_app(tmp_path, provider, bound_subject="original-google-account")
    user = _authenticate(app, provider, subject="original-google-account")
    assert user.username == "account-owner"
    assert user.auth_mode == provider
    assert user.role == "reader"


@pytest.mark.parametrize("provider", PROVIDERS)
def test_legacy_email_only_provisioning_still_works(tmp_path, provider):
    app = _provisioned_app(tmp_path, provider, bound_subject=None)
    user = _authenticate(app, provider, subject="original-google-account")
    assert user.username == "account-owner"
    assert user.auth_mode == provider


@pytest.mark.parametrize("verified_claim", (False, None, "true"))
@pytest.mark.parametrize("bound_subject", (None, "original-google-account"))
def test_oidc_rejects_unverified_email_claim_even_when_identity_matches(
    tmp_path, verified_claim, bound_subject,
):
    app = _provisioned_app(tmp_path, "google_oidc", bound_subject=bound_subject)
    claims = {"email": "alice@example.com", "sub": "original-google-account"}
    if verified_claim is not None:
        claims["email_verified"] = verified_claim
    request = SimpleNamespace(app=app, headers={"Authorization": "Bearer verified-signature-token"})
    with pytest.raises(HTTPException) as exc:
        authenticate_google_oidc_request(request, verifier=lambda *_: claims)
    assert exc.value.status_code == 403
    assert "not verified" in exc.value.detail


def test_iap_assertion_does_not_require_google_oidc_email_verified_claim(tmp_path):
    app = _provisioned_app(tmp_path, "google_iap_jwt", bound_subject="original-google-account")
    request = SimpleNamespace(app=app, headers={"X-Goog-IAP-JWT-Assertion": "verified-assertion"})
    user = authenticate_google_iap_request(
        request,
        verifier=lambda *_: {"email": "alice@example.com", "sub": "original-google-account"},
    )
    assert user.username == "account-owner"
    assert user.role == "reader"


@pytest.mark.parametrize("provider", PROVIDERS)
def test_database_role_rotation_downgrade_and_deactivation_use_each_request_snapshot(tmp_path, provider):
    """No cached permission survives a new verified request after an RBAC edit.

    This exercises only the test-injected verifier boundary. It does NOT
    authenticate against Google's live issuer, or assert token revocation.
    """
    app = _provisioned_app(tmp_path, provider, bound_subject="original-google-account")

    def current_identity():
        return _authenticate(app, provider, subject="original-google-account")

    # Initially only a reader. No mutate permissions.
    reader = current_identity()
    assert reader.role_codes == ("reader",)
    assert "certificate.view" in reader.permissions
    with pytest.raises(HTTPException) as denied:
        require_permissions(reader, {"certificate.issue"})
    assert denied.value.status_code == 403

    # A separately committed RBAC role change must affect the NEXT request.
    with app.state.session_factory() as session:
        admin_role = RbacRole(role_code="admin", description="Test admin")
        session.add(admin_role)
        session.flush()
        assignment = session.query(AppUserRole).one()
        assignment.rbac_role_id = admin_role.id
        session.commit()

    admin = current_identity()
    assert admin.role_codes == ("admin",)
    require_permissions(admin, {"certificate.issue"})
    assert "certificate.issue" in admin.permissions

    # Downgrade the same subject, same email and same credential verifier input.
    # A previous request's granted permissions must not leak into new requests.
    with app.state.session_factory() as session:
        assignment = session.query(AppUserRole).one()
        reader_role = session.query(RbacRole).filter_by(role_code="reader").one()
        assignment.rbac_role_id = reader_role.id
        session.commit()

    again = current_identity()
    assert again.role_codes == ("reader",)
    assert "certificate.issue" not in again.permissions
    with pytest.raises(HTTPException) as denied_again:
        require_permissions(again, {"certificate.issue"})
    assert denied_again.value.status_code == 403

    # Removing the assignment is not a fallback to a default/env role.
    with app.state.session_factory() as session:
        session.delete(session.query(AppUserRole).one())
        session.commit()
    with pytest.raises(HTTPException) as missing_assignment:
        current_identity()
    assert missing_assignment.value.status_code == 403

    # An inactive provisioned account cannot regain access via matching claims.
    with app.state.session_factory() as session:
        account = session.query(AppUser).one()
        account.is_active = False
        session.commit()
    with pytest.raises(HTTPException) as inactive:
        current_identity()
    assert inactive.value.status_code == 403



def _asgi_request(app, method, path, *, headers=None, json_body=None):
    """Exercise ASGI FastAPI routing without installing a second HTTP client."""
    content = b"" if json_body is None else json.dumps(json_body).encode("utf-8")
    raw_headers = [(b"host", b"localhost")]
    raw_headers.extend(
        (key.lower().encode("ascii"), value.encode("utf-8"))
        for key, value in (headers or {}).items()
    )
    if json_body is not None:
        raw_headers.append((b"content-type", b"application/json"))

    async def exchange():
        replies = []
        first = True

        async def receive():
            nonlocal first
            if first:
                first = False
                return {"type": "http.request", "body": content, "more_body": False}
            # A real client waits for disconnect; middleware cancels this
            # waiter after the response finishes.
            await asyncio.Event().wait()

        async def send(message):
            replies.append(message)

        await app(
            {
                "type": "http", "asgi": {"version": "3.0"},
                "http_version": "1.1", "scheme": "http",
                "method": method, "path": path, "raw_path": path.encode("utf-8"),
                "root_path": "", "query_string": b"",
                "headers": raw_headers, "client": ("127.0.0.1", 9876),
                "server": ("localhost", 80), "app": app,
            },
            receive, send,
        )
        status = next(msg["status"] for msg in replies if msg["type"] == "http.response.start")
        payload = b"".join(
            msg.get("body", b"") for msg in replies
            if msg["type"] == "http.response.body"
        )
        return SimpleNamespace(status_code=status, json=lambda: json.loads(payload))

    return asyncio.run(exchange())


@pytest.mark.parametrize("provider", PROVIDERS)
def test_authenticated_http_routes_recompute_access_and_forbid_stale_certificate_issue(
    tmp_path, monkeypatch, provider,
):
    """Exercise the real FastAPI auth dependency and certificate.issue endpoint.

    Google signature verification is substituted ONLY at the verifier seam;
    requests, dependency injection, database lookup, and RBAC gates are real.
    No Google token or live production resource is involved.
    """
    app = _provisioned_app(tmp_path, provider, bound_subject="original-google-account")
    claims = {
        "email": "alice@example.com", "email_verified": True,
        "sub": "original-google-account",
    }
    verifier_name = (
        "_verify_google_oidc_assertion"
        if provider == "google_oidc" else "_verify_iap_jwt_assertion"
    )
    monkeypatch.setattr(auth_module, verifier_name, lambda *_: claims)
    header = (
        {"Authorization": "Bearer synthetic-verified-credential"}
        if provider == "google_oidc" else
        {"X-Goog-IAP-JWT-Assertion": "synthetic-verified-assertion"}
    )
    # A valid-shaped but nonexistent Site; readers must fail on permission
    # before any domain mutation or Site-specific workflow is attempted.
    post_url = "/sites/ffffffff-ffff-ffff-ffff-ffffffffffff/certificates"
    post_body = {"certificate_type": "GMP"}

    class ASGIClient:
        def get(self, path, *, headers=None):
            return _asgi_request(app, "GET", path, headers=headers)

        def post(self, path, *, headers=None, json=None):
            return _asgi_request(app, "POST", path, headers=headers, json_body=json)

    client = ASGIClient()
    assert client.get("/auth/me").status_code == 401

    initial = client.get("/auth/me", headers=header)
    assert initial.status_code == 200
    assert initial.json()["role_codes"] == ["reader"]
    assert "certificate.issue" not in initial.json()["permissions"]
    assert client.get("/sites", headers=header).status_code == 200
    assert client.post(post_url, headers=header, json=post_body).status_code == 403

    with app.state.session_factory() as session:
        admin = RbacRole(role_code="admin", description="Synthetic admin role")
        session.add(admin)
        session.flush()
        session.query(AppUserRole).one().rbac_role_id = admin.id
        session.commit()

    promoted = client.get("/auth/me", headers=header)
    assert promoted.status_code == 200
    assert promoted.json()["role_codes"] == ["admin"]
    assert "certificate.issue" in promoted.json()["permissions"]

    with app.state.session_factory() as session:
        reader_role = session.query(RbacRole).filter_by(role_code="reader").one()
        session.query(AppUserRole).one().rbac_role_id = reader_role.id
        session.commit()

    downgraded = client.get("/auth/me", headers=header)
    assert downgraded.status_code == 200
    assert downgraded.json()["role_codes"] == ["reader"]
    assert "certificate.issue" not in downgraded.json()["permissions"]
    # The REAL write route denies the same previously-privileged session.
    assert client.post(post_url, headers=header, json=post_body).status_code == 403

    with app.state.session_factory() as session:
        session.delete(session.query(AppUserRole).one())
        session.commit()

    assert client.get("/auth/me", headers=header).status_code == 403
    assert client.post(post_url, headers=header, json=post_body).status_code == 403

    with app.state.session_factory() as session:
        session.query(AppUser).one().is_active = False
        session.commit()

    assert client.get("/auth/me", headers=header).status_code == 403
    assert client.get("/sites", headers=header).status_code == 403
