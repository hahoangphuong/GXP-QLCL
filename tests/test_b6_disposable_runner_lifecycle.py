"""Exercise B6 disposable runner cleanup with fake commands, never a real DB."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNNERS = (
    ("G", "tools/run_b6g_schema_expand_postgres_integration.sh"),
    ("H", "tools/run_b6h_production_line_postgres_integration.sh"),
    ("J", "tools/run_b6j_production_line_postgres_integration.sh"),
)


@pytest.mark.skipif(shutil.which("bash") is None, reason="B6 runners require bash")
@pytest.mark.parametrize(("suffix", "script"), RUNNERS)
@pytest.mark.parametrize(
    ("create_result", "expected_status", "expected_commands"),
    (
        (9, 9, ("createdb",)),
        (0, 13, ("createdb", "probe-python", "dropdb")),
    ),
)
def test_runner_never_deletes_an_existing_database(
    tmp_path: Path,
    suffix: str,
    script: str,
    create_result: int,
    expected_status: int,
    expected_commands: tuple[str, ...],
) -> None:
    # Simulate createdb declining an existing database. The pre-existing DB
    # must never be removed. On the success path, a later command failure
    # must clean up precisely the DB created by this run.
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    commands_file = tmp_path / "invocations.txt"
    name = f"gxp_b6{suffix.lower()}_test_existing"
    socket_host = "/tmp/b6-explicit-test-socket"

    def fake_command(command: str, exit_code: int) -> None:
        script_path = fake_bin / command
        script_path.write_text(
            "#!/bin/sh\n"
            f"printf '{command}:%s\\n' \"$*\" >> \"$B6_FAKE_INVOCATIONS\"\n"
            f"exit {exit_code}\n",
            encoding="utf-8",
        )
        script_path.chmod(0o755)

    fake_command("createdb", create_result)
    fake_command("dropdb", 0)
    fake_command("probe-python", 13)
    env = os.environ.copy()
    env["PATH"] = str(fake_bin) + os.pathsep + env.get("PATH", "")
    env[f"B6{suffix}_DISPOSABLE_DATABASE"] = name
    env[f"B6{suffix}_PYTHON_BIN"] = str(fake_bin / "probe-python")
    env[f"B6{suffix}_POSTGRES_SOCKET_HOST"] = socket_host
    env["PGHOST"] = "/tmp/should-never-be-used"
    env["PGUSER"] = "someone-else"
    env["B6_FAKE_INVOCATIONS"] = str(commands_file)
    result = subprocess.run(
        ["bash", str(ROOT / script)], cwd=ROOT, env=env, capture_output=True, text=True, check=False
    )
    assert result.returncode == expected_status, result.stdout + result.stderr
    invocations = commands_file.read_text(encoding="utf-8").splitlines()
    assert [line.split(":", 1)[0] for line in invocations] == list(expected_commands)
    assert invocations[0] == f"createdb:--host={socket_host} --username=postgres {name}"
    if create_result == 0:
        assert invocations[1].startswith("probe-python:-m alembic upgrade ")
        assert invocations[2] == f"dropdb:--host={socket_host} --username=postgres --if-exists {name}"
