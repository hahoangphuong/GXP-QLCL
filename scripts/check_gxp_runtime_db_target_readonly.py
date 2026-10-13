"""Read-only VM runtime target check before any rehearsal 0023 migration.

No Python packages, database SQL, git changes, service restarts or writes.
Reads the systemd service MainPID environment in memory and emits ONLY
the database name, source-of-name, readiness revision fields and decision.
Never prints URL, host, username, password, process environ or raw errors.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlsplit
from urllib.request import urlopen

SERVICE = "gxp-web"
TARGET = "gxp_legacy_rehearsal"
HEALTH_URL = "http://127.0.0.1/readyz"


def _get_main_pid() -> int:
    run = subprocess.run(
        ["systemctl", "show", SERVICE, "--property=MainPID", "--value"],
        capture_output=True, text=True, timeout=8, check=False,
    )
    if run.returncode != 0 or not run.stdout.strip().isdigit():
        raise ValueError("Unable to determine service MainPID")
    pid = int(run.stdout.strip())
    if pid < 2:
        raise ValueError("Service has no active MainPID")
    return pid


def _get_service_env(pid: int) -> dict[str, str]:
    # Never log this raw value: it may include secret connection credentials.
    values = Path(f"/proc/{pid}/environ").read_bytes().split(b"\0")
    wanted = {b"DATABASE_URL", b"DB_NAME", b"DB_MODE"}
    result: dict[str, str] = {}
    for value in values:
        name, separator, content = value.partition(b"=")
        if separator and name in wanted:
            result[name.decode("ascii")] = content.decode("utf-8", errors="replace")
    return result


def _safe_database_name(env: dict[str, str]) -> tuple[str | None, str]:
    url = env.get("DATABASE_URL", "").strip()
    if url:
        parsed = urlsplit(url)
        if not parsed.scheme.startswith("postgresql") or not parsed.path.strip("/"):
            return None, "DATABASE_URL_INVALID_OR_NOT_POSTGRES"
        return unquote(parsed.path.lstrip("/")), "DATABASE_URL"
    name = env.get("DB_NAME", "").strip()
    if name:
        return name, "DB_NAME"
    return None, "TARGET_NOT_EXPOSED_IN_MAINPID_ENV"


def _read_readyz() -> dict:
    try:
        response = urlopen(HEALTH_URL, timeout=8)
    except HTTPError as error:
        response = error
    with response:
        raw = response.read(32768)
        parsed = json.loads(raw.decode("utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError("Invalid readiness response")
        # Whitelist fields; database_error may contain sensitive material.
        return {
            "http_status": response.status,
            "ok": parsed.get("ok") is True,
            "database_reachable": parsed.get("database_reachable") is True,
            "schema_current": parsed.get("schema_current") is True,
            "expected_revision": parsed.get("expected_revision"),
            "actual_revision": parsed.get("actual_revision"),
        }


def assess_runtime(name: str | None, source: str, health: dict) -> dict:
    if name is None:
        state = "BLOCK_UNKNOWN_RUNTIME_TARGET"
    elif name == TARGET:
        state = "BLOCK_ACTIVE_SERVICE_TARGETS_REHEARSAL"
    elif (
        health.get("http_status") == 200
        and health.get("ok") is True
        and health.get("database_reachable") is True
        and health.get("schema_current") is True
        and health.get("expected_revision") == health.get("actual_revision")
    ):
        state = "OBSERVED_SERVICE_TARGET_DIFFERENT_FROM_REHEARSAL"
    else:
        state = "BLOCK_RUNTIME_READINESS_OR_REVISION_DRIFT"
    return {
        "schema": "GXP_DDK_0023_RUNTIME_TARGET_PREFLIGHT_V1",
        "service": SERVICE,
        "inspection": "READ_ONLY_MAINPID_ENV_AND_LOCAL_READYZ",
        "runtime_database_name": name,
        "database_name_source": source,
        **health,
        "status": state,
        "database_reads": 0,
        "database_writes": 0,
        "important_limitation": (
            "This observes systemd MainPID environment and local readiness; "
            "it does not certify every child process, socket, or later config change. "
            "It is NOT permission to apply a migration."
        ),
    }


def main() -> int:
    try:
        pid = _get_main_pid()
        env = _get_service_env(pid)
        name, source = _safe_database_name(env)
        health = _read_readyz()
        result = assess_runtime(name, source, health)
    except (OSError, ValueError, subprocess.TimeoutExpired, URLError, UnicodeError):
        # No raw exceptions or URLs; they might embed credentials.
        result = {
            "schema": "GXP_DDK_0023_RUNTIME_TARGET_PREFLIGHT_V1",
            "service": SERVICE,
            "status": "BLOCK_RUNTIME_INSPECTION_ERROR",
            "database_reads": 0,
            "database_writes": 0,
        }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if result["status"] == "OBSERVED_SERVICE_TARGET_DIFFERENT_FROM_REHEARSAL" else 2


if __name__ == "__main__":
    raise SystemExit(main())
