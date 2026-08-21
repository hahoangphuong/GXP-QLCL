from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
import re
import sys
from typing import Any


REQUIRED_WRAPPER_KEYS = (
    "PROJECT_ID",
    "REGION",
    "SQL_INSTANCE",
    "CLOUD_SQL_CONNECTION_NAME",
    "DB_PASSWORD_SECRET",
    "DEPLOY_GIT_SHA",
    "DEPLOY_GIT_SHORT_SHA",
    "DEPLOY_BRANCH",
    "DRY_RUN",
)
BOOLEAN_TRUE = {"1", "true", "yes", "on"}
NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]{1,62}$")


@dataclass(frozen=True)
class ProdDeployPlan:
    project_id: str
    region: str
    sql_instance: str
    cloud_sql_connection_name: str
    db_password_secret: str
    db_name: str
    db_user: str
    service_name: str
    migration_job_name: str
    artifact_registry_repo: str
    image_name: str
    image_tag: str
    image_uri: str
    runtime_service_account: str
    dry_run: bool
    runtime_env: dict[str, str]
    secret_env: dict[str, str]
    labels: dict[str, str]
    frontend_topology: str
    storage_topology: str


@dataclass(frozen=True)
class ValidationReport:
    ok: bool
    errors: list[str]
    warnings: list[str]
    plan: ProdDeployPlan | None


def _get(source: dict[str, str], key: str, default: str = "") -> str:
    return (source.get(key, default) or "").strip()


def _require(source: dict[str, str], key: str, errors: list[str]) -> str:
    value = _get(source, key)
    if not value:
        errors.append(f"{key} is required.")
    return value


def _default_runtime_service_account(project_id: str) -> str:
    return f"gxp-web-runtime@{project_id}.iam.gserviceaccount.com"


def _build_image_tag(source: dict[str, str]) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"prod-{timestamp}-{_get(source, 'DEPLOY_GIT_SHORT_SHA').lower()}"


def _labels(source: dict[str, str]) -> dict[str, str]:
    branch = re.sub(r"[^a-z0-9-]+", "-", _get(source, "DEPLOY_BRANCH").lower()).strip("-") or "unknown"
    short_sha = re.sub(r"[^a-z0-9]+", "", _get(source, "DEPLOY_GIT_SHORT_SHA").lower())[:12] or "unknown"
    return {
        "managed-by": "codex",
        "deploy-branch": branch[:63],
        "deploy-sha": short_sha,
    }


