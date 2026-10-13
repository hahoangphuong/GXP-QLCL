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
from http.client import HTTPConnection
from pathlib import Path
from urllib.parse import unquote, urlsplit

SERVICE = "gxp-web"
TARGET = "gxp_legacy_rehearsal"
BACKEND_HOST = "127.0.0.1"
# The live systemd ExecStart has --host 127.0.0.1 --port APP_PORT.
# Nginx on 80/443 only forwards /api/; /readyz is NOT on port 80.


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


def _get_backend_port(pid: int) -> int:
    """Read only numeric Uvicorn listen port from MainPID argv; never log argv."""
    values = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\\0")
    argv = [value.decode("utf-8", errors="replace") for value in values if value]
    def argument(flag: str) -> str | None:
        matches: list[str] = []
        for index, item in enumerate(argv):
            if item == flag and index + 1 < len(argv):
                matches.append(argv[index + 1])
            elif item.startswith(flag + "="):
                matches.append(item[len(flag) + 1:])
        if len(matches) != 1:
            return None
        return matches[0]
    host = argument("--host")
    port = argument("--port")
    if host != BACKEND_HOST or port is None or not port.isascii() or not port.isdecimal():
        raise ValueError("Unable to verify Uvicorn loopback listen address")
    number = int(port)
    if not (1 <= number <= 65535):
        raise ValueError("Backend port out of range")
    return number


def _read_readyz(port: int) -> dict:
    # Direct loopback connection bypasses nginx, proxy environment variables,
    # TLS redirects and external hostnames. Response whitelists safe fields.
    conn = HTTPConnection(BACKEND_HOST, port, timeout=8)
    try:
        conn.request("GET", "/readyz", headers={"Accept": "application/json"})
        response = conn.getresponse()
        status = response.status
        raw = response.read(32769)
        if len(raw) > 32768:
            raise ValueError("Readiness payload exceeds 32 KiB")
        parsed = json.loads(raw.decode("utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError("Invalid readiness response")
        return {
            "http_status": status,
            "ok": parsed.get("ok") is True,
            "database_reachable": parsed.get("database_reachable") is True,
            "schema_current": parsed.get("schema_current") is True,
            "expected_revision": parsed.get("expected_revision"),
            "actual_revision": parsed.get("actual_revision"),
        }
    finally:
        conn.close()

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
        "direct_database_queries": 0,
        "readiness_indirect_database_read": True,
        "database_writes": 0,
        "important_limitation": (
            "This observes systemd MainPID environment and local readiness; "
            "it does not certify every child process, socket, or later config change. "
            "It is NOT permission to apply a migration."
        ),
    }


def main() -> int:
    # Public stage identifiers, never the inspected value or exception text.
    # The previous catch-all reported only BLOCK_RUNTIME_INSPECTION_ERROR
    # and prevented operators from finding which read-only probe failed.
    stage = "SYSTEMD_MAINPID"
    try:
        pid = _get_main_pid()
        stage = "MAINPID_PROC_ENVIRONMENT"
        env = _get_service_env(pid)
        stage = "SAFE_DB_NAME_EXTRACTION"
        name, source = _safe_database_name(env)
        # An observed rehearsal target is always unsafe to upgrade, even
        # when readiness is unreachable; do not hide that behind a URLError.
        if name == TARGET:
            result = assess_runtime(name, source, {"http_status": None})
            print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
            return 2
        stage = "MAINPID_BACKEND_PORT"
        port = _get_backend_port(pid)
        stage = "LOCALHOST_READYZ"
        health = _read_readyz(port)
        stage = "ASSESS_RUNTIME"
        result = assess_runtime(name, source, health)
        result["readyz_port"] = port
    except (OSError, ValueError, subprocess.TimeoutExpired, URLError, UnicodeError) as error:
        # Only constant stage labels + exception CLASS may be emitted.
        # Exception messages can contain URL credentials or HTTP details.
        result = {
            "schema": "GXP_DDK_0023_RUNTIME_TARGET_PREFLIGHT_V1",
            "service": SERVICE,
            "status": "BLOCK_RUNTIME_INSPECTION_ERROR",
            "failed_stage": stage,
            "error_category": type(error).__name__,
            "runtime_database_name": name if stage in (
                "MAINPID_BACKEND_PORT", "LOCALHOST_READYZ", "ASSESS_RUNTIME"
            ) else None,
            "database_name_source": source if stage in (
                "MAINPID_BACKEND_PORT", "LOCALHOST_READYZ", "ASSESS_RUNTIME"
            ) else None,
            "direct_database_queries": 0,
            "readiness_indirect_database_read": stage == "ASSESS_RUNTIME",
            "database_writes": 0,
        }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if result["status"] == "OBSERVED_SERVICE_TARGET_DIFFERENT_FROM_REHEARSAL" else 2


if __name__ == "__main__":
    raise SystemExit(main())
