"""Adversarial database identity matching for both supported Google auth adapters."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.auth import authenticate_google_iap_request, authenticate_google_oidc_request
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
