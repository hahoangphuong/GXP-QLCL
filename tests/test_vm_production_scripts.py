import hashlib
import json
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


def test_vm_shell_scripts_are_tracked_as_executable_in_git():
    expected_modes = {
        "infra/vm/bootstrap_vm.sh": "100755",
        "infra/vm/configure_postgres.sh": "100755",
        "infra/vm/configure_tailscale.sh": "100755",
        "infra/vm/deploy_prod.sh": "100755",
        "infra/vm/backup_postgres.sh": "100755",
        "infra/vm/restore_postgres.sh": "100755",
        "infra/vm/verify_prod.sh": "100755",
        "infra/vm/common.sh": "100644",
    }
    completed = subprocess.run(
        ["git", "ls-files", "--stage", "infra/vm"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    modes_by_path: dict[str, str] = {}
    for line in completed.stdout.splitlines():
        mode, _blob, _stage, path = line.split(maxsplit=3)
        modes_by_path[path] = mode

    for path, expected_mode in expected_modes.items():
        assert modes_by_path.get(path) == expected_mode, f"{path}: expected {expected_mode}, got {modes_by_path.get(path)}"


def test_vm_deploy_script_enforces_clean_git_and_fast_forward_flow():
    text = (ROOT / "infra" / "vm" / "deploy_prod.sh").read_text(encoding="utf-8")

    assert 'git -C "${REPO_ROOT}" status --porcelain' in text
    assert '--untracked-files=no' not in text
    assert 'git -C "${REPO_ROOT}" fetch origin' in text
    assert 'git -C "${REPO_ROOT}" rev-parse --verify "origin/${DEPLOY_BRANCH}^{commit}"' in text
    assert "git archive --format=tar" in text
    assert "git reset --hard" not in text
    assert 'SUCCESS=0' in text
    assert 'trap cleanup EXIT' in text
    assert 'SWITCHED_RELEASES=0' in text


def test_vm_deploy_script_preserves_pre_switch_atomicity_and_post_switch_rollback_contract():
    text = (ROOT / "infra" / "vm" / "deploy_prod.sh").read_text(encoding="utf-8")

    assert text.index('CURRENT_STAGE="render_runtime_assets"') < text.index('CURRENT_STAGE="database_backup"')
    assert text.index('CURRENT_STAGE="database_backup"') < text.index('CURRENT_STAGE="alembic_upgrade"')
    assert text.index('CURRENT_STAGE="alembic_upgrade"') < text.index('CURRENT_STAGE="switch_release_symlinks"')
    assert text.index('CURRENT_STAGE="switch_release_symlinks"') < text.index('CURRENT_STAGE="restart_services"')
    assert text.index('CURRENT_STAGE="restart_services"') < text.index('CURRENT_STAGE="post_switch_health"')
    assert text.index('CURRENT_STAGE="post_switch_health"') < text.index('CURRENT_STAGE="write_release_metadata"')
    assert text.index('CURRENT_STAGE="write_release_metadata"') < text.index('CURRENT_STAGE="retention"')
    assert 'cp "${STAGED_SERVICE_FILE}" "/etc/systemd/system/${SYSTEMD_SERVICE_NAME}.service"' in text
    assert 'cp "${STAGED_NGINX_FILE}" "/etc/nginx/sites-available/${NGINX_SITE_NAME}.conf"' in text
    assert 'if [[ "${SUCCESS}" != "1" && "${SWITCHED_CONFIG}" == "1" ]]; then' in text
    assert 'if [[ -s "${PREVIOUS_SERVICE_FILE}" ]]; then' in text
    assert 'if [[ -s "${PREVIOUS_NGINX_FILE}" ]]; then' in text
    assert 'if [[ "${SUCCESS}" != "1" && "${SWITCHED_RELEASES}" == "1" ]]; then' in text
    assert 'ln -sfn "${ORIGINAL_BACKEND_RELEASE_TARGET}" "${VM_CURRENT_BACKEND_RELEASE_LINK}"' in text
    assert 'ln -sfn "${ORIGINAL_BACKEND_VENV_TARGET}" "${VM_CURRENT_BACKEND_VENV_LINK}"' in text
    assert 'ln -sfn "${ORIGINAL_FRONTEND_TARGET}" "${VM_FRONTEND_DIST_DIR}"' in text
    assert 'alembic downgrade' not in text


def test_vm_deploy_script_writes_release_metadata_only_after_health_passes():
    text = (ROOT / "infra" / "vm" / "deploy_prod.sh").read_text(encoding="utf-8")

    metadata_section = text[text.index('CURRENT_STAGE="write_release_metadata"') :]
    assert 'curl -fsS "http://127.0.0.1:${APP_PORT}/healthz"' in text
    assert 'curl -fsS "http://127.0.0.1:${APP_PORT}/readyz"' in text
    assert 'CURRENT_STAGE="post_switch_health"' in text
    assert 'CURRENT_STAGE="write_release_metadata"' in text
    assert 'mv "${VM_RELEASE_METADATA_FILE}.tmp" "${VM_RELEASE_METADATA_FILE}"' in metadata_section


def test_vm_deploy_script_uses_vm_runtime_requirements_and_db_backup():
    text = (ROOT / "infra" / "vm" / "deploy_prod.sh").read_text(encoding="utf-8")

    assert 'RUNTIME_REQUIREMENTS_LOCK_FILE="$(json_query runtime_requirements_lock_file)"' in text
    assert 'install --no-cache-dir -r "${NEW_BACKEND_RELEASE}/${RUNTIME_REQUIREMENTS_LOCK_FILE}"' in text
    assert 'run_as_app_user "${NEW_BACKEND_RELEASE}/infra/vm/backup_postgres.sh"' in text
    assert 'run_as_app_user env DATABASE_URL="${DATABASE_URL}" "${NEW_BACKEND_VENV}/bin/alembic"' in text
    assert "render_vm_runtime_assets.py" in text
    assert 'pnpm install --frozen-lockfile' in text
    assert "GXP_FRONTEND_DIST_ROOT" in text
    assert 'systemctl enable "${SYSTEMD_SERVICE_NAME}"' in text
    assert 'systemctl enable nginx' in text
    assert 'VM_CURRENT_BACKEND_RELEASE_LINK' in text
    assert 'VM_CURRENT_BACKEND_VENV_LINK' in text


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

    assert 'python${PYTHON_SERIES}' in text
    assert "VM_PYTHON_SERIES" in text
    assert "VM_PYTHON_BIN" in text
    assert "VM_NODE_MAJOR" in text
    assert "corepack enable" in text
    assert 'corepack prepare "${NODE_PACKAGE_MANAGER}" --activate' in text
    assert "google-cloud-cli" in text
    assert "VM_SWAP_SIZE_GB" in text
    assert "VM_SWAPPINESS" in text
    assert "coreutils" in text
    assert "mount" in text
    assert "procps" in text
    assert "util-linux" in text


def test_vm_bootstrap_script_uses_explicit_postgres_major_and_guards_cloud_shell():
    text = (ROOT / "infra" / "vm" / "bootstrap_vm.sh").read_text(encoding="utf-8")

    assert 'POSTGRES_MAJOR="${VM_POSTGRES_MAJOR:-18}"' in text
    assert 'POSTGRES_CLUSTER_NAME="${VM_POSTGRES_CLUSTER_NAME:-main}"' in text
    assert '"postgresql-${POSTGRES_MAJOR}"' in text
    assert '"postgresql-client-${POSTGRES_MAJOR}"' in text
    assert "DEVSHELL_PROJECT_ID" in text
    assert "CLOUD_SHELL" in text
    assert "bootstrap_vm.sh must run on the target Compute Engine VM, not Cloud Shell." in text
    assert "VM_EXPECTED_PROJECT_ID" in text
    assert "VM_EXPECTED_INSTANCE_NAME" in text
    assert "VM_EXPECTED_ZONE" in text
    assert "Could not verify Compute Engine metadata for the expected VM identity." in text


def test_vm_bootstrap_script_orders_minimal_prereqs_swap_and_explicit_postgres_flow():
    text = (ROOT / "infra" / "vm" / "bootstrap_vm.sh").read_text(encoding="utf-8")

    assert text.rindex("ensure_supported_python_packages") < text.rindex("validate_python_baseline")
    assert text.rindex("validate_python_baseline") < text.rindex("install_minimal_bootstrap_prerequisites")
    assert text.rindex("install_minimal_bootstrap_prerequisites") < text.rindex("configure_swap")
    assert text.rindex("configure_swap") < text.rindex("ensure_pgdg_repository")
    assert text.rindex("ensure_pgdg_repository") < text.rindex("install_postgresql_packages")
    assert text.rindex("install_postgresql_packages") < text.rindex("install_nodejs")
    assert text.rindex("install_nodejs") < text.rindex("install_gcloud")
    assert "apt-get install -y --no-install-recommends \"${BOOTSTRAP_MINIMAL_APT_PACKAGES[@]}\"" in text
    assert "need_cmd swapon" in text
    assert "need_cmd mkswap" in text
    assert "need_cmd sysctl" in text
    assert "need_cmd free" in text
    assert "need_cmd stat" in text
    assert "need_cmd fallocate" in text
    assert 'apt-cache show "postgresql-${POSTGRES_MAJOR}"' in text
    assert 'pg_createcluster "${POSTGRES_MAJOR}" "${POSTGRES_CLUSTER_NAME}"' in text


def test_configure_postgres_uses_explicit_cluster_contract():
    text = (ROOT / "infra" / "vm" / "configure_postgres.sh").read_text(encoding="utf-8")

    assert 'POSTGRES_MAJOR="${VM_POSTGRES_MAJOR:-18}"' in text
    assert 'POSTGRES_CLUSTER_NAME="${VM_POSTGRES_CLUSTER_NAME:-main}"' in text
    assert 'pg_lsclusters --no-header' in text
    assert 'PG_CLUSTER_DIR="${VM_POSTGRES_CLUSTER_DIR:-/etc/postgresql/${POSTGRES_MAJOR}/${POSTGRES_CLUSTER_NAME}}"' in text
    assert 'pg_ctlcluster "${POSTGRES_MAJOR}" "${POSTGRES_CLUSTER_NAME}" restart' in text
    assert "find /etc/postgresql" not in text


def test_configure_and_restore_postgres_avoid_literal_psql_variable_regressions():
    configure = (ROOT / "infra" / "vm" / "configure_postgres.sh").read_text(encoding="utf-8")
    restore = (ROOT / "infra" / "vm" / "restore_postgres.sh").read_text(encoding="utf-8")

    assert "DO $$" not in configure
    assert """-Atqc "SELECT 1 FROM pg_database WHERE datname = :'db_name'""" not in configure
    assert """-Atqc "SELECT 1 FROM pg_database WHERE datname = :'target_db'""" not in restore
    assert configure.count("-v ON_ERROR_STOP=1") >= 4
    assert restore.count("-v ON_ERROR_STOP=1") >= 4
    assert "SELECT format(" in configure
    assert "\\gexec" in configure
    assert """SELECT 1 FROM pg_database WHERE datname = :'db_name';""" in configure
    assert """SELECT 1 FROM pg_database WHERE datname = :'target_db';""" in restore


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
        "VM_PYTHON_SERIES=3.12",
        "VM_PYTHON_BIN=/usr/bin/python3.12",
        "VM_SRC_DIR=/opt/gxp/src/GXP-QLCL",
        "VM_BACKEND_RELEASES_DIR=/opt/gxp/backend-releases",
        "VM_BACKEND_VENV_RELEASES_DIR=/opt/gxp/backend-venvs",
        "VM_CURRENT_BACKEND_RELEASE_LINK=/opt/gxp/current-backend",
        "VM_CURRENT_BACKEND_VENV_LINK=/opt/gxp/current-venv",
        "VM_FRONTEND_DIST_DIR=/opt/gxp/frontend-dist",
        "VM_FRONTEND_RELEASES_DIR=/opt/gxp/frontend-releases",
        "VM_RUNTIME_ENV_FILE=/etc/gxp/runtime.env",
        "VM_RELEASE_RETENTION_COUNT=3",
        "SYSTEMD_SERVICE_NAME=gxp-web",
        "NGINX_SITE_NAME=gxp-web",
        "VM_TLS_PROVISIONING_MODE=existing_files",
        "VM_SWAP_SIZE_GB=4",
        "VM_SWAPPINESS=10",
        "VM_NODE_MAJOR=22",
        "VM_NODE_MIN_VERSION=22.12.0",
        "VM_COREPACK_VERSION=0.31.0",
        "VM_NODE_PACKAGE_MANAGER=pnpm@11.19.0",
        "VM_POSTGRES_MAJOR=18",
        "VM_POSTGRES_CLUSTER_NAME=main",
        "VM_SUPPORTED_POSTGRES_MAJORS=17,18",
        "VM_EXPECTED_PROJECT_ID=",
        "VM_EXPECTED_INSTANCE_NAME=",
        "VM_EXPECTED_ZONE=",
        "PG_SHARED_BUFFERS_MB=256",
        "PG_MAX_CONNECTIONS=30",
    ]:
        assert required in text
    assert "__SET_IN_0640_RUNTIME_ENV_FILE__" in text


def _bash_path() -> Path | None:
    if os.name != "nt":
        bash_path = shutil.which("bash")
        return Path(bash_path) if bash_path else None
    git_exe = shutil.which("git")
    if not git_exe:
        return None
    candidate = Path(git_exe).resolve().parents[1] / "bin" / "bash.exe"
    return candidate if candidate.exists() else None


def _run_bash(script: str, *, env: dict[str, str], cwd: Path) -> subprocess.CompletedProcess[str]:
    bash_path = _bash_path()
    if bash_path is None:
        raise AssertionError("A bash executable is required for VM shell execution tests.")
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


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8", newline="\n")
    path.chmod(0o755)


def _write_runtime_env(
    path: Path,
    *,
    db_name: str = "gxp_qlcl",
    db_user: str = "gxp_app",
    db_password: str = "secret",
    db_host: str = "127.0.0.1",
    db_port: str = "5432",
) -> None:
    path.write_text(
        "\n".join(
            [
                "DB_MODE=local_postgres",
                f"DB_NAME={db_name!r}",
                f"DB_USER={db_user!r}",
                f"DB_PASSWORD={db_password!r}",
                f"DB_HOST={db_host!r}",
                f"DB_PORT={db_port!r}",
            ]
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _bootstrap_test_env(fake_bin: Path, runtime_env: Path, tmp_path: Path) -> dict[str, str]:
    env = _base_env(fake_bin, runtime_env)
    python_series = f"{sys.version_info[0]}.{sys.version_info[1]}"
    env["BOOTSTRAP_UNSAFE_SKIP_ROOT_CHECK"] = "1"
    env["VM_PYTHON_BIN"] = (fake_bin / "python3").as_posix()
    env["VM_PYTHON_SERIES"] = python_series
    env["VM_METADATA_BASE_URL"] = "http://127.0.0.1:9/computeMetadata/v1"
    env["VM_OS_RELEASE_FILE"] = (tmp_path / "os-release").as_posix()
    env["VM_APT_KEYRINGS_DIR"] = (tmp_path / "apt-keyrings").as_posix()
    env["VM_APT_SOURCES_DIR"] = (tmp_path / "apt-sources").as_posix()
    env["VM_SYSCTL_DIR"] = (tmp_path / "sysctl").as_posix()
    env["VM_SYSCTL_FILE"] = (tmp_path / "sysctl" / "60-gxp-vm.conf").as_posix()
    env["VM_FSTAB_FILE"] = (tmp_path / "fstab").as_posix()
    env["VM_SWAPFILE_PATH"] = (tmp_path / "swapfile").as_posix()
    env["VM_APP_ROOT"] = (tmp_path / "app-root").as_posix()
    env["VM_SRC_DIR"] = (tmp_path / "app-root" / "src" / "GXP-QLCL").as_posix()
    env["VM_BACKEND_RELEASES_DIR"] = (tmp_path / "app-root" / "backend-releases").as_posix()
    env["VM_BACKEND_VENV_RELEASES_DIR"] = (tmp_path / "app-root" / "backend-venvs").as_posix()
    env["VM_CURRENT_BACKEND_RELEASE_LINK"] = (tmp_path / "app-root" / "current-backend").as_posix()
    env["VM_CURRENT_BACKEND_VENV_LINK"] = (tmp_path / "app-root" / "current-venv").as_posix()
    env["VM_FRONTEND_DIST_DIR"] = (tmp_path / "app-root" / "frontend-dist").as_posix()
    env["VM_FRONTEND_RELEASES_DIR"] = (tmp_path / "app-root" / "frontend-releases").as_posix()
    env["BACKUP_LOCAL_STAGING_DIR"] = (tmp_path / "backups").as_posix()
    env["VM_APP_GROUP"] = "root"
    env["GXP_USER"] = "root"
    return env


def _configure_postgres_test_env(fake_bin: Path, runtime_env: Path, tmp_path: Path) -> dict[str, str]:
    env = _base_env(fake_bin, runtime_env)
    env["CONFIGURE_POSTGRES_UNSAFE_SKIP_ROOT_CHECK"] = "1"
    env["VM_POSTGRES_MAJOR"] = "18"
    env["VM_POSTGRES_CLUSTER_NAME"] = "main"
    env["VM_SUPPORTED_POSTGRES_MAJORS"] = "17,18"
    env["VM_POSTGRES_CLUSTER_DIR"] = (tmp_path / "pg" / "18" / "main").as_posix()
    return env


def test_bootstrap_script_aborts_in_cloud_shell_before_mutation(tmp_path: Path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    runtime_env = tmp_path / "runtime.env"
    runtime_env.write_text("", encoding="utf-8")
    command_log = tmp_path / "command.log"
    python_sh = sys.executable.replace("\\", "/")
    (tmp_path / "os-release").write_text("ID=ubuntu\nVERSION_CODENAME=noble\n", encoding="utf-8", newline="\n")

    _write_executable(fake_bin / "python3", f"#!/usr/bin/env bash\n\"{python_sh}\" \"$@\"\n")
    for name in ["apt-get", "apt-cache", "install", "groupadd", "useradd", "ln", "chown"]:
        _write_executable(
            fake_bin / name,
            textwrap.dedent(
                f"""\
                #!/usr/bin/env bash
                set -euo pipefail
                printf '%s %s\\n' "{name}" "$*" >> "{command_log.as_posix()}"
                exit 0
                """
            ),
        )

    env = _bootstrap_test_env(fake_bin, runtime_env, tmp_path)
    env["DEVSHELL_PROJECT_ID"] = "gxp-qlcl-vm"

    completed = _run_bash("./infra/vm/bootstrap_vm.sh", env=env, cwd=ROOT)

    assert completed.returncode != 0
    assert "must run on the target Compute Engine VM, not Cloud Shell" in (completed.stderr or completed.stdout)
    assert not command_log.exists() or command_log.read_text(encoding="utf-8") == ""
    assert not (tmp_path / "swapfile").exists()
    assert not (tmp_path / "app-root").exists()


def test_bootstrap_script_orders_minimal_prereqs_before_repo_setup_on_fresh_host(tmp_path: Path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    runtime_env = tmp_path / "runtime.env"
    runtime_env.write_text("", encoding="utf-8")
    python_sh = sys.executable.replace("\\", "/")
    command_log = tmp_path / "command.log"
    cluster_state = tmp_path / "cluster.state"
    node_installed = tmp_path / "node.installed"
    pnpm_ready = tmp_path / "pnpm.ready"
    pgdg_repo_attempts = tmp_path / "pgdg.repo.attempts"
    python_series = f"{sys.version_info[0]}.{sys.version_info[1]}"
    (tmp_path / "os-release").write_text("ID=ubuntu\nVERSION_CODENAME=noble\n", encoding="utf-8", newline="\n")
    (tmp_path / "fstab").write_text("", encoding="utf-8", newline="\n")

    _write_executable(fake_bin / "python3", f"#!/usr/bin/env bash\n\"{python_sh}\" \"$@\"\n")
    _write_executable(fake_bin / "curl", "#!/usr/bin/env bash\nset -euo pipefail\nprintf 'dummy-key'\n")
    _write_executable(
        fake_bin / "gpg",
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "output=\"\"\n"
        "while [[ $# -gt 0 ]]; do\n"
        "  case \"$1\" in\n"
        "    -o)\n"
        "      shift\n"
        "      output=\"$1\"\n"
        "      ;;\n"
        "  esac\n"
        "  shift || true\n"
        "done\n"
        "mkdir -p \"$(dirname \"$output\")\"\n"
        "printf 'gpg' > \"$output\"\n",
    )
    _write_executable(
        fake_bin / "pg_lsclusters",
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            set -euo pipefail
            [[ -f "{cluster_state.as_posix()}" ]] && cat "{cluster_state.as_posix()}"
            """
        ),
    )
    _write_executable(
        fake_bin / "pg_createcluster",
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            set -euo pipefail
            printf '%s %s 5432 online postgres /var/lib/postgresql/%s/%s /var/log/postgresql/postgresql-%s-%s.log\n' "$1" "$2" "$1" "$2" "$1" "$2" > "{cluster_state.as_posix()}"
            """
        ),
    )
    _write_executable(
        fake_bin / "node",
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            set -euo pipefail
            version='0.0.0'
            [[ -f "{node_installed.as_posix()}" ]] && version='22.12.0'
            if [[ "$1" == "-p" && "$2" == "process.versions.node" ]]; then
              printf '%s\n' "$version"
              exit 0
            fi
            exit 1
            """
        ),
    )
    _write_executable(fake_bin / "npm", "#!/usr/bin/env bash\nset -euo pipefail\nexit 0\n")
    _write_executable(
        fake_bin / "corepack",
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            set -euo pipefail
            if [[ "${{1:-}}" == "prepare" ]]; then
              printf '1' > "{pnpm_ready.as_posix()}"
            fi
            exit 0
            """
        ),
    )
    _write_executable(
        fake_bin / "pnpm",
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            set -euo pipefail
            [[ -f "{pnpm_ready.as_posix()}" ]] || exit 1
            if [[ "${{1:-}}" == "--version" ]]; then
              printf '11.19.0\n'
              exit 0
            fi
            exit 0
            """
        ),
    )
    _write_executable(fake_bin / "gcloud", "#!/usr/bin/env bash\nset -euo pipefail\nexit 0\n")
    _write_executable(
        fake_bin / "apt-get",
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            set -euo pipefail
            printf 'apt-get %s\\n' "$*" >> "{command_log.as_posix()}"
            if [[ "$1" == "update" ]]; then
              exit 0
            fi
            if [[ "$1" != "install" ]]; then
              exit 0
            fi
            for arg in "$@"; do
              case "$arg" in
                mount)
                  cat > "{(fake_bin / 'swapon').as_posix()}" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf 'swapon %s\n' "$*" >> "__COMMAND_LOG__"
if [[ "${1:-}" == "--show=NAME" || "${1:-}" == "--show" ]]; then
  [[ -f "__SWAP_ACTIVE__" ]] && cat "__SWAP_ACTIVE__"
  exit 0
fi
printf '%s\n' "$1" > "__SWAP_ACTIVE__"
exit 0
EOF
                  sed -i "s|__COMMAND_LOG__|{command_log.as_posix()}|g; s|__SWAP_ACTIVE__|{(tmp_path / 'swap.active').as_posix()}|g" "{(fake_bin / 'swapon').as_posix()}"
                  chmod +x "{(fake_bin / 'swapon').as_posix()}"
                  ;;
                util-linux)
                  cat > "{(fake_bin / 'mkswap').as_posix()}" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf 'mkswap %s\n' "$*" >> "__COMMAND_LOG__"
exit 0
EOF
                  cat > "{(fake_bin / 'fallocate').as_posix()}" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
: > "${{@: -1}}"
EOF
                  sed -i "s|__COMMAND_LOG__|{command_log.as_posix()}|g" "{(fake_bin / 'mkswap').as_posix()}"
                  chmod +x "{(fake_bin / 'mkswap').as_posix()}" "{(fake_bin / 'fallocate').as_posix()}"
                  ;;
                procps)
                  cat > "{(fake_bin / 'sysctl').as_posix()}" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf 'sysctl %s\n' "$*" >> "__COMMAND_LOG__"
exit 0
EOF
                  cat > "{(fake_bin / 'free').as_posix()}" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf 'Mem: 2G 1G 1G\n'
EOF
                  sed -i "s|__COMMAND_LOG__|{command_log.as_posix()}|g" "{(fake_bin / 'sysctl').as_posix()}"
                  chmod +x "{(fake_bin / 'sysctl').as_posix()}" "{(fake_bin / 'free').as_posix()}"
                  ;;
                coreutils)
                  cat > "{(fake_bin / 'stat').as_posix()}" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "-c" && "${2:-}" == "%s" ]]; then
  wc -c < "$3" | tr -d '[:space:]'
  printf '\n'
  exit 0
fi
exit 1
EOF
                  chmod +x "{(fake_bin / 'stat').as_posix()}"
                  ;;
                postgresql-18)
                  ;;
                nodejs)
                  printf '1' > "{node_installed.as_posix()}"
                  ;;
              esac
            done
            exit 0
            """
        ),
    )
    _write_executable(
        fake_bin / "apt-cache",
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            set -euo pipefail
            printf 'apt-cache %s\\n' "$*" >> "{command_log.as_posix()}"
            package="${{2:-}}"
            case "$package" in
              python3.12|python3.12-venv)
                exit 0
                ;;
              postgresql-18)
                attempts=0
                [[ -f "{pgdg_repo_attempts.as_posix()}" ]] && attempts="$(cat "{pgdg_repo_attempts.as_posix()}")"
                attempts=$((attempts + 1))
                printf '%s\n' "$attempts" > "{pgdg_repo_attempts.as_posix()}"
                [[ "$attempts" -ge 2 ]]
                exit $?
                ;;
              python{python_series}|python{python_series}-venv)
                exit 0
                ;;
              *)
                exit 1
                ;;
            esac
            """
        ),
    )
    _write_executable(
        fake_bin / "install",
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            set -euo pipefail
            printf 'install %s\\n' "$*" >> "{command_log.as_posix()}"
            if [[ "$1" == "-d" ]]; then
              skip_next=0
              for arg in "$@"; do
                if [[ "$skip_next" == "1" ]]; then
                  skip_next=0
                  continue
                fi
                case "$arg" in
                  -d)
                    ;;
                  -m|-o|-g)
                    skip_next=1
                    ;;
                  *)
                    mkdir -p "$arg"
                    ;;
                esac
              done
              exit 0
            fi
            exit 0
            """
        ),
    )
    for name, body in {
        "dd": "#!/usr/bin/env bash\nset -euo pipefail\nexit 0\n",
        "chmod": "#!/usr/bin/env bash\nset -euo pipefail\nexit 0\n",
        "getent": "#!/usr/bin/env bash\nset -euo pipefail\nexit 2\n",
        "groupadd": "#!/usr/bin/env bash\nset -euo pipefail\nexit 0\n",
        "useradd": "#!/usr/bin/env bash\nset -euo pipefail\nexit 0\n",
        "id": "#!/usr/bin/env bash\nset -euo pipefail\n[[ \"$1\" == \"-u\" ]] && exit 1\nexit 0\n",
        "chown": "#!/usr/bin/env bash\nset -euo pipefail\nexit 0\n",
        "ln": textwrap.dedent(
            """\
            #!/usr/bin/env bash
            set -euo pipefail
            target="${@: -2:1}"
            link="${@: -1}"
            mkdir -p "$(dirname "$link")"
            printf '%s\n' "$target" > "$link"
            exit 0
            """
        ),
    }.items():
        _write_executable(fake_bin / name, body)

    env = _bootstrap_test_env(fake_bin, runtime_env, tmp_path)
    env["INSTALL_GCLOUD"] = "0"

    completed = _run_bash("./infra/vm/bootstrap_vm.sh", env=env, cwd=ROOT)

    assert completed.returncode == 0, completed.stderr or completed.stdout
    log_text = command_log.read_text(encoding="utf-8")
    assert "apt-get update" in log_text
    assert "apt-get install -y --no-install-recommends ca-certificates coreutils curl gnupg mount procps util-linux" in log_text
    assert "apt-cache show postgresql-18" in log_text
    expected_install = f"apt-get install -y --no-install-recommends git nginx python{python_series} python{python_series}-venv python3-pip rsync sudo postgresql-18 postgresql-client-18"
    assert expected_install in log_text
    assert log_text.index("apt-get install -y --no-install-recommends ca-certificates coreutils curl gnupg mount procps util-linux") < log_text.index(expected_install)
    assert log_text.index("swapon ") < log_text.index(expected_install)
    assert (tmp_path / "swap.active").read_text(encoding="utf-8").strip() == (tmp_path / "swapfile").as_posix()
    assert "18 main" in cluster_state.read_text(encoding="utf-8")


