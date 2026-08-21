from pathlib import Path

from backend.app.config import DEFAULT_SQLITE_DATABASE_URL, load_app_config, resolve_database_url, validate_runtime_config
from backend.app.storage.factory import create_storage_service_from_env
from tools.validate_phase14_cloud_run_contract import parse_env_file, validate_env_contract


def test_resolve_database_url_builds_cloud_sql_socket_url():
    url = resolve_database_url(
        {
            "DB_DRIVER": "postgresql+psycopg",
            "DB_NAME": "gxp_qlcl",
            "DB_USER": "gxp_app",
            "DB_PASSWORD": "secret value",
            "CLOUD_SQL_CONNECTION_NAME": "project:asia-southeast1:instance",
        }
    )

    assert url.startswith("postgresql+psycopg://gxp_app:secret+value@/")
    assert "host=%2Fcloudsql%2Fproject%3Aasia-southeast1%3Ainstance" in url


def test_load_app_config_uses_composed_database_url_when_explicit_url_missing():
    config = load_app_config(
        {
            "DB_NAME": "gxp_qlcl",
            "DB_USER": "gxp_app",
            "DB_PASSWORD": "secret",
            "CLOUD_SQL_CONNECTION_NAME": "project:asia-southeast1:instance",
        }
    )

    assert config.database_url.startswith("postgresql+psycopg://")


def test_validate_env_contract_accepts_cloud_run_baseline():
    report = validate_env_contract(
        {
            "APP_ENV": "production",
            "DEPLOYMENT_PLATFORM": "google_cloud_run",
            "AUTH_MODE": "google_iap_jwt",
            "AUTH_ROLE_SOURCE": "database",
            "AUTH_IAP_EXPECTED_AUDIENCE": "/projects/123/locations/asia-southeast1/services/gxp-web",
            "AUTH_IAP_ALLOWED_EMAIL_DOMAIN": "example.com",
            "DB_NAME": "gxp_qlcl",
            "DB_USER": "gxp_app",
            "DB_PASSWORD": "secret",
            "CLOUD_SQL_CONNECTION_NAME": "project:asia-southeast1:instance",
            "STORAGE_CLASS": "synology_private_share_prod",
            "STORAGE_INSPECTION_ROOT": "/mnt/synology/inspection",
            "STORAGE_DKKD_ROOT": "/mnt/synology/dkkd",
            "STORAGE_TEMPLATE_ROOT": "/mnt/synology/templates",
        }
    )

    assert report.errors == []


def test_validate_env_contract_rejects_sqlite_and_missing_iap_audience():
    report = validate_env_contract(
        {
            "DEPLOYMENT_PLATFORM": "google_cloud_run",
            "AUTH_MODE": "google_iap_jwt",
            "DATABASE_URL": "sqlite:///tmp/local.db",
            "STORAGE_INSPECTION_ROOT": "/mnt/synology/inspection",
        }
    )

    assert "AUTH_IAP_EXPECTED_AUDIENCE is required when AUTH_MODE=google_iap_jwt." in report.errors
    assert "DATABASE_URL must not point to sqlite when DEPLOYMENT_PLATFORM=google_cloud_run." in report.errors


def test_parse_env_file_reads_example_contract(tmp_path: Path):
    env_file = tmp_path / "cloudrun.env"
    env_file.write_text(
        "DEPLOYMENT_PLATFORM=google_cloud_run\n"
        "AUTH_MODE=header_stub\n"
        "STORAGE_INSPECTION_ROOT=/mnt/synology/inspection\n",
        encoding="utf-8",
    )

    parsed = parse_env_file(env_file)

    assert parsed["DEPLOYMENT_PLATFORM"] == "google_cloud_run"
    assert parsed["AUTH_MODE"] == "header_stub"
    assert parsed["STORAGE_INSPECTION_ROOT"] == "/mnt/synology/inspection"


