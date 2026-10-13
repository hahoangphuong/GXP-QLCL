"""Read-only VM runtime target preflight: secret-free and fail-closed."""
from __future__ import annotations

import json
import subprocess
from urllib.error import URLError

import pytest

from scripts import check_gxp_runtime_db_target_readonly as preflight


READY = {
    "http_status": 200, "ok": True, "database_reachable": True,
    "schema_current": True, "expected_revision": "20261008_0022",
    "actual_revision": "20261008_0022",
}


def test_service_uses_rehearsal_blocks_regardless_of_healthy_readyz():
    result = preflight.assess_runtime(
        "gxp_legacy_rehearsal", "DATABASE_URL", READY)
    assert result["status"] == "BLOCK_ACTIVE_SERVICE_TARGETS_REHEARSAL"
    assert result["database_writes"] == 0
    assert result["readiness_indirect_database_read"] is True


def test_independent_database_and_ready_revision_may_pass_as_observation_only():
    result = preflight.assess_runtime("gxp_qlcl", "DB_NAME", READY)
    assert result["status"] == "OBSERVED_SERVICE_TARGET_DIFFERENT_FROM_REHEARSAL"
    assert "NOT permission" in result["important_limitation"]


@pytest.mark.parametrize("name,source,ready,status", [
    (None, "TARGET_NOT_EXPOSED_IN_MAINPID_ENV", READY, "BLOCK_UNKNOWN_RUNTIME_TARGET"),
    ("gxp_qlcl", "DB_NAME", {**READY, "schema_current": False}, "BLOCK_RUNTIME_READINESS_OR_REVISION_DRIFT"),
    ("gxp_qlcl", "DB_NAME", {**READY, "http_status": 503}, "BLOCK_RUNTIME_READINESS_OR_REVISION_DRIFT"),
    ("gxp_qlcl", "DB_NAME", {**READY, "actual_revision": "20261012_0023"}, "BLOCK_RUNTIME_READINESS_OR_REVISION_DRIFT"),
])
def test_runtime_preflight_always_fails_closed(name, source, ready, status):
    assert preflight.assess_runtime(name, source, ready)["status"] == status


@pytest.mark.parametrize("environment,expected", [
    ({"DATABASE_URL": "postgresql+psycopg://alice:s3cret@localhost/gxp_legacy_rehearsal"}, ("gxp_legacy_rehearsal", "DATABASE_URL")),
    ({"DB_NAME": "gxp_qlcl", "DB_MODE": "local_postgres"}, ("gxp_qlcl", "DB_NAME")),
    ({"DATABASE_URL": "sqlite:///tmp/cache.db"}, (None, "DATABASE_URL_INVALID_OR_NOT_POSTGRES")),
    ({"DATABASE_URL": "postgresql://some_user:s3cret@localhost/gxp_qlcl", "DB_NAME": "gxp_legacy_rehearsal"}, ("gxp_qlcl", "DATABASE_URL")),
    ({}, (None, "TARGET_NOT_EXPOSED_IN_MAINPID_ENV")),
])
def test_parses_only_target_db_without_exposing_credentials(environment, expected):
    assert preflight._safe_database_name(environment) == expected
    assert "s3cret" not in json.dumps(expected)


def test_main_no_env_logging_even_when_database_credential_present(monkeypatch, capsys):
    monkeypatch.setattr(preflight, "_get_main_pid", lambda: 2468)
    monkeypatch.setattr(preflight, "_get_backend_port", lambda _: 8000)
    monkeypatch.setattr(preflight, "_get_service_env", lambda _: {
        "DATABASE_URL": "postgresql+psycopg://alice:super-secret@127.0.0.1/gxp_qlcl"
    })
    monkeypatch.setattr(preflight, "_read_readyz", lambda _: dict(READY))
    assert preflight.main() == 0
    output = capsys.readouterr().out
    assert "OBSERVED_SERVICE_TARGET_DIFFERENT_FROM_REHEARSAL" in output
    assert "super-secret" not in output
    assert "alice" not in output


def test_missing_proc_env_or_network_does_not_claim_clearance(monkeypatch, capsys):
    monkeypatch.setattr(preflight, "_get_main_pid", lambda: 2468)
    monkeypatch.setattr(preflight, "_get_backend_port", lambda _: 8000)
    monkeypatch.setattr(
        preflight, "_get_service_env",
        lambda _: (_ for _ in ()).throw(PermissionError("s3cret")),
    )
    assert preflight.main() == 2
    output = capsys.readouterr().out
    assert "BLOCK_RUNTIME_INSPECTION_ERROR" in output
    assert "s3cret" not in output


