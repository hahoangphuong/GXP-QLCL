from backend.app.main import create_app


def test_create_app_exposes_readonly_routes():
    app = create_app("sqlite:///:memory:")
    routes = {route.path for route in app.routes if hasattr(route, "path")}
    assert "/healthz" in routes
    assert "/companies" in routes
    assert "/sites" in routes
    assert "/cases" in routes
    assert "/storage/inspection-folder" in routes
