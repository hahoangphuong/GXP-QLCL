import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import textwrap


ROOT = Path(__file__).resolve().parents[1]


def test_vm_scripts_exist():
    expected = [
        ROOT / "infra" / "vm" / "common.sh",
        ROOT / "infra" / "vm" / "bootstrap_vm.sh",
        ROOT / "infra" / "vm" / "configure_postgres.sh",
        ROOT / "infra" / "vm" / "configure_tailscale.sh",
        ROOT / "infra" / "vm" / "deploy_prod.sh",
        ROOT / "infra" / "vm" / "backup_postgres.sh",
        ROOT / "infra" / "vm" / "restore_postgres.sh",
        ROOT / "infra" / "vm" / "verify_prod.sh",
        ROOT / "infra" / "vm" / "gxp-web.service",
        ROOT / "infra" / "vm" / "nginx.gxp.conf",
    ]
    for path in expected:
        assert path.exists(), path.as_posix()


def test_vm_deploy_script_enforces_clean_git_and_fast_forward_flow():
    text = (ROOT / "infra" / "vm" / "deploy_prod.sh").read_text(encoding="utf-8")

    assert 'git -C "${REPO_ROOT}" status --porcelain --untracked-files=no' in text
    assert 'git -C "${REPO_ROOT}" fetch origin' in text
    assert 'git -C "${REPO_ROOT}" checkout --detach "${TARGET_SHA}"' in text
    assert 'git -C "${REPO_ROOT}" rev-parse --verify "origin/${DEPLOY_BRANCH}^{commit}"' in text
    assert "git reset --hard" not in text
    assert 'SUCCESS=0' in text
    assert 'trap cleanup EXIT' in text


def test_vm_deploy_script_uses_vm_runtime_requirements_and_db_backup():
    text = (ROOT / "infra" / "vm" / "deploy_prod.sh").read_text(encoding="utf-8")

    assert "backend/requirements.runtime.vm.txt" in text
    assert '"${SCRIPT_DIR}/backup_postgres.sh"' in text
    assert '"${VM_VENV_DIR}/bin/alembic" -c "${REPO_ROOT}/alembic.ini" upgrade head' in text
    assert "render_vm_runtime_assets.py" in text
    assert "corepack prepare" in text
    assert "GXP_FRONTEND_DIST_ROOT" in text
    assert 'systemctl enable "${SYSTEMD_SERVICE_NAME}"' in text
    assert 'systemctl enable nginx' in text


def test_vm_backup_and_restore_scripts_use_pg_dump_and_pg_restore():
    backup = (ROOT / "infra" / "vm" / "backup_postgres.sh").read_text(encoding="utf-8")
    restore = (ROOT / "infra" / "vm" / "restore_postgres.sh").read_text(encoding="utf-8")

    assert "pg_dump \\" in backup
    assert "--format=custom" in backup
    assert "gcloud storage cp" in backup
    assert 'rm -f "${OUTPUT_FILE}" "${CHECKSUM_FILE}"' in backup
    assert "ALLOW_USER_GCLOUD_AUTH" in backup
    assert "pg_restore --clean --if-exists" in restore
    assert "CONFIRM_RESTORE" in restore
    assert "sha256sum -c" in restore


def test_vm_bootstrap_script_installs_node_gcloud_and_swap_defaults():
    text = (ROOT / "infra" / "vm" / "bootstrap_vm.sh").read_text(encoding="utf-8")

    assert "VM_NODE_MAJOR" in text
    assert "corepack enable" in text
    assert "google-cloud-cli" in text
    assert "/swapfile" in text
    assert "VM_SWAP_SIZE_GB" in text
    assert "VM_SWAPPINESS" in text


def test_vm_scripts_use_runtime_env_parser_not_shell_source():
    for path in [
        ROOT / "infra" / "vm" / "configure_postgres.sh",
        ROOT / "infra" / "vm" / "backup_postgres.sh",
        ROOT / "infra" / "vm" / "restore_postgres.sh",
        ROOT / "infra" / "vm" / "deploy_prod.sh",
        ROOT / "infra" / "vm" / "verify_prod.sh",
    ]:
        text = path.read_text(encoding="utf-8")
        assert "load_runtime_env" in text
        assert "source \"${RUNTIME_ENV_FILE}\"" not in text


def test_vm_runtime_example_declares_fresh_machine_controls():
    text = (ROOT / "backend" / ".env.vm.production.example").read_text(encoding="utf-8")

    for required in [
        "VM_APP_ROOT=/opt/gxp",
        "VM_SRC_DIR=/opt/gxp/src/GXP-QLCL",
        "VM_VENV_DIR=/opt/gxp/venv",
        "VM_FRONTEND_DIST_DIR=/opt/gxp/frontend-dist",
        "VM_FRONTEND_RELEASES_DIR=/opt/gxp/frontend-releases",
        "VM_RUNTIME_ENV_FILE=/etc/gxp/runtime.env",
        "SYSTEMD_SERVICE_NAME=gxp-web",
        "NGINX_SITE_NAME=gxp-web",
        "VM_SWAP_SIZE_GB=4",
        "VM_SWAPPINESS=10",
        "VM_NODE_MAJOR=22",
        "VM_NODE_MIN_VERSION=22.12.0",
        "VM_NODE_PACKAGE_MANAGER=pnpm@11.19.0",
        "PG_SHARED_BUFFERS_MB=256",
        "PG_MAX_CONNECTIONS=30",
    ]:
        assert required in text


