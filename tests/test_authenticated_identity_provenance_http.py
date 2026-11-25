"""Read-only /auth/me operator receipt binds identity to runtime provenance.

This endpoint can support human UAT evidence, but mocked Google verifier
checks below are not live Google token verification or approval to go live.
"""
from dataclasses import replace

import backend.app.auth as auth_module
from backend.app.main import create_app
from test_auth_identity_subject_binding import _asgi_request, _provisioned_app


def test_header_stub_receipt_discloses_test_auth_mode_and_deployed_commit():
    app = create_app(
        "sqlite:///:memory:",
        app_env={
            "AUTH_MODE": "header_stub",
            "AUTH_DEFAULT_ROLE": "reader",
            "DEPLOY_GIT_SHA": "synthetic-header-commit",
        },
    )
    denied = _asgi_request(app, "GET", "/auth/me")
    assert denied.status_code == 401
    ok = _asgi_request(
        app, "GET", "/auth/me",
        headers={"X-Auth-User": "synthetic-reader", "X-Auth-Role": "reader"},
    )
    assert ok.status_code == 200
    receipt = ok.json()
    assert receipt["username"] == "synthetic-reader"
    assert receipt["auth_mode"] == "header_stub"
    assert receipt["auth_role_source"] == "env_map"
    assert receipt["deployment_git_sha"] == "synthetic-header-commit"
    assert receipt["role_codes"] == ["reader"]
    assert "certificate.issue" not in receipt["permissions"]


def test_oidc_database_receipt_contains_verified_claim_owner_and_git_sha(
    tmp_path, monkeypatch,
):
    app = _provisioned_app(
        tmp_path, "google_oidc", bound_subject="synthetic-google-subject",
    )
    app.state.config = replace(
        app.state.config, deployment_git_sha="synthetic-oidc-deployment-sha",
    )
    monkeypatch.setattr(
        auth_module, "_verify_google_oidc_assertion",
        lambda token, client_id: {
            "email": "alice@example.com",
            "sub": "synthetic-google-subject",
            "email_verified": True,
        },
    )
    # Header role overrides cannot substitute for actual Google bearer token.
    no_bearer = _asgi_request(
        app, "GET", "/auth/me",
        headers={"X-Auth-User": "synthetic-admin", "X-Auth-Role": "admin"},
    )
    assert no_bearer.status_code == 401
    ok = _asgi_request(
        app, "GET", "/auth/me",
        headers={
            "Authorization": "Bearer synthetic-verified-credential",
            "X-Auth-Role": "admin",
        },
    )
    assert ok.status_code == 200, ok.json()
    receipt = ok.json()
    assert receipt["username"] == "account-owner"
    assert receipt["email"] == "alice@example.com"
    assert receipt["subject"] == "synthetic-google-subject"
    assert receipt["auth_mode"] == "google_oidc"
    assert receipt["auth_role_source"] == "database"
    assert receipt["deployment_git_sha"] == "synthetic-oidc-deployment-sha"
    assert receipt["role_codes"] == ["reader"]
    assert "certificate.issue" not in receipt["permissions"]

    # A different synthetic runtime stamp remains distinct on /auth/me.
    # Operators cannot infer real deployment identity from a green CI test.
    app.state.config = replace(app.state.config, deployment_git_sha="")
    missing_sha = _asgi_request(
        app, "GET", "/auth/me",
        headers={"Authorization": "Bearer synthetic-verified-credential"},
    )
    assert missing_sha.status_code == 200
    assert missing_sha.json()["deployment_git_sha"] is None


def test_direct_identity_helper_preserves_legacy_call_without_runtime_provenance():
    from backend.app.api.routers.identity import current_identity
    from backend.app.auth import build_authenticated_user

    user = build_authenticated_user(
        "synthetic-direct", "reader", permissions={"document.read"},
    )
    receipt = current_identity(user)
    assert receipt.username == "synthetic-direct"
    assert receipt.role_codes == ["reader"]
    assert receipt.permissions == ["document.read"]
    assert receipt.auth_mode == "header_stub"
    assert receipt.auth_role_source is None
    assert receipt.deployment_git_sha is None
