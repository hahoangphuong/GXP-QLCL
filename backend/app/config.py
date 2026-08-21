from __future__ import annotations

from dataclasses import dataclass
import os
from urllib.parse import quote_plus

from backend.app.project_paths import phase_artifact_path
from backend.app.storage.types import StorageServiceProtocol


DEFAULT_SQLITE_DATABASE_URL = f"sqlite:///{phase_artifact_path('phase2', 'staging_readonly.db').as_posix()}"
PRODUCTION_ENV_NAMES = {"prod", "production"}


@dataclass(frozen=True)
class AppConfig:
    app_name: str = "GxP Web"
    app_mode: str = "application_foundation"
    app_env: str = "development"
    deployment_platform: str = "google_cloud_run"
    frontend_topology: str = "single_cloud_run_service"
    auth_mode: str = "header_stub"
    auth_default_role: str = "reader"
    auth_role_map: str = ""
    auth_iap_expected_audience: str = ""
    auth_iap_allowed_email_domain: str = ""
    auth_trusted_header_fallback: bool = False
    database_url: str = DEFAULT_SQLITE_DATABASE_URL
    auth_role_source: str = "env_map"
    deployment_git_sha: str = ""
    deployment_git_short_sha: str = ""
    deployment_branch: str = ""
    deployment_image_uri: str = ""
    deployment_timestamp_utc: str = ""
    cloud_run_service_name: str = ""
    db_name: str = ""
    db_user: str = ""

    @property
    def is_production(self) -> bool:
        return self.app_env.strip().lower() in PRODUCTION_ENV_NAMES


def _read_bool(source: dict[str, str], key: str, default: bool) -> bool:
    raw = source.get(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def resolve_database_url(source: dict[str, str]) -> str:
    explicit = source.get("DATABASE_URL", "").strip()
    if explicit:
        return explicit

    db_name = source.get("DB_NAME", "").strip()
    db_user = source.get("DB_USER", "").strip()
    db_password = source.get("DB_PASSWORD", "").strip()
    db_driver = source.get("DB_DRIVER", "").strip() or "postgresql+psycopg"
    db_host = source.get("DB_HOST", "").strip()
    cloud_sql_connection_name = source.get("CLOUD_SQL_CONNECTION_NAME", "").strip()

    if not db_name or not db_user or not db_password:
        return DEFAULT_SQLITE_DATABASE_URL

    quoted_user = quote_plus(db_user)
    quoted_password = quote_plus(db_password)
    if cloud_sql_connection_name:
        quoted_db_name = quote_plus(db_name)
        quoted_socket = quote_plus(f"/cloudsql/{cloud_sql_connection_name}")
        return f"{db_driver}://{quoted_user}:{quoted_password}@/{quoted_db_name}?host={quoted_socket}"
    if db_host:
        quoted_db_name = quote_plus(db_name)
        return f"{db_driver}://{quoted_user}:{quoted_password}@{db_host}/{quoted_db_name}"
    return DEFAULT_SQLITE_DATABASE_URL


def validate_runtime_config(
    config: AppConfig,
    *,
    database_url: str,
    storage_service: StorageServiceProtocol | None,
    storage_error: str | None,
) -> None:
    if not config.is_production:
        return

    database_url = database_url.strip()
    if not database_url:
        raise RuntimeError("Production startup failed: database_url resolved blank.")
    if database_url.startswith("sqlite:"):
        raise RuntimeError("Production startup failed: sqlite is not allowed in production.")

    auth_mode = config.auth_mode.strip().lower()
    if auth_mode == "header_stub":
        raise RuntimeError("Production startup failed: AUTH_MODE=header_stub is not allowed.")
    if auth_mode != "google_iap_jwt":
        raise RuntimeError(f"Production startup failed: unsupported AUTH_MODE={config.auth_mode!r}.")
    if not config.auth_iap_expected_audience.strip():
        raise RuntimeError("Production startup failed: AUTH_IAP_EXPECTED_AUDIENCE is required.")
    if config.auth_trusted_header_fallback:
        raise RuntimeError("Production startup failed: AUTH_TRUSTED_HEADER_FALLBACK must be disabled.")
    if config.auth_role_source.strip().lower() != "database":
        raise RuntimeError("Production startup failed: AUTH_ROLE_SOURCE must be 'database'.")
    if config.auth_role_map.strip():
        raise RuntimeError("Production startup failed: AUTH_ROLE_MAP must not own production authorization.")

    if storage_error is not None:
        raise RuntimeError(f"Production startup failed: storage is not configured: {storage_error}")
    if storage_service is None:
        raise RuntimeError("Production startup failed: storage service is required.")
    storage_class = storage_service.config.storage_class.strip().lower()
    if "fake" in storage_class:
        raise RuntimeError("Production startup failed: fake storage adapters are not allowed.")
    if storage_class != "external_bridge_http":
        raise RuntimeError("Production startup failed: main app must use STORAGE_CLASS=external_bridge_http.")


def load_app_config(env: dict[str, str] | None = None) -> AppConfig:
    source = os.environ if env is None else env
    return AppConfig(
        app_name=source.get("APP_NAME", "GxP Web"),
        app_mode=source.get("APP_MODE", "application_foundation"),
        app_env=source.get("APP_ENV", source.get("ENV", "development")),
        deployment_platform=source.get("DEPLOYMENT_PLATFORM", "google_cloud_run"),
        frontend_topology=source.get("FRONTEND_TOPOLOGY", "single_cloud_run_service"),
        auth_mode=source.get("AUTH_MODE", "header_stub"),
        auth_default_role=source.get("AUTH_DEFAULT_ROLE", "reader"),
        auth_role_map=source.get("AUTH_ROLE_MAP", ""),
        auth_iap_expected_audience=source.get("AUTH_IAP_EXPECTED_AUDIENCE", ""),
        auth_iap_allowed_email_domain=source.get("AUTH_IAP_ALLOWED_EMAIL_DOMAIN", ""),
        auth_trusted_header_fallback=_read_bool(source, "AUTH_TRUSTED_HEADER_FALLBACK", False),
        auth_role_source=source.get("AUTH_ROLE_SOURCE", "env_map"),
        database_url=resolve_database_url(source),
        deployment_git_sha=source.get("DEPLOY_GIT_SHA", ""),
        deployment_git_short_sha=source.get("DEPLOY_GIT_SHORT_SHA", ""),
        deployment_branch=source.get("DEPLOY_BRANCH", ""),
        deployment_image_uri=source.get("DEPLOY_IMAGE_URI", ""),
        deployment_timestamp_utc=source.get("DEPLOY_TIMESTAMP_UTC", ""),
        cloud_run_service_name=source.get("CLOUD_RUN_SERVICE_NAME", ""),
        db_name=source.get("DB_NAME", ""),
        db_user=source.get("DB_USER", ""),
    )