def test_configure_postgres_is_idempotent_uses_safe_psql_and_keeps_password_secret(tmp_path: Path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    runtime_env = tmp_path / "runtime.env"
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    state_file = state_dir / "postgres-state.json"
    command_log = tmp_path / "command.log"
    python_sh = sys.executable.replace("\\", "/")
    pg_cluster_dir = tmp_path / "pg" / "18" / "main"
    (pg_cluster_dir / "conf.d").mkdir(parents=True)
    (pg_cluster_dir / "pg_hba.conf").write_text("", encoding="utf-8", newline="\n")
    special_password = " weird ' \" $HOME \\\\ ; : spaces "
    rotated_password = "rotated ' \" $PATH \\\\ ; : pass"
    db_name = "gxp_qlcl"
    db_user = "gxp_app"

    _write_runtime_env(runtime_env, db_name=db_name, db_user=db_user, db_password=special_password)
    _write_executable(fake_bin / "python3", f"#!/usr/bin/env bash\n\"{python_sh}\" \"$@\"\n")
    _write_executable(
        fake_bin / "runuser",
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            set -euo pipefail
            [[ "$1" == "-u" ]] || exit 2
            shift 2
            [[ "$1" == "--" ]] || exit 2
            shift
            exec "$@"
            """
        ),
    )
    _write_executable(
        fake_bin / "pg_lsclusters",
        "#!/usr/bin/env bash\nset -euo pipefail\nprintf '18 main 5432 online postgres /var/lib/postgresql/18/main /var/log/postgresql/postgresql-18-main.log\\n'\n",
    )
    _write_executable(
        fake_bin / "pg_ctlcluster",
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            set -euo pipefail
            printf 'pg_ctlcluster %s\\n' "$*" >> "{command_log.as_posix()}"
            exit 0
            """
        ),
    )
    _write_executable(
        fake_bin / "pg_isready",
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            set -euo pipefail
            printf 'pg_isready %s\\n' "$*" >> "{command_log.as_posix()}"
            exit 0
            """
        ),
    )
    _write_executable(
        fake_bin / "createdb",
        textwrap.dedent(
            f"""\
            #!/usr/bin/env python3
            import json
            import sys
            from pathlib import Path

            state_path = Path(r"{state_file.as_posix()}")
            log_path = Path(r"{command_log.as_posix()}")
            state = {{"roles": {{}}, "databases": {{}}, "createdb_calls": 0}}
            if state_path.exists():
                state.update(json.loads(state_path.read_text(encoding="utf-8")))
            args = sys.argv[1:]
            owner = None
            db_name = None
            i = 0
            while i < len(args):
                if args[i] == "--owner":
                    owner = args[i + 1]
                    i += 2
                    continue
                db_name = args[i]
                i += 1
            if owner not in state["roles"]:
                sys.stderr.write(f'createdb:\nERROR: role "{{owner}}" does not exist\n')
                raise SystemExit(1)
            if db_name is None:
                raise SystemExit(2)
            state["createdb_calls"] = int(state.get("createdb_calls", 0)) + 1
            state["databases"][db_name] = {{"owner": owner}}
            state_path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
            with log_path.open("a", encoding="utf-8") as fh:
                fh.write(f'createdb {{owner}} {{db_name}}\\n')
            """
        ),
    )
    _write_executable(
        fake_bin / "psql",
        textwrap.dedent(
            f"""\
            #!/usr/bin/env python3
            import json
            import os
            import sys
            from pathlib import Path

            state_path = Path(r"{state_file.as_posix()}")
            log_path = Path(r"{command_log.as_posix()}")

            def load_state() -> dict:
                if state_path.exists():
                    return json.loads(state_path.read_text(encoding="utf-8"))
                return {{"roles": {{}}, "databases": {{}}, "createdb_calls": 0}}

            def save_state(state: dict) -> None:
                state_path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")

            def arg_value(args: list[str], option: str) -> str | None:
                for index, arg in enumerate(args):
                    if arg == option and index + 1 < len(args):
                        return args[index + 1]
                    prefix = option + "="
                    if arg.startswith(prefix):
                        return arg[len(prefix):]
                return None

            def set_values(args: list[str]) -> dict[str, str]:
                values: dict[str, str] = {{}}
                for index, arg in enumerate(args):
                    if arg == "--set" and index + 1 < len(args):
                        key, _, value = args[index + 1].partition("=")
                        values[key] = value
                    elif arg.startswith("--set="):
                        key, _, value = arg[len("--set="):].partition("=")
                        values[key] = value
                return values

            args = sys.argv[1:]
            stdin_sql = sys.stdin.read()
            command_sql = ""
            if "-Atqc" in args:
                command_sql = args[args.index("-Atqc") + 1]
            elif "-tc" in args:
                command_sql = args[args.index("-tc") + 1]
            elif "-c" in args:
                command_sql = args[args.index("-c") + 1]
            sets = set_values(args)
            on_error_stop = False
            for index, arg in enumerate(args):
                if arg == "-v" and index + 1 < len(args) and args[index + 1] == "ON_ERROR_STOP=1":
                    on_error_stop = True
            with log_path.open("a", encoding="utf-8") as fh:
                fh.write(f'psql args={{args!r}} stdin={{stdin_sql!r}} sql={{command_sql!r}}\\n')
            if not on_error_stop:
                sys.stderr.write("missing ON_ERROR_STOP\\n")
                raise SystemExit(1)
                if "DO $$" in stdin_sql and (":'db_user'" in stdin_sql or ":'db_password'" in stdin_sql):
                    sys.stderr.write('ERROR: syntax error at or near ":"\\n')
                    sys.stderr.write("LINE 3:\\n")
                    sys.stderr.write("IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'db_user')\\n")
                    raise SystemExit(1)
                if ":'db_name'" in command_sql or ":'target_db'" in command_sql:
                    sys.stderr.write('ERROR: syntax error at or near ":"\\n')
                    sys.stderr.write("LINE 1:\\n")
                    sys.stderr.write("SELECT 1 FROM pg_database WHERE datname = :'db_name'\\n")
                    raise SystemExit(1)
            state = load_state()
            if os.environ.get("PSQL_FORCE_ROLE_SQL_ERROR") == "1" and "CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD %L" in stdin_sql:
                sys.stderr.write("ERROR: synthetic role setup failure\\n")
                raise SystemExit(1)
            if "CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD %L" in stdin_sql:
                db_user = sets["db_user"]
                db_password = sets["db_password"]
                state["roles"].setdefault(db_user, {{}})
                state["roles"][db_user].update(
                    {{
                        "password": db_password,
                        "login": True,
                        "superuser": False,
                        "createdb": False,
                        "createrole": False,
                    }}
                )
                save_state(state)
                raise SystemExit(0)
            if "SELECT 1 FROM pg_database WHERE datname = :'db_name';" in stdin_sql:
                if sets.get("db_name") in state["databases"]:
                    sys.stdout.write("1\\n")
                raise SystemExit(0)
            if "SELECT 1 FROM pg_database WHERE datname = :'target_db';" in stdin_sql:
                if sets.get("target_db") in state["databases"]:
                    sys.stdout.write("1\\n")
                raise SystemExit(0)
            if command_sql == "SHOW server_version_num":
                sys.stdout.write("180005\\n")
                raise SystemExit(0)
            if "SELECT current_database() || E'\\\\t' || current_user" in command_sql:
                db_name = arg_value(args, "--dbname")
                db_user = arg_value(args, "--username")
                db_host = arg_value(args, "--host")
                db_port = arg_value(args, "--port")
                role = state["roles"].get(db_user)
                database = state["databases"].get(db_name)
                if db_host != "127.0.0.1" or db_port != "5432" or role is None or database is None:
                    raise SystemExit(1)
                if database["owner"] != db_user or role["password"] != os.environ.get("PGPASSWORD"):
                    raise SystemExit(1)
                sys.stdout.write(f"{{db_name}}\\t{{db_user}}\\n")
                raise SystemExit(0)
            if "SELECT version_num FROM alembic_version" in command_sql:
                sys.stdout.write("123\\n")
                raise SystemExit(0)
            if "SELECT current_database(), current_user;" in command_sql:
                sys.stdout.write("ok\\n")
                raise SystemExit(0)
            raise SystemExit(0)
            """
        ),
    )
    _write_executable(
        fake_bin / "install",
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            set -euo pipefail
            if [[ "$1" == "-d" ]]; then
              shift
              while [[ $# -gt 0 ]]; do
                case "$1" in
                  -m|-o|-g)
                    shift 2
                    ;;
                  *)
                    mkdir -p "$1"
                    shift
                    ;;
                esac
              done
              exit 0
            fi
            exec /usr/bin/install "$@"
            """
        ),
    )

    env = _configure_postgres_test_env(fake_bin, runtime_env, tmp_path)
    first_run = _run_bash("./infra/vm/configure_postgres.sh", env=env, cwd=ROOT)

    assert first_run.returncode == 0, first_run.stderr or first_run.stdout
    assert special_password not in (first_run.stdout + first_run.stderr)
    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert state["roles"][db_user]["password"] == special_password
    assert state["roles"][db_user]["createdb"] is False
    assert state["roles"][db_user]["createrole"] is False
    assert state["roles"][db_user]["superuser"] is False
    assert state["databases"][db_name]["owner"] == db_user
    assert state["createdb_calls"] == 1

    _write_runtime_env(runtime_env, db_name=db_name, db_user=db_user, db_password=rotated_password)
    second_run = _run_bash("./infra/vm/configure_postgres.sh", env=env, cwd=ROOT)

    assert second_run.returncode == 0, second_run.stderr or second_run.stdout
    assert rotated_password not in (second_run.stdout + second_run.stderr)
    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert state["roles"][db_user]["password"] == rotated_password
    assert list(state["roles"]) == [db_user]
    assert list(state["databases"]) == [db_name]
    assert state["createdb_calls"] == 1
    log_text = command_log.read_text(encoding="utf-8")
    assert "createdb gxp_app gxp_qlcl" in log_text
    assert "pg_isready -h 127.0.0.1 -p 5432 -d gxp_qlcl" in log_text


