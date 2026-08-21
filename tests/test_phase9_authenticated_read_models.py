from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.auth import (
    authenticate_google_iap_request,
    build_authenticated_user,
    parse_role_map,
    require_role,
    resolve_mapped_role,
)
from backend.app.db.base import Base
from backend.app.db.models.phase1 import AppUser, AppUserRole, RbacPermission, RbacRole, RbacRolePermission
from backend.app.main import create_app


def test_build_authenticated_user_accepts_valid_stub_headers():
    user = build_authenticated_user("alice", "manager")

    assert user.username == "alice"
    assert user.role == "manager"
    assert user.auth_mode == "header_stub"


def test_build_authenticated_user_rejects_missing_identity():
    try:
        build_authenticated_user("", "reader")
    except HTTPException as exc:
        assert exc.status_code == 401
    else:
        raise AssertionError("Expected HTTPException for missing username")


def test_require_role_rejects_disallowed_role():
    user = build_authenticated_user("alice", "viewer")

    try:
        require_role(user, {"reader", "manager"})
    except HTTPException as exc:
        assert exc.status_code == 403
    else:
        raise AssertionError("Expected HTTPException for disallowed role")


def test_phase9_detail_routes_are_registered():
    app = create_app("sqlite:///:memory:")
    routes = {route.path for route in app.routes if hasattr(route, "path")}

    assert "/companies/{company_id}" in routes
    assert "/sites/{site_id}" in routes
    assert "/cases/{case_id}" in routes


def test_parse_role_map_accepts_email_role_pairs():
    mapping = parse_role_map("alice@example.com=manager;bob@example.com=admin")

    assert mapping == {
        "alice@example.com": "manager",
        "bob@example.com": "admin",
    }


def test_resolve_mapped_role_prefers_explicit_email_mapping():
    role = resolve_mapped_role(
        "alice@example.com",
        default_role="reader",
        role_map_raw="alice@example.com=manager",
    )

    assert role == "manager"


def test_authenticate_google_iap_request_uses_verified_claims():
    app = create_app(
        "sqlite:///:memory:",
        app_env={
            "AUTH_MODE": "google_iap_jwt",
            "AUTH_IAP_EXPECTED_AUDIENCE": "/projects/123/global/backendServices/456",
            "AUTH_DEFAULT_ROLE": "reader",
            "AUTH_ROLE_MAP": "alice@example.com=manager",
            "AUTH_IAP_ALLOWED_EMAIL_DOMAIN": "example.com",
        },
    )
    request = SimpleNamespace(
        app=app,
        headers={"X-Goog-IAP-JWT-Assertion": "token"},
    )

    user = authenticate_google_iap_request(
        request,
        verifier=lambda assertion, audience: {
            "email": "alice@example.com",
            "sub": "accounts.google.com:alice-subject",
            "aud": audience,
            "raw": assertion,
        },
    )

    assert user.username == "alice@example.com"
    assert user.role == "manager"
    assert user.auth_mode == "google_iap_jwt"
    assert user.email == "alice@example.com"
    assert user.subject == "accounts.google.com:alice-subject"


def test_authenticate_google_iap_request_can_use_explicit_header_fallback():
    app = create_app(
        "sqlite:///:memory:",
        app_env={
            "AUTH_MODE": "google_iap_jwt",
            "AUTH_IAP_EXPECTED_AUDIENCE": "/projects/123/global/backendServices/456",
            "AUTH_DEFAULT_ROLE": "inspector",
            "AUTH_TRUSTED_HEADER_FALLBACK": "true",
            "AUTH_IAP_ALLOWED_EMAIL_DOMAIN": "example.com",
        },
    )
    request = SimpleNamespace(
        app=app,
        headers={
            "X-Goog-Authenticated-User-Email": "accounts.google.com:inspector@example.com",
            "X-Goog-Authenticated-User-Id": "accounts.google.com:abc123",
        },
    )

    user = authenticate_google_iap_request(request)

    assert user.username == "inspector@example.com"
    assert user.role == "inspector"
    assert user.email == "inspector@example.com"
    assert user.subject == "abc123"


def test_authenticate_google_iap_request_fails_closed_without_assertion_or_fallback():
    app = create_app(
        "sqlite:///:memory:",
        app_env={
            "AUTH_MODE": "google_iap_jwt",
            "AUTH_IAP_EXPECTED_AUDIENCE": "/projects/123/global/backendServices/456",
        },
    )
    request = SimpleNamespace(app=app, headers={})

    try:
        authenticate_google_iap_request(request)
    except HTTPException as exc:
        assert exc.status_code == 401
    else:
        raise AssertionError("Expected HTTPException for missing Google Cloud IAP identity assertion")


def test_authenticate_google_iap_request_rejects_outside_domain():
    app = create_app(
        "sqlite:///:memory:",
        app_env={
            "AUTH_MODE": "google_iap_jwt",
            "AUTH_IAP_EXPECTED_AUDIENCE": "/projects/123/global/backendServices/456",
            "AUTH_IAP_ALLOWED_EMAIL_DOMAIN": "example.com",
        },
    )
    request = SimpleNamespace(
        app=app,
        headers={"X-Goog-IAP-JWT-Assertion": "token"},
    )

    try:
        authenticate_google_iap_request(
            request,
            verifier=lambda assertion, audience: {"email": "outsider@other.com", "sub": "outsider"},
        )
    except HTTPException as exc:
        assert exc.status_code == 403
    else:
        raise AssertionError("Expected HTTPException for outside Google identity domain")


def test_authenticate_google_iap_request_fails_closed_on_ambiguous_database_identity(tmp_path):
    database_path = tmp_path / "auth-ambiguity.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        role = RbacRole(role_code="manager", description="Manager")
        permission = RbacPermission(permission_code="case.edit", description="Edit case")
        user_by_email = AppUser(
            username="email-owner",
            external_email="alice@example.com",
            display_name="Email Owner",
            is_active=True,
        )
        user_by_subject = AppUser(
            username="subject-owner",
            external_subject="subject-123",
            display_name="Subject Owner",
            is_active=True,
        )
        session.add_all([role, permission, user_by_email, user_by_subject])
        session.flush()
        session.add(AppUserRole(app_user_id=user_by_email.id, rbac_role_id=role.id))
        session.add(AppUserRole(app_user_id=user_by_subject.id, rbac_role_id=role.id))
        session.add(RbacRolePermission(rbac_role_id=role.id, rbac_permission_id=permission.id))
        session.commit()

    app = create_app(
        database_url,
        app_env={
            "AUTH_MODE": "google_iap_jwt",
            "AUTH_ROLE_SOURCE": "database",
            "AUTH_IAP_EXPECTED_AUDIENCE": "/projects/123/global/backendServices/456",
            "AUTH_IAP_ALLOWED_EMAIL_DOMAIN": "example.com",
        },
    )
    request = SimpleNamespace(
        app=app,
        headers={"X-Goog-IAP-JWT-Assertion": "token"},
    )

    try:
        authenticate_google_iap_request(
            request,
            verifier=lambda assertion, audience: {
                "email": "alice@example.com",
                "sub": "subject-123",
            },
        )
    except HTTPException as exc:
        assert exc.status_code == 403
        assert "different provisioned users" in exc.detail
    else:
        raise AssertionError("Expected ambiguity between email and subject claims to fail closed")
