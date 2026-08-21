from __future__ import annotations

from pathlib import Path

from backend.app.main import create_app


def test_create_app_allows_dev_defaults():
    app = create_app()

    assert app.state.config.is_production is False


def test_create_app_rejects_production_sqlite_default():
    try:
        create_app(app_env={"APP_ENV": "production"})
    except RuntimeError as exc:
        assert "sqlite" in str(exc)
    else:
        raise AssertionError("Expected production startup with sqlite fallback to fail.")


def test_create_app_accepts_production_cloud_sql_and_bridge_config(monkeypatch):
    monkeypatch.setattr("backend.app.main.build_session_factory", lambda _url: lambda: None)
    app = create_app(
        app_env={
            "APP_ENV": "production",
            "DATABASE_URL": "postgresql+psycopg://user:secret@host/db",
            "AUTH_MODE": "google_iap_jwt",
            "AUTH_ROLE_SOURCE": "database",
            "AUTH_IAP_EXPECTED_AUDIENCE": "iap-audience",
        },
        storage_env={
            "STORAGE_CLASS": "external_bridge_http",
            "STORAGE_BRIDGE_BASE_URL": "https://bridge.internal",
        },
    )

    assert app.state.config.is_production is True
    assert app.state.storage_service is not None