def test_configure_postgres_stops_immediately_on_admin_sql_error(tmp_path: Path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    runtime_env = tmp_path / "runtime.env"
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    state_file = state_dir / "postgres-state.json"
    command_log = tmp_path / "command.log"
    python_sh = sys.executable.replace("\\", "/")
    pg_cluster_dir = tmp_path / "pg" / "18" / "main"
    (pg_cluster_dir / "conf.d").mkdir(parents=True)
    (pg_cluster_dir / "pg_hba.conf").write_text("", encoding="utf-8", newline="\n")

    _write_runtime_env(runtime_env, db_password="sql-error-password")
    _write_executable(fake_bin / "python3", f"#!/usr/bin/env bash\n\"{python_sh}\" \"$@\"\n")
    _write_executable(
        fake_bin / "runuser",
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            set -euo pipefail
            shift 3
            exec "$@"
            """
        ),
    )
    _write_executable(
        fake_bin / "pg_lsclusters",
        "#!/usr/bin/env bash\nset -euo pipefail\nprintf '18 main 5432 online postgres /var/lib/postgresql/18/main /var/log/postgresql/postgresql-18-main.log\\n'\n",
    )
    _write_executable(fake_bin / "pg_ctlcluster", "#!/usr/bin/env bash\nset -euo pipefail\nexit 0\n")
    _write_executable(fake_bin / "pg_isready", "#!/usr/bin/env bash\nset -euo pipefail\nexit 0\n")
    _write_executable(
        fake_bin / "createdb",
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            set -euo pipefail
            printf 'createdb %s\\n' "$*" >> "{command_log.as_posix()}"
            exit 0
            """
        ),
    )
    _write_executable(
        fake_bin / "psql",
        textwrap.dedent(
            f"""\
            #!/usr/bin/env python3
            import os
            import sys
            from pathlib import Path

            log_path = Path(r"{command_log.as_posix()}")
            args = sys.argv[1:]
            stdin_sql = sys.stdin.read()
            with log_path.open("a", encoding="utf-8") as fh:
                fh.write(f'psql args={{args!r}} stdin={{stdin_sql!r}}\\n')
            if "CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD %L" in stdin_sql and os.environ.get("PSQL_FORCE_ROLE_SQL_ERROR") == "1":
                sys.stderr.write("ERROR: synthetic role setup failure\\n")
                raise SystemExit(1)
            if "-Atqc" in args and args[args.index("-Atqc") + 1] == "SHOW server_version_num":
                sys.stdout.write("180005\\n")
                raise SystemExit(0)
            raise SystemExit(0)
            """
        ),
    )
    _write_executable(
        fake_bin / "install",
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            set -euo pipefail
            if [[ "$1" == "-d" ]]; then
              shift
              while [[ $# -gt 0 ]]; do
                case "$1" in
                  -m|-o|-g)
                    shift 2
                    ;;
                  *)
                    mkdir -p "$1"
                    shift
                    ;;
                esac
              done
              exit 0
            fi
            exec /usr/bin/install "$@"
            """
        ),
    )

    env = _configure_postgres_test_env(fake_bin, runtime_env, tmp_path)
    env["PSQL_FORCE_ROLE_SQL_ERROR"] = "1"
    completed = _run_bash("./infra/vm/configure_postgres.sh", env=env, cwd=ROOT)

    assert completed.returncode != 0
    assert "synthetic role setup failure" in (completed.stderr or completed.stdout)
    log_text = command_log.read_text(encoding="utf-8")
    assert "createdb " not in log_text
    assert "pg_isready " not in log_text
    assert not state_file.exists()


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

    completed = _run_bash("./infra/vm/backup_postgres.sh", env=env, cwd=ROOT)

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
    (tmp_path / "gxp.dump.sha256").write_text(f"{checksum}  gxp.dump\n", encoding="utf-8", newline="\n")
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

    completed = _run_bash(
        f"TARGET_DB=gxp_qlcl CONFIRM_RESTORE=RESTORE_gxp_qlcl ./infra/vm/restore_postgres.sh '{dump_file.as_posix()}'",
        env=env,
        cwd=ROOT,
    )

    assert completed.returncode != 0
    assert "must not default to the production database name" in (completed.stderr or completed.stdout)


def test_restore_script_creates_missing_restore_db_via_privileged_admin_path(tmp_path: Path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    runtime_env = tmp_path / "runtime.env"
    dump_file = tmp_path / "gxp.dump"
    dump_file.write_text("payload", encoding="utf-8")
    checksum = hashlib.sha256(dump_file.read_bytes()).hexdigest()
    (tmp_path / "gxp.dump.sha256").write_text(f"{checksum}  gxp.dump\n", encoding="utf-8", newline="\n")
    python_sh = sys.executable.replace("\\", "/")
    admin_log = tmp_path / "admin.log"
    createdb_log = tmp_path / "createdb.log"
    restore_log = tmp_path / "restore.log"

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
    (fake_bin / "admin-runner").write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            set -euo pipefail
            printf '%s\\n' "$*" >> "{admin_log.as_posix()}"
            "$@"
            """
        ),
        encoding="utf-8",
    )
    (fake_bin / "psql").write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "stdin_payload=\"$(cat)\"\n"
        "if printf '%s' \"$stdin_payload\" | grep -q \"SELECT 1 FROM pg_database WHERE datname = :'target_db';\"; then\n"
        "  exit 0\n"
        "fi\n"
        "if printf '%s' \"$*\" | grep -q -- '--dbname gxp_qlcl_restore'; then\n"
        "  exit 0\n"
        "fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    (fake_bin / "createdb").write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            set -euo pipefail
            printf '%s\\n' "$*" >> "{createdb_log.as_posix()}"
            exit 0
            """
        ),
        encoding="utf-8",
    )
    (fake_bin / "pg_restore").write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            set -euo pipefail
            printf '%s\\n' "$*" >> "{restore_log.as_posix()}"
            exit 0
            """
        ),
        encoding="utf-8",
    )
    for script_path in fake_bin.iterdir():
        script_path.chmod(0o755)

    env = _base_env(fake_bin, runtime_env)

    completed = _run_bash(
        f"POSTGRES_ADMIN_CMD=admin-runner TARGET_DB=gxp_qlcl_restore CONFIRM_RESTORE=RESTORE_gxp_qlcl_restore ./infra/vm/restore_postgres.sh '{dump_file.as_posix()}'",
        env=env,
        cwd=ROOT,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert "createdb --owner gxp_app gxp_qlcl_restore" in admin_log.read_text(encoding="utf-8")
    assert "--owner gxp_app gxp_qlcl_restore" in createdb_log.read_text(encoding="utf-8")
    assert "--username gxp_app" not in createdb_log.read_text(encoding="utf-8")
    assert "--dbname gxp_qlcl_restore" in restore_log.read_text(encoding="utf-8")


def test_vm_runtime_env_permission_contract_is_documented_in_scripts():
    bootstrap = (ROOT / "infra" / "vm" / "bootstrap_vm.sh").read_text(encoding="utf-8")
    common = (ROOT / "infra" / "vm" / "common.sh").read_text(encoding="utf-8")

    assert 'ensure_dir "${RUNTIME_ENV_DIR}" 0750 root "${GXP_GROUP}"' in bootstrap
    assert '[[ -r "${env_file}" ]] || fail "Runtime env file is not readable by user $(id -un): ${env_file}"' in common
