from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
import re
import sys
from typing import Any


BOOLEAN_TRUE = {"1", "true", "yes", "on"}
NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]{1,62}$")
ALLOWED_AUTH_PROVIDERS = {"google_oidc", "google_iap_jwt"}
ALLOWED_STORAGE_CLASSES = {"synology_smb", "external_bridge_http"}
ALLOWED_DB_MODES = {"local_postgres", "cloud_sql"}


@dataclass(frozen=True)
class VmDeployPlan:
    deployment_platform: str
    frontend_topology: str
    auth_provider: str
    db_mode: str
    database_url_redacted: str
    db_name: str
    db_user: str
    db_host: str
    db_port: int
    storage_class: str
    inspection_root: str
    dkkd_root: str
    template_root: str
    vm_app_root: str
    vm_src_dir: str
    vm_venv_dir: str
    vm_frontend_dist_dir: str
    vm_runtime_env_file: str
    vm_release_metadata_file: str
    systemd_service_name: str
    nginx_site_name: str
    public_base_url: str
    backup_gcs_bucket: str
    backup_local_staging_dir: str
    deploy_branch: str
    runtime_requirements_file: str
    runtime_env: dict[str, str]


@dataclass(frozen=True)
class ValidationReport:
    ok: bool
    errors: list[str]
    warnings: list[str]
    plan: VmDeployPlan | None


def _get(source: dict[str, str], key: str, default: str = "") -> str:
    return (source.get(key, default) or "").strip()


def _require(source: dict[str, str], key: str, errors: list[str], default: str = "") -> str:
    value = _get(source, key, default)
    if not value:
        errors.append(f"{key} is required.")
    return value


def _bool(value: str) -> bool:
    return value.strip().lower() in BOOLEAN_TRUE


def _resolve_database_url(source: dict[str, str], errors: list[str]) -> str:
    explicit = _get(source, "DATABASE_URL")
    if explicit:
        return explicit

    db_mode = _get(source, "DB_MODE", "local_postgres").lower()
    db_driver = _get(source, "DB_DRIVER", "postgresql+psycopg")
    db_name = _require(source, "DB_NAME", errors, "gxp_qlcl")
    db_user = _require(source, "DB_USER", errors, "gxp_app")
    db_password = _require(source, "DB_PASSWORD", errors)

    if db_mode == "local_postgres":
        db_host = _get(source, "DB_HOST", "127.0.0.1")
        db_port = _get(source, "DB_PORT", "5432")
        return f"{db_driver}://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"

    cloud_sql_connection_name = _require(source, "CLOUD_SQL_CONNECTION_NAME", errors)
    return f"{db_driver}://{db_user}:{db_password}@/{db_name}?host=/cloudsql/{cloud_sql_connection_name}"


def _redact_database_url(url: str) -> str:
    if "://" not in url or "@" not in url:
        return url
    scheme, remainder = url.split("://", 1)
    credentials, suffix = remainder.split("@", 1)
    if ":" not in credentials:
        return f"{scheme}://***@{suffix}"
    user, _password = credentials.split(":", 1)
    return f"{scheme}://{user}:***@{suffix}"