@pytest.mark.parametrize("failing_stage,expected_stage", [
    ("pid", "SYSTEMD_MAINPID"),
    ("env", "MAINPID_PROC_ENVIRONMENT"),
    ("name", "SAFE_DB_NAME_EXTRACTION"),
    ("readyz", "LOCALHOST_READYZ"),
    ("port", "MAINPID_BACKEND_PORT"),
])
def test_diagnostic_identifies_only_safe_failed_stage(
    failing_stage, expected_stage, monkeypatch, capsys,
):
    def fail():
        raise PermissionError("secret://alice:s3cret@db.example")
    monkeypatch.setattr(
        preflight, "_get_main_pid",
        fail if failing_stage == "pid" else lambda: 2468,
    )
    monkeypatch.setattr(
        preflight, "_get_service_env",
        (lambda _: fail()) if failing_stage == "env"
        else lambda _: {"DATABASE_URL": "postgresql://alice:super-secret@localhost/gxp_qlcl"},
    )
    monkeypatch.setattr(
        preflight, "_safe_database_name",
        (lambda _: fail()) if failing_stage == "name"
        else lambda _: ("gxp_qlcl", "DATABASE_URL"),
    )
    monkeypatch.setattr(
        preflight, "_get_backend_port",
        (lambda _: fail()) if failing_stage == "port" else lambda _: 8000,
    )
    monkeypatch.setattr(
        preflight, "_read_readyz",
        (lambda _: fail()) if failing_stage == "readyz" else lambda _: dict(READY),
    )
    assert preflight.main() == 2
    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "BLOCK_RUNTIME_INSPECTION_ERROR"
    assert data["failed_stage"] == expected_stage
    assert data["error_category"] == "PermissionError"
    assert data["database_writes"] == 0
    assert "alice" not in json.dumps(data)
    assert "s3cret" not in json.dumps(data)
    assert "super-secret" not in json.dumps(data)
    assert "db.example" not in json.dumps(data)


def test_successful_probe_has_no_failed_stage(monkeypatch, capsys):
    monkeypatch.setattr(preflight, "_get_main_pid", lambda: 2468)
    monkeypatch.setattr(preflight, "_get_backend_port", lambda _: 8000)
    monkeypatch.setattr(preflight, "_get_service_env", lambda _: {"DB_NAME": "gxp_qlcl"})
    monkeypatch.setattr(preflight, "_read_readyz", lambda _: dict(READY))
    assert preflight.main() == 0
    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "OBSERVED_SERVICE_TARGET_DIFFERENT_FROM_REHEARSAL"
    assert "failed_stage" not in data


def test_main_pid_argv_port_discovery_never_uses_nginx_port(monkeypatch):
    from pathlib import Path
    class Proc:
        def read_bytes(self):
            return b"/opt/gxp/release/bin/uvicorn\\0backend.app.main:app\\0--host\\0127.0.0.1\\0--port\\08000\\0"
    monkeypatch.setattr(Path, "read_bytes", lambda self: Proc().read_bytes())
    assert preflight._get_backend_port(2468) == 8000


def test_main_pid_wrong_host_refused_before_readyz(monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(Path, "read_bytes", lambda self: b"uvicorn\\0--host\\00.0.0.0\\0--port\\08000\\0")
    with pytest.raises(ValueError, match="loopback"):
        preflight._get_backend_port(2468)


def test_direct_loopback_readiness_ignores_proxy_and_redacts_errors(monkeypatch):
    requested = []
    class Response:
        status = 200
        def read(self, n):
            return json.dumps(READY | {"database_error": "password=secret"}).encode()
    class Connection:
        def __init__(self, host, port, timeout):
            requested.append((host, port, timeout))
        def request(self, verb, path, headers):
            requested.append((verb, path))
        def getresponse(self):
            return Response()
        def close(self):
            pass
    monkeypatch.setattr(preflight, "HTTPConnection", Connection)
    result = preflight._read_readyz(8000)
    assert requested[:2] == [("127.0.0.1", 8000, 8), ("GET", "/readyz")]
    assert result["http_status"] == 200
    assert "secret" not in json.dumps(result)


def test_main_uses_discovered_backend_port(monkeypatch, capsys):
    monkeypatch.setattr(preflight, "_get_main_pid", lambda: 2468)
    monkeypatch.setattr(preflight, "_get_service_env", lambda _: {"DB_NAME": "gxp_qlcl"})
    monkeypatch.setattr(preflight, "_get_backend_port", lambda _: 8177)
    seen = []
    monkeypatch.setattr(preflight, "_read_readyz", lambda port: seen.append(port) or dict(READY))
    assert preflight.main() == 0
    assert seen == [8177]
    assert json.loads(capsys.readouterr().out)["readyz_port"] == 8177


def test_rehearsal_db_does_not_probe_any_network(monkeypatch, capsys):
    monkeypatch.setattr(preflight, "_get_main_pid", lambda: 2468)
    monkeypatch.setattr(preflight, "_get_service_env", lambda _: {"DB_NAME": "gxp_legacy_rehearsal"})
    monkeypatch.setattr(preflight, "_get_backend_port", lambda _: (_ for _ in ()).throw(AssertionError("Do not probe")))
    assert preflight.main() == 2
    value = json.loads(capsys.readouterr().out)
    assert value["status"] == "BLOCK_ACTIVE_SERVICE_TARGETS_REHEARSAL"
    assert value["readiness_indirect_database_read"] is False