def _git_bash_path() -> Path | None:
    git_exe = shutil.which("git")
    if not git_exe:
        return None
    candidate = Path(git_exe).resolve().parents[1] / "bin" / "bash.exe"
    return candidate if candidate.exists() else None


def _run_git_bash(script: str, *, env: dict[str, str], cwd: Path) -> subprocess.CompletedProcess[str]:
    bash_path = _git_bash_path()
    if bash_path is None:
        raise AssertionError("Git Bash is required for VM shell execution tests.")
    return subprocess.run(
        [str(bash_path), "-lc", script],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _base_env(fake_bin: Path, runtime_env: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    env["VM_RUNTIME_ENV_FILE"] = runtime_env.as_posix()
    return env


def test_backup_script_executes_and_cleans_up_local_artifacts(tmp_path: Path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    runtime_env = tmp_path / "runtime.env"
    remote_store = tmp_path / "remote"
    remote_store.mkdir()
    backup_dir = tmp_path / "backup"
    python_sh = sys.executable.replace("\\", "/")

    runtime_env.write_text(
        "\n".join(
            [
                "DB_NAME=gxp_qlcl",
                "DB_USER=gxp_app",
                "DB_PASSWORD='p@ss word'",
                "DB_HOST=127.0.0.1",
                "DB_PORT=5432",
                "BACKUP_GCS_BUCKET=gs://gxp-backups",
                f"BACKUP_LOCAL_STAGING_DIR='{backup_dir.as_posix()}'",
            ]
        ),
        encoding="utf-8",
    )
    (fake_bin / "install").write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "target=\"${@: -1}\"\n"
        "if [[ \"$1\" == \"-d\" ]]; then\n"
        "  mkdir -p \"$target\"\n"
        "  exit 0\n"
        "fi\n"
        "exec /usr/bin/install \"$@\"\n",
        encoding="utf-8",
    )
    (fake_bin / "python3").write_text(f"#!/usr/bin/env bash\n\"{python_sh}\" \"$@\"\n", encoding="utf-8")
    (fake_bin / "pg_dump").write_text(
        "#!/usr/bin/env bash\n"
        "for ((i=1; i<=$#; i++)); do\n"
        "  if [[ \"${!i}\" == \"--file\" ]]; then\n"
        "    j=$((i+1))\n"
        "    printf 'dump' > \"${!j}\"\n"
        "  fi\n"
        "done\n",
        encoding="utf-8",
    )
    (fake_bin / "curl").write_text(
        "#!/usr/bin/env bash\nprintf 'gxp-vm@gxp-qlcl.iam.gserviceaccount.com'\n",
        encoding="utf-8",
    )
    (fake_bin / "gcloud").write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            set -euo pipefail
            REMOTE_STORE="{remote_store.as_posix()}"
            if [[ "$1" == "auth" && "$2" == "list" ]]; then
              exit 0
            fi
            if [[ "$1" == "storage" && "$2" == "cp" ]]; then
              mkdir -p "$REMOTE_STORE"
              cp "$3" "$REMOTE_STORE/$(basename "$3")"
              cp "$4" "$REMOTE_STORE/$(basename "$4")"
              exit 0
            fi
            if [[ "$1" == "storage" && "$2" == "ls" ]]; then
              target="${{3##*/}}"
              [[ -f "$REMOTE_STORE/$target" ]]
              exit $?
            fi
            exit 1
            """
        ),
        encoding="utf-8",
    )
    for script_path in fake_bin.iterdir():
        script_path.chmod(0o755)

    env = _base_env(fake_bin, runtime_env)

    completed = _run_git_bash("./infra/vm/backup_postgres.sh", env=env, cwd=ROOT)

    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert not list(backup_dir.glob("*.dump"))
    assert any(remote_store.glob("*.dump"))


def test_restore_script_requires_nonproduction_target_and_checksum(tmp_path: Path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    runtime_env = tmp_path / "runtime.env"
    dump_file = tmp_path / "gxp.dump"
    dump_file.write_text("payload", encoding="utf-8")
    checksum = hashlib.sha256(dump_file.read_bytes()).hexdigest()
    (tmp_path / "gxp.dump.sha256").write_text(f"{checksum}  gxp.dump\n", encoding="utf-8")
    python_sh = sys.executable.replace("\\", "/")

    runtime_env.write_text(
        "\n".join(
            [
                "DB_NAME=gxp_qlcl",
                "DB_USER=gxp_app",
                "DB_PASSWORD=secret",
                "DB_HOST=127.0.0.1",
                "DB_PORT=5432",
            ]
        ),
        encoding="utf-8",
    )
    (fake_bin / "python3").write_text(f"#!/usr/bin/env bash\n\"{python_sh}\" \"$@\"\n", encoding="utf-8")
    (fake_bin / "psql").write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    (fake_bin / "createdb").write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    (fake_bin / "pg_restore").write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    for script_path in fake_bin.iterdir():
        script_path.chmod(0o755)

    env = _base_env(fake_bin, runtime_env)

    completed = _run_git_bash(
        f"TARGET_DB=gxp_qlcl CONFIRM_RESTORE=RESTORE_gxp_qlcl ./infra/vm/restore_postgres.sh '{dump_file.as_posix()}'",
        env=env,
        cwd=ROOT,
    )

    assert completed.returncode != 0
    assert "must not default to the production database name" in (completed.stderr or completed.stdout)
