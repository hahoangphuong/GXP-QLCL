from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.config import resolve_database_url


DEFAULT_ENV_PATH = Path("backend/.env.cloudrun.example")
SUPPORTED_AUTH_MODES = {"header_stub", "google_iap_jwt"}


@dataclass(frozen=True)
class ValidationReport:
    errors: list[str]
    warnings: list[str]
    resolved_database_url: str

    @property
    def ok(self) -> bool:
        return not self.errors


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator:
            raise ValueError(f"Invalid env line: {raw_line!r}")
        values[key.strip()] = value.strip()
    return values


def validate_env_contract(env: dict[str, str]) -> ValidationReport:
    errors: list[str] = []
    warnings: list[str] = []

    deployment_platform = env.get("DEPLOYMENT_PLATFORM", "").strip() or "google_cloud_run"
    auth_mode = env.get("AUTH_MODE", "").strip() or "header_stub"
    storage_class = env.get("STORAGE_CLASS", "").strip() or "local_filesystem_fake"
    resolved_database_url = resolve_database_url(env)

    if deployment_platform != "google_cloud_run":
        errors.append("DEPLOYMENT_PLATFORM must be google_cloud_run for the Cloud Run deployment baseline.")

    if auth_mode not in SUPPORTED_AUTH_MODES:
        errors.append(f"AUTH_MODE must be one of {sorted(SUPPORTED_AUTH_MODES)}.")

    if auth_mode == "google_iap_jwt":
        if not env.get("AUTH_IAP_EXPECTED_AUDIENCE", "").strip():
            errors.append("AUTH_IAP_EXPECTED_AUDIENCE is required when AUTH_MODE=google_iap_jwt.")
        if not env.get("AUTH_IAP_ALLOWED_EMAIL_DOMAIN", "").strip():
            warnings.append("AUTH_IAP_ALLOWED_EMAIL_DOMAIN is blank; operator domain restriction is not enforced.")
        if env.get("AUTH_TRUSTED_HEADER_FALLBACK", "").strip().lower() in {"1", "true", "yes", "on"}:
            errors.append("AUTH_TRUSTED_HEADER_FALLBACK must be disabled for production-compatible Cloud Run config.")
        if (env.get("AUTH_ROLE_SOURCE", "").strip() or "env_map") != "database":
            errors.append("AUTH_ROLE_SOURCE must be database for production-compatible Cloud Run config.")
        if env.get("AUTH_ROLE_MAP", "").strip():
            errors.append("AUTH_ROLE_MAP must be blank for production-compatible Cloud Run config.")

    explicit_database_url = env.get("DATABASE_URL", "").strip()
    if explicit_database_url:
        if explicit_database_url.startswith("sqlite:"):
            errors.append("DATABASE_URL must not point to sqlite when DEPLOYMENT_PLATFORM=google_cloud_run.")
    else:
        db_name = env.get("DB_NAME", "").strip()
        db_user = env.get("DB_USER", "").strip()
        db_password = env.get("DB_PASSWORD", "").strip()
        cloud_sql_connection_name = env.get("CLOUD_SQL_CONNECTION_NAME", "").strip()
        db_host = env.get("DB_HOST", "").strip()
        if not (db_name and db_user and db_password):
            errors.append("Provide DATABASE_URL or the DB_NAME/DB_USER/DB_PASSWORD component set.")
        if not cloud_sql_connection_name and not db_host:
            errors.append("Provide CLOUD_SQL_CONNECTION_NAME or DB_HOST when DATABASE_URL is not set.")
        if cloud_sql_connection_name and db_host:
            warnings.append("Both CLOUD_SQL_CONNECTION_NAME and DB_HOST are set; unix socket Cloud SQL path will win.")

    if storage_class == "local_filesystem_fake":
        errors.append("STORAGE_CLASS=local_filesystem_fake is not allowed for production-compatible Cloud Run config.")
    if storage_class == "external_bridge_http":
        if not env.get("STORAGE_BRIDGE_BASE_URL", "").strip():
            errors.append("STORAGE_BRIDGE_BASE_URL is required when STORAGE_CLASS=external_bridge_http.")
        if not env.get("STORAGE_BRIDGE_AUTH_AUDIENCE", "").strip():
            warnings.append(
                "STORAGE_BRIDGE_AUTH_AUDIENCE is blank; service-to-service identity for the storage bridge is not configured."
            )
    else:
        if not env.get("STORAGE_INSPECTION_ROOT", "").strip():
            errors.append("STORAGE_INSPECTION_ROOT is required.")
        if not env.get("STORAGE_DKKD_ROOT", "").strip():
            warnings.append("STORAGE_DKKD_ROOT is blank; DDKD folder workflows will be unavailable.")
        if not env.get("STORAGE_TEMPLATE_ROOT", "").strip():
            warnings.append("STORAGE_TEMPLATE_ROOT is blank; managed template storage will be unavailable.")

    return ValidationReport(
        errors=errors,
        warnings=warnings,
        resolved_database_url=resolved_database_url,
    )


def _build_cli_payload(report: ValidationReport) -> dict[str, object]:
    return {
        "ok": report.ok,
        "errors": report.errors,
        "warnings": report.warnings,
        "resolved_database_url": report.resolved_database_url,
    }


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    env_path = Path(args[0]) if args else DEFAULT_ENV_PATH
    env = parse_env_file(env_path)
    report = validate_env_contract(env)
    print(json.dumps(_build_cli_payload(report), ensure_ascii=True, indent=2))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
