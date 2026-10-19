"""Only synthetic local subprocess/file mocks; never probe the real VM or GCS."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

from tools import audit_vm_backup_trigger_readonly as auditor


def _cron(*, direct=False, unknown=False):
    return {
        "per_user_crontab": {
            "root": "UNVERIFIED" if unknown else "NO_DIRECT_TARGET_REFERENCE",
            "gxp": "NO_DIRECT_TARGET_REFERENCE",
        },
        "system_cron_directory": "READ",
        "system_cron_files_read": 3,
        "system_cron_files_unverified": 0,
        "system_cron_files_matching_known_entrypoint": int(direct),
        "other_users_not_checked": True,
        "indirect_wrapper_schedules_not_ruled_out": True,
    }


def _configured(monkeypatch, *, timer_active="inactive", direct=False, unknown=False):
    def fake_properties(unit, keys):
        if unit == auditor.TIMER:
            return {
                "LoadState": "loaded",
                "ActiveState": timer_active,
                "UnitFileState": "disabled",
                "LastTriggerUSec": "",
            }
        assert unit == auditor.SERVICE
        return {"LoadState": "loaded", "ActiveState": "inactive", "Result": "success"}

    monkeypatch.setattr(auditor, "_properties", fake_properties)
    monkeypatch.setattr(auditor, "_unit_opt_in", lambda: "UNIT_EXPLICITLY_DISABLED")
    monkeypatch.setattr(
        auditor, "_cron_snapshot", lambda: _cron(direct=direct, unknown=unknown)
    )
    monkeypatch.setattr(
        auditor, "_journal_summary", lambda: {
            "status": "JOURNAL_METADATA_ONLY", "entries_observed": 2,
        },
    )


def test_known_local_trigger_not_active_is_not_backup_freshness(monkeypatch):
    _configured(monkeypatch)
    result = auditor.audit_local_backup_trigger()
    assert result["status"] == "NO_ACTIVE_KNOWN_LOCAL_TRIGGER_OBSERVED"
    assert result["service"]["source_unit_opt_in"] == "UNIT_EXPLICITLY_DISABLED"
    assert result["service"]["source_unit_opt_in_is_not_effective_env_proof"]
    assert result["external_scheduler_not_checked"] is True
    for key in (
        "actual_backup_run_verified", "backup_freshness_verified",
        "backup_pair_checksum_verified", "disposable_restore_verified",
        "backup_or_restore_started", "scheduler_modified",
    ):
        assert result[key] is False
    assert result["database_writes"] == result["storage_writes"] == 0


@pytest.mark.parametrize("timer_active,direct", [
    ("active", False), ("inactive", True), ("active", True),
])
def test_local_trigger_reference_does_not_claim_success(
    monkeypatch, timer_active, direct,
):
    _configured(monkeypatch, timer_active=timer_active, direct=direct)
    result = auditor.audit_local_backup_trigger()
    assert result["status"] == "LOCAL_TRIGGER_REFERENCE_OBSERVED"
    assert not result["actual_backup_run_verified"]
    assert not result["backup_freshness_verified"]


def test_unknown_root_cron_fails_closed(monkeypatch):
    _configured(monkeypatch, unknown=True)
    result = auditor.audit_local_backup_trigger()
    assert result["status"] == "LOCAL_TRIGGER_UNVERIFIED"
    assert result["cron"]["per_user_crontab"]["root"] == "UNVERIFIED"


def test_missing_systemd_timer_must_not_be_reported_as_no_trigger(monkeypatch):
    _configured(monkeypatch)
    monkeypatch.setattr(auditor, "_properties", lambda _unit, _keys: None)
    assert auditor.audit_local_backup_trigger()["status"] == "LOCAL_TRIGGER_UNVERIFIED"


def test_properties_output_only_contains_allowlisted_values(monkeypatch):
    def fake_call(args):
        assert args[:2] == ["systemctl", "show"]
        return subprocess.CompletedProcess(
            args, 0,
            stdout=(
                "LoadState=loaded\nActiveState=active\n"
                "UnitFileState=enabled\nLastTriggerUSec=Mon 2026-10-19\n"
                "Environment=DB_PASSWORD=SECRET_DO_NOT_PRINT\n"
            ),
        )

    monkeypatch.setattr(auditor, "_call", fake_call)
    props = auditor._properties(
        auditor.TIMER,
        ("LoadState", "ActiveState", "UnitFileState", "LastTriggerUSec"),
    )
    assert "Environment" not in props
    assert props["ActiveState"] == "active"
    assert auditor._enum("SECRET_DO_NOT_PRINT", "timer_active_state") == "unknown"


def test_unit_explicitly_disabled_or_conflicted_does_not_claim_active(monkeypatch):
    def fake_call(args):
        assert args == ["systemctl", "cat", auditor.SERVICE, "--no-pager"]
        return subprocess.CompletedProcess(
            args, 0,
            stdout="# Environment=GXP_NIGHTLY_BACKUP_ENABLED=1\n"
                   "Environment=GXP_NIGHTLY_BACKUP_ENABLED=0\n"
                   "Environment=DATABASE_URL=postgresql://sensitive\n",
        )
    monkeypatch.setattr(auditor, "_call", fake_call)
    assert auditor._unit_opt_in() == "UNIT_EXPLICITLY_DISABLED"
    monkeypatch.setattr(
        auditor, "_call", lambda args: subprocess.CompletedProcess(
            args, 0,
            stdout=(
                "Environment=GXP_NIGHTLY_BACKUP_ENABLED=1\n"
                "Environment=GXP_NIGHTLY_BACKUP_ENABLED=0\n"
            ),
        ),
    )
    assert auditor._unit_opt_in() == "UNKNOWN"


def test_cron_comment_and_unrelated_words_not_interpreted_as_active():
    assert auditor._has_target_command(
        "# run_vm_nightly_backup.py disabled\n"
        "12 1 * * * echo 'hello'\n"
    ) is False
    assert auditor._has_target_command("30 1 * * * /opt/gxp/backup_postgres.sh") is True


def test_cron_file_symlink_and_oversized_content_are_not_trusted(tmp_path):
    path = tmp_path / "cron"
    path.write_text("* * * * * pg_dump\n")
    link = tmp_path / "shortcut"
    link.symlink_to(path)
    assert auditor._safe_read(link) is None
    path.write_bytes(b"x" * 131073)
    assert auditor._safe_read(path) is None


def test_journal_counts_without_disclosing_message_contents(monkeypatch):
    timestamp = str(1792386000000000)
    line = json.dumps({
        "__REALTIME_TIMESTAMP": timestamp,
        "MESSAGE": "DB_PASSWORD=SUPER_SECRET should not appear",
        "SENSITIVE": "private-path",
    })
    monkeypatch.setattr(
        auditor, "_call", lambda args: subprocess.CompletedProcess(
            args, 0, stdout=line + "\nmalformed json\n"
        ),
    )
    result = auditor._journal_summary()
    rendered = json.dumps(result)
    assert result["entries_observed"] == 1
    assert result["status"] == "JOURNAL_METADATA_ONLY"
    assert "SUPER_SECRET" not in rendered and "private-path" not in rendered
    assert result["journal_entries_are_not_verified_backup_runs"] is True


def test_read_only_command_executor_never_uses_shell(monkeypatch):
    calls = []
    def run(args, **kwargs):
        calls.append((args, kwargs))
        assert kwargs["stdin"] == subprocess.DEVNULL
        assert kwargs["stderr"] == subprocess.DEVNULL
        assert kwargs["timeout"] == 12
        assert kwargs["check"] is False
        assert "shell" not in kwargs
        return subprocess.CompletedProcess(args, 0, stdout="")

    monkeypatch.setattr(auditor.subprocess, "run", run)
    assert auditor._call(["systemctl", "show", auditor.TIMER]) is not None
    assert calls[0][0][0] == "systemctl"


def test_cli_does_not_echo_subprocess_exception_secret(monkeypatch, capsys):
    def explode():
        raise RuntimeError("SECRET_PASSWORD=DO_NOT_LEAK")
    monkeypatch.setattr(auditor, "audit_local_backup_trigger", explode)
    assert auditor.main([]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.strip() == "LOCAL_BACKUP_TRIGGER_AUDIT_BLOCKED"


def test_unprivileged_cron_probe_cannot_claim_missing_trigger(monkeypatch):
    def fake_call(args, *, capture_stderr=False):
        if args[0] == "crontab":
            assert capture_stderr is True
            return subprocess.CompletedProcess(args, 1, stdout="", stderr="permission denied")
        raise AssertionError("only crontab probe expected")
    monkeypatch.setattr(auditor, "_call", fake_call)
    monkeypatch.setattr(auditor, "_safe_read", lambda path: "")
    monkeypatch.setattr(
        auditor.Path, "iterdir", lambda self: iter([]),
    )
    cron = auditor._cron_snapshot()
    assert cron["per_user_crontab"]["root"] == "UNVERIFIED"
    assert cron["per_user_crontab"]["gxp"] == "UNVERIFIED"



def test_absent_service_must_never_report_success_even_if_systemctl_result_success(monkeypatch):
    _configured(monkeypatch)
    old_properties = auditor._properties
    def no_service(unit, keys):
        if unit == auditor.SERVICE:
            return {"LoadState": "not-found", "ActiveState": "inactive", "Result": "success"}
        return old_properties(unit, keys)
    monkeypatch.setattr(auditor, "_properties", no_service)
    report = auditor.audit_local_backup_trigger()
    assert report["service"]["load_state"] == "not-found"
    assert report["service"]["unit_result_known_success"] is False
    assert report["actual_backup_run_verified"] is False


@pytest.mark.parametrize("user", ["root", "gxp"])
def test_empty_user_crontabs_are_distinguished_from_privilege_errors(monkeypatch, user):
    def call(args, *, capture_stderr=False):
        assert args[0] == "crontab"
        assert capture_stderr is True
        if args[2] == user:
            return subprocess.CompletedProcess(
                args, 1, stdout="", stderr=f"no crontab for {user}\\n"
            )
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
    monkeypatch.setattr(auditor, "_call", call)
    monkeypatch.setattr(auditor, "_safe_read", lambda _path: "")
    monkeypatch.setattr(auditor.Path, "iterdir", lambda self: iter([]))
    report = auditor._cron_snapshot()
    assert report["per_user_crontab"][user] == "NO_CRONTAB"
    assert report["system_cron_files_matching_known_entrypoint"] == 0


@pytest.mark.parametrize("message", [
    "permission denied",
    "no crontab for other_user",
    "no crontab for root\\npassword=SECRET",
    "",
])
def test_untrusted_crontab_errors_remain_unverified(monkeypatch, message):
    def call(args, *, capture_stderr=False):
        assert capture_stderr is True
        return subprocess.CompletedProcess(args, 1, stdout="", stderr=message)
    monkeypatch.setattr(auditor, "_call", call)
    monkeypatch.setattr(auditor, "_safe_read", lambda _path: "")
    monkeypatch.setattr(auditor.Path, "iterdir", lambda self: iter([]))
    report = auditor._cron_snapshot()
    assert report["per_user_crontab"]["root"] == "UNVERIFIED"
    assert report["per_user_crontab"]["gxp"] == "UNVERIFIED"
    assert "SECRET" not in json.dumps(report)


def test_unreadable_cron_file_reason_is_aggregated_without_filename(tmp_path, monkeypatch):
    config = tmp_path / "sensitive-cron-file"
    config.write_text("* * * * * /opt/private/secret-command\\n")
    shortcut = tmp_path / "untrusted-link"
    shortcut.symlink_to(config)
    oversized = tmp_path / "oversized"
    oversized.write_bytes(b"x" * 131073)
    folder = tmp_path / "directory"
    folder.mkdir()
    assert auditor._unreadable_reason(shortcut) == "symlink"
    assert auditor._unreadable_reason(oversized) == "oversized"
    assert auditor._unreadable_reason(folder) == "nonregular"
    assert auditor._unreadable_reason(tmp_path / "missing") == "read_error"

    def call(args, *, capture_stderr=False):
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
    monkeypatch.setattr(auditor, "_call", call)
    monkeypatch.setattr(auditor.Path, "iterdir", lambda self: iter([shortcut, oversized, folder]))
    monkeypatch.setattr(auditor, "_safe_read", lambda path: None if path != Path("/etc/crontab") else "")
    report = auditor._cron_snapshot()
    assert report["system_cron_files_unverified"] == 3
    assert report["system_cron_unverified_reasons"] == {
        "symlink": 1, "oversized": 1, "nonregular": 1, "read_error": 0,
    }
    printed = json.dumps(report)
    assert "sensitive-cron-file" not in printed
    assert "secret-command" not in printed


def test_stderr_is_only_captured_for_explicit_cron_classification(monkeypatch):
    observed = []
    def fake_run(args, **kw):
        observed.append((args, kw))
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="no crontab for root")
    monkeypatch.setattr(auditor.subprocess, "run", fake_run)
    auditor._call(["systemctl", "show", auditor.TIMER])
    auditor._call(["crontab", "-u", "root", "-l"], capture_stderr=True)
    assert observed[0][1]["stderr"] == subprocess.DEVNULL
    assert observed[1][1]["stderr"] == subprocess.PIPE
    assert observed[0][1]["check"] is False
    assert observed[1][1]["check"] is False
