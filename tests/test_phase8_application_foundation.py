import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.app.config import load_app_config
from backend.app.main import create_app
from backend.app.auth import ROLE_PERMISSIONS, build_authenticated_user
from backend.app.api.routers.identity import current_identity
from backend.app.api.routers.health import healthz
from backend.app.api.routers.health import readyz
from backend.app.api.routers.status import admin_system_status, app_status


def _request_app(app, path: str, headers: list[tuple[bytes, bytes]] | None = None):
    messages: list[dict[str, object]] = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    asyncio.run(
        app(
            {
                "type": "http",
                "asgi": {"version": "3.0"},
                "http_version": "1.1",
                "method": "GET",
                "scheme": "http",
                "path": path,
                "raw_path": path.encode("utf-8"),
                "query_string": b"",
                "headers": headers or [],
                "client": ("127.0.0.1", 12345),
                "server": ("testserver", 80),
                "root_path": "",
            },
            receive,
            send,
        )
    )
    status = next(message["status"] for message in messages if message["type"] == "http.response.start")
    body = b"".join(message.get("body", b"") for message in messages if message["type"] == "http.response.body")
    return status, json.loads(body)


def test_application_status_endpoint_exposes_google_cloud_default():
    app = create_app(
        "sqlite:///:memory:",
        app_env={
            "DEPLOYMENT_GIT_SHA": "abcdef1234567890",
            "DEPLOYMENT_GIT_SHORT_SHA": "abcdef1",
            "DEPLOYMENT_BRANCH": "main",
        },
    )
    payload = app_status(SimpleNamespace(app=app))
    assert payload["deployment_platform"] == "compute_engine_vm"
    assert payload["frontend_topology"] == "nginx_static_proxy"
    assert payload["auth"]["mode"] == payload["auth_mode"]
    assert payload["deployment"]["git_sha"] == "abcdef1234567890"
    assert payload["deployment"]["git_short_sha"] == "abcdef1"
    assert payload["deployment"]["branch"] == "main"
    assert "phases" in payload


def test_admin_system_status_requires_the_existing_admin_permission():
    app = create_app("sqlite:///:memory:")
    admin = build_authenticated_user("admin01", "admin", permissions=ROLE_PERMISSIONS["admin"])
    payload = admin_system_status(SimpleNamespace(app=app), user=admin)

    assert payload["app_name"] == "GxP Web"

    manager = build_authenticated_user("manager01", "manager", permissions=ROLE_PERMISSIONS["manager"])
    with pytest.raises(HTTPException, match="missing required permission"):
        admin_system_status(SimpleNamespace(app=app), user=manager)


def test_authenticated_identity_route_is_registered():
    app = create_app("sqlite:///:memory:")
    routes = {route.path for route in app.routes if hasattr(route, "path")}

    assert "/auth/me" in routes
    assert "/admin/runtime-status" in routes


def test_authenticated_identity_exposes_only_backend_resolved_authorization_context():
    user = build_authenticated_user(
        "admin01",
        "admin",
        email="admin@example.test",
        subject="google-subject",
        role_codes=("admin", "reader"),
        permissions=("admin.users", "case.view"),
    )

    payload = current_identity(user)

    assert payload.username == "admin01"
    assert payload.email == "admin@example.test"
    assert payload.subject == "google-subject"
    assert payload.role_codes == ["admin", "reader"]
    assert payload.permissions == ["admin.users", "case.view"]


def test_identity_and_admin_status_routes_enforce_header_stub_rbac_end_to_end():
    app = create_app("sqlite:///:memory:")
    admin_headers = [(b"x-auth-user", b"admin01"), (b"x-auth-role", b"admin")]
    manager_headers = [(b"x-auth-user", b"manager01"), (b"x-auth-role", b"manager")]

    identity_status, identity_payload = _request_app(app, "/auth/me", admin_headers)
    admin_status, _ = _request_app(app, "/admin/runtime-status", admin_headers)
    manager_status, manager_payload = _request_app(app, "/admin/runtime-status", manager_headers)

    assert identity_status == 200
    assert identity_payload["role_codes"] == ["admin"]
    assert "admin.users" in identity_payload["permissions"]
    assert admin_status == 200
    assert manager_status == 403
    assert manager_payload["detail"] == "User is missing required permission."


def test_health_endpoint_reflects_application_foundation_mode():
    app = create_app("sqlite:///:memory:", app_env={"DEPLOYMENT_GIT_SHA": "abcdef1234567890"})
    payload = healthz(SimpleNamespace(app=app))
    assert payload["mode"] == "application_foundation"
    assert payload["deployment_git_sha"] == "abcdef1234567890"


