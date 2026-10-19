"""Redacted, read-only LOCAL trigger discovery for the GXP nightly backup.

No database/storage access, no backup, restore, scheduler installation or state
change. External Cloud Scheduler, other machines and indirect scripts are out
of scope. This is an observation, not a substitute for restore verification.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import stat
import subprocess
import sys
from typing import Any

TIMER = "gxp-postgres-nightly-backup.timer"
SERVICE = "gxp-postgres-nightly-backup.service"
MATCH = re.compile(
    r"(?:backup_postgres\.sh|run_vm_nightly_backup\.py|"
    r"gxp-postgres-nightly-backup|\bpg_dump\b)"
)
ENABLED = re.compile(r"^Environment=GXP_NIGHTLY_BACKUP_ENABLED=([01])$")
ALLOWED = {
    "timer_load_state": {"loaded", "not-found", "masked", "error", "unknown"},
    "timer_active_state": {"active", "inactive", "failed", "activating", "unknown"},
    "timer_unit_file_state": {"enabled", "disabled", "static", "masked", "not-found", "unknown"},
    "service_load_state": {"loaded", "not-found", "masked", "error", "unknown"},
    "service_active_state": {"active", "inactive", "failed", "activating", "unknown"},
}


def _call(
    args: list[str], *, capture_stderr: bool = False,
) -> subprocess.CompletedProcess[str] | None:
    # The caller supplies only literals from this module, never source/env data.
    try:
        return subprocess.run(
            args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE if capture_stderr else subprocess.DEVNULL,
            text=True, errors="replace",
            timeout=12, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _properties(unit: str, keys: tuple[str, ...]) -> dict[str, str] | None:
    result = _call([
        "systemctl", "show", unit,
        "--no-pager", "--property=" + ",".join(keys),
    ])
    if result is None or result.returncode != 0:
        return None
    values: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key in keys and key not in values and len(value) <= 200:
            values[key] = value
    return values if all(k in values for k in keys) else None


def _enum(value: str | None, key: str) -> str:
    return value if value in ALLOWED[key] else "unknown"


def _unit_opt_in() -> str:
    result = _call(["systemctl", "cat", SERVICE, "--no-pager"])
    if result is None or result.returncode != 0:
        return "UNKNOWN"
    matches: set[str] = set()
    for line in result.stdout.splitlines():
        token = line.strip()
        if token.startswith("#"):
            continue
        found = ENABLED.fullmatch(token)
        if found:
            matches.add(found.group(1))
    # One unambiguous opt-in marker is required. Real systemd may also load
    # EnvironmentFile contents, so this does NOT prove the effective env.
    if matches == {"0"}:
        return "UNIT_EXPLICITLY_DISABLED"
    if matches == {"1"}:
        return "UNIT_EXPLICITLY_ENABLED_UNVERIFIED"
    return "UNKNOWN"


def _safe_read(path: Path) -> str | None:
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > 131072:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _unreadable_reason(path: Path) -> str:
    """Classify a skipped cron file without ever disclosing its path/content."""
    try:
        info = path.lstat()
    except OSError:
        return "read_error"
    if stat.S_ISLNK(info.st_mode):
        return "symlink"
    if not stat.S_ISREG(info.st_mode):
        return "nonregular"
    if info.st_size > 131072:
        return "oversized"
    return "read_error"


def _no_user_crontab(result: subprocess.CompletedProcess[str], user: str) -> bool:
    """Accept only the exact, known English crontab 'no entry' response.

    Other languages, permission failures, spoofed multiline stderr and
    missing executable remain UNVERIFIED. Raw stderr is never reported.
    """
    raw = result.stderr
    return (
        result.returncode == 1
        and isinstance(raw, str)
        and re.fullmatch(
            r"no crontab for " + re.escape(user) + r"\s*",
            raw,
        ) is not None
    )


def _has_target_command(raw: str) -> bool:
    # Strip comment lines; never return untrusted cron text or script names.
    return any(
        MATCH.search(line) is not None
        for line in raw.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )


def _cron_snapshot() -> dict[str, Any]:
    statuses: dict[str, str] = {}
    for user in ("root", "gxp"):
        # Inspect stderr only for this fixed, read-only command. Accept exactly
        # the canonical no-crontab message, never print or return stderr.
        result = _call(["crontab", "-u", user, "-l"], capture_stderr=True)
        if result is None:
            statuses[user] = "UNVERIFIED"
        elif result.returncode == 0:
            statuses[user] = (
                "TARGET_REFERENCE_PRESENT" if _has_target_command(result.stdout)
                else "NO_DIRECT_TARGET_REFERENCE"
            )
        elif _no_user_crontab(result, user):
            statuses[user] = "NO_CRONTAB"
        else:
            statuses[user] = "UNVERIFIED"

    file_paths = [Path("/etc/crontab")]
    cron_dir = Path("/etc/cron.d")
    directory_status = "READ"
    try:
        file_paths.extend(sorted(cron_dir.iterdir()))
    except OSError:
        directory_status = "UNAVAILABLE"
    direct = 0
    unreadable = 0
    read = 0
    skipped = {
        "symlink": 0, "oversized": 0,
        "nonregular": 0, "read_error": 0,
    }
    for path in file_paths:
        raw = _safe_read(path)
        if raw is None:
            unreadable += 1
            skipped[_unreadable_reason(path)] += 1
            continue
        read += 1
        direct += int(_has_target_command(raw))
    return {
        "per_user_crontab": statuses,
        "system_cron_directory": directory_status,
        "system_cron_files_read": read,
        "system_cron_files_unverified": unreadable,
        "system_cron_unverified_reasons": skipped,
        "system_cron_files_matching_known_entrypoint": direct,
        "other_users_not_checked": True,
        "indirect_wrapper_schedules_not_ruled_out": True,
    }


def _journal_summary() -> dict[str, Any]:
    result = _call([
        "journalctl", "--unit", SERVICE, "--no-pager",
        "--output=json", "-n", "500",
    ])
    if result is None or result.returncode != 0:
        return {"status": "UNVERIFIED", "entries_observed": 0}
    count = 0
    last: int | None = None
    for line in result.stdout.splitlines():
        try:
            entry = json.loads(line)
            ts = int(entry.get("__REALTIME_TIMESTAMP", ""))
            if ts > 0:
                last = max(last or 0, ts)
            count += 1
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
    return {
        "status": "JOURNAL_METADATA_ONLY",
        "entries_observed": count,
        "max_entries": 500,
        "last_entry_utc": (
            datetime.fromtimestamp(last / 1_000_000, timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%SZ") if last is not None else None
        ),
        "journal_entries_are_not_verified_backup_runs": True,
    }


def audit_local_backup_trigger() -> dict[str, Any]:
    timer = _properties(TIMER, ("LoadState", "ActiveState", "UnitFileState", "LastTriggerUSec"))
    service = _properties(SERVICE, ("LoadState", "ActiveState", "Result"))
    cron = _cron_snapshot()
    t_load = _enum(timer.get("LoadState") if timer else None, "timer_load_state")
    t_active = _enum(timer.get("ActiveState") if timer else None, "timer_active_state")
    t_enable = _enum(timer.get("UnitFileState") if timer else None, "timer_unit_file_state")
    s_load = _enum(service.get("LoadState") if service else None, "service_load_state")
    s_active = _enum(service.get("ActiveState") if service else None, "service_active_state")
    opt_in = _unit_opt_in()
    direct = (
        cron["system_cron_files_matching_known_entrypoint"] > 0
        or any(x == "TARGET_REFERENCE_PRESENT" for x in cron["per_user_crontab"].values())
    )
    any_unknown = (
        timer is None or service is None
        or cron["system_cron_directory"] != "READ"
        or cron["system_cron_files_unverified"] != 0
        or any(x == "UNVERIFIED" for x in cron["per_user_crontab"].values())
    )
    return {
        "schema": "gxp-vm-local-backup-trigger-discovery-readonly/v1",
        "status": (
            "LOCAL_TRIGGER_REFERENCE_OBSERVED"
            if t_active == "active" or direct
            else "LOCAL_TRIGGER_UNVERIFIED" if any_unknown
            else "NO_ACTIVE_KNOWN_LOCAL_TRIGGER_OBSERVED"
        ),
        "timer": {
            "load_state": t_load,
            "active_state": t_active,
            "unit_file_state": t_enable,
            "last_trigger_recorded": bool(
                timer and timer.get("LastTriggerUSec") not in
                ("", "n/a", "0", "0s", "unknown")
            ),
        },
        "service": {
            "load_state": s_load,
            "active_state": s_active,
            "unit_result_known_success": bool(
                s_load == "loaded" and service and service.get("Result") == "success"
            ),
            "source_unit_opt_in": opt_in,
            "source_unit_opt_in_is_not_effective_env_proof": True,
        },
        "cron": cron,
        "journal": _journal_summary(),
        "external_scheduler_not_checked": True,
        "actual_backup_run_verified": False,
        "backup_freshness_verified": False,
        "backup_pair_checksum_verified": False,
        "disposable_restore_verified": False,
        "backup_or_restore_started": False,
        "scheduler_modified": False,
        "database_writes": 0,
        "storage_writes": 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    try:
        report = audit_local_backup_trigger()
        print(json.dumps(report, sort_keys=True))
        return 0
    except Exception:
        # Subprocess output, paths, cron contents, and exception messages must
        # never leak into the terminal or GitHub issue.
        print("LOCAL_BACKUP_TRIGGER_AUDIT_BLOCKED", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
