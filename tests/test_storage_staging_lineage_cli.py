from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.app.storage.staging import StagingAudit, StagingCandidate
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
        "truncated": truncated,
        "incomplete_reason": "storage_access_failed" if truncated else None,
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
            value=self.can_write_other_tables if "pg_catalog.pg_class" in sql else "on",
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
    assert engine.connection.statements[:3] == [
        "SET TRANSACTION READ ONLY",
        "SHOW transaction_read_only",
        "SET LOCAL search_path = pg_catalog, public, pg_temp",
    ]
    assert len(engine.connection.statements) == 5
    assert "public.document_version" in engine.connection.statements[3]
    assert "pg_catalog.pg_class" in engine.connection.statements[4]
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
