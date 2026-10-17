"""Regression suite for the uninstalled / explicitly disabled nightly backup unit.

All data and paths are disposable; no actual PostgreSQL, systemd or GCS is used.
"""
from __future__ import annotations

from pathlib import Path
import os

import pytest

from tools import run_vm_nightly_backup as guard
from tools.env_utils import serialize_systemd_environment_file_contents


SHA = "a" * 40
DB_NAME = "gxp_legacy_rehearsal"


def values() -> tuple[dict[str, str], dict[str, str]]:
    canonical = {
        "APP_ENV": "production",
        "DB_MODE": "local_postgres",
        "DB_NAME": DB_NAME,
        "DB_USER": "gxp_app",
        "DB_HOST": "127.0.0.1",
        "DB_PORT": "5432",
        "BACKUP_GCS_BUCKET": "gs://synthetic-backups",
    }
    live = {
        **canonical,
        "DATABASE_URL": f"postgresql+psycopg://gxp_app:synthetic@127.0.0.1:5432/{DB_NAME}",
        "DEPLOYMENT_GIT_SHA": SHA,
    }
    return canonical, live


def test_unit_is_inert_with_utc_no_catchup_timer():
    root = Path(__file__).resolve().parents[1] / "infra" / "vm"
    service = (root / "gxp-postgres-nightly-backup.service").read_text(encoding="utf-8")
    timer = (root / "gxp-postgres-nightly-backup.timer").read_text(encoding="utf-8")
    assert "Environment=GXP_NIGHTLY_BACKUP_ENABLED=0" in service
    assert "ExecStart=/usr/bin/python3 /opt/gxp/current-backend/tools/run_vm_nightly_backup.py" in service
    assert "User=gxp" in service
    assert "OnCalendar=*-*-* 01:30:00 UTC" in timer
    assert "Persistent=false" in timer
    assert "Unit=gxp-postgres-nightly-backup.service" in timer
    assert "systemctl enable" not in service + timer
    assert "systemctl start" not in service + timer


def test_disabled_early_exits_without_any_io(monkeypatch, capsys):
    monkeypatch.delenv("GXP_NIGHTLY_BACKUP_ENABLED", raising=False)
    monkeypatch.setattr(guard, "verify_live_unit", lambda _: pytest.fail("unexpected systemd probe"))
    monkeypatch.setattr(guard.os, "execv", lambda *_: pytest.fail("unexpected backup"))
    assert guard.run() == 3
    assert "SCHEDULE_DISABLED" in capsys.readouterr().out


@pytest.fixture
def prepared(tmp_path: Path, monkeypatch):
    if os.name == "nt":
        pytest.skip("POSIX release symlinks required")
    real = tmp_path / "release"
    (real / "infra" / "vm").mkdir(parents=True)
    (real / "infra" / "vm" / "backup_postgres.sh").write_text("# only synthetic", encoding="utf-8")
    backend = tmp_path / "current-backend"
    backend.symlink_to(real, target_is_directory=True)
    canonical_path = tmp_path / "runtime.env"
    active_path = tmp_path / "runtime.systemd.env"
    metadata_path = tmp_path / "current-release.json"
    canonical, live = values()

    def write(canonical_map=canonical, active_map=live, meta_sha=SHA):
        canonical_path.write_text(
            "\n".join(f"{k}={v}" for k, v in canonical_map.items()) + "\n", encoding="utf-8"
        )
        active_path.write_text(serialize_systemd_environment_file_contents(active_map), encoding="utf-8")
        metadata_path.write_text(
            '{"current_sha":"' + meta_sha + '","backend_release_dir":"' + str(real) + '"}', encoding="utf-8"
        )

    write()
    monkeypatch.setattr(guard, "ROOT", real)
    monkeypatch.setattr(guard, "CANONICAL_ENV", canonical_path)
    monkeypatch.setattr(guard, "LIVE_ENV", active_path)
    monkeypatch.setattr(guard, "RELEASE_META", metadata_path)
    monkeypatch.setattr(guard, "BACKEND_LINK", backend)
    monkeypatch.setenv("GXP_NIGHTLY_BACKUP_ENABLED", "1")
    monkeypatch.setenv("VM_RUNTIME_ENV_FILE", str(canonical_path))
    monkeypatch.delenv("ALLOW_USER_GCLOUD_AUTH", raising=False)
    checked = []
    monkeypatch.setattr(guard, "verify_live_unit", lambda p: checked.append(str(p)))
    invoked = []
    monkeypatch.setattr(guard.os, "execv", lambda path, argv: invoked.append((path, argv)))
    return canonical, live, write, checked, invoked, real, backend


