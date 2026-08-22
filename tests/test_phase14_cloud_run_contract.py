from pathlib import Path

from backend.app.auth import authenticate_google_oidc_request
from backend.app.config import DEFAULT_SQLITE_DATABASE_URL, load_app_config, resolve_database_url, validate_runtime_config
from backend.app.storage.factory import create_storage_service_from_env
from tools.env_utils import parse_env_file
from tools.validate_phase14_cloud_run_contract import validate_env_contract


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


def test_resolve_database_url_builds_local_postgres_url():
    url = resolve_database_url(
        {
            "DB_MODE": "local_postgres",
            "DB_DRIVER": "postgresql+psycopg",
            "DB_NAME": "gxp_qlcl",
            "DB_USER": "gxp_app",
            "DB_PASSWORD": "secret value",
            "DB_HOST": "127.0.0.1",
            "DB_PORT": "5432",
        }
    )

    assert url == "postgresql+psycopg://gxp_app:secret+value@127.0.0.1:5432/gxp_qlcl"


def test_validate_env_contract_accepts_cloud_run_baseline():
    report = validate_env_contract(
        {
            "APP_ENV": "production",
            "DEPLOYMENT_PLATFORM": "google_cloud_run",
            "AUTH_PROVIDER": "google_iap_jwt",
            "AUTH_ROLE_SOURCE": "database",
            "AUTH_IAP_EXPECTED_AUDIENCE": "/projects/123/locations/asia-southeast1/services/gxp-web",
            "AUTH_ALLOWED_EMAIL_DOMAIN": "example.com",
            "DB_MODE": "cloud_sql",
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


def test_validate_env_contract_rejects_sqlite_and_missing_iap_audience():
    report = validate_env_contract(
        {
            "DEPLOYMENT_PLATFORM": "google_cloud_run",
            "AUTH_MODE": "google_iap_jwt",
            "DATABASE_URL": "sqlite:///tmp/local.db",
            "STORAGE_CLASS": "external_bridge_http",
            "STORAGE_BRIDGE_BASE_URL": "https://bridge.internal",
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
            "AUTH_PROVIDER": "google_iap_jwt",
            "AUTH_ROLE_SOURCE": "database",
            "AUTH_IAP_EXPECTED_AUDIENCE": "/projects/123/locations/asia-southeast1/services/gxp-web",
            "DB_MODE": "cloud_sql",
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


def test_validate_env_contract_accepts_google_oidc_with_local_postgres_and_direct_smb():
    report = validate_env_contract(
        {
            "APP_ENV": "production",
            "DEPLOYMENT_PLATFORM": "google_cloud_run",
            "AUTH_PROVIDER": "google_oidc",
            "AUTH_ROLE_SOURCE": "database",
            "AUTH_OIDC_CLIENT_ID": "gxp-web.apps.googleusercontent.com",
            "DB_MODE": "local_postgres",
            "DB_NAME": "gxp_qlcl",
            "DB_USER": "gxp_app",
            "DB_PASSWORD": "secret",
            "DB_HOST": "127.0.0.1",
            "DB_PORT": "5432",
            "STORAGE_CLASS": "synology_smb",
            "STORAGE_INSPECTION_ROOT": "/mnt/synology/inspection",
            "STORAGE_DKKD_ROOT": "/mnt/synology/dkkd",
            "STORAGE_TEMPLATE_ROOT": "/mnt/synology/templates",
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
            "DB_MODE": "local_postgres",
            "DB_NAME": "gxp_qlcl",
            "DB_USER": "gxp_app",
            "DB_PASSWORD": "secret",
            "DB_HOST": "127.0.0.1",
            "DB_PORT": "5432",
            "AUTH_PROVIDER": "google_oidc",
            "AUTH_ROLE_SOURCE": "database",
            "AUTH_OIDC_CLIENT_ID": "gxp-web.apps.googleusercontent.com",
        }
    )
    storage = create_storage_service_from_env(
        {
            "STORAGE_CLASS": "synology_smb",
            "STORAGE_INSPECTION_ROOT": r"\\100.95.45.127\Hồ sơ nội bộ\01 - Kiểm tra GPs",
        }
    )

    validate_runtime_config(config, database_url=config.database_url, storage_service=storage, storage_error=None)


def test_load_app_config_prefers_auth_provider_and_db_mode():
    config = load_app_config(
        {
            "AUTH_PROVIDER": "google_oidc",
            "AUTH_OIDC_CLIENT_ID": "gxp-web.apps.googleusercontent.com",
            "DB_MODE": "local_postgres",
            "DB_NAME": "gxp_qlcl",
            "DB_USER": "gxp_app",
            "DB_PASSWORD": "secret",
        }
    )

    assert config.auth_mode == "google_oidc"
    assert config.db_mode == "local_postgres"
    assert config.auth_oidc_client_id == "gxp-web.apps.googleusercontent.com"


def test_create_storage_service_from_env_supports_synology_smb_alias(tmp_path: Path):
    service = create_storage_service_from_env(
        {
            "STORAGE_CLASS": "synology_smb",
            "STORAGE_INSPECTION_ROOT": r"\\100.95.45.127\Hồ sơ nội bộ\01 - Kiểm tra GPs",
        }
    )

    assert service.config.storage_class == "synology_smb"


def test_authenticate_google_oidc_request_uses_database_role_source():
    class _Config:
        auth_oidc_client_id = "gxp-web.apps.googleusercontent.com"
        auth_iap_allowed_email_domain = "example.com"
        auth_role_source = "env_map"
        auth_default_role = "reader"
        auth_role_map = "operator@example.com=manager"

    class _State:
        config = _Config()

    class _Request:
        headers = {"Authorization": "Bearer token"}
        app = type("App", (), {"state": _State()})()

    request = _Request()

    user = authenticate_google_oidc_request(
        request,
        verifier=lambda token, client_id: {"email": "operator@example.com", "sub": "sub-1"},
    )

    assert user.auth_mode == "google_oidc"
    assert user.email == "operator@example.com"
    assert "manager" in user.role_codes
