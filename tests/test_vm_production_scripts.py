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
    assert 'apt-cache show "postgresql-${POSTGRES_MAJOR}"' in text
    assert 'pg_createcluster "${POSTGRES_MAJOR}" "${POSTGRES_CLUSTER_NAME}"' in text


def test_configure_postgres_uses_explicit_cluster_contract():
    text = (ROOT / "infra" / "vm" / "configure_postgres.sh").read_text(encoding="utf-8")

    assert 'POSTGRES_MAJOR="${VM_POSTGRES_MAJOR:-18}"' in text
    assert 'POSTGRES_CLUSTER_NAME="${VM_POSTGRES_CLUSTER_NAME:-main}"' in text
    assert 'pg_lsclusters --no-header' in text
    assert 'PG_CLUSTER_DIR="/etc/postgresql/${POSTGRES_MAJOR}/${POSTGRES_CLUSTER_NAME}"' in text
    assert 'pg_ctlcluster "${POSTGRES_MAJOR}" "${POSTGRES_CLUSTER_NAME}" restart' in text
    assert "find /etc/postgresql" not in text


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


def test_bootstrap_script_aborts_in_cloud_shell_before_mutation(tmp_path: Path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    runtime_env = tmp_path / "runtime.env"
    runtime_env.write_text("", encoding="utf-8")
    command_log = tmp_path / "command.log"
    python_sh = sys.executable.replace("\\", "/")
    (tmp_path / "os-release").write_text("ID=ubuntu\nVERSION_CODENAME=noble\n", encoding="utf-8", newline="\n")

    _write_executable(fake_bin / "python3", f"#!/usr/bin/env bash\n\"{python_sh}\" \"$@\"\n")
    for name in ["apt-get", "apt-cache", "install", "groupadd", "useradd", "swapon", "mkswap", "sysctl", "ln", "chown"]:
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
            "swapon": textwrap.dedent(
                f"""\
                #!/usr/bin/env bash
                set -euo pipefail
                printf 'swapon %s\\n' "$*" >> "{command_log.as_posix()}"
                if [[ "${{1:-}}" == "--show=NAME" || "${{1:-}}" == "--show" ]]; then
                  [[ -f "{(tmp_path / 'swap.active').as_posix()}" ]] && cat "{(tmp_path / 'swap.active').as_posix()}"
                  exit 0
                fi
            printf '%s\n' "$1" > "{(tmp_path / 'swap.active').as_posix()}"
            exit 0
            """
        ),
        "mkswap": textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            set -euo pipefail
            printf 'mkswap %s\\n' "$*" >> "{command_log.as_posix()}"
            exit 0
            """
        ),
        "sysctl": textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            set -euo pipefail
            printf 'sysctl %s\\n' "$*" >> "{command_log.as_posix()}"
            exit 0
            """
        ),
        "free": "#!/usr/bin/env bash\nset -euo pipefail\nprintf 'Mem: 2G 1G 1G\\n'\n",
        "fallocate": "#!/usr/bin/env bash\nset -euo pipefail\n: > \"${@: -1}\"\n",
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
    assert "apt-get install -y --no-install-recommends ca-certificates curl gnupg" in log_text
    assert "apt-cache show postgresql-18" in log_text
    expected_install = f"apt-get install -y --no-install-recommends git nginx procps python{python_series} python{python_series}-venv python3-pip rsync sudo postgresql-18 postgresql-client-18"
    assert expected_install in log_text
    assert log_text.index("apt-get install -y --no-install-recommends ca-certificates curl gnupg") < log_text.index(expected_install)
    assert log_text.index("swapon ") < log_text.index(expected_install)
    assert (tmp_path / "swap.active").read_text(encoding="utf-8").strip() == (tmp_path / "swapfile").as_posix()
    assert "18 main" in cluster_state.read_text(encoding="utf-8")


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
        "if printf '%s' \"$*\" | grep -q -- '--dbname=postgres'; then\n"
        "  exit 1\n"
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
