from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.env_utils import parse_env_file
from tools.validate_phase14_cloud_run_contract import validate_env_contract


DEFAULT_CONFIG_PATH = Path("infra/cloudrun/service_bootstrap.example.json")
ALLOWED_STORAGE_MODES = {"nfs_volume", "external_bridge", "disabled"}
FORBIDDEN_STORAGE_MODES = {"tailscale_smb_in_container", "smbnetfs", "container_mount"}


@dataclass(frozen=True)
class Phase15ValidationReport:
    errors: list[str]
    warnings: list[str]
    deploy_command_preview: list[str]

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


def _load_secret_bindings(path: Path, errors: list[str]) -> dict[str, str]:
    if not path.exists():
        errors.append(f"secret bindings file does not exist: {path}")
        return {}
    payload = load_json_file(path)
    if not isinstance(payload, dict):
        errors.append("secret bindings file must contain a JSON object.")
        return {}
    result: dict[str, str] = {}
    for key, value in payload.items():
        if not isinstance(key, str) or not key.strip():
            errors.append("secret bindings contain a blank env var name.")
            continue
        if not isinstance(value, str) or not value.strip():
            errors.append(f"secret binding {key!r} must map to a non-blank secret reference.")
            continue
        result[key.strip()] = value.strip()
    return result


def _build_deploy_command_preview(config: dict[str, Any], secret_bindings: dict[str, str]) -> list[str]:
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
    ]
    if config.get("cloud_sql_connection_name"):
        command.extend(["--add-cloudsql-instances", config["cloud_sql_connection_name"]])
    if config.get("vpc_network"):
        command.extend(["--network", config["vpc_network"]])
    if config.get("vpc_subnet"):
        command.extend(["--subnet", config["vpc_subnet"]])
    if config.get("vpc_egress"):
        command.extend(["--vpc-egress", config["vpc_egress"]])
    command.append("--allow-unauthenticated" if config["allow_unauthenticated"] else "--no-allow-unauthenticated")

    if secret_bindings:
        joined = ",".join(f"{key}={value}" for key, value in sorted(secret_bindings.items()))
        command.extend(["--set-secrets", joined])

    if config["storage_mode"] == "nfs_volume":
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


