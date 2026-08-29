from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import re
import sys
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.vm_postgres_config import validate_vm_postgres_config


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
    app_user: str
    app_group: str
    python_series: str
    python_bin: str
    vm_src_dir: str
    vm_backend_releases_dir: str
    vm_backend_venv_releases_dir: str
    vm_current_backend_release_link: str
    vm_current_backend_venv_link: str
    vm_frontend_dist_dir: str
    vm_frontend_releases_dir: str
    vm_runtime_env_file: str
    vm_systemd_env_file: str
    vm_release_metadata_file: str
    vm_release_retention_count: int
    systemd_service_name: str
    nginx_site_name: str
    nginx_server_name: str
    app_port: int
    tls_cert_path: str
    tls_key_path: str
    tls_provisioning_mode: str
    node_major: int
    node_min_version: str
    corepack_version: str
    node_package_manager: str
    node_build_options: str
    supported_postgres_majors: str
    swap_size_gb: int
    swappiness: int
    pg_shared_buffers_mb: int
    pg_effective_cache_size_mb: int
    pg_work_mem_mb: int
    pg_maintenance_work_mem_mb: int
    pg_autovacuum_work_mem_mb: int
    pg_max_connections: int
    pg_listen_addresses: str
    public_base_url: str
    backup_gcs_bucket: str
    backup_local_staging_dir: str
    deploy_branch: str
    runtime_requirements_file: str
    runtime_requirements_lock_file: str
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


