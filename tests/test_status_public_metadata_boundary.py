"""The unauthenticated bootstrap status must not disclose runtime internals."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.app.api.routers.status import admin_system_status, app_status
from backend.app.auth import build_authenticated_user
from backend.app.main import create_app


def test_public_bootstrap_metadata_is_redacted_but_admin_runtime_retains_details():
    app = create_app(
        "sqlite:///:memory:",
        app_env={
            "AUTH_MODE": "google_oidc",
            "AUTH_OIDC_CLIENT_ID": "public-web-client",
            "AUTH_ROLE_SOURCE": "database",
            "AUTH_ALLOWED_EMAIL_DOMAIN": "example.invalid",
            "DB_NAME": "internal_rehearsal_name",
            "DB_USER": "internal_runtime_role",
            "DEPLOY_IMAGE_URI": "private.registry.invalid/internal/runtime:synthetic",
            "CLOUD_RUN_SERVICE_NAME": "internal-service",
            "DEPLOY_GIT_SHA": "fixed-fixture-commit",
            "DEPLOY_BRANCH": "synthetic-test-branch",
        },
    )
    request = SimpleNamespace(app=app)
    paths = {route.path for route in app.routes if hasattr(route, "path")}
    assert "/app/status" in paths
    assert "/admin/runtime-status" in paths

    public = app_status(request)
    assert public["auth"]["mode"] == "google_oidc"
    assert public["auth"]["oidc_client_id"] == "public-web-client"
    assert public["auth"]["allowed_email_domain"] == "example.invalid"
    assert public["deployment"]["git_sha"] == "fixed-fixture-commit"

    internal = ("db_name", "db_user", "image_uri", "cloud_run_service_name")
    # Keep nullable JSON fields in the public contract for existing TS clients.
    assert all(public["deployment"][key] is None for key in internal)
    assert "internal_rehearsal_name" not in str(public)
    assert "internal_runtime_role" not in str(public)
    assert "private.registry.invalid" not in str(public)
    assert "internal-service" not in str(public)

    admin = build_authenticated_user(
        "synthetic-admin", "admin", permissions={"admin.users"}
    )
    full = admin_system_status(request, user=admin)
    assert full["deployment"]["db_name"] == "internal_rehearsal_name"
    assert full["deployment"]["db_user"] == "internal_runtime_role"
    assert full["deployment"]["image_uri"] == (
        "private.registry.invalid/internal/runtime:synthetic"
    )
    assert full["deployment"]["cloud_run_service_name"] == "internal-service"
    assert full["auth"] == public["auth"]

    reader = build_authenticated_user(
        "synthetic-reader", "reader", permissions={"certificate.view"}
    )
    with pytest.raises(HTTPException) as forbidden:
        admin_system_status(request, user=reader)
    assert forbidden.value.status_code == 403