def test_exact_source_target_and_handoff(prepared, capsys):
    _, _, _, checked, invoked, real, _ = prepared
    assert guard.run() == 0
    assert checked == [str(guard.LIVE_ENV)]
    assert invoked == [("/usr/bin/bash", ["bash", str(real / "infra" / "vm" / "backup_postgres.sh")])]
    assert "BACKUP_TARGET_VERIFIED database=" + DB_NAME in capsys.readouterr().out


@pytest.mark.parametrize("case", [
    "canonical_wrong_db", "live_wrong_db", "active_url_wrong_db",
    "active_url_wrong_host", "canonical_url_wrong_db", "release_sha_wrong",
    "metadata_sha_invalid", "breakglass", "cloudsql", "missing_bucket",
    "wrong_backend_release", "missing_active_url",
])
def test_preflight_blocks_wrong_target_before_backup(prepared, case: str, monkeypatch):
    canonical, live, write, checked, invoked, _, backend = prepared
    meta_sha = SHA
    if case == "canonical_wrong_db":
        canonical["DB_NAME"] = "another_database"
    elif case == "live_wrong_db":
        live["DB_NAME"] = "another_database"
    elif case == "active_url_wrong_db":
        live["DATABASE_URL"] = live["DATABASE_URL"].replace(DB_NAME, "another_database")
    elif case == "active_url_wrong_host":
        live["DATABASE_URL"] = live["DATABASE_URL"].replace("127.0.0.1", "not-local.test")
    elif case == "canonical_url_wrong_db":
        canonical["DATABASE_URL"] = live["DATABASE_URL"].replace(DB_NAME, "another_database")
    elif case == "release_sha_wrong":
        live["DEPLOYMENT_GIT_SHA"] = "b" * 40
    elif case == "metadata_sha_invalid":
        meta_sha = "invalid-sha"
    elif case == "breakglass":
        canonical["ALLOW_USER_GCLOUD_AUTH"] = "1"
    elif case == "cloudsql":
        canonical["DB_MODE"] = "cloud_sql"
        live["DB_MODE"] = "cloud_sql"
    elif case == "missing_bucket":
        canonical["BACKUP_GCS_BUCKET"] = ""
    elif case == "wrong_backend_release":
        backend.unlink()
        backend.symlink_to(backend.parent / "other-release", target_is_directory=True)
    elif case == "missing_active_url":
        live.pop("DATABASE_URL")
    write(canonical, live, meta_sha=meta_sha)
    assert guard.run() == 4
    assert invoked == []


def test_parser_error_does_not_leak_secrets(prepared, capsys):
    _, _, _, _, invoked, _, _ = prepared
    guard.CANONICAL_ENV.write_text("SECRET_PASSWORD=dont_leak_me\nmalformed line", encoding="utf-8")
    assert guard.run() == 4
    capture = capsys.readouterr()
    output = capture.out + capture.err
    assert "dont_leak_me" not in output
    assert invoked == []


def test_unknown_live_service_blocks_before_dump(prepared, monkeypatch):
    _, _, _, _, invoked, _, _ = prepared

    def fail_service(_):
        raise guard.BackupBlocked("cannot verify the running backend systemd unit")

    monkeypatch.setattr(guard, "verify_live_unit", fail_service)
    assert guard.run() == 4
    assert invoked == []


def test_disabled_even_when_opt_in_variable_blank(prepared, monkeypatch):
    _, _, _, checked, invoked, _, _ = prepared
    monkeypatch.setenv("GXP_NIGHTLY_BACKUP_ENABLED", "")
    assert guard.run() == 3
    assert checked == []
    assert invoked == []

def test_systemd_environment_file_binding_is_exact(monkeypatch):
    from types import SimpleNamespace

    calls = []
    def fake_run(args, **_kwargs):
        calls.append(args)
        if "show" in args:
            return SimpleNamespace(stdout="/etc/gxp/runtime.systemd.env (ignore_errors=no)\\n")
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(guard.subprocess, "run", fake_run)
    guard.verify_live_unit(Path("/etc/gxp/runtime.systemd.env"))
    assert len(calls) == 2
    with pytest.raises(guard.BackupBlocked, match="expected live environment"):
        guard.verify_live_unit(Path("/etc/gxp/not-active.env"))


def test_systemd_environment_probe_failure_is_fail_closed(monkeypatch):
    def fail(_args, **_kwargs):
        raise OSError("synthetic systemd failure")
    monkeypatch.setattr(guard.subprocess, "run", fail)
    with pytest.raises(guard.BackupBlocked, match="cannot verify"):
        guard.verify_live_unit(Path("/etc/gxp/runtime.systemd.env"))
