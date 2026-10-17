from __future__ import annotations

"""Fail-closed nightly backup entrypoint. Inert unless the service opt-in is 1.

Only stdlib + repository env parser are needed. No scheduling or provisioning
takes place here. Approved activation is a separate operator action.
"""

import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.env_utils import parse_env_file, parse_systemd_env_file

CANONICAL_ENV = Path("/etc/gxp/runtime.env")
LIVE_ENV = Path("/etc/gxp/runtime.systemd.env")
RELEASE_META = Path("/opt/gxp/current-release.json")
BACKEND_LINK = Path("/opt/gxp/current-backend")
SYSTEMD_SERVICE = "gxp-web"


class BackupBlocked(Exception):
    pass


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise BackupBlocked(reason)


def url_database(url: str) -> tuple[str, str, str, int | None]:
    """Never return or log the credential-bearing URL."""
    try:
        split = urlsplit(url)
        database = unquote(split.path.lstrip("/"))
        host = split.hostname or ""
        username = unquote(split.username or "")
        port = split.port
    except ValueError as exc:
        raise BackupBlocked("invalid database URL") from exc
    require(
        split.scheme.startswith("postgresql") and bool(database)
        and "/" not in database and bool(host) and bool(username),
        "database URL is not an explicit PostgreSQL target",
    )
    return database, username, host, port


def validate_backup_target(
    canonical: dict[str, str],
    live: dict[str, str],
    metadata: dict[str, object],
    *,
    release_root: Path,
    link_target: str,
) -> str:
    """Pure preflight, separately testable without database or service access."""
    require(canonical.get("APP_ENV") == live.get("APP_ENV") == "production", "application environment mismatch")
    require(canonical.get("DB_MODE") == live.get("DB_MODE") == "local_postgres", "database mode mismatch")
    for key in ("DB_NAME", "DB_USER", "DB_HOST", "DB_PORT"):
        require(bool(canonical.get(key)) and canonical.get(key) == live.get(key), "canonical/live " + key + " mismatch")
    name = canonical["DB_NAME"]
    require(bool(re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", name)), "database name invalid")
    require(live.get("DATABASE_URL", "") != "", "live DATABASE_URL is not explicit")
    for env_name, env in (("live", live), ("canonical", canonical)):
        if env.get("DATABASE_URL"):
            db, user, host, port = url_database(env["DATABASE_URL"])
            require(db == name and user == canonical["DB_USER"], env_name + " database URL target mismatch")
            require(host == canonical["DB_HOST"] and port == int(canonical["DB_PORT"]),
                    env_name + " database URL host or port mismatch")
    require(canonical.get("BACKUP_GCS_BUCKET", "").startswith("gs://")
            and canonical["BACKUP_GCS_BUCKET"] != "gs://YOUR_GXP_BACKUP_BUCKET",
            "backup bucket not configured")
    require(canonical.get("ALLOW_USER_GCLOUD_AUTH", "0") != "1", "break-glass GCloud identity is not allowed for scheduled backup")
    sha = str(metadata.get("current_sha", ""))
    require(bool(re.fullmatch(r"[0-9a-f]{40}", sha)), "release metadata SHA unavailable")
    require(live.get("DEPLOYMENT_GIT_SHA") == sha, "live runtime release SHA mismatch")
    expected_root = str(metadata.get("backend_release_dir", ""))
    require(bool(expected_root) and link_target == expected_root,
            "backend release link does not match metadata")
    require(release_root.resolve() == Path(expected_root).resolve(),
            "backup entrypoint is not from live backend release")
    return name


def verify_live_unit(active_env: Path) -> None:
    """Ensure that the checked file is used by the running backend service."""
    try:
        response = subprocess.run(
            ["systemctl", "show", SYSTEMD_SERVICE, "--property=EnvironmentFiles", "--value"],
            capture_output=True, text=True, timeout=12, check=True,
        )
        subprocess.run(["systemctl", "is-active", "--quiet", SYSTEMD_SERVICE],
                       capture_output=True, timeout=12, check=True)
    except (OSError, subprocess.SubprocessError) as exc:
        raise BackupBlocked("cannot verify the running backend systemd unit") from exc
    require(
        re.search(r"(?<!\\S)" + re.escape(str(active_env)) + r"(?=\\s|$)", response.stdout) is not None,
        "running backend does not use the expected live environment file",
    )


def run() -> int:
    # A committed timer or even an accidentally started service must not back up.
    if os.environ.get("GXP_NIGHTLY_BACKUP_ENABLED") != "1":
        print("SCHEDULE_DISABLED: explicit nightly backup opt-in is absent")
        return 3
    try:
        require(os.environ.get("VM_RUNTIME_ENV_FILE", str(CANONICAL_ENV)) == str(CANONICAL_ENV),
                "noncanonical runtime env override rejected")
        require(os.environ.get("ALLOW_USER_GCLOUD_AUTH", "0") != "1",
                "break-glass GCloud identity override rejected")
        verify_live_unit(LIVE_ENV)
        canonical = parse_env_file(CANONICAL_ENV)
        live = parse_systemd_env_file(LIVE_ENV)
        metadata = json.loads(RELEASE_META.read_text(encoding="utf-8"))
        require(isinstance(metadata, dict), "release metadata shape invalid")
        require(BACKEND_LINK.is_symlink(), "backend release link is not a symlink")
        name = validate_backup_target(
            canonical, live, metadata, release_root=ROOT,
            link_target=os.readlink(BACKEND_LINK),
        )
        backup_script = ROOT / "infra" / "vm" / "backup_postgres.sh"
        require(backup_script.is_file(), "deployed backup script missing")
    except BackupBlocked as exc:
        print("BACKUP_PRECHECK_BLOCKED: " + str(exc), file=sys.stderr)
        return 4
    except (OSError, ValueError, TypeError, KeyError):
        # Env-parser exceptions can contain complete input lines with secrets.
        print("BACKUP_PRECHECK_BLOCKED: unreadable or malformed configuration", file=sys.stderr)
        return 4
    print(f"BACKUP_TARGET_VERIFIED database={name} release={metadata['current_sha']}", flush=True)
    # Handoff to existing owner script; no alternate pg_dump/GCloud path.
    os.execv("/usr/bin/bash", ["bash", str(backup_script)])
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