def validate_service_bootstrap_config(config: dict[str, Any], *, root: Path | None = None) -> Phase15ValidationReport:
    errors: list[str] = []
    warnings: list[str] = []
    repo_root = ROOT if root is None else root

    _require_nonblank_string(config, "project_id", errors)
    _require_nonblank_string(config, "region", errors)
    _require_nonblank_string(config, "service_name", errors)
    _require_nonblank_string(config, "image", errors)
    _require_nonblank_string(config, "service_account", errors)
    env_file_value = _require_nonblank_string(config, "env_file", errors)
    secret_file_value = _require_nonblank_string(config, "secret_bindings_file", errors)
    _require_nonblank_string(config, "cpu", errors)
    _require_nonblank_string(config, "memory", errors)
    _require_nonblank_string(config, "ingress", errors)
    storage_mode = _require_nonblank_string(config, "storage_mode", errors)
    min_instances = _require_int(config, "min_instances", errors, minimum=0)
    max_instances = _require_int(config, "max_instances", errors, minimum=0)
    _require_int(config, "timeout_seconds", errors, minimum=1)
    _require_int(config, "concurrency", errors, minimum=1)

    if min_instances is not None and max_instances is not None and min_instances > max_instances:
        errors.append("min_instances must be <= max_instances.")

    if not isinstance(config.get("allow_unauthenticated"), bool):
        errors.append("allow_unauthenticated must be a boolean.")

    env_file_path = repo_root / env_file_value if env_file_value else None
    secret_bindings_path = repo_root / secret_file_value if secret_file_value else None

    env_contract: dict[str, str] = {}
    if env_file_path is not None:
        if not env_file_path.exists():
            errors.append(f"env_file does not exist: {env_file_path}")
        else:
            env_contract = parse_env_file(env_file_path)
            phase14 = validate_env_contract(env_contract)
            errors.extend(f"env contract: {item}" for item in phase14.errors)
            warnings.extend(f"env contract: {item}" for item in phase14.warnings)

    secret_bindings = _load_secret_bindings(secret_bindings_path, errors) if secret_bindings_path is not None else {}
    if "DB_PASSWORD" not in secret_bindings:
        warnings.append("DB_PASSWORD is not bound from Secret Manager in secret_bindings_file.")
    for key, value in secret_bindings.items():
        if value.endswith(":latest"):
            warnings.append(f"secret binding {key} uses :latest; pin an explicit version for deterministic production rollout.")

    if env_contract:
        env_cloud_sql = env_contract.get("CLOUD_SQL_CONNECTION_NAME", "").strip()
        config_cloud_sql = str(config.get("cloud_sql_connection_name", "")).strip()
        if env_cloud_sql and config_cloud_sql and env_cloud_sql != config_cloud_sql:
            errors.append("cloud_sql_connection_name does not match CLOUD_SQL_CONNECTION_NAME in env_file.")
        env_auth_mode = env_contract.get("AUTH_MODE", "").strip().lower()
        if env_auth_mode == "google_iap_jwt" and bool(config.get("allow_unauthenticated")):
            warnings.append("allow_unauthenticated=true while AUTH_MODE=google_iap_jwt; verify IAP exposure model carefully.")

    normalized_storage_mode = storage_mode.lower()
    if normalized_storage_mode in FORBIDDEN_STORAGE_MODES:
        errors.append(
            "Cloud Run does not support mounting SMB/Tailscale file systems from inside the container; "
            "use native NFS volumes or an external storage bridge."
        )
    elif normalized_storage_mode not in ALLOWED_STORAGE_MODES:
        errors.append(f"storage_mode must be one of {sorted(ALLOWED_STORAGE_MODES)}.")

    mounts = config.get("storage_mounts", [])
    if normalized_storage_mode == "nfs_volume":
        if not isinstance(mounts, list) or not mounts:
            errors.append("storage_mounts must contain at least one mount when storage_mode=nfs_volume.")
        if not str(config.get("vpc_network", "")).strip():
            errors.append("vpc_network is required when storage_mode=nfs_volume.")
        if not str(config.get("vpc_subnet", "")).strip():
            errors.append("vpc_subnet is required when storage_mode=nfs_volume.")
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
            "NFS volume mode requires Synology (or equivalent bridge) to expose a VPC-reachable NFS endpoint; "
            "Cloud Run cannot mount SMB/Tailscale shares from inside the container."
        )
    elif mounts:
        warnings.append("storage_mounts are present but storage_mode is not nfs_volume; mounts will be ignored by the deploy script.")

    if normalized_storage_mode == "external_bridge":
        bridge_base_url = str(config.get("bridge_base_url", "")).strip()
        bridge_auth_audience = str(config.get("bridge_auth_audience", "")).strip()
        if not bridge_base_url:
            errors.append("bridge_base_url is required when storage_mode=external_bridge.")
        if not bridge_auth_audience:
            errors.append("bridge_auth_audience is required when storage_mode=external_bridge.")
        warnings.append(
            "external_bridge mode means Cloud Run will not mount Synology directly; file-touching requests need a separate adapter/service."
        )
    if normalized_storage_mode == "disabled":
        warnings.append("disabled storage_mode is suitable only for non-storage rollout validation.")

    preview_config = dict(config)
    preview_config["storage_mode"] = normalized_storage_mode
    deploy_command_preview = _build_deploy_command_preview(preview_config, secret_bindings)
    return Phase15ValidationReport(errors=errors, warnings=warnings, deploy_command_preview=deploy_command_preview)


def _build_cli_payload(report: Phase15ValidationReport) -> dict[str, Any]:
    return {
        "ok": report.ok,
        "errors": report.errors,
        "warnings": report.warnings,
        "deploy_command_preview": report.deploy_command_preview,
    }


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    config_path = Path(args[0]) if args else DEFAULT_CONFIG_PATH
    config = load_json_file(config_path)
    report = validate_service_bootstrap_config(config, root=ROOT)
    print(json.dumps(_build_cli_payload(report), ensure_ascii=True, indent=2))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