def test_ready_endpoint_reports_schema_mismatch_without_runtime_tables():
    app = create_app("sqlite:///:memory:")
    response = readyz(SimpleNamespace(app=app))
    assert response.status_code == 503


def test_frontend_dist_serves_only_explicit_spa_paths(monkeypatch, tmp_path):
    frontend_dist = tmp_path / "frontend" / "dist"
    assets_dir = frontend_dist / "assets"
    assets_dir.mkdir(parents=True)
    (frontend_dist / "index.html").write_text("<html><body>shell</body></html>", encoding="utf-8")
    (assets_dir / "index.js").write_text("console.log('ok');", encoding="utf-8")

    monkeypatch.setenv("GXP_FRONTEND_DIST_ROOT", str(frontend_dist))
    app = create_app("sqlite:///:memory:")
    route_paths = {route.path for route in app.routes if hasattr(route, "path")}
    spa_route = next(route for route in app.routes if getattr(route, "path", "") == "/{full_path:path}")
    search_response = spa_route.endpoint("search")
    case_response = spa_route.endpoint("cases/abc")
    asset_response = spa_route.endpoint("assets/index.js")

    assert "/assets" in route_paths
    assert search_response.path.name == "index.html"
    assert case_response.path.name == "index.html"
    assert asset_response.path.name == "index.js"

    with pytest.raises(HTTPException) as exc_info:
        spa_route.endpoint("scanner/unrecognized-path")

    assert exc_info.value.status_code == 404


def test_frontend_fallback_does_not_replace_registered_api_routes(monkeypatch, tmp_path):
    frontend_dist = tmp_path / "frontend" / "dist"
    frontend_dist.mkdir(parents=True)
    (frontend_dist / "index.html").write_text("<html><body>shell</body></html>", encoding="utf-8")
    monkeypatch.setenv("GXP_FRONTEND_DIST_ROOT", str(frontend_dist))
    app = create_app("sqlite:///:memory:")
    messages: list[dict[str, object]] = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    asyncio.run(
        app(
            {
                "type": "http",
                "asgi": {"version": "3.0"},
                "http_version": "1.1",
                "method": "GET",
                "scheme": "http",
                "path": "/app/status",
                "raw_path": b"/app/status",
                "query_string": b"",
                "headers": [],
                "client": ("127.0.0.1", 12345),
                "server": ("testserver", 80),
                "root_path": "",
            },
            receive,
            send,
        )
    )

    assert any(message["type"] == "http.response.start" and message["status"] == 200 for message in messages)


def test_existing_readonly_routes_remain_registered():
    app = create_app("sqlite:///:memory:")
    routes = {route.path for route in app.routes if hasattr(route, "path")}

    assert "/healthz" in routes
    assert "/readyz" in routes
    assert "/app/status" in routes
    assert "/companies" in routes
    assert "/sites" in routes
    assert "/cases" in routes
    assert "/storage/inspection-folder" in routes
    assert "/storage/dkkd-folder" in routes


def test_load_app_config_prefers_deployment_runtime_env_names():
    config = load_app_config(
        {
            "DEPLOYMENT_GIT_SHA": "1234567890abcdef",
            "DEPLOYMENT_GIT_SHORT_SHA": "1234567",
            "DEPLOYMENT_BRANCH": "main",
            "DEPLOY_GIT_SHA": "old-sha-should-not-win",
            "DEPLOY_GIT_SHORT_SHA": "oldold1",
            "DEPLOY_BRANCH": "stale",
        }
    )

    assert config.deployment_git_sha == "1234567890abcdef"
    assert config.deployment_git_short_sha == "1234567"
    assert config.deployment_branch == "main"


def test_request_logger_uses_same_deployment_sha(caplog):
    app = create_app(
        "sqlite:///:memory:",
        app_env={
            "DEPLOYMENT_GIT_SHA": "abcdef1234567890",
            "GXP_FRONTEND_DIST_ROOT": "missing-dist-root",
        },
    )
    messages: list[dict[str, object]] = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    with caplog.at_level("INFO", logger="gxp.request"):
        asyncio.run(
            app(
                {
                    "type": "http",
                    "asgi": {"version": "3.0"},
                    "http_version": "1.1",
                    "method": "GET",
                    "scheme": "http",
                    "path": "/healthz",
                    "raw_path": b"/healthz",
                    "query_string": b"",
                    "headers": [],
                    "client": ("127.0.0.1", 12345),
                    "server": ("testserver", 80),
                    "root_path": "",
                },
                receive,
                send,
            )
        )

    assert any(message["type"] == "http.response.start" and message["status"] == 200 for message in messages)
    assert any('"deployment_git_sha": "abcdef1234567890"' in record.message for record in caplog.records)
