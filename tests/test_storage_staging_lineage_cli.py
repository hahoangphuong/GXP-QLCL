from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.app.storage.staging import RootScanCoverage, StagingAudit, StagingCandidate
from backend.app.storage.staging_lineage import StagingLineageItem, StagingLineageReport
from tools import reconcile_storage_staging_lineage as cli


def _write_inventory(tmp_path: Path, *, truncated: bool = False) -> Path:
    path = tmp_path / "staging.json"
    payload = {
        "candidates": [{
            "root": "inspection", "relative_path": "2026/one/.gxp-stage-aabbcc.tmp",
            "category": "managed_candidate", "size": 10,
        }],
        "scanned_directories": 1, "scanned_entries": 3,
        "requested_roots": ["inspection"],
        "root_coverage": [{
            "root": "inspection",
            "status": "partial" if truncated else "complete",
            "scanned_directories": 1, "scanned_entries": 3,
        }],
        "truncated": truncated,
        "incomplete_reason": "storage_access_failed" if truncated else None,
        "failed_root": "inspection" if truncated else None,
        "failed_relative_path": "" if truncated else None,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_lineage_cli_without_dedicated_env_never_connects(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("GXP_STORAGE_LINEAGE_READONLY_DATABASE_URL", raising=False)
    monkeypatch.setattr(cli, "create_engine",
        lambda *args, **kwargs: pytest.fail("must not connect"))
    code = cli.main(["--inventory-json", str(_write_inventory(tmp_path))])
    assert code == 3
    assert json.loads(capsys.readouterr().out)["reason"] == "read_only_database_url_not_configured"


def test_lineage_cli_malformed_input_never_opens_database(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GXP_STORAGE_LINEAGE_READONLY_DATABASE_URL", "postgresql://user:secret@host/db")
    path = tmp_path / "malformed.json"
    path.write_text('{"candidates":"not an array"}', encoding="utf-8")
    monkeypatch.setattr(cli, "create_engine",
        lambda *args, **kwargs: pytest.fail("must not connect on malformed input"))
    assert cli.main(["--inventory-json", str(path)]) == 3
    assert json.loads(capsys.readouterr().out) == {
        "status": "incomplete", "reason": "lineage_audit_failed",
    }


def test_lineage_cli_rejects_non_postgres_database(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GXP_STORAGE_LINEAGE_READONLY_DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setattr(cli, "create_engine",
        lambda *args, **kwargs: pytest.fail("must not open SQLite"))
    assert cli.main(["--inventory-json", str(_write_inventory(tmp_path))]) == 3
    assert json.loads(capsys.readouterr().out)["reason"] == "lineage_audit_failed"


class _FakeResult:
    def __init__(self, *, role_flags=None, value="on"):
        self.role_flags = role_flags or (False, False, False, True, True, True, False, False, False)
        self.value = value

    def scalar_one(self):
        return self.value

    def one(self):
        return self.role_flags


class _FakeTransaction:
    def __init__(self):
        self.rollbacks = 0

    def rollback(self):
        self.rollbacks += 1


class _FakeConnection:
    def __init__(self):
        self.transaction = _FakeTransaction()
        self.statements = []
        self.role_flags = (False, False, False, True, True, True, False, False, False)
        self.can_write_other_tables = False

    def begin(self):
        return self.transaction

    def exec_driver_sql(self, sql):
        self.statements.append(sql)
        return _FakeResult(
            role_flags=self.role_flags,
            value=(
                self.can_write_other_tables if "pg_catalog.pg_class" in sql
                else "repeatable read" if sql == "SHOW transaction_isolation"
                else "on"
            ),
        )

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None


class _FakeEngine:
    def __init__(self):
        self.connection = _FakeConnection()
        self.disposed = False

    def connect(self):
        return self.connection

    def dispose(self):
        self.disposed = True


class _FakeSession:
    def __init__(self, *, bind, autoflush):
        assert autoflush is False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None


def test_lineage_cli_confirms_read_only_and_always_rolls_back(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GXP_STORAGE_LINEAGE_READONLY_DATABASE_URL", "postgresql://reader:private@host/db")
    engine = _FakeEngine()
    engine_urls = []
    def configured_engine(url, **kwargs):
        engine_urls.append(url)
        return engine
    monkeypatch.setattr(cli, "create_engine", configured_engine)
    monkeypatch.setattr(cli, "Session", _FakeSession)
    seen = []

    def reconcile(session, inventory, *, max_candidates):
        seen.append(inventory)
        return StagingLineageReport(
            items=(StagingLineageItem(
                root="inspection", relative_path="2026/one/.gxp-stage-aabbcc.tmp",
                category="managed_candidate", size=10,
                document_version_ids=(), template_definition_ids=(),
                enclosing_inspection_binding_ids=(),
                evidence="no_exact_locator_evidence",
            ),),
            input_inventory_truncated=inventory.truncated,
            input_incomplete_reason=inventory.incomplete_reason,
            inspected_candidates=1,
        )

    monkeypatch.setattr(cli, "reconcile_staging_lineage", reconcile)
    result = cli.main(["--inventory-json", str(_write_inventory(tmp_path, truncated=True))])
    data = json.loads(capsys.readouterr().out)
    assert result == 2
    assert data["input_inventory_truncated"] is True
    assert data["status"] == "review_only"
    assert engine.connection.statements[:4] == [
        "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY",
        "SHOW transaction_read_only",
        "SHOW transaction_isolation",
        "SET LOCAL search_path = pg_catalog, public, pg_temp",
    ]
    assert len(engine.connection.statements) == 6
    assert "public.document_version" in engine.connection.statements[4]
    assert "pg_catalog.pg_class" in engine.connection.statements[5]
    assert engine.connection.transaction.rollbacks == 1
    assert engine.disposed
    assert len(seen) == 1
    assert len(engine_urls) == 1
    assert engine_urls[0].drivername == "postgresql+psycopg"


def test_lineage_cli_rejects_unsupported_postgres_driver(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv(
        "GXP_STORAGE_LINEAGE_READONLY_DATABASE_URL",
        "postgresql+psycopg2://reader:secret@host/db",
    )
    monkeypatch.setattr(cli, "create_engine",
        lambda *args, **kwargs: pytest.fail("unsupported driver must never connect"))
    assert cli.main(["--inventory-json", str(_write_inventory(tmp_path))]) == 3
    assert json.loads(capsys.readouterr().out)["reason"] == "lineage_audit_failed"


@pytest.mark.parametrize(
    "role_flags",
    [
        (True, False, False, True, True, True, False, False, False),
        (False, True, False, True, True, True, False, False, False),
        (False, False, True, True, True, True, False, False, False),
        (False, False, False, True, True, True, True, False, False),
        (False, False, False, True, True, True, False, True, False),
        (False, False, False, True, True, True, False, False, True),
        (False, False, False, True, False, True, False, False, False),
    ],
)
def test_lineage_cli_rejects_privileged_or_incomplete_reader_grants(
    tmp_path, monkeypatch, capsys, role_flags,
):
    monkeypatch.setenv(
        "GXP_STORAGE_LINEAGE_READONLY_DATABASE_URL",
        "postgresql+psycopg://admin:secret@localhost/test",
    )
    engine = _FakeEngine()
    engine.connection.role_flags = role_flags
    monkeypatch.setattr(cli, "create_engine", lambda *args, **kwargs: engine)
    monkeypatch.setattr(cli, "Session", lambda **kwargs:
        pytest.fail("unauthorized DB role must be rejected before Session"))
    assert cli.main(["--inventory-json", str(_write_inventory(tmp_path))]) == 3
    output = capsys.readouterr().out
    assert json.loads(output)["reason"] == "lineage_audit_failed"
    assert "secret" not in output
    assert engine.connection.transaction.rollbacks == 1
    assert engine.disposed


def test_lineage_cli_rejects_reader_with_writes_to_other_business_tables(
    tmp_path, monkeypatch, capsys,
):
    monkeypatch.setenv(
        "GXP_STORAGE_LINEAGE_READONLY_DATABASE_URL",
        "postgresql+psycopg://other_writer:secret@localhost/test",
    )
    engine = _FakeEngine()
    engine.connection.can_write_other_tables = True
    monkeypatch.setattr(cli, "create_engine", lambda *args, **kwargs: engine)
    monkeypatch.setattr(cli, "Session", lambda **kwargs:
        pytest.fail("writable schema role must not reach lineage SELECTs"))
    assert cli.main(["--inventory-json", str(_write_inventory(tmp_path))]) == 3
    assert json.loads(capsys.readouterr().out)["reason"] == "lineage_audit_failed"
    assert engine.connection.transaction.rollbacks == 1
    assert engine.disposed


def test_lineage_cli_db_failure_never_leaks_secret_and_rolls_back(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GXP_STORAGE_LINEAGE_READONLY_DATABASE_URL", "postgresql://reader:secret@host/db")
    engine = _FakeEngine()
    monkeypatch.setattr(cli, "create_engine", lambda *args, **kwargs: engine)
    monkeypatch.setattr(cli, "Session", _FakeSession)
    def fail(*args, **kwargs):
        raise RuntimeError("private-db-password")
    monkeypatch.setattr(cli, "reconcile_staging_lineage", fail)
    assert cli.main(["--inventory-json", str(_write_inventory(tmp_path))]) == 3
    output = capsys.readouterr().out
    assert json.loads(output)["reason"] == "lineage_audit_failed"
    assert "private-db-password" not in output
    assert engine.connection.transaction.rollbacks == 1
    assert engine.disposed


@pytest.mark.parametrize(
    "case",
    [
        "truncated_string", "entries_string", "directories_boolean",
        "size_negative", "size_boolean", "wrong_category",
        "bad_root", "traversal", "absolute_path", "not_staging_filename",
        "duplicate_locator", "complete_with_failure_reason",
        "incomplete_without_reason", "incomplete_without_failed_root",
        "failure_path_without_error", "counter_lower_than_findings",
        "unknown_candidate_key", "unknown_root_key", "missing_required_key",
        "invalid_incomplete_reason",
        "missing_root_scope", "empty_root_scope", "string_root_scope",
        "duplicate_root_scope", "unknown_root_scope",
        "candidate_outside_declared_root", "failed_root_outside_scope",
        "complete_without_directories", "complete_with_too_few_scanned_roots",
        "missing_coverage", "coverage_string", "coverage_unknown_status",
        "coverage_wrong_root", "coverage_extra_root", "coverage_invalid_count",
        "coverage_count_mismatch", "complete_with_partial_coverage",
        "truncated_with_complete_coverage", "not_started_with_counts",
        "failed_root_coverage_complete", "candidate_under_unstarted_root",
    ],
)
def test_lineage_cli_rejects_structurally_invalid_inventory_before_db(
    tmp_path, monkeypatch, capsys, case,
):
    path = _write_inventory(tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    candidate = data["candidates"][0]
    if case == "truncated_string":
        data["truncated"] = "false"
    elif case == "entries_string":
        data["scanned_entries"] = "3"
    elif case == "directories_boolean":
        data["scanned_directories"] = True
    elif case == "size_negative":
        candidate["size"] = -1
    elif case == "size_boolean":
        candidate["size"] = False
    elif case == "wrong_category":
        candidate["category"] = "legacy_smb_candidate"
    elif case == "bad_root":
        candidate["root"] = "arbitrary"
    elif case == "traversal":
        candidate["relative_path"] = "../escape/.gxp-stage-aabbcc.tmp"
    elif case == "absolute_path":
        candidate["relative_path"] = "/tmp/.gxp-stage-aabbcc.tmp"
    elif case == "not_staging_filename":
        candidate["relative_path"] = "2026/one/regular-file.pdf"
    elif case == "duplicate_locator":
        data["candidates"].append(dict(candidate))
    elif case == "complete_with_failure_reason":
        data["incomplete_reason"] = "storage_access_failed"
    elif case == "incomplete_without_reason":
        data["truncated"] = True
    elif case == "incomplete_without_failed_root":
        data["truncated"] = True
        data["incomplete_reason"] = "storage_access_failed"
    elif case == "failure_path_without_error":
        data["failed_root"] = "inspection"
        data["failed_relative_path"] = ""
    elif case == "counter_lower_than_findings":
        data["scanned_entries"] = 0
    elif case == "unknown_candidate_key":
        candidate["unknown"] = "not in scanner export"
    elif case == "unknown_root_key":
        data["unknown"] = "not in scanner export"
    elif case == "missing_required_key":
        del data["scanned_entries"]
    elif case == "invalid_incomplete_reason":
        data["truncated"] = True
        data["incomplete_reason"] = "already_deleted"
    elif case == "missing_root_scope":
        del data["requested_roots"]
    elif case == "empty_root_scope":
        data["requested_roots"] = []
    elif case == "string_root_scope":
        data["requested_roots"] = "inspection"
    elif case == "duplicate_root_scope":
        data["requested_roots"] = ["inspection", "inspection"]
    elif case == "unknown_root_scope":
        data["requested_roots"] = ["inspection", "unknown"]
    elif case == "candidate_outside_declared_root":
        candidate["root"] = "dkkd"
    elif case == "failed_root_outside_scope":
        data["truncated"] = True
        data["incomplete_reason"] = "storage_access_failed"
        data["failed_root"] = "template"
        data["failed_relative_path"] = ""
    elif case == "complete_without_directories":
        data["scanned_directories"] = 0
    elif case == "complete_with_too_few_scanned_roots":
        data["requested_roots"] = ["inspection", "dkkd"]
    elif case == "missing_coverage":
        del data["root_coverage"]
    elif case == "coverage_string":
        data["root_coverage"] = "complete"
    elif case == "coverage_unknown_status":
        data["root_coverage"][0]["status"] = "maybe"
    elif case == "coverage_wrong_root":
        data["root_coverage"][0]["root"] = "dkkd"
    elif case == "coverage_extra_root":
        data["root_coverage"].append(dict(data["root_coverage"][0]))
    elif case == "coverage_invalid_count":
        data["root_coverage"][0]["scanned_entries"] = "3"
    elif case == "coverage_count_mismatch":
        data["root_coverage"][0]["scanned_entries"] = 2
    elif case == "complete_with_partial_coverage":
        data["root_coverage"][0]["status"] = "partial"
    elif case == "truncated_with_complete_coverage":
        data["truncated"] = True
        data["incomplete_reason"] = "directory_budget_exceeded"
    elif case == "not_started_with_counts":
        data["truncated"] = True
        data["incomplete_reason"] = "directory_budget_exceeded"
        data["root_coverage"][0]["status"] = "not_started"
    elif case == "failed_root_coverage_complete":
        data["truncated"] = True
        data["incomplete_reason"] = "storage_access_failed"
        data["failed_root"] = "inspection"
        data["failed_relative_path"] = ""
    elif case == "candidate_under_unstarted_root":
        data["truncated"] = True
        data["incomplete_reason"] = "directory_budget_exceeded"
        data["root_coverage"][0]["status"] = "not_started"
        data["root_coverage"][0]["scanned_directories"] = 0
        data["root_coverage"][0]["scanned_entries"] = 0
        data["scanned_directories"] = 0
        data["scanned_entries"] = 0
    path.write_text(json.dumps(data), encoding="utf-8")

    monkeypatch.setenv(
        "GXP_STORAGE_LINEAGE_READONLY_DATABASE_URL",
        "postgresql+psycopg://reader:secret@localhost/gxp_qlcl_test",
    )
    monkeypatch.setattr(
        cli, "create_engine",
        lambda *args, **kwargs: pytest.fail("untrusted JSON opened database"),
    )
    assert cli.main(["--inventory-json", str(path)]) == 3
    result = json.loads(capsys.readouterr().out)
    assert result == {"status": "incomplete", "reason": "lineage_audit_failed"}


def test_lineage_cli_rejects_duplicate_json_object_key_before_db(
    tmp_path, monkeypatch, capsys,
):
    path = _write_inventory(tmp_path)
    data = path.read_text(encoding="utf-8")
    assert '"scanned_entries": 3' in data
    path.write_text(
        data.replace('"scanned_entries": 3', '"scanned_entries": 3, "scanned_entries": 300'),
        encoding="utf-8",
    )
    monkeypatch.setenv(
        "GXP_STORAGE_LINEAGE_READONLY_DATABASE_URL",
        "postgresql+psycopg://reader:secret@localhost/gxp_qlcl_test",
    )
    monkeypatch.setattr(
        cli, "create_engine",
        lambda *args, **kwargs: pytest.fail("duplicate JSON keys opened database"),
    )
    assert cli.main(["--inventory-json", str(path)]) == 3
    assert json.loads(capsys.readouterr().out)["reason"] == "lineage_audit_failed"


def test_lineage_cli_rejects_oversized_json_without_unbounded_read(
    tmp_path, monkeypatch, capsys,
):
    path = tmp_path / "oversized.json"
    path.write_bytes(b" " * (cli._MAX_JSON_BYTES + 1))
    monkeypatch.setenv(
        "GXP_STORAGE_LINEAGE_READONLY_DATABASE_URL",
        "postgresql+psycopg://reader:secret@localhost/gxp_qlcl_test",
    )
    monkeypatch.setattr(
        cli, "create_engine",
        lambda *args, **kwargs: pytest.fail("oversized JSON opened database"),
    )
    assert cli.main(["--inventory-json", str(path)]) == 3
    assert json.loads(capsys.readouterr().out)["reason"] == "lineage_audit_failed"


def test_lineage_direct_read_only_reconciliation_validates_before_engine(
    tmp_path, monkeypatch,
):
    from backend.app.storage.staging import StagingAudit, StagingCandidate
    inventory = StagingAudit(
        candidates=(StagingCandidate(
            root="inspection", relative_path="../.gxp-stage-aabbcc.tmp",
            category="managed_candidate", size=8,
        ),),
        scanned_directories=1, scanned_entries=1,
        truncated=False, incomplete_reason=None,
        requested_roots=("inspection",),
        root_coverage=(RootScanCoverage(
            root="inspection", status="complete",
            scanned_directories=1, scanned_entries=1,
        ),),
    )
    monkeypatch.setattr(
        cli, "create_engine",
        lambda *args, **kwargs: pytest.fail("bad direct inventory opened database"),
    )
    with pytest.raises(ValueError, match="invalid logical locator"):
        cli._read_only_reconcile("postgresql+psycopg://reader:secret@localhost/db", inventory)


def test_lineage_cli_empty_scanned_scope_is_not_all_roots(
    tmp_path, monkeypatch, capsys,
):
    path = _write_inventory(tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["candidates"] = []
    data["scanned_directories"] = 1
    data["scanned_entries"] = 0
    data["root_coverage"][0]["scanned_entries"] = 0
    path.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setenv(
        "GXP_STORAGE_LINEAGE_READONLY_DATABASE_URL",
        "postgresql+psycopg://reader:secret@localhost/test",
    )
    from backend.app.storage.staging_lineage import StagingLineageReport
    observed = []

    def fake_reconcile(url, inventory):
        observed.append(inventory)
        return StagingLineageReport(
            items=(), inspected_candidates=0,
            input_inventory_truncated=False,
            input_incomplete_reason=None,
            input_requested_roots=inventory.requested_roots,
            input_root_coverage=inventory.root_coverage,
        )
    monkeypatch.setattr(cli, "_read_only_reconcile", fake_reconcile)
    assert cli.main(["--inventory-json", str(path)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["input_requested_roots"] == ["inspection"]
    assert output["input_root_coverage"] == [{
        "root": "inspection", "status": "complete",
        "scanned_directories": 1, "scanned_entries": 0,
    }]
    assert output["status"] == "review_only"
    assert observed[0].requested_roots == ("inspection",)
