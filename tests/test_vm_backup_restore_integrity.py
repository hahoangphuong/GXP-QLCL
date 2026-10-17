"""Disposable, executable regression checks for the real VM backup/restore scripts.

No PostgreSQL, Google Cloud, or service on the host is accessed: all external
commands are replaced by fixture executables and DB names are synthetic.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import textwrap

import pytest

ROOT = Path(__file__).resolve().parents[1]
VM = ROOT / "infra" / "vm"
pytestmark = pytest.mark.skipif(
    not shutil.which("bash") or not shutil.which("sha256sum"),
    reason="requires POSIX Bash and GNU sha256sum",
)


def _exe(path: Path, body: str) -> None:
    path.write_text("#!/usr/bin/env bash\nset -euo pipefail\n" + textwrap.dedent(body), encoding="utf-8")
    path.chmod(0o755)


def _fixture(tmp_path: Path) -> tuple[Path, dict[str, str], Path]:
    work = tmp_path / "isolated-vm"
    vm = work / "infra" / "vm"
    vm.mkdir(parents=True)
    for name in ("restore_postgres.sh", "backup_postgres.sh"):
        shutil.copy2(VM / name, vm / name)
    (vm / "common.sh").write_text(
        """#!/usr/bin/env bash
set -euo pipefail
load_runtime_env() { :; }
need_cmd() { command -v "$1" >/dev/null || exit 90; }
fail() { printf 'ERROR: %s\\n' "$*" >&2; exit 1; }
""", encoding="utf-8"
    )
    fake = work / "bin"
    fake.mkdir()
    command_log = work / "database-command-log.txt"
    _exe(fake / "postgres-admin", """
        printf 'postgres-admin %s\\n' "$*" >> "$FAKE_COMMAND_LOG"
        case "$1" in
          psql)
            if [[ "${FAKE_TARGET_DB_EXISTS:-1}" == "1" ]]; then printf '1\\n'; fi
            ;;
          createdb) : ;;
          *) exit 99 ;;
        esac
    """)
    _exe(fake / "pg_restore", """
        printf 'pg_restore %s\\n' "$*" >> "$FAKE_COMMAND_LOG"
    """)
    _exe(fake / "psql", """
        printf 'psql %s\\n' "$*" >> "$FAKE_COMMAND_LOG"
    """)
    _exe(fake / "createdb", """
        printf 'createdb %s\\n' "$*" >> "$FAKE_COMMAND_LOG"
    """)
    env = {**os.environ,
           "PATH": str(fake) + os.pathsep + os.environ["PATH"],
           "FAKE_COMMAND_LOG": str(command_log),
           "TARGET_DB": "isolated_restore_target",
           "CONFIRM_RESTORE": "RESTORE_isolated_restore_target",
           "DB_MODE": "local_postgres",
           "DB_NAME": "isolated_active_db",
           "DB_USER": "isolated_user",
           "DB_PASSWORD": "synthetic-only",
           "POSTGRES_ADMIN_CMD": str(fake / "postgres-admin")}
    return vm, env, command_log


def _run(script: Path, env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", str(script), *args], env=env, capture_output=True, text=True, check=False)


def _dump(tmp_path: Path) -> Path:
    path = tmp_path / "relocated" / "gxp-test-backup.dump"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"disposable pg_dump custom bytes - never a real database")
    return path


def _sidecar(path: Path, *, recorded_path: str | None = None, hash_override: str | None = None) -> None:
    digest = hash_override or hashlib.sha256(path.read_bytes()).hexdigest()
    (path.parent / (path.name + ".sha256")).write_text(
        digest + "  " + (recorded_path or path.name) + "\n", encoding="utf-8"
    )


@pytest.mark.parametrize("case", ["missing", "wrong_digest", "wrong_name", "multi_entry", "malformed"])
def test_restore_rejects_unverified_dump_before_any_db_command(tmp_path: Path, case: str) -> None:
    vm, env, log = _fixture(tmp_path)
    dump = _dump(tmp_path)
    if case == "wrong_digest":
        _sidecar(dump, hash_override="0" * 64)
    elif case == "wrong_name":
        _sidecar(dump, recorded_path="some-other-backup.dump")
    elif case == "multi_entry":
        _sidecar(dump)
        with Path(str(dump) + ".sha256").open("a", encoding="utf-8") as f:
            f.write(hashlib.sha256(dump.read_bytes()).hexdigest() + "  other.dump\n")
    elif case == "malformed":
        Path(str(dump) + ".sha256").write_text("not-a-valid-sha256-line\n", encoding="utf-8")
    result = _run(vm / "restore_postgres.sh", env, str(dump))
    assert result.returncode != 0, (case, result.stdout, result.stderr)
    assert not log.exists(), f"DB operation executed despite failed {case} integrity gate: {log.read_text()}"


@pytest.mark.parametrize("manifest_style", ["relative", "legacy_absolute"])
def test_restore_checks_selected_relocated_dump_and_then_proceeds(tmp_path: Path, manifest_style: str) -> None:
    vm, env, log = _fixture(tmp_path)
    dump = _dump(tmp_path)
    recorded = dump.name if manifest_style == "relative" else "/old-vm/tmp/staging/" + dump.name
    _sidecar(dump, recorded_path=recorded)
    result = _run(vm / "restore_postgres.sh", env, str(dump))
    assert result.returncode == 0, (result.stdout, result.stderr)
    records = log.read_text(encoding="utf-8")
    assert "postgres-admin psql" in records
    assert f"pg_restore --clean --if-exists --exit-on-error --no-owner" in records
    assert str(dump) in records


def test_restore_rejects_valid_digest_for_different_dump_filename(tmp_path: Path) -> None:
    vm, env, log = _fixture(tmp_path)
    dump = _dump(tmp_path)
    _sidecar(dump, recorded_path="/old-vm/other.dump")
    result = _run(vm / "restore_postgres.sh", env, str(dump))
    assert result.returncode != 0, (result.stdout, result.stderr)
    assert not log.exists()


def test_restore_verifies_selected_bytes_not_existing_original_file(tmp_path: Path) -> None:
    vm, env, log = _fixture(tmp_path)
    original = tmp_path / "original-vm" / "gxp-test-backup.dump"
    original.parent.mkdir()
    original.write_bytes(b"original-good-backup")
    dump = _dump(tmp_path)
    # Legacy manifest points to a valid origin dump but selected relocated bytes differ.
    _sidecar(dump, recorded_path=str(original),
             hash_override=hashlib.sha256(original.read_bytes()).hexdigest())
    result = _run(vm / "restore_postgres.sh", env, str(dump))
    assert result.returncode != 0, (result.stdout, result.stderr)
    assert not log.exists(), "restore must not trust a good old path instead of selected bytes"


def test_backup_writes_relocatable_manifest_and_uploads_matching_pair(tmp_path: Path) -> None:
    vm, env, _ = _fixture(tmp_path)
    fake = Path(env["PATH"].split(os.pathsep)[0])
    remote = tmp_path / "emulated-object-storage"
    remote.mkdir()
    _exe(fake / "pg_dump", """
        while [[ "$#" -gt 0 ]]; do
          case "$1" in --file) printf 'fake custom dump bytes' > "$2"; shift 2;; *) shift;; esac
        done
    """)
    _exe(fake / "curl", "printf 'isolated-sa@example.invalid\\n'\n")
    _exe(fake / "gcloud", """
        if [[ "$1" == auth ]]; then printf 'isolated-sa@example.invalid\\n'; exit 0; fi
        if [[ "$1" == storage && "$2" == cp ]]; then
          [[ "$#" == 5 ]] || exit 91
          cp "$3" "$GCS_FAKE_DIR/$(basename "$3")"
          cp "$4" "$GCS_FAKE_DIR/$(basename "$4")"
          exit 0
        fi
        if [[ "$1" == storage && "$2" == ls ]]; then
          test -f "$GCS_FAKE_DIR/$(basename "$3")"
          exit
        fi
        exit 92
    """)
    env.update({"GCS_FAKE_DIR": str(remote), "BACKUP_GCS_BUCKET": "gs://synthetic",
                "BACKUP_LOCAL_STAGING_DIR": str(tmp_path / "local-stage")})
    result = _run(vm / "backup_postgres.sh", env)
    assert result.returncode == 0, (result.stdout, result.stderr)
    checksums = list(remote.glob("*.sha256"))
    assert len(checksums) == 1, sorted(p.name for p in remote.iterdir())
    manifest = checksums[0].read_text(encoding="utf-8").strip()
    assert re.fullmatch(r"[a-f0-9]{64}  gxp-db-[0-9TZ]+\.dump", manifest), manifest
    dump = remote / checksums[0].name.removesuffix(".sha256")
    assert dump.is_file()
    assert manifest.split()[0] == hashlib.sha256(dump.read_bytes()).hexdigest()


@pytest.mark.parametrize("target_db", [
    "gxp_qlcl", "gxp_legacy_rehearsal", "unrelated_database",
])
def test_restore_rejects_non_disposable_db_before_any_database_command(
    tmp_path: Path, target_db: str,
) -> None:
    vm, env, log = _fixture(tmp_path)
    dump = _dump(tmp_path)
    _sidecar(dump)
    env["TARGET_DB"] = target_db
    env["CONFIRM_RESTORE"] = "RESTORE_" + target_db
    result = _run(vm / "restore_postgres.sh", env, str(dump))
    assert result.returncode != 0, (result.stdout, result.stderr)
    assert not log.exists(), "Non-disposable restore attempted a DB query or write"


def test_restore_rejects_existing_disposable_db_before_pg_restore(tmp_path: Path) -> None:
    vm, env, log = _fixture(tmp_path)
    dump = _dump(tmp_path)
    _sidecar(dump)
    env["FAKE_TARGET_DB_EXISTS"] = "1"
    result = _run(vm / "restore_postgres.sh", env, str(dump))
    assert result.returncode != 0, (result.stdout, result.stderr)
    records = log.read_text(encoding="utf-8") if log.exists() else ""
    assert "postgres-admin psql" in records, "Must distinguish existing from missing DB"
    assert "pg_restore " not in records, "A valid checksum must not authorize wiping an existing DB"
    assert "createdb " not in records


def test_restore_creates_only_missing_disposable_db(tmp_path: Path) -> None:
    vm, env, log = _fixture(tmp_path)
    dump = _dump(tmp_path)
    _sidecar(dump)
    env["FAKE_TARGET_DB_EXISTS"] = "0"
    result = _run(vm / "restore_postgres.sh", env, str(dump))
    assert result.returncode == 0, (result.stdout, result.stderr)
    records = log.read_text(encoding="utf-8")
    assert "postgres-admin psql" in records
    assert "postgres-admin createdb" in records
    assert "pg_restore " in records


def test_restore_fail_closed_when_disposable_db_exists_in_remote_mode(tmp_path: Path) -> None:
    vm, env, log = _fixture(tmp_path)
    dump = _dump(tmp_path)
    _sidecar(dump)
    env["DB_MODE"] = "remote_postgres"
    result = _run(vm / "restore_postgres.sh", env, str(dump))
    assert result.returncode != 0, (result.stdout, result.stderr)
    records = log.read_text(encoding="utf-8") if log.exists() else ""
    assert "pg_restore " not in records
