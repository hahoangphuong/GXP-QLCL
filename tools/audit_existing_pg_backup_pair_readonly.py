"""Offline inspection of an existing PostgreSQL dump + SHA256 sidecar.

This does NOT create a backup, connect to PostgreSQL/GCS, invoke restore, or
grant permission to change any canonical certificate or Case data.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys


class BackupPairBlocked(ValueError):
    """Fail closed without disclosing backup paths or internal archive content."""


def _require(ok: bool, reason: str) -> None:
    if not ok:
        raise BackupPairBlocked(reason)


def _regular_file(path: Path) -> os.stat_result:
    try:
        info = path.lstat()
    except OSError as exc:
        raise BackupPairBlocked("FILE_UNAVAILABLE") from exc
    _require(stat.S_ISREG(info.st_mode), "NOT_REGULAR_FILE")
    return info


def _sidecar_checksum(backup: Path) -> str:
    sidecar = Path(str(backup) + ".sha256")
    info = _regular_file(sidecar)
    _require(info.st_size <= 4096, "INVALID_SIDECAR_SIZE")
    try:
        lines = sidecar.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise BackupPairBlocked("INVALID_SIDECAR") from exc
    _require(len(lines) == 1, "INVALID_SIDECAR_ENTRIES")
    match = re.fullmatch(r"([a-fA-F0-9]{64}) ([ *])(.+)", lines[0])
    _require(match is not None, "INVALID_SIDECAR_ENTRY")
    original = match.group(3)
    _require(
        original == backup.name or (
            Path(original).is_absolute()
            and Path(original).name == backup.name
        ),
        "SIDECAR_FILENAME_MISMATCH",
    )
    _require(not any(ord(ch) < 32 or ord(ch) == 127 for ch in original),
             "SIDECAR_FILENAME_UNSAFE")
    return match.group(1).lower()


def inspect_existing_backup_pair(backup: Path) -> dict[str, object]:
    """Read existing bytes and PostgreSQL archive TOC only; never restore.

    A matching digest proves pair consistency, not origin from a particular
    PostgreSQL database or that pg_restore will succeed on a new database.
    """
    before = _regular_file(backup)
    _require(before.st_size > 0, "EMPTY_BACKUP")
    expected = _sidecar_checksum(backup)
    digest = sha256()
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        with os.fdopen(os.open(backup, flags), "rb") as source:
            opened = os.fstat(source.fileno())
            _require(stat.S_ISREG(opened.st_mode), "NOT_REGULAR_FILE")
            _require(
                (before.st_dev, before.st_ino) == (opened.st_dev, opened.st_ino),
                "BACKUP_CHANGED_WHILE_READING",
            )
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise BackupPairBlocked("BACKUP_READ_FAILED") from exc
    _require(digest.hexdigest() == expected, "BACKUP_SHA256_MISMATCH")

    try:
        completed = subprocess.run(
            ["pg_restore", "--list", str(backup)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise BackupPairBlocked("ARCHIVE_LIST_CHECK_UNAVAILABLE") from exc
    _require(completed.returncode == 0, "PG_RESTORE_LIST_FAILED")
    after = _regular_file(backup)
    _require(
        (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
        (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns),
        "BACKUP_CHANGED_WHILE_READING",
    )
    return {
        "schema": "gxp-existing-pg-backup-pair-offline-readiness/v1",
        "status": "BACKUP_PAIR_INTEGRITY_AND_TOC_VERIFIED_ONLY",
        "backup_pair_sha256_verified": True,
        "pg_restore_archive_list_verified": True,
        "source_database_identity_verified": False,
        "backup_freshness_verified": False,
        "restore_drill_verified": False,
        "canonical_fk_write_authorized": False,
        "database_writes": 0,
        "storage_writes": 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        outcome = inspect_existing_backup_pair(args.backup)
    except Exception as exc:
        # Deliberately never print paths, filenames, TOC, secrets, or messages
        # returned from filesystem/external subprocess errors.
        code = exc.args[0] if isinstance(exc, BackupPairBlocked) else "CHECK_UNAVAILABLE"
        print("BACKUP_PAIR_OFFLINE_AUDIT_BLOCKED: " + code, file=sys.stderr)
        return 2
    print(json.dumps(outcome, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