def _parse_int(source: dict[str, str], key: str, errors: list[str], default: int) -> int:
    raw = _get(source, key, str(default))
    try:
        value = int(raw)
    except ValueError:
        errors.append(f"{key} must be an integer.")
        return default
    return value


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
    postgres_config, postgres_errors = validate_vm_postgres_config(source)
    errors.extend(postgres_errors)
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
    app_user = _get(source, "VM_APP_USER", "gxp")
    app_group = _get(source, "VM_APP_GROUP", app_user)
    python_series = _get(source, "VM_PYTHON_SERIES", "3.12")
    python_bin = _get(source, "VM_PYTHON_BIN", "/usr/bin/python3.12")
    if python_series != "3.12":
        errors.append("VM_PYTHON_SERIES must remain 3.12 for the current production baseline.")
    vm_src_dir = _get(source, "VM_SRC_DIR", "/opt/gxp/src/GXP-QLCL")
    vm_backend_releases_dir = _get(source, "VM_BACKEND_RELEASES_DIR", "/opt/gxp/backend-releases")
    vm_backend_venv_releases_dir = _get(source, "VM_BACKEND_VENV_RELEASES_DIR", "/opt/gxp/backend-venvs")
    vm_current_backend_release_link = _get(source, "VM_CURRENT_BACKEND_RELEASE_LINK", "/opt/gxp/current-backend")
    vm_current_backend_venv_link = _get(source, "VM_CURRENT_BACKEND_VENV_LINK", "/opt/gxp/current-venv")
    vm_frontend_dist_dir = _get(source, "VM_FRONTEND_DIST_DIR", "/opt/gxp/frontend-dist")
    vm_frontend_releases_dir = _get(source, "VM_FRONTEND_RELEASES_DIR", "/opt/gxp/frontend-releases")
    vm_runtime_env_file = _get(source, "VM_RUNTIME_ENV_FILE", "/etc/gxp/runtime.env")
    vm_systemd_env_file = _get(source, "VM_SYSTEMD_ENV_FILE", "/etc/gxp/runtime.systemd.env")
    vm_release_metadata_file = _get(source, "VM_RELEASE_METADATA_FILE", "/opt/gxp/current-release.json")
    vm_release_retention_count = _parse_int(source, "VM_RELEASE_RETENTION_COUNT", errors, 3)
    if vm_release_retention_count < 2:
        errors.append("VM_RELEASE_RETENTION_COUNT must be >= 2.")
    systemd_service_name = _get(source, "SYSTEMD_SERVICE_NAME", "gxp-web")
    nginx_site_name = _get(source, "NGINX_SITE_NAME", "gxp-web")
    public_base_url = _require(source, "PUBLIC_BASE_URL", errors)
    parsed_public_url = urlparse(public_base_url)
    if parsed_public_url.scheme != "https":
        errors.append("PUBLIC_BASE_URL must be https for the VM production baseline.")
    if not parsed_public_url.hostname:
        errors.append("PUBLIC_BASE_URL must include a hostname.")
    nginx_server_name = _get(source, "NGINX_SERVER_NAME", parsed_public_url.hostname or "_")
    app_port = _parse_int(source, "APP_PORT", errors, 8000)
    if app_port <= 0 or app_port > 65535:
        errors.append("APP_PORT must be between 1 and 65535.")
    tls_cert_path = _require(source, "VM_TLS_CERT_PATH", errors, "/etc/ssl/certs/gxp.crt")
    tls_key_path = _require(source, "VM_TLS_KEY_PATH", errors, "/etc/ssl/private/gxp.key")
    tls_provisioning_mode = _get(source, "VM_TLS_PROVISIONING_MODE", "existing_files")
    if tls_provisioning_mode not in {"existing_files", "letsencrypt_certbot"}:
        errors.append("VM_TLS_PROVISIONING_MODE must be existing_files or letsencrypt_certbot.")
    node_major = _parse_int(source, "VM_NODE_MAJOR", errors, 22)
    if node_major < 20:
        errors.append("VM_NODE_MAJOR must be >= 20 for the current frontend toolchain.")
    node_min_version = _get(source, "VM_NODE_MIN_VERSION", "22.12.0")
    corepack_version = _get(source, "VM_COREPACK_VERSION", "0.31.0")
    node_package_manager = _get(source, "VM_NODE_PACKAGE_MANAGER", "pnpm@11.19.0")
    node_build_options = _get(source, "VM_NODE_BUILD_OPTIONS", "--max-old-space-size=512")
    if not node_package_manager.startswith("pnpm@"):
        errors.append("VM_NODE_PACKAGE_MANAGER must pin pnpm with a value like pnpm@11.19.0.")
    supported_postgres_majors = _get(source, "VM_SUPPORTED_POSTGRES_MAJORS", "17,18")
    if not re.fullmatch(r"\d+(,\d+)*", supported_postgres_majors):
        errors.append("VM_SUPPORTED_POSTGRES_MAJORS must be a comma-separated list like 17,18.")
    swap_size_gb = _parse_int(source, "VM_SWAP_SIZE_GB", errors, 4)
    swappiness = _parse_int(source, "VM_SWAPPINESS", errors, 10)
    if swap_size_gb < 0:
        errors.append("VM_SWAP_SIZE_GB must be >= 0.")
    if swappiness < 0 or swappiness > 100:
        errors.append("VM_SWAPPINESS must be between 0 and 100.")
    pg_shared_buffers_mb = _parse_int(source, "PG_SHARED_BUFFERS_MB", errors, 256)
    pg_effective_cache_size_mb = _parse_int(source, "PG_EFFECTIVE_CACHE_SIZE_MB", errors, 768)
    pg_work_mem_mb = _parse_int(source, "PG_WORK_MEM_MB", errors, 4)
    pg_maintenance_work_mem_mb = _parse_int(source, "PG_MAINTENANCE_WORK_MEM_MB", errors, 64)
    pg_autovacuum_work_mem_mb = _parse_int(source, "PG_AUTOVACUUM_WORK_MEM_MB", errors, 64)
    pg_max_connections = _parse_int(source, "PG_MAX_CONNECTIONS", errors, 30)
    pg_listen_addresses = "127.0.0.1" if postgres_config is None else postgres_config.listen_addresses_csv
    if pg_max_connections < 10 or pg_max_connections > 100:
        warnings.append("PG_MAX_CONNECTIONS is outside the usual small-VM baseline range of 10-100.")
    backup_gcs_bucket = _require(source, "BACKUP_GCS_BUCKET", errors)
    backup_local_staging_dir = _get(source, "BACKUP_LOCAL_STAGING_DIR", "/var/backups/gxp-temp")
    deploy_branch = _get(source, "DEPLOY_BRANCH", "main")

    for key, value in (
        ("SYSTEMD_SERVICE_NAME", systemd_service_name),
        ("NGINX_SITE_NAME", nginx_site_name),
        ("VM_APP_USER", app_user),
        ("VM_APP_GROUP", app_group),
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
        "SMB_USERNAME": _get(source, "SMB_USERNAME"),
        "SMB_PASSWORD": _get(source, "SMB_PASSWORD"),
        "SMB_AUTH_PROTOCOL": _get(source, "SMB_AUTH_PROTOCOL", "ntlm"),
        "SMB_PORT": _get(source, "SMB_PORT", "445"),
        "SMB_ENCRYPT": _get(source, "SMB_ENCRYPT", "false"),
        "SMB_CONNECTION_TIMEOUT_SECONDS": _get(source, "SMB_CONNECTION_TIMEOUT_SECONDS", "60"),
        "APP_PORT": str(app_port),
        "VM_APP_ROOT": vm_app_root,
        "VM_APP_USER": app_user,
        "VM_APP_GROUP": app_group,
        "VM_PYTHON_SERIES": python_series,
        "VM_PYTHON_BIN": python_bin,
        "VM_SRC_DIR": vm_src_dir,
        "VM_BACKEND_RELEASES_DIR": vm_backend_releases_dir,
        "VM_BACKEND_VENV_RELEASES_DIR": vm_backend_venv_releases_dir,
        "VM_CURRENT_BACKEND_RELEASE_LINK": vm_current_backend_release_link,
        "VM_CURRENT_BACKEND_VENV_LINK": vm_current_backend_venv_link,
        "VM_FRONTEND_DIST_DIR": vm_frontend_dist_dir,
        "VM_FRONTEND_RELEASES_DIR": vm_frontend_releases_dir,
        "VM_RUNTIME_ENV_FILE": vm_runtime_env_file,
        "VM_SYSTEMD_ENV_FILE": vm_systemd_env_file,
        "VM_RELEASE_METADATA_FILE": vm_release_metadata_file,
        "VM_RELEASE_RETENTION_COUNT": str(vm_release_retention_count),
        "SYSTEMD_SERVICE_NAME": systemd_service_name,
        "NGINX_SITE_NAME": nginx_site_name,
        "GXP_FRONTEND_DIST_ROOT": _get(source, "GXP_FRONTEND_DIST_ROOT", vm_frontend_dist_dir),
        "NGINX_SERVER_NAME": nginx_server_name,
        "VM_TLS_CERT_PATH": tls_cert_path,
        "VM_TLS_KEY_PATH": tls_key_path,
        "VM_TLS_PROVISIONING_MODE": tls_provisioning_mode,
        "VM_NODE_MAJOR": str(node_major),
        "VM_NODE_MIN_VERSION": node_min_version,
        "VM_COREPACK_VERSION": corepack_version,
        "VM_NODE_PACKAGE_MANAGER": node_package_manager,
        "VM_NODE_BUILD_OPTIONS": node_build_options,
        "VM_SUPPORTED_POSTGRES_MAJORS": supported_postgres_majors,
        "VM_SWAP_SIZE_GB": str(swap_size_gb),
        "VM_SWAPPINESS": str(swappiness),
        "PG_SHARED_BUFFERS_MB": str(pg_shared_buffers_mb),
        "PG_EFFECTIVE_CACHE_SIZE_MB": str(pg_effective_cache_size_mb),
        "PG_WORK_MEM_MB": str(pg_work_mem_mb),
        "PG_MAINTENANCE_WORK_MEM_MB": str(pg_maintenance_work_mem_mb),
        "PG_AUTOVACUUM_WORK_MEM_MB": str(pg_autovacuum_work_mem_mb),
        "PG_MAX_CONNECTIONS": str(pg_max_connections),
        "PG_LISTEN_ADDRESSES": pg_listen_addresses,
        "PUBLIC_BASE_URL": public_base_url,
        "BACKUP_GCS_BUCKET": backup_gcs_bucket,
        "BACKUP_LOCAL_STAGING_DIR": backup_local_staging_dir,
        "DEPLOY_BRANCH": deploy_branch,
    }
    if postgres_config is not None and postgres_config.private_access is not None:
        runtime_env["PG_PRIVATE_CLIENT_CIDR"] = postgres_config.private_access.client_cidr
        runtime_env["PG_PRIVATE_DB_NAME"] = postgres_config.private_access.db_name
        runtime_env["PG_PRIVATE_RUNTIME_USER"] = postgres_config.private_access.runtime_user
        runtime_env["PG_PRIVATE_MIGRATOR_USER"] = postgres_config.private_access.migrator_user
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
            app_user=app_user,
            app_group=app_group,
            python_series=python_series,
            python_bin=python_bin,
            vm_src_dir=vm_src_dir,
            vm_backend_releases_dir=vm_backend_releases_dir,
            vm_backend_venv_releases_dir=vm_backend_venv_releases_dir,
            vm_current_backend_release_link=vm_current_backend_release_link,
            vm_current_backend_venv_link=vm_current_backend_venv_link,
            vm_frontend_dist_dir=vm_frontend_dist_dir,
            vm_frontend_releases_dir=vm_frontend_releases_dir,
            vm_runtime_env_file=vm_runtime_env_file,
            vm_systemd_env_file=vm_systemd_env_file,
            vm_release_metadata_file=vm_release_metadata_file,
            vm_release_retention_count=vm_release_retention_count,
            systemd_service_name=systemd_service_name,
            nginx_site_name=nginx_site_name,
            nginx_server_name=nginx_server_name,
            app_port=app_port,
            tls_cert_path=tls_cert_path,
            tls_key_path=tls_key_path,
            tls_provisioning_mode=tls_provisioning_mode,
            node_major=node_major,
            node_min_version=node_min_version,
            corepack_version=corepack_version,
            node_package_manager=node_package_manager,
            node_build_options=node_build_options,
            supported_postgres_majors=supported_postgres_majors,
            swap_size_gb=swap_size_gb,
            swappiness=swappiness,
            pg_shared_buffers_mb=pg_shared_buffers_mb,
            pg_effective_cache_size_mb=pg_effective_cache_size_mb,
            pg_work_mem_mb=pg_work_mem_mb,
            pg_maintenance_work_mem_mb=pg_maintenance_work_mem_mb,
            pg_autovacuum_work_mem_mb=pg_autovacuum_work_mem_mb,
            pg_max_connections=pg_max_connections,
            pg_listen_addresses=pg_listen_addresses,
            public_base_url=public_base_url,
            backup_gcs_bucket=backup_gcs_bucket,
            backup_local_staging_dir=backup_local_staging_dir,
            deploy_branch=deploy_branch,
            runtime_requirements_file="backend/requirements.runtime.vm.txt",
            runtime_requirements_lock_file="backend/requirements.runtime.vm.lock.txt",
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
