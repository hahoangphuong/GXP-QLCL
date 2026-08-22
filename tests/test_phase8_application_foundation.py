from types import SimpleNamespace

from backend.app.main import create_app
from backend.app.api.routers.health import healthz
from backend.app.api.routers.health import readyz
from backend.app.api.routers.status import app_status


def test_application_status_endpoint_exposes_google_cloud_default():
    app = create_app("sqlite:///:memory:")
    payload = app_status(SimpleNamespace(app=app))
    assert payload["deployment_platform"] == "compute_engine_vm"
    assert payload["frontend_topology"] == "nginx_static_proxy"
    assert payload["auth"]["mode"] == payload["auth_mode"]
    assert "phases" in payload


def test_health_endpoint_reflects_application_foundation_mode():
    app = create_app("sqlite:///:memory:")
    payload = healthz(SimpleNamespace(app=app))
    assert payload["mode"] == "application_foundation"


def test_ready_endpoint_reports_schema_mismatch_without_runtime_tables():
    app = create_app("sqlite:///:memory:")
    response = readyz(SimpleNamespace(app=app))
    assert response.status_code == 503


def test_frontend_dist_is_served_as_spa(monkeypatch, tmp_path):
    frontend_dist = tmp_path / "frontend" / "dist"
    assets_dir = frontend_dist / "assets"
    assets_dir.mkdir(parents=True)
    (frontend_dist / "index.html").write_text("<html><body>shell</body></html>", encoding="utf-8")
    (assets_dir / "index.js").write_text("console.log('ok');", encoding="utf-8")

    monkeypatch.setenv("GXP_FRONTEND_DIST_ROOT", str(frontend_dist))
    app = create_app("sqlite:///:memory:")
    route_paths = {route.path for route in app.routes if hasattr(route, "path")}
    spa_route = next(route for route in app.routes if getattr(route, "path", "") == "/{full_path:path}")
    response = spa_route.endpoint("cases/abc")

    assert "/assets" in route_paths
    assert response.path.name == "index.html"


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