def validate_vm_prod_deploy_env(env: dict[str, str] | None = None) -> ValidationReport:
    source = os.environ if env is None else env
    errors: list[str] = []
    warnings: list[str] = []

    deployment_platform = _get(source, "DEPLOYMENT_PLATFORM", "compute_engine_vm")
    if deployment_platform != "compute_engine_vm":
        errors.append("DEPLOYMENT_PLATFORM must be compute_engine_vm for the current production baseline.")

    frontend_topology = _get(source, "FRONTEND_TOPOLOGY", "nginx_static_proxy")
    if frontend_topology not in {"nginx_static_proxy", "backend_serves_static"}:
        errors.append("FRONTEND_TOPOLOGY must be nginx_static_proxy or backend_serves_static.")

    auth_provider = _get(source, "AUTH_PROVIDER", _get(source, "AUTH_MODE", "google_oidc")).lower()
    if auth_provider not in ALLOWED_AUTH_PROVIDERS:
        errors.append(f"AUTH_PROVIDER must be one of {sorted(ALLOWED_AUTH_PROVIDERS)}.")
    if auth_provider == "google_oidc":
        _require(source, "AUTH_OIDC_CLIENT_ID", errors)
    if auth_provider == "google_iap_jwt":
        _require(source, "AUTH_IAP_EXPECTED_AUDIENCE", errors)
    if not _get(source, "AUTH_ALLOWED_EMAIL_DOMAIN"):
        warnings.append("AUTH_ALLOWED_EMAIL_DOMAIN is blank; operator domain restriction is not enforced.")

    if _bool(_get(source, "AUTH_TRUSTED_HEADER_FALLBACK", "false")):
        errors.append("AUTH_TRUSTED_HEADER_FALLBACK must be false in production.")
    if _get(source, "AUTH_ROLE_SOURCE", "database").lower() != "database":
        errors.append("AUTH_ROLE_SOURCE must be database in production.")
    if _get(source, "AUTH_ROLE_MAP"):
        errors.append("AUTH_ROLE_MAP must be blank in production.")

    db_mode = _get(source, "DB_MODE", "local_postgres").lower()
    if db_mode not in ALLOWED_DB_MODES:
        errors.append(f"DB_MODE must be one of {sorted(ALLOWED_DB_MODES)}.")
    db_name = _require(source, "DB_NAME", errors, "gxp_qlcl")
    db_user = _require(source, "DB_USER", errors, "gxp_app")
    if db_user.lower() == "postgres":
        errors.append("DB_USER must not be postgres for application runtime.")
    db_host = _get(source, "DB_HOST", "127.0.0.1")
    db_port = _get(source, "DB_PORT", "5432")
    if db_mode == "local_postgres":
        if db_host not in {"127.0.0.1", "localhost"}:
            errors.append("DB_HOST must stay local/private for VM production baseline.")
        if db_port != "5432":
            warnings.append("DB_PORT is not 5432; confirm local PostgreSQL listener intentionally differs from baseline.")
    database_url = _resolve_database_url(source, errors)

    storage_class = _get(source, "STORAGE_CLASS", "synology_smb").lower()
    if storage_class not in ALLOWED_STORAGE_CLASSES:
        errors.append(f"STORAGE_CLASS must be one of {sorted(ALLOWED_STORAGE_CLASSES)}.")
    inspection_root = _require(source, "STORAGE_INSPECTION_ROOT", errors)
    dkkd_root = _require(source, "STORAGE_DKKD_ROOT", errors)
    template_root = _require(source, "STORAGE_TEMPLATE_ROOT", errors)
    if storage_class == "synology_smb":
        _require(source, "SMB_USERNAME", errors)
        _require(source, "SMB_PASSWORD", errors)

    vm_app_root = _get(source, "VM_APP_ROOT", "/opt/gxp")
    vm_src_dir = _get(source, "VM_SRC_DIR", "/opt/gxp/src/GXP-QLCL")
    vm_venv_dir = _get(source, "VM_VENV_DIR", "/opt/gxp/venv")
    vm_frontend_dist_dir = _get(source, "VM_FRONTEND_DIST_DIR", "/opt/gxp/frontend-dist")
    vm_runtime_env_file = _get(source, "VM_RUNTIME_ENV_FILE", "/etc/gxp/runtime.env")
    vm_release_metadata_file = _get(source, "VM_RELEASE_METADATA_FILE", "/opt/gxp/current-release.json")
    systemd_service_name = _get(source, "SYSTEMD_SERVICE_NAME", "gxp-web")
    nginx_site_name = _get(source, "NGINX_SITE_NAME", "gxp-web")
    public_base_url = _require(source, "PUBLIC_BASE_URL", errors)
    backup_gcs_bucket = _require(source, "BACKUP_GCS_BUCKET", errors)
    backup_local_staging_dir = _get(source, "BACKUP_LOCAL_STAGING_DIR", "/var/backups/gxp-temp")
    deploy_branch = _get(source, "DEPLOY_BRANCH", "main")

    for key, value in (
        ("SYSTEMD_SERVICE_NAME", systemd_service_name),
        ("NGINX_SITE_NAME", nginx_site_name),
    ):
        if value and not NAME_PATTERN.match(value):
            errors.append(f"{key} must match {NAME_PATTERN.pattern}.")

    runtime_env = {
        "APP_ENV": "production",
        "DEPLOYMENT_PLATFORM": "compute_engine_vm",
        "FRONTEND_TOPOLOGY": frontend_topology,
        "AUTH_PROVIDER": auth_provider,
        "AUTH_ROLE_SOURCE": "database",
        "AUTH_ALLOWED_EMAIL_DOMAIN": _get(source, "AUTH_ALLOWED_EMAIL_DOMAIN"),
        "AUTH_OIDC_CLIENT_ID": _get(source, "AUTH_OIDC_CLIENT_ID"),
        "AUTH_IAP_EXPECTED_AUDIENCE": _get(source, "AUTH_IAP_EXPECTED_AUDIENCE"),
        "AUTH_TRUSTED_HEADER_FALLBACK": "false",
        "DB_MODE": db_mode,
        "DB_DRIVER": _get(source, "DB_DRIVER", "postgresql+psycopg"),
        "DB_NAME": db_name,
        "DB_USER": db_user,
        "DB_HOST": db_host,
        "DB_PORT": db_port,
        "STORAGE_CLASS": storage_class,
        "STORAGE_INSPECTION_ROOT": inspection_root,
        "STORAGE_DKKD_ROOT": dkkd_root,
        "STORAGE_TEMPLATE_ROOT": template_root,
        "SMB_AUTH_PROTOCOL": _get(source, "SMB_AUTH_PROTOCOL", "ntlm"),
        "SMB_PORT": _get(source, "SMB_PORT", "445"),
        "SMB_ENCRYPT": _get(source, "SMB_ENCRYPT", "false"),
        "SMB_CONNECTION_TIMEOUT_SECONDS": _get(source, "SMB_CONNECTION_TIMEOUT_SECONDS", "60"),
        "GXP_FRONTEND_DIST_ROOT": vm_frontend_dist_dir,
    }
    runtime_env = {key: value for key, value in runtime_env.items() if value}

    plan = None
    if not errors:
        plan = VmDeployPlan(
            deployment_platform=deployment_platform,
            frontend_topology=frontend_topology,
            auth_provider=auth_provider,
            db_mode=db_mode,
            database_url_redacted=_redact_database_url(database_url),
            db_name=db_name,
            db_user=db_user,
            db_host=db_host,
            db_port=int(db_port),
            storage_class=storage_class,
            inspection_root=inspection_root,
            dkkd_root=dkkd_root,
            template_root=template_root,
            vm_app_root=vm_app_root,
            vm_src_dir=vm_src_dir,
            vm_venv_dir=vm_venv_dir,
            vm_frontend_dist_dir=vm_frontend_dist_dir,
            vm_runtime_env_file=vm_runtime_env_file,
            vm_release_metadata_file=vm_release_metadata_file,
            systemd_service_name=systemd_service_name,
            nginx_site_name=nginx_site_name,
            public_base_url=public_base_url,
            backup_gcs_bucket=backup_gcs_bucket,
            backup_local_staging_dir=backup_local_staging_dir,
            deploy_branch=deploy_branch,
            runtime_requirements_file="backend/requirements.runtime.vm.txt",
            runtime_env=runtime_env,
        )

    return ValidationReport(ok=not errors, errors=errors, warnings=warnings, plan=plan)


def main(argv: list[str] | None = None) -> int:
    _ = argv
    report = validate_vm_prod_deploy_env()
    payload: dict[str, Any] = {
        "ok": report.ok,
        "errors": report.errors,
        "warnings": report.warnings,
        "plan": None if report.plan is None else asdict(report.plan),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
