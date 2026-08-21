from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.validate_phase14_cloud_run_contract import parse_env_file


DEFAULT_CONFIG_PATH = Path("infra/cloudrun/storage_bridge_bootstrap.example.json")


@dataclass(frozen=True)
class Phase18ValidationReport:
    errors: list[str]
    warnings: list[str]
    deploy_command_preview: list[str]
    invoker_binding_preview: list[str]

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

    deployment_platform = env.get("DEPLOYMENT_PLATFORM", "").strip() or "google_cloud_run"
    if deployment_platform != "google_cloud_run":
        errors.append("DEPLOYMENT_PLATFORM must be google_cloud_run for the bridge baseline.")

    storage_class = env.get("STORAGE_CLASS", "").strip() or "local_filesystem_fake"
    if storage_class == "external_bridge_http":
        errors.append("Bridge runtime must not use STORAGE_CLASS=external_bridge_http.")
    if not env.get("STORAGE_INSPECTION_ROOT", "").strip():
        errors.append("STORAGE_INSPECTION_ROOT is required for the bridge runtime.")
    if not env.get("STORAGE_DKKD_ROOT", "").strip():
        warnings.append("STORAGE_DKKD_ROOT is blank; DDKD bridge operations will be unavailable.")
    if not env.get("STORAGE_TEMPLATE_ROOT", "").strip():
        warnings.append("STORAGE_TEMPLATE_ROOT is blank; template bridge operations will be unavailable.")
    return errors, warnings


def _build_deploy_preview(config: dict[str, Any]) -> list[str]:
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
        config["image"],
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
    ]
    if config.get("vpc_network"):
        command.extend(["--network", config["vpc_network"]])
    if config.get("vpc_subnet"):
        command.extend(["--subnet", config["vpc_subnet"]])
    if config.get("vpc_egress"):
        command.extend(["--vpc-egress", config["vpc_egress"]])
    for mount in config.get("storage_mounts", []):
        readonly = str(bool(mount.get("read_only", False))).lower()
        command.extend(
            [
                "--add-volume",
                (
                    f"name={mount['name']},type=nfs,location={mount['server']}:{mount['export_path']},"
                    f"mount-path={mount['mount_path']},readonly={readonly}"
                ),
            ]
        )
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

    _require_nonblank_string(config, "project_id", errors)
    _require_nonblank_string(config, "region", errors)
    _require_nonblank_string(config, "service_name", errors)
    _require_nonblank_string(config, "image", errors)
    _require_nonblank_string(config, "service_account", errors)
    _require_nonblank_string(config, "caller_service_account", errors)
    env_file_value = _require_nonblank_string(config, "env_file", errors)
    _require_nonblank_string(config, "cpu", errors)
    _require_nonblank_string(config, "memory", errors)
    _require_nonblank_string(config, "ingress", errors)
    min_instances = _require_int(config, "min_instances", errors, minimum=0)
    max_instances = _require_int(config, "max_instances", errors, minimum=0)
    _require_int(config, "timeout_seconds", errors, minimum=1)
    _require_int(config, "concurrency", errors, minimum=1)

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

    if not str(config.get("vpc_network", "")).strip():
        errors.append("vpc_network is required for the bridge baseline.")
    if not str(config.get("vpc_subnet", "")).strip():
        errors.append("vpc_subnet is required for the bridge baseline.")

    mounts = config.get("storage_mounts")
    if not isinstance(mounts, list) or not mounts:
        errors.append("storage_mounts must contain at least one NFS mount for the bridge baseline.")
    else:
        for index, mount in enumerate(mounts):
            if not isinstance(mount, dict):
                errors.append(f"storage_mounts[{index}] must be an object.")
                continue
            for field in ("name", "mount_path", "server", "export_path"):
                value = mount.get(field)
                if not isinstance(value, str) or not value.strip():
                    errors.append(f"storage_mounts[{index}].{field} must be a non-blank string.")
            if not isinstance(mount.get("read_only"), bool):
                errors.append(f"storage_mounts[{index}].read_only must be a boolean.")

    warnings.append(
        "Cloud Run NFS volumes are documented as no-lock; confirm bridge-side file-touching behavior is acceptable for non-production use."
    )

    deploy_command_preview = _build_deploy_preview(config)
    invoker_binding_preview = _build_invoker_binding_preview(config)
    return Phase18ValidationReport(
        errors=errors,
        warnings=warnings,
        deploy_command_preview=deploy_command_preview,
        invoker_binding_preview=invoker_binding_preview,
    )


def _build_cli_payload(report: Phase18ValidationReport) -> dict[str, Any]:
    return {
        "ok": report.ok,
        "errors": report.errors,
        "warnings": report.warnings,
        "deploy_command_preview": report.deploy_command_preview,
        "invoker_binding_preview": report.invoker_binding_preview,
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
