"""No PostgreSQL, GCS, backup creation or restoration is allowed in these tests."""
from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess

import pytest

from tools.audit_existing_pg_backup_pair_readonly import (
    BackupPairBlocked,
    inspect_existing_backup_pair,
    main,
)


def _pair(tmp_path: Path) -> Path:
    backup = tmp_path / "existing-gxp.dump"
    backup.write_bytes(b"synthetic archive for checksum testing only")
    digest = hashlib.sha256(backup.read_bytes()).hexdigest()
    Path(str(backup) + ".sha256").write_text(
        f"{digest}  {backup.name}\n", encoding="utf-8"
    )
    return backup


def _safe_restore_probe(monkeypatch):
    commands = []

    def fake_run(command, **options):
        commands.append((command, options))
        assert command[:2] == ["pg_restore", "--list"]
        assert options["stdin"] == subprocess.DEVNULL
        assert options["stdout"] == subprocess.DEVNULL
        assert options["stderr"] == subprocess.DEVNULL
        assert options["timeout"] == 120
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(
        "tools.audit_existing_pg_backup_pair_readonly.subprocess.run",
        fake_run,
    )
    return commands


def test_existing_pair_only_checks_hash_and_archive_toc(tmp_path, monkeypatch):
    backup = _pair(tmp_path)
    calls = _safe_restore_probe(monkeypatch)
    result = inspect_existing_backup_pair(backup)
    assert result["status"] == "BACKUP_PAIR_INTEGRITY_AND_TOC_VERIFIED_ONLY"
    assert result["backup_pair_sha256_verified"] is True
    assert result["pg_restore_archive_list_verified"] is True
    assert result["source_database_identity_verified"] is False
    assert result["backup_freshness_verified"] is False
    assert result["restore_drill_verified"] is False
    assert result["canonical_fk_write_authorized"] is False
    assert result["database_writes"] == result["storage_writes"] == 0
    assert len(calls) == 1
    assert calls[0][0] == ["pg_restore", "--list", str(backup)]


@pytest.mark.parametrize("mutation", [
    "missing_sidecar", "bad_checksum", "sidecar_wrong_filename",
    "multi_entry", "sidecar_symlink", "backup_symlink",
    "empty_archive", "sidecar_oversized",
])
def test_invalid_existing_pair_fails_before_any_external_command(
    tmp_path, monkeypatch, mutation,
):
    backup = _pair(tmp_path)
    sidecar = Path(str(backup) + ".sha256")
    if mutation == "missing_sidecar":
        sidecar.unlink()
    elif mutation == "bad_checksum":
        backup.write_bytes(b"mismatched bytes")
    elif mutation == "sidecar_wrong_filename":
        sidecar.write_text("0" * 64 + "  other.dump\n")
    elif mutation == "multi_entry":
        sidecar.write_text(sidecar.read_text() * 2)
    elif mutation == "sidecar_symlink":
        original = tmp_path / "actual.sha256"
        sidecar.rename(original)
        sidecar.symlink_to(original)
    elif mutation == "backup_symlink":
        original = tmp_path / "actual.dump"
        backup.rename(original)
        backup.symlink_to(original)
    elif mutation == "empty_archive":
        backup.write_bytes(b"")
    elif mutation == "sidecar_oversized":
        sidecar.write_text("a" * 5000)
    monkeypatch.setattr(
        "tools.audit_existing_pg_backup_pair_readonly.subprocess.run",
        lambda *_args, **_kwargs: pytest.fail("external check ran before SHA validation"),
    )
    with pytest.raises(BackupPairBlocked):
        inspect_existing_backup_pair(backup)


def test_pg_restore_list_failure_does_not_claim_restore(tmp_path, monkeypatch):
    backup = _pair(tmp_path)
    monkeypatch.setattr(
        "tools.audit_existing_pg_backup_pair_readonly.subprocess.run",
        lambda command, **options: subprocess.CompletedProcess(command, 1),
    )
    with pytest.raises(BackupPairBlocked, match="PG_RESTORE_LIST_FAILED"):
        inspect_existing_backup_pair(backup)


def test_offline_probe_detects_backup_changed_during_archive_list(
    tmp_path, monkeypatch,
):
    backup = _pair(tmp_path)

    def mutate(_command, **_kwargs):
        backup.write_bytes(b"changed after hashing")
        return subprocess.CompletedProcess(["pg_restore", "--list"], 0)

    monkeypatch.setattr(
        "tools.audit_existing_pg_backup_pair_readonly.subprocess.run", mutate,
    )
    with pytest.raises(BackupPairBlocked, match="BACKUP_CHANGED_WHILE_READING"):
        inspect_existing_backup_pair(backup)


def test_cli_failure_does_not_disclose_sensitive_backup_path(tmp_path, capsys):
    sensitive = tmp_path / "secret-db-password-in-filename.dump"
    exit_code = main(["--backup", str(sensitive)])
    capture = capsys.readouterr()
    assert exit_code == 2
    assert capture.out == ""
    assert "secret-db-password" not in capture.err
    assert capture.err.startswith("BACKUP_PAIR_OFFLINE_AUDIT_BLOCKED:")


def test_portable_legacy_absolute_sidecar_entry(tmp_path, monkeypatch):
    backup = _pair(tmp_path)
    sidecar = Path(str(backup) + ".sha256")
    digest = hashlib.sha256(backup.read_bytes()).hexdigest()
    sidecar.write_text(f"{digest}  /old-vm/stage/{backup.name}\n")
    _safe_restore_probe(monkeypatch)
    assert inspect_existing_backup_pair(backup)["backup_pair_sha256_verified"] is True