def validate_prod_deploy_env(env: dict[str, str] | None = None) -> ValidationReport:
    source = os.environ if env is None else env
    errors: list[str] = []
    warnings: list[str] = []

    wrapper_values = {key: _require(source, key, errors) for key in REQUIRED_WRAPPER_KEYS}

    dry_run_raw = wrapper_values["DRY_RUN"].lower()
    if dry_run_raw not in {"0", "1"}:
        errors.append("DRY_RUN must be 0 or 1.")
    dry_run = dry_run_raw == "1"

    project_id = wrapper_values["PROJECT_ID"]
    region = wrapper_values["REGION"]
    sql_instance = wrapper_values["SQL_INSTANCE"]
    cloud_sql_connection_name = wrapper_values["CLOUD_SQL_CONNECTION_NAME"]
    db_password_secret = wrapper_values["DB_PASSWORD_SECRET"]

    db_name = _get(source, "DB_NAME", "gxp_qlcl")
    db_user = _get(source, "DB_USER", "gxp_app")
    service_name = _get(source, "SERVICE_NAME", "gxp-web")
    migration_job_name = _get(source, "MIGRATION_JOB_NAME", "gxp-web-migrate")
    artifact_registry_repo = _get(source, "ARTIFACT_REGISTRY_REPO", "gxp-qlcl")
    image_name = _get(source, "IMAGE_NAME", "gxp-web")
    runtime_service_account = _get(source, "RUNTIME_SERVICE_ACCOUNT", _default_runtime_service_account(project_id))

    for key, value in (
        ("SERVICE_NAME", service_name),
        ("MIGRATION_JOB_NAME", migration_job_name),
        ("ARTIFACT_REGISTRY_REPO", artifact_registry_repo),
        ("IMAGE_NAME", image_name),
        ("SQL_INSTANCE", sql_instance),
    ):
        if value and not NAME_PATTERN.match(value):
            errors.append(f"{key} must match {NAME_PATTERN.pattern}.")

    frontend_topology = _get(source, "FRONTEND_TOPOLOGY", "single_cloud_run_service")
    if frontend_topology != "single_cloud_run_service":
        errors.append("FRONTEND_TOPOLOGY must be single_cloud_run_service for the current production baseline.")

    storage_class = _get(source, "STORAGE_CLASS", "external_bridge_http")
    storage_topology = "bridge_adapter"
    if storage_class != "external_bridge_http":
        errors.append("STORAGE_CLASS must be external_bridge_http for the current production baseline.")

    auth_mode = _get(source, "AUTH_MODE", "google_iap_jwt")
    auth_role_source = _get(source, "AUTH_ROLE_SOURCE", "database")
    if auth_mode != "google_iap_jwt":
        errors.append("AUTH_MODE must be google_iap_jwt in production.")
    if auth_role_source != "database":
        errors.append("AUTH_ROLE_SOURCE must be database in production.")
    if _get(source, "AUTH_ROLE_MAP"):
        errors.append("AUTH_ROLE_MAP must be blank in production.")
    if _get(source, "AUTH_DEFAULT_ROLE"):
        warnings.append("AUTH_DEFAULT_ROLE is ignored in production database-backed RBAC mode.")
    if _get(source, "AUTH_TRUSTED_HEADER_FALLBACK", "false").lower() in BOOLEAN_TRUE:
        errors.append("AUTH_TRUSTED_HEADER_FALLBACK must be false in production.")

    auth_iap_expected_audience = _require(source, "AUTH_IAP_EXPECTED_AUDIENCE", errors)
    auth_iap_allowed_email_domain = _require(source, "AUTH_IAP_ALLOWED_EMAIL_DOMAIN", errors)
    storage_bridge_base_url = _require(source, "STORAGE_BRIDGE_BASE_URL", errors)
    storage_bridge_auth_audience = _require(source, "STORAGE_BRIDGE_AUTH_AUDIENCE", errors)
    bridge_auth_mode = _get(source, "BRIDGE_AUTH_MODE", "google_oidc")
    if bridge_auth_mode not in {"google_oidc", "hmac_jwt"}:
        errors.append("BRIDGE_AUTH_MODE must be google_oidc or hmac_jwt.")
    if bridge_auth_mode == "hmac_jwt" and not _get(source, "STORAGE_BRIDGE_SIGNING_KEY_SECRET"):
        errors.append("STORAGE_BRIDGE_SIGNING_KEY_SECRET is required when BRIDGE_AUTH_MODE=hmac_jwt.")

    image_tag = _build_image_tag(source)
    image_uri = f"{region}-docker.pkg.dev/{project_id}/{artifact_registry_repo}/{image_name}:{image_tag}"

    runtime_env = {
        "APP_ENV": "production",
        "DEPLOYMENT_PLATFORM": "google_cloud_run",
        "FRONTEND_TOPOLOGY": frontend_topology,
        "AUTH_MODE": "google_iap_jwt",
        "AUTH_ROLE_SOURCE": "database",
        "AUTH_IAP_EXPECTED_AUDIENCE": auth_iap_expected_audience,
        "AUTH_IAP_ALLOWED_EMAIL_DOMAIN": auth_iap_allowed_email_domain,
        "AUTH_TRUSTED_HEADER_FALLBACK": "false",
        "DB_DRIVER": _get(source, "DB_DRIVER", "postgresql+psycopg"),
        "DB_NAME": db_name,
        "DB_USER": db_user,
        "CLOUD_SQL_CONNECTION_NAME": cloud_sql_connection_name,
        "STORAGE_CLASS": "external_bridge_http",
        "STORAGE_BRIDGE_BASE_URL": storage_bridge_base_url,
        "STORAGE_BRIDGE_AUTH_AUDIENCE": storage_bridge_auth_audience,
        "BRIDGE_AUTH_MODE": bridge_auth_mode,
        "DEPLOY_GIT_SHA": _get(source, "DEPLOY_GIT_SHA"),
        "DEPLOY_GIT_SHORT_SHA": _get(source, "DEPLOY_GIT_SHORT_SHA"),
        "DEPLOY_BRANCH": _get(source, "DEPLOY_BRANCH"),
        "DEPLOY_IMAGE_URI": image_uri,
        "DEPLOY_TIMESTAMP_UTC": datetime.now(timezone.utc).isoformat(),
        "CLOUD_RUN_SERVICE_NAME": service_name,
    }
    if bridge_auth_mode == "hmac_jwt":
        runtime_env["STORAGE_BRIDGE_CLIENT_ID"] = _require(source, "STORAGE_BRIDGE_CLIENT_ID", errors)
        runtime_env["STORAGE_BRIDGE_TOKEN_ISSUER"] = _require(source, "STORAGE_BRIDGE_TOKEN_ISSUER", errors)

    secret_env = {"DB_PASSWORD": f"{db_password_secret}:latest"}
    if bridge_auth_mode == "hmac_jwt":
        secret_env["STORAGE_BRIDGE_SIGNING_KEY"] = f"{_get(source, 'STORAGE_BRIDGE_SIGNING_KEY_SECRET')}:latest"

    if cloud_sql_connection_name != f"{project_id}:{region}:{sql_instance}":
        errors.append("CLOUD_SQL_CONNECTION_NAME must exactly match PROJECT_ID:REGION:SQL_INSTANCE.")

    plan = None
    if not errors:
        plan = ProdDeployPlan(
            project_id=project_id,
            region=region,
            sql_instance=sql_instance,
            cloud_sql_connection_name=cloud_sql_connection_name,
            db_password_secret=db_password_secret,
            db_name=db_name,
            db_user=db_user,
            service_name=service_name,
            migration_job_name=migration_job_name,
            artifact_registry_repo=artifact_registry_repo,
            image_name=image_name,
            image_tag=image_tag,
            image_uri=image_uri,
            runtime_service_account=runtime_service_account,
            dry_run=dry_run,
            runtime_env=runtime_env,
            secret_env=secret_env,
            labels=_labels(source),
            frontend_topology=frontend_topology,
            storage_topology=storage_topology,
        )

    return ValidationReport(ok=not errors, errors=errors, warnings=warnings, plan=plan)


def main(argv: list[str] | None = None) -> int:
    _ = argv
    report = validate_prod_deploy_env()
    payload: dict[str, Any] = {
        "ok": report.ok,
        "errors": report.errors,
        "warnings": report.warnings,
        "plan": None if report.plan is None else asdict(report.plan),
    }
    print(json.dumps(payload, ensure_ascii=True, indent=2))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
