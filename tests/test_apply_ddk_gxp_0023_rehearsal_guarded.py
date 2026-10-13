"""No-live-DB tests for SHA-pinned, guarded 0023 rehearsal apply helper."""
from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import apply_ddk_gxp_0023_rehearsal_guarded as runner


SAMPLE_SQL = """BEGIN;

-- Running upgrade 20261008_0022 -> 20261012_0023
CREATE TABLE business_eligibility_gxp_source_group (
    id UUID NOT NULL, PRIMARY KEY (id)
);
CREATE INDEX ix_begxp_group_source_workbook
    ON business_eligibility_gxp_source_group (id);
CREATE TABLE business_eligibility_gxp_reference_evidence (
    id UUID NOT NULL, PRIMARY KEY (id)
);
CREATE INDEX ix_business_eligibility_gxp_reference_evidence_source_group_id
    ON business_eligibility_gxp_reference_evidence (id);
UPDATE alembic_version SET version_num='20261012_0023'
    WHERE alembic_version.version_num = '20261008_0022';
COMMIT;
"""


def _artifact(tmp_path, monkeypatch):
    source = tmp_path / "0023-reviewed.sql"
    raw = SAMPLE_SQL.encode("utf-8")
    source.write_bytes(raw)
    monkeypatch.setattr(runner, "EXPECTED_SHA256", hashlib.sha256(raw).hexdigest())
    return source


def test_guarded_transaction_checks_source_revision_and_empty_tables(tmp_path, monkeypatch):
    body = runner.verify_reviewed_sql(_artifact(tmp_path, monkeypatch).read_bytes())
    transaction = runner.build_guarded_transaction(body)
    assert transaction.count("BEGIN TRANSACTION") == 1
    assert transaction.count("COMMIT;") == 1
    assert "BEGIN;\n" not in transaction
    assert "gxp_legacy_rehearsal" in transaction
    assert "20261008_0022" in transaction and "20261012_0023" in transaction
    assert "ACCESS EXCLUSIVE MODE" in transaction
    assert "Serializable read-write transaction required" in transaction
    assert "DDK GxP provenance tables already exist" in transaction
    assert "New source-only provenance tables are unexpectedly populated" in transaction
    assert "SET LOCAL statement_timeout = '30s'" in transaction


def test_default_is_no_write_and_explicit_target_is_required(tmp_path, monkeypatch, capsys):
    source = _artifact(tmp_path, monkeypatch)
    monkeypatch.setattr(
        runner, "apply_transaction",
        lambda _: (_ for _ in ()).throw(AssertionError("No DB calls without exact --apply/target")),
    )
    base = ["--sql-file", str(source)]
    assert runner.main(base) == 0
    assert "NO_WRITE_REVIEW_ONLY" in capsys.readouterr().out
    assert runner.main(base + ["--apply"]) == 2
    assert runner.main(base + ["--apply", "--confirm-target", "gxp_qlcl"]) == 2
    assert runner.main(base + ["--confirm-target", "gxp_legacy_rehearsal"]) == 2


def test_explicit_apply_uses_only_local_socket_with_no_shell(tmp_path, monkeypatch):
    source = _artifact(tmp_path, monkeypatch)
    calls = []
    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    assert runner.main([
        "--sql-file", str(source), "--apply",
        "--confirm-target", "gxp_legacy_rehearsal",
    ]) == 0
    assert len(calls) == 1
    command, kw = calls[0]
    assert command == [
        "sudo", "-n", "-u", "postgres", "psql", "-X",
        "-v", "ON_ERROR_STOP=1", "-h", "/var/run/postgresql",
        "-U", "postgres", "-d", "gxp_legacy_rehearsal",
    ]
    assert "shell" not in kw
    assert kw["input"].startswith("\\set ON_ERROR_STOP on\nBEGIN TRANSACTION")


def test_apply_failure_does_not_claim_success_or_log_secrets(
    tmp_path, monkeypatch, capsys,
):
    source = _artifact(tmp_path, monkeypatch)
    monkeypatch.setattr(
        runner.subprocess, "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=3, stderr="sensitive PostgreSQL error"),
    )
    assert runner.main([
        "--sql-file", str(source), "--apply",
        "--confirm-target", "gxp_legacy_rehearsal",
    ]) == 2
    streams = capsys.readouterr()
    assert "COMMITTED" not in streams.out
    assert "sensitive" not in streams.err


def test_sql_tamper_and_byte_drift_block_before_db_call(tmp_path, monkeypatch):
    source = _artifact(tmp_path, monkeypatch)
    def forbidden(*_args, **_kwargs):
        raise AssertionError("DB call forbidden")
    monkeypatch.setattr(runner, "apply_transaction", forbidden)
    source.write_bytes(source.read_bytes() + b"\nDROP TABLE certificate;\n")
    assert runner.main([
        "--sql-file", str(source), "--apply",
        "--confirm-target", "gxp_legacy_rehearsal",
    ]) == 2
    source = _artifact(tmp_path, monkeypatch)
    original_verify = runner.verify_reviewed_sql
    def source_changed(raw):
        body = original_verify(raw)
        source.write_bytes(b"changed")
        return body
    monkeypatch.setattr(runner, "verify_reviewed_sql", source_changed)
    assert runner.main([
        "--sql-file", str(source), "--apply",
        "--confirm-target", "gxp_legacy_rehearsal",
    ]) == 2


def test_renamed_version_or_extra_table_blocked_at_sql_audit(tmp_path, monkeypatch):
    _artifact(tmp_path, monkeypatch)
    for changed in (
        SAMPLE_SQL.replace("20261012_0023", "20261012_0024"),
        SAMPLE_SQL.replace(
            "CREATE TABLE business_eligibility_gxp_reference_evidence",
            "CREATE TABLE certificate",
        ),
    ):
        raw = changed.encode("utf-8")
        monkeypatch.setattr(runner, "EXPECTED_SHA256", hashlib.sha256(raw).hexdigest())
        with pytest.raises(runner.GuardFailure):
            runner.verify_reviewed_sql(raw)