def test_validate_env_contract_accepts_external_bridge_storage_mode():
    report = validate_env_contract(
        {
            "APP_ENV": "production",
            "DEPLOYMENT_PLATFORM": "google_cloud_run",
            "AUTH_MODE": "google_iap_jwt",
            "AUTH_ROLE_SOURCE": "database",
            "AUTH_IAP_EXPECTED_AUDIENCE": "/projects/123/locations/asia-southeast1/services/gxp-web",
            "DB_NAME": "gxp_qlcl",
            "DB_USER": "gxp_app",
            "DB_PASSWORD": "secret",
            "CLOUD_SQL_CONNECTION_NAME": "project:asia-southeast1:instance",
            "STORAGE_CLASS": "external_bridge_http",
            "STORAGE_BRIDGE_BASE_URL": "https://bridge.internal",
            "STORAGE_BRIDGE_AUTH_AUDIENCE": "https://bridge.internal",
        }
    )

    assert report.errors == []


def test_load_app_config_dev_fallback_keeps_sqlite():
    config = load_app_config({})

    assert config.database_url == DEFAULT_SQLITE_DATABASE_URL
    assert config.is_production is False


def test_validate_runtime_config_accepts_dev_sqlite_and_fake_storage(tmp_path: Path):
    storage = create_storage_service_from_env({"STORAGE_INSPECTION_ROOT": str(tmp_path / "inspection")})
    config = load_app_config({})

    validate_runtime_config(config, database_url=config.database_url, storage_service=storage, storage_error=None)


def test_validate_runtime_config_rejects_production_sqlite():
    config = load_app_config({"APP_ENV": "production"})

    try:
        validate_runtime_config(config, database_url=config.database_url, storage_service=None, storage_error="Missing storage")
    except RuntimeError as exc:
        assert "sqlite" in str(exc)
    else:
        raise AssertionError("Expected production sqlite validation to fail.")


def test_validate_runtime_config_rejects_header_stub_in_production(tmp_path: Path):
    storage = create_storage_service_from_env(
        {
            "STORAGE_INSPECTION_ROOT": str(tmp_path / "inspection"),
            "STORAGE_CLASS": "external_bridge_http",
            "STORAGE_BRIDGE_BASE_URL": "https://bridge.internal",
        }
    )
    config = load_app_config(
        {
            "APP_ENV": "production",
            "DATABASE_URL": "postgresql+psycopg://user:secret@host/db",
            "AUTH_MODE": "header_stub",
        }
    )

    try:
        validate_runtime_config(config, database_url=config.database_url, storage_service=storage, storage_error=None)
    except RuntimeError as exc:
        assert "header_stub" in str(exc)
    else:
        raise AssertionError("Expected production header_stub validation to fail.")


def test_validate_runtime_config_rejects_fake_storage_in_production():
    config = load_app_config(
        {
            "APP_ENV": "production",
            "DATABASE_URL": "postgresql+psycopg://user:secret@host/db",
            "AUTH_MODE": "google_iap_jwt",
            "AUTH_ROLE_SOURCE": "database",
            "AUTH_IAP_EXPECTED_AUDIENCE": "/projects/123/locations/asia-southeast1/services/gxp-web",
        }
    )
    storage = create_storage_service_from_env({"STORAGE_INSPECTION_ROOT": ".", "STORAGE_CLASS": "local_filesystem_fake"})

    try:
        validate_runtime_config(config, database_url=config.database_url, storage_service=storage, storage_error=None)
    except RuntimeError as exc:
        assert "fake storage" in str(exc)
    else:
        raise AssertionError("Expected production fake storage validation to fail.")


def test_validate_runtime_config_rejects_direct_filesystem_storage_in_main_app_production(tmp_path: Path):
    config = load_app_config(
        {
            "APP_ENV": "production",
            "DATABASE_URL": "postgresql+psycopg://user:secret@host/db",
            "AUTH_MODE": "google_iap_jwt",
            "AUTH_ROLE_SOURCE": "database",
            "AUTH_IAP_EXPECTED_AUDIENCE": "/projects/123/locations/asia-southeast1/services/gxp-web",
        }
    )
    storage = create_storage_service_from_env(
        {
            "STORAGE_CLASS": "synology_private_share_prod",
            "STORAGE_INSPECTION_ROOT": str(tmp_path / "inspection"),
        }
    )

    try:
        validate_runtime_config(config, database_url=config.database_url, storage_service=storage, storage_error=None)
    except RuntimeError as exc:
        assert "external_bridge_http" in str(exc)
    else:
        raise AssertionError("Expected direct filesystem storage to fail in main-app production mode.")
