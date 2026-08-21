from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.validate_phase14_cloud_run_contract import parse_env_file


DEFAULT_CONFIG_PATH = Path("infra/cloudrun/storage_bridge_bootstrap.example.json")
NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]{1,62}$")


@dataclass(frozen=True)
class Phase18ValidationReport:
    errors: list[str]
    warnings: list[str]
    build_command_preview: list[str]
    deploy_command_preview: list[str]
    invoker_binding_preview: list[str]
    bridge_base_url_source: str

    @property
    def ok(self) -> bool:
        return not self.errors


def load_json_file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _require_nonblank_string(config: dict[str, Any], key: str, errors: list[str]) -> str:
    value = config.get(key)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{key} must be a non-blank string.")
        return ""
    return value.strip()


def _require_int(config: dict[str, Any], key: str, errors: list[str], *, minimum: int = 0) -> int | None:
    value = config.get(key)
    if not isinstance(value, int):
        errors.append(f"{key} must be an integer.")
        return None
    if value < minimum:
        errors.append(f"{key} must be >= {minimum}.")
        return None
    return value


def validate_bridge_env_contract(env: dict[str, str]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if (env.get("DEPLOYMENT_PLATFORM", "").strip() or "google_cloud_run") != "google_cloud_run":
        errors.append("DEPLOYMENT_PLATFORM must be google_cloud_run for the bridge runtime.")
    if (env.get("BRIDGE_RUNTIME", "").strip() or "storage_bridge") != "storage_bridge":
        errors.append("BRIDGE_RUNTIME must be storage_bridge.")

    storage_class = env.get("STORAGE_CLASS", "").strip()
    if storage_class != "synology_smb_bridge":
        errors.append("STORAGE_CLASS must be synology_smb_bridge for the Cloud Run bridge baseline.")

    for key in ("STORAGE_INSPECTION_ROOT", "SMB_AUTH_PROTOCOL"):
        if not env.get(key, "").strip():
            errors.append(f"{key} is required for the bridge runtime.")
    if not env.get("STORAGE_DKKD_ROOT", "").strip():
        warnings.append("STORAGE_DKKD_ROOT is blank; DDKD bridge operations will be unavailable.")
    if not env.get("STORAGE_TEMPLATE_ROOT", "").strip():
        warnings.append("STORAGE_TEMPLATE_ROOT is blank; template bridge operations will be unavailable.")
    if (env.get("BRIDGE_AUTH_MODE", "").strip() or "google_oidc") != "google_oidc":
        errors.append("BRIDGE_AUTH_MODE must be google_oidc for the production Cloud Run bridge baseline.")
    if (env.get("TAILSCALE_ENABLE", "").strip() or "0") != "1":
        errors.append("TAILSCALE_ENABLE must be 1 for the Cloud Run bridge baseline.")
    return errors, warnings


def _build_image_uri(config: dict[str, Any]) -> str:
    region = config["region"]
    project_id = config["project_id"]
    artifact_registry_repo = config["artifact_registry_repo"]
    image_name = config["image_name"]
    image_tag = config["image_tag"]
    return f"{region}-docker.pkg.dev/{project_id}/{artifact_registry_repo}/{image_name}:{image_tag}"


def _build_build_preview(config: dict[str, Any]) -> list[str]:
    return [
        "gcloud",
        "builds",
        "submit",
        "--project",
        config["project_id"],
        "--tag",
        _build_image_uri(config),
        "--file",
        "backend/Dockerfile.storage_bridge",
        ".",
    ]


def _build_deploy_preview(config: dict[str, Any]) -> list[str]:
    image_uri = _build_image_uri(config)
    command = [
        "gcloud",
        "run",
        "deploy",
        config["service_name"],
        "--project",
        config["project_id"],
        "--region",
        config["region"],
        "--image",
        image_uri,
        "--service-account",
        config["service_account"],
        "--env-vars-file",
        config["env_file"],
        "--cpu",
        str(config["cpu"]),
        "--memory",
        str(config["memory"]),
        "--concurrency",
        str(config["concurrency"]),
        "--timeout",
        f"{config['timeout_seconds']}s",
        "--min-instances",
        str(config["min_instances"]),
        "--max-instances",
        str(config["max_instances"]),
        "--ingress",
        config["ingress"],
        "--execution-environment",
        "gen2",
        "--no-allow-unauthenticated",
        "--set-secrets",
        (
            "TAILSCALE_AUTHKEY="
            f"{config['tailscale_authkey_secret']}:latest,"
            f"SMB_USERNAME={config['smb_username_secret']}:latest,"
            f"SMB_PASSWORD={config['smb_password_secret']}:latest"
        ),
    ]
    return command


def _build_invoker_binding_preview(config: dict[str, Any]) -> list[str]:
    return [
        "gcloud",
        "run",
        "services",
        "add-iam-policy-binding",
        config["service_name"],
        "--project",
        config["project_id"],
        "--region",
        config["region"],
        f"--member=serviceAccount:{config['caller_service_account']}",
        "--role=roles/run.invoker",
    ]


def validate_storage_bridge_bootstrap(config: dict[str, Any], *, root: Path | None = None) -> Phase18ValidationReport:
    errors: list[str] = []
    warnings: list[str] = []
    repo_root = ROOT if root is None else root

    project_id = _require_nonblank_string(config, "project_id", errors)
    region = _require_nonblank_string(config, "region", errors)
    service_name = _require_nonblank_string(config, "service_name", errors)
    _require_nonblank_string(config, "service_account", errors)
    _require_nonblank_string(config, "caller_service_account", errors)
    _require_nonblank_string(config, "artifact_registry_repo", errors)
    _require_nonblank_string(config, "image_name", errors)
    _require_nonblank_string(config, "image_tag", errors)
    _require_nonblank_string(config, "tailscale_authkey_secret", errors)
    _require_nonblank_string(config, "smb_username_secret", errors)
    _require_nonblank_string(config, "smb_password_secret", errors)
    env_file_value = _require_nonblank_string(config, "env_file", errors)
    _require_nonblank_string(config, "cpu", errors)
    _require_nonblank_string(config, "memory", errors)
    _require_nonblank_string(config, "ingress", errors)
    min_instances = _require_int(config, "min_instances", errors, minimum=0)
    max_instances = _require_int(config, "max_instances", errors, minimum=0)
    _require_int(config, "timeout_seconds", errors, minimum=1)
    _require_int(config, "concurrency", errors, minimum=1)

    for key, value in (("service_name", service_name), ("artifact_registry_repo", config.get("artifact_registry_repo", "")), ("image_name", config.get("image_name", ""))):
        if value and not NAME_PATTERN.match(value):
            errors.append(f"{key} must match {NAME_PATTERN.pattern}.")

    if min_instances is not None and max_instances is not None and min_instances > max_instances:
        errors.append("min_instances must be <= max_instances.")
    if config.get("allow_unauthenticated") is not False:
        errors.append("allow_unauthenticated must be false for the bridge baseline.")

    env_file_path = repo_root / env_file_value if env_file_value else None
    if env_file_path is None or not env_file_path.exists():
        errors.append(f"env_file does not exist: {env_file_path}")
    else:
        env = parse_env_file(env_file_path)
        env_errors, env_warnings = validate_bridge_env_contract(env)
        errors.extend(f"env contract: {item}" for item in env_errors)
        warnings.extend(f"env contract: {item}" for item in env_warnings)

    warnings.append(
        "Cloud Run bridge over Tailscale userspace + SMB is an infrastructure adapter baseline; verify Synology test-folder flows before binding production dossiers."
    )

    return Phase18ValidationReport(
        errors=errors,
        warnings=warnings,
        build_command_preview=_build_build_preview(config) if not errors else [],
        deploy_command_preview=_build_deploy_preview(config) if not errors else [],
        invoker_binding_preview=_build_invoker_binding_preview(config) if not errors else [],
        bridge_base_url_source="gcloud run services describe <service> --region <region> --format='value(status.url)'",
    )


def _build_cli_payload(report: Phase18ValidationReport) -> dict[str, Any]:
    return {
        "ok": report.ok,
        "errors": report.errors,
        "warnings": report.warnings,
        "build_command_preview": report.build_command_preview,
        "deploy_command_preview": report.deploy_command_preview,
        "invoker_binding_preview": report.invoker_binding_preview,
        "bridge_base_url_source": report.bridge_base_url_source,
    }


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    config_path = Path(args[0]) if args else DEFAULT_CONFIG_PATH
    config = load_json_file(config_path)
    report = validate_storage_bridge_bootstrap(config, root=ROOT)
    print(json.dumps(_build_cli_payload(report), ensure_ascii=True, indent=2))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
