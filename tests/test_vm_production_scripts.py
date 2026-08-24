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

    assert text.index('CURRENT_STAGE="pre_deploy_consistency_gate"') < text.index('CURRENT_STAGE="resolve_release_targets"')
    assert text.index('CURRENT_STAGE="render_runtime_assets"') < text.index('CURRENT_STAGE="database_backup"')
    assert text.index('CURRENT_STAGE="database_backup"') < text.index('CURRENT_STAGE="alembic_upgrade"')
    assert text.index('CURRENT_STAGE="build_backend_venv"') < text.index('CURRENT_STAGE="resolve_database_url"')
    assert text.index('CURRENT_STAGE="resolve_database_url"') < text.index('CURRENT_STAGE="build_frontend"')
    assert text.index('CURRENT_STAGE="alembic_upgrade"') < text.index('CURRENT_STAGE="switch_release_symlinks"')
    assert text.index('CURRENT_STAGE="switch_release_symlinks"') < text.index('CURRENT_STAGE="restart_services"')
    assert text.index('CURRENT_STAGE="restart_services"') < text.index('CURRENT_STAGE="post_switch_health"')
    assert text.index('CURRENT_STAGE="post_switch_health"') < text.index('CURRENT_STAGE="write_release_metadata"')
    assert text.index('CURRENT_STAGE="write_release_metadata"') < text.index('CURRENT_STAGE="retention"')
    assert 'cp "${STAGED_SERVICE_FILE}" "/etc/systemd/system/${SYSTEMD_SERVICE_NAME}.service"' in text
    assert 'cp "${STAGED_NGINX_FILE}" "/etc/nginx/sites-available/${NGINX_SITE_NAME}.conf"' in text
    assert 'install -m 0640 -o root -g "${VM_APP_GROUP}" "${STAGED_SYSTEMD_ENV_FILE}" "${VM_SYSTEMD_ENV_FILE}.tmp"' in text
    assert 'mv "${VM_SYSTEMD_ENV_FILE}.tmp" "${VM_SYSTEMD_ENV_FILE}"' in text
    assert 'render_runtime_asset service "${STAGED_SERVICE_FILE}" \\' in text
    assert 'VM_SERVICE_ENVIRONMENT_FILE="${VM_SYSTEMD_ENV_FILE}"' in text
    assert 'render_runtime_asset service "${VALIDATION_SERVICE_FILE}" \\' in text
    assert 'VM_SERVICE_ENVIRONMENT_FILE="${STAGED_SYSTEMD_ENV_FILE}"' in text
    assert 'render_runtime_asset nginx "${STAGED_NGINX_FILE}"' in text
    assert 'if [[ "${SUCCESS}" != "1" && "${SWITCHED_CONFIG}" == "1" ]]; then' in text
    assert 'if [[ "${SYSTEMD_SERVICE_FILE_EXISTED_BEFORE}" == "1" && -s "${PREVIOUS_SERVICE_FILE}" ]]; then' in text
    assert 'if [[ "${NGINX_SITE_FILE_EXISTED_BEFORE}" == "1" && -s "${PREVIOUS_NGINX_FILE}" ]]; then' in text
    assert 'if [[ "${SYSTEMD_ENV_FILE_EXISTED_BEFORE}" == "1" && -s "${PREVIOUS_SYSTEMD_ENV_FILE}" ]]; then' in text
    assert 'if [[ "${SUCCESS}" != "1" && "${SWITCHED_RELEASES}" == "1" ]]; then' in text
    assert 'restore_managed_symlink "${VM_CURRENT_BACKEND_RELEASE_LINK}" "${BACKEND_RELEASE_LINK_EXISTED_BEFORE}" "${ORIGINAL_BACKEND_RELEASE_TARGET}" "${VM_APP_USER}" "${VM_APP_GROUP}"' in text
    assert 'restore_managed_symlink "${VM_CURRENT_BACKEND_VENV_LINK}" "${BACKEND_VENV_LINK_EXISTED_BEFORE}" "${ORIGINAL_BACKEND_VENV_TARGET}" "${VM_APP_USER}" "${VM_APP_GROUP}"' in text
    assert 'restore_managed_symlink "${VM_FRONTEND_DIST_DIR}" "${FRONTEND_DIST_EXISTED_BEFORE}" "${ORIGINAL_FRONTEND_TARGET}" "${VM_APP_USER}" "${VM_APP_GROUP}"' in text
    assert 'else\n    rm -rf "${path}" || true' in text
    assert 'validate_pre_deploy_runtime_baseline' in text
    assert 'No successful deploy baseline metadata exists yet, but managed runtime paths are already present' in text
    assert 'RUNTIME_ASSET_STAGING_DIR="$(mktemp -d)"' in text
    assert 'STAGED_SERVICE_FILE="${RUNTIME_ASSET_STAGING_DIR}/${SYSTEMD_SERVICE_NAME}.service"' in text
    assert 'VALIDATION_SERVICE_FILE="${RUNTIME_ASSET_STAGING_DIR}/${SYSTEMD_SERVICE_NAME}.validation.service"' in text
    assert 'STAGED_NGINX_FILE="${RUNTIME_ASSET_STAGING_DIR}/${NGINX_SITE_NAME}.conf"' in text
    assert 'STAGED_SYSTEMD_ENV_FILE="${RUNTIME_ASSET_STAGING_DIR}/$(basename "${VM_SYSTEMD_ENV_FILE}")"' in text
    assert 'PREVIOUS_SERVICE_FILE="${RUNTIME_ASSET_STAGING_DIR}/${SYSTEMD_SERVICE_NAME}.previous.service"' in text
    assert 'PREVIOUS_NGINX_FILE="${RUNTIME_ASSET_STAGING_DIR}/${NGINX_SITE_NAME}.previous.conf"' in text
    assert 'PREVIOUS_SYSTEMD_ENV_FILE="${RUNTIME_ASSET_STAGING_DIR}/$(basename "${VM_SYSTEMD_ENV_FILE}").previous"' in text
    assert 'STAGED_SERVICE_FILE="$(mktemp)"' not in text
    assert 'STAGED_NGINX_FILE="$(mktemp)"' not in text
    assert 'alembic downgrade' not in text


def test_vm_service_template_points_to_generated_systemd_env_file():
    service_text = (ROOT / "infra" / "vm" / "gxp-web.service").read_text(encoding="utf-8")
    render_text = (ROOT / "tools" / "render_vm_runtime_assets.py").read_text(encoding="utf-8")

    assert "EnvironmentFile={{VM_SERVICE_ENVIRONMENT_FILE}}" in service_text
    assert "EnvironmentFile={{VM_RUNTIME_ENV_FILE}}" not in service_text
    assert "def _replacement_map(kind: str)" in render_text
    assert "def _service_replacement_map()" in render_text
    assert "def _nginx_replacement_map()" in render_text
    assert 'service_environment_file = os.environ.get("VM_SERVICE_ENVIRONMENT_FILE", "").strip() or _required_env("VM_SYSTEMD_ENV_FILE")' in render_text
    assert 'public_base_url = _required_env("PUBLIC_BASE_URL")' in render_text
    assert "MARKER_PATTERN" in render_text
    assert "still contains unresolved markers" in render_text
    assert 'VM_SERVICE_ENVIRONMENT_FILE' in render_text


def test_vm_deploy_script_writes_release_metadata_only_after_health_passes():
    text = (ROOT / "infra" / "vm" / "deploy_prod.sh").read_text(encoding="utf-8")

    metadata_section = text[text.index('CURRENT_STAGE="write_release_metadata"') :]
    assert 'wait_for_http_endpoint "/healthz" 30 "${SYSTEMD_SERVICE_NAME}"' in text
    assert 'wait_for_http_endpoint "/readyz" 30 "${SYSTEMD_SERVICE_NAME}"' in text
    assert 'CURRENT_STAGE="post_switch_health"' in text
    assert 'CURRENT_STAGE="write_release_metadata"' in text
    assert 'mv "${VM_RELEASE_METADATA_FILE}.tmp" "${VM_RELEASE_METADATA_FILE}"' in metadata_section


def test_vm_deploy_script_uses_vm_runtime_requirements_and_db_backup():
    text = (ROOT / "infra" / "vm" / "deploy_prod.sh").read_text(encoding="utf-8")

    assert 'RUNTIME_REQUIREMENTS_LOCK_FILE="$(json_query runtime_requirements_lock_file)"' in text
    assert 'install --no-cache-dir -r "${NEW_BACKEND_RELEASE}/${RUNTIME_REQUIREMENTS_LOCK_FILE}"' in text
    assert 'CURRENT_STAGE="node_version_check"' in text
    assert 'CURRENT_NODE_VERSION="$(node -p \'process.versions.node\')" || fail "Could not determine the active Node.js runtime version."' in text
    assert 'python3 - "${CURRENT_NODE_VERSION}" "${NODE_MIN_VERSION}" <<\'PY\'' in text
    assert 'node - "${NODE_MIN_VERSION}" <<\'PY\'' not in text
    assert '[[ -f "${NEW_BACKEND_RELEASE}/frontend/package.json" ]] || fail "Release frontend package manifest missing: ${NEW_BACKEND_RELEASE}/frontend/package.json"' in text
    assert 'FRONTEND_PACKAGE_MANAGER="$(' in text
    assert 'python3 - "${NEW_BACKEND_RELEASE}/frontend/package.json" <<\'PY\'' in text
    assert '[[ "${FRONTEND_PACKAGE_MANAGER}" == "${NODE_PACKAGE_MANAGER}" ]] || fail "frontend/package.json packageManager mismatch. Expected ${NODE_PACKAGE_MANAGER}, got ${FRONTEND_PACKAGE_MANAGER}."' in text
    assert 'cd "${NEW_BACKEND_RELEASE}/frontend"' in text
    assert 'COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack pnpm --version' in text
    assert 'fail "Could not determine the Corepack-managed pnpm version in the frontend release directory."' in text
    assert '[[ "${CURRENT_PNPM_VERSION}" == "${NODE_PACKAGE_MANAGER#pnpm@}" ]] || fail "pnpm version mismatch in frontend release directory. Expected ${NODE_PACKAGE_MANAGER#pnpm@}, got ${CURRENT_PNPM_VERSION}."' in text
    assert 'CURRENT_STAGE="resolve_database_url"' in text
    assert "env -u PYTHONHOME PYTHONPATH='${NEW_BACKEND_RELEASE}' '${NEW_BACKEND_VENV}/bin/python' - <<'PY'" in text
    assert 'export COREPACK_ENABLE_DOWNLOAD_PROMPT=0' in text
    assert 'export PATH=\\"${NEW_BACKEND_VENV}/bin:\\${PATH}\\"' in text
    assert "export PATH='${NEW_BACKEND_VENV}/bin:\\$PATH'" not in text
    assert 'command -v node >/dev/null' in text
    assert 'command -v corepack >/dev/null' in text
    assert 'command -v pnpm >/dev/null' in text
    assert 'command -v rsync >/dev/null' in text
    assert 'cd \'${NEW_BACKEND_RELEASE}/frontend\'' in text
    assert 'corepack pnpm install --frozen-lockfile' in text
    assert 'corepack pnpm build' in text
    assert 'run_as_app_user "${NEW_BACKEND_RELEASE}/infra/vm/backup_postgres.sh"' in text
    assert 'run_as_app_user env DATABASE_URL="${DATABASE_URL}" "${NEW_BACKEND_VENV}/bin/alembic"' in text
    assert "render_vm_runtime_assets.py" in text
    assert '[[ -d "${NEW_BACKEND_RELEASE}" ]] || fail "New backend release directory is missing before service validation: ${NEW_BACKEND_RELEASE}"' in text
    assert '[[ -x "${NEW_BACKEND_VENV}/bin/uvicorn" ]] || fail "New backend release venv is missing an executable uvicorn before service validation: ${NEW_BACKEND_VENV}/bin/uvicorn"' in text
    assert 'VM_SERVICE_WORKING_DIRECTORY="${NEW_BACKEND_RELEASE}" \\' in text
    assert 'VM_SERVICE_EXECUTABLE="${NEW_BACKEND_VENV}/bin/uvicorn" \\' in text
    assert 'render_runtime_asset service "${VALIDATION_SERVICE_FILE}" \\' in text
    assert 'systemd-analyze verify "${VALIDATION_SERVICE_FILE}" >/dev/null' in text
    assert 'python3 tools/runtime_env.py write-systemd "${RUNTIME_ENV_FILE}" "${STAGED_SYSTEMD_ENV_FILE}"' in text
    assert 'CURRENT_STAGE="storage_readiness_check"' in text
    assert "from backend.app.storage.factory import create_storage_service_from_env" in text
    assert "service.list('')" in text
    assert "GXP_FRONTEND_DIST_ROOT" in text
    assert 'systemctl enable "${SYSTEMD_SERVICE_NAME}"' in text
    assert 'systemctl enable nginx' in text
    assert 'VM_CURRENT_BACKEND_RELEASE_LINK' in text
    assert 'VM_CURRENT_BACKEND_VENV_LINK' in text
    assert 'VM_SYSTEMD_ENV_FILE' in text
    assert 'NGINX_SERVER_NAME="$(json_query nginx_server_name)"' in text
    assert 'render_runtime_asset() {' in text
    assert 'VM_RUNTIME_ENV_FILE="${RUNTIME_ENV_FILE}"' in text
    assert 'VM_SERVICE_ENVIRONMENT_FILE="${VM_SYSTEMD_ENV_FILE}"' in text
    assert 'FRONTEND_BUILD_DIR=""' in text
    assert 'FRONTEND_BUILD_DIR="$(mktemp -d)"' in text
    assert 'install -d -m 0750 -o "${VM_APP_USER}" -g "${VM_APP_GROUP}" "${FRONTEND_BUILD_DIR}"' in text
    assert "python3 - <<'PY'\nfrom backend.app.config import resolve_database_url" not in text


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
    assert 'COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack enable --install-directory "${COREPACK_SHIM_DIR}"' in text
    assert 'COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack prepare "${NODE_PACKAGE_MANAGER}" --activate' in text
    assert 'COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack pnpm --version' in text
    assert "verify_app_user_node_toolchain" in text
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
        "VM_SYSTEMD_ENV_FILE=/etc/gxp/runtime.systemd.env",
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


def _run_deploy_node_gate_case(
    tmp_path: Path,
    *,
    node_version: str,
    frontend_corepack_pnpm_version: str,
    global_pnpm_version: str = "11.22.0",
    frontend_package_manager: str = "pnpm@11.19.0",
) -> tuple[subprocess.CompletedProcess[str], Path]:
    def _bash_style(path: Path) -> str:
        value = path.as_posix()
        if os.name == "nt" and len(value) >= 3 and value[1:3] == ":/":
            return f"/{value[0].lower()}{value[2:]}"
        return value

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    runtime_env = tmp_path / "runtime.env"
    export_root = tmp_path / "export-root"
    command_log = tmp_path / "command.log"
    python_sh = sys.executable.replace("\\", "/")
    release_sha = "abcdef1234567890abcdef1234567890abcdef12"
    backend_releases_dir = tmp_path / "backend-releases"
    backend_venvs_dir = tmp_path / "backend-venvs"
    frontend_releases_dir = tmp_path / "frontend-releases"
    frontend_dist_dir = tmp_path / "frontend-dist"
    release_metadata_file = tmp_path / "current-release.json"
    tls_cert_path = tmp_path / "tls.crt"
    tls_key_path = tmp_path / "tls.key"
    fake_bin_bash = _bash_style(fake_bin)
    (fake_home / ".bash_profile").write_text(
        f'export PATH="{fake_bin_bash}:$PATH"\n',
        encoding="utf-8",
        newline="\n",
    )
    (fake_home / ".profile").write_text(
        f'export PATH="{fake_bin_bash}:$PATH"\n',
        encoding="utf-8",
        newline="\n",
    )

    (export_root / "backend").mkdir(parents=True)
    (export_root / "frontend").mkdir(parents=True)
    (export_root / "backend" / "requirements.runtime.vm.lock.txt").write_text("", encoding="utf-8", newline="\n")
    (export_root / "frontend" / "package.json").write_text(
        json.dumps({"name": "frontend", "packageManager": frontend_package_manager}) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    tls_cert_path.write_text("cert\n", encoding="utf-8", newline="\n")
    tls_key_path.write_text("key\n", encoding="utf-8", newline="\n")

    runtime_env.write_text(
        "\n".join(
            [
                "AUTH_PROVIDER=google_oidc",
                "AUTH_OIDC_CLIENT_ID=test-client-id",
                "AUTH_ALLOWED_EMAIL_DOMAIN=example.com",
                "DB_MODE=local_postgres",
                "DB_NAME=gxp_qlcl",
                "DB_USER=gxp_app",
                "DB_PASSWORD=secret",
                "DB_HOST=127.0.0.1",
                "DB_PORT=5432",
                "STORAGE_CLASS=synology_smb",
                "STORAGE_INSPECTION_ROOT=//synology/inspection",
                "STORAGE_DKKD_ROOT=//synology/dkkd",
                "STORAGE_TEMPLATE_ROOT=//synology/templates",
                "SMB_USERNAME=smb-user",
                "SMB_PASSWORD=smb-password",
                f"VM_APP_ROOT={_bash_style(tmp_path)}",
                "VM_APP_USER=gxp",
                "VM_APP_GROUP=gxp",
                "VM_PYTHON_SERIES=3.12",
                f"VM_PYTHON_BIN={_bash_style(fake_bin / 'vm-python')}",
                f"VM_SRC_DIR={_bash_style(ROOT)}",
                f"VM_BACKEND_RELEASES_DIR={_bash_style(backend_releases_dir)}",
                f"VM_BACKEND_VENV_RELEASES_DIR={_bash_style(backend_venvs_dir)}",
                f"VM_CURRENT_BACKEND_RELEASE_LINK={_bash_style(tmp_path / 'current-backend')}",
                f"VM_CURRENT_BACKEND_VENV_LINK={_bash_style(tmp_path / 'current-venv')}",
                f"VM_FRONTEND_DIST_DIR={_bash_style(frontend_dist_dir)}",
                f"VM_FRONTEND_RELEASES_DIR={_bash_style(frontend_releases_dir)}",
                f"VM_RELEASE_METADATA_FILE={_bash_style(release_metadata_file)}",
                "VM_RELEASE_RETENTION_COUNT=3",
                "SYSTEMD_SERVICE_NAME=gxp-web",
                "NGINX_SITE_NAME=gxp-web",
                "PUBLIC_BASE_URL=https://example.com",
                f"VM_TLS_CERT_PATH={_bash_style(tls_cert_path)}",
                f"VM_TLS_KEY_PATH={_bash_style(tls_key_path)}",
                "VM_TLS_PROVISIONING_MODE=existing_files",
                "VM_NODE_MAJOR=22",
                "VM_NODE_MIN_VERSION=22.12.0",
                "VM_COREPACK_VERSION=0.31.0",
                "VM_NODE_PACKAGE_MANAGER=pnpm@11.19.0",
                "VM_NODE_BUILD_OPTIONS=--max-old-space-size=512",
                "VM_SUPPORTED_POSTGRES_MAJORS=17,18",
                "VM_SWAP_SIZE_GB=4",
                "VM_SWAPPINESS=10",
                "PG_SHARED_BUFFERS_MB=256",
                "PG_EFFECTIVE_CACHE_SIZE_MB=768",
                "PG_WORK_MEM_MB=4",
                "PG_MAINTENANCE_WORK_MEM_MB=64",
                "PG_AUTOVACUUM_WORK_MEM_MB=64",
                "PG_MAX_CONNECTIONS=30",
                "BACKUP_GCS_BUCKET=gs://gxp-backups",
            ]
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )

    python3_impl = tmp_path / "python3_impl.py"
    python3_impl.write_text(
        textwrap.dedent(
            f"""\
            import subprocess
            import sys
            from pathlib import Path

            real_python = r"{python_sh}"
            log_path = Path(r"{command_log.as_posix()}")
            args = sys.argv[1:]
            stdin_payload = sys.stdin.read()
            with log_path.open("a", encoding="utf-8") as fh:
                fh.write(f"system-python args={{args!r}}\\n")
            completed = subprocess.run([real_python, *args], input=stdin_payload, text=True, capture_output=True, check=False)
            sys.stdout.write(completed.stdout.replace("\\r\\n", "\\n"))
            sys.stderr.write(completed.stderr.replace("\\r\\n", "\\n"))
            raise SystemExit(completed.returncode)
            """
        ),
        encoding="utf-8",
        newline="\n",
    )
    _write_executable(fake_bin / "python3", f"#!/usr/bin/env bash\nexec \"{python_sh}\" \"{python3_impl.as_posix()}\" \"$@\"\n")
    _write_executable(
        fake_bin / "vm-python",
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            set -euo pipefail
            printf 'vm-python %s\\n' "$*" >> "{command_log.as_posix()}"
            exit 91
            """
        ),
    )
    _write_executable(
        fake_bin / "runuser",
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            set -euo pipefail
            [[ "$1" == "-u" ]] || exit 2
            shift 2
            [[ "$1" == "--" ]] || exit 2
            shift
            cmd="$1"
            shift
            if [[ "$cmd" == "git" ]]; then
              exec "{(fake_bin / 'git').as_posix()}" "$@"
            fi
            exec "$cmd" "$@"
            """
        ),
    )
    git_impl = tmp_path / "git_impl.py"
    git_impl.write_text(
        textwrap.dedent(
            f"""\
            import sys
            import tarfile
            from pathlib import Path

            export_root = Path(r"{export_root.as_posix()}")
            log_path = Path(r"{command_log.as_posix()}")
            release_sha = "{release_sha}"
            args = sys.argv[1:]
            if len(args) >= 2 and args[0] == "-C":
                args = args[2:]
            with log_path.open("a", encoding="utf-8") as fh:
                fh.write(f"git args={{args!r}}\\n")
            if args[:2] == ["status", "--porcelain"]:
                raise SystemExit(0)
            if args[:2] == ["fetch", "origin"]:
                raise SystemExit(0)
            if args[:2] == ["rev-parse", "--verify"]:
                sys.stdout.write(release_sha + "\\n")
                raise SystemExit(0)
            if args[:2] == ["archive", "--format=tar"]:
                with tarfile.open(fileobj=sys.stdout.buffer, mode="w|") as tar:
                    for path in sorted(export_root.rglob("*")):
                        tar.add(path, arcname=path.relative_to(export_root).as_posix(), recursive=False)
                raise SystemExit(0)
            raise SystemExit(1)
            """
        ),
        encoding="utf-8",
        newline="\n",
    )
    _write_executable(fake_bin / "git", f"#!/usr/bin/env bash\nexec \"{python_sh}\" \"{git_impl.as_posix()}\" \"$@\"\n")
    _write_executable(
        fake_bin / "node",
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            set -euo pipefail
            printf 'node %s\\n' "$*" >> "{command_log.as_posix()}"
            if [[ "${{1:-}}" == "-p" && "${{2:-}}" == "process.versions.node" ]]; then
              printf '{node_version}\\n'
              exit 0
            fi
            cat >/dev/null
            exit 0
            """
        ),
    )
    (fake_bin / "node.cmd").write_text(
        "\r\n".join(
            [
                "@echo off",
                f'>> "{command_log.as_posix()}" echo node %*',
                'if "%~1"=="-p" if "%~2"=="process.versions.node" (',
                f"  echo {node_version}",
                "  exit /b 0",
                ")",
                "exit /b 0",
                "",
            ]
        ),
        encoding="utf-8",
        newline="\r\n",
    )
    _write_executable(
        fake_bin / "pnpm",
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            set -euo pipefail
            printf 'pnpm %s\\n' "$*" >> "{command_log.as_posix()}"
            if [[ "${{1:-}}" == "--version" ]]; then
              printf '{global_pnpm_version}\\n'
              exit 0
            fi
            exit 0
            """
        ),
    )
    (fake_bin / "pnpm.cmd").write_text(
        "\r\n".join(
            [
                "@echo off",
                f'>> "{command_log.as_posix()}" echo pnpm %*',
                'if "%~1"=="--version" (',
                f"  echo {global_pnpm_version}",
                "  exit /b 0",
                ")",
                "exit /b 0",
                "",
            ]
        ),
        encoding="utf-8",
        newline="\r\n",
    )
    _write_executable(
        fake_bin / "corepack",
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            set -euo pipefail
            printf 'corepack %s prompt=%s cwd=%s\\n' "$*" "${{COREPACK_ENABLE_DOWNLOAD_PROMPT:-}}" "$PWD" >> "{command_log.as_posix()}"
            if [[ "${{1:-}}" == "pnpm" && "${{2:-}}" == "--version" ]]; then
              [[ "${{COREPACK_ENABLE_DOWNLOAD_PROMPT:-}}" == "0" ]] || exit 1
              if [[ "$PWD" == */frontend ]]; then
                printf '{frontend_corepack_pnpm_version}\\n'
              else
                printf '{global_pnpm_version}\\n'
              fi
              exit 0
            fi
            exit 0
            """
        ),
    )
    for name in ["install", "systemctl", "curl", "nginx", "pg_dump", "rsync", "chown"]:
        _write_executable(
            fake_bin / name,
            textwrap.dedent(
                """\
                #!/usr/bin/env bash
                set -euo pipefail
                if [[ "${1:-}" == "-d" ]]; then
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
                exit 0
                """
            ),
        )

    env = _base_env(fake_bin, runtime_env)
    env["DEPLOY_PROD_UNSAFE_SKIP_ROOT_CHECK"] = "1"
    env["HOME"] = _bash_style(fake_home)

    completed = _run_bash(f'PATH="{fake_bin_bash}:$PATH" ./infra/vm/deploy_prod.sh', env=env, cwd=ROOT)
    return completed, command_log


def test_deploy_script_node_version_gate_accepts_supported_node_and_exact_pnpm(tmp_path: Path):
    completed, command_log = _run_deploy_node_gate_case(tmp_path, node_version="22.23.2", frontend_corepack_pnpm_version="11.19.0")

    assert completed.returncode != 0
    assert "Deploy failed during stage: build_backend_venv" in completed.stderr
    assert "Node.js version check failed." not in completed.stderr
    assert "pnpm version mismatch" not in completed.stderr
    assert "packageManager mismatch" not in completed.stderr
    log_text = command_log.read_text(encoding="utf-8")
    assert "node -p process.versions.node" in log_text
    assert "corepack pnpm --version prompt=0" in log_text
    assert "cwd=" in log_text
    assert "/frontend" in log_text
    assert "cwd=" + ROOT.as_posix() not in log_text


def test_deploy_script_node_version_gate_rejects_old_node_with_clear_error(tmp_path: Path):
    completed, command_log = _run_deploy_node_gate_case(tmp_path, node_version="22.9.0", frontend_corepack_pnpm_version="11.19.0")

    assert completed.returncode != 0
    assert "Node.js version 22.9.0 is lower than required minimum 22.12.0." in completed.stderr
    assert "Node.js version check failed." in completed.stderr
    assert "Deploy failed during stage: node_version_check" in completed.stderr
    assert "pnpm version mismatch" not in completed.stderr
    log_text = command_log.read_text(encoding="utf-8")
    assert "corepack pnpm --version" not in log_text


def test_deploy_script_node_version_gate_rejects_pnpm_version_mismatch(tmp_path: Path):
    completed, command_log = _run_deploy_node_gate_case(tmp_path, node_version="22.23.2", frontend_corepack_pnpm_version="11.18.0")

    assert completed.returncode != 0
    assert "pnpm version mismatch in frontend release directory. Expected 11.19.0, got 11.18.0." in completed.stderr
    assert "Deploy failed during stage: node_version_check" in completed.stderr
    assert "Node.js version check failed." not in completed.stderr
    log_text = command_log.read_text(encoding="utf-8")
    assert "node -p process.versions.node" in log_text
    assert "corepack pnpm --version prompt=0" in log_text


def test_deploy_script_node_version_gate_rejects_frontend_package_manager_mismatch(tmp_path: Path):
    completed, command_log = _run_deploy_node_gate_case(
        tmp_path,
        node_version="22.23.2",
        frontend_corepack_pnpm_version="11.18.0",
        frontend_package_manager="pnpm@11.18.0",
    )

    assert completed.returncode != 0
    assert "frontend/package.json packageManager mismatch. Expected pnpm@11.19.0, got pnpm@11.18.0." in completed.stderr
    assert "Deploy failed during stage: node_version_check" in completed.stderr
    log_text = command_log.read_text(encoding="utf-8")
    assert "corepack pnpm --version" not in log_text


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
            printf 'corepack %s prompt=%s\\n' "$*" "${{COREPACK_ENABLE_DOWNLOAD_PROMPT:-}}" >> "{command_log.as_posix()}"
            [[ "${{COREPACK_ENABLE_DOWNLOAD_PROMPT:-}}" == "0" ]] || exit 1
            if [[ "${{1:-}}" == "prepare" ]]; then
              printf '1' > "{pnpm_ready.as_posix()}"
              exit 0
            fi
            if [[ "${{1:-}}" == "enable" ]]; then
              exit 0
            fi
            if [[ "${{1:-}}" == "pnpm" && "${{2:-}}" == "--version" ]]; then
              [[ -f "{pnpm_ready.as_posix()}" ]] || exit 1
              printf '11.19.0\\n'
              exit 0
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
        "runuser": textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            set -euo pipefail
            printf 'runuser %s\\n' "$*" >> "{command_log.as_posix()}"
            [[ "$1" == "-u" ]] || exit 2
            shift 2
            [[ "$1" == "--" ]] || exit 2
            shift
            exec "$@"
            """
        ),
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
    assert "corepack enable --install-directory /usr/local/bin prompt=0" in log_text
    assert "corepack prepare pnpm@11.19.0 --activate prompt=0" in log_text
    assert "corepack pnpm --version prompt=0" in log_text
    assert "runuser -u root -- bash -lc" in log_text
    assert (tmp_path / "swap.active").read_text(encoding="utf-8").strip() == (tmp_path / "swapfile").as_posix()
    assert "18 main" in cluster_state.read_text(encoding="utf-8")


def test_deploy_script_defers_application_database_url_resolution_until_release_venv_exists(tmp_path: Path):
    def _bash_style(path: Path) -> str:
        value = path.as_posix()
        if os.name == "nt" and len(value) >= 3 and value[1:3] == ":/":
            return f"/{value[0].lower()}{value[2:]}"
        return value

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    runtime_env = tmp_path / "runtime.env"
    export_root = tmp_path / "export-root"
    command_log = tmp_path / "command.log"
    python_sh = sys.executable.replace("\\", "/")
    release_sha = "1234567890abcdef1234567890abcdef12345678"
    backend_releases_dir = tmp_path / "backend-releases"
    backend_venvs_dir = tmp_path / "backend-venvs"
    frontend_releases_dir = tmp_path / "frontend-releases"
    frontend_dist_dir = tmp_path / "frontend-dist"
    release_metadata_file = tmp_path / "current-release.json"
    tls_cert_path = tmp_path / "tls.crt"
    tls_key_path = tmp_path / "tls.key"
    fake_bin_bash = _bash_style(fake_bin)
    (fake_home / ".bash_profile").write_text(
        f'export PATH="{fake_bin_bash}:$PATH"\n',
        encoding="utf-8",
        newline="\n",
    )
    (fake_home / ".profile").write_text(
        f'export PATH="{fake_bin_bash}:$PATH"\n',
        encoding="utf-8",
        newline="\n",
    )

    (export_root / "backend" / "app").mkdir(parents=True)
    (export_root / "frontend").mkdir(parents=True)
    (export_root / "infra" / "vm").mkdir(parents=True)
    (export_root / "tools").mkdir(parents=True)
    (export_root / "backend" / "requirements.runtime.vm.lock.txt").write_text("", encoding="utf-8", newline="\n")
    (export_root / "frontend" / "package.json").write_text(
        json.dumps({"name": "frontend", "packageManager": "pnpm@11.19.0"}) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (export_root / "backend" / "app" / "__init__.py").write_text("", encoding="utf-8")
    (export_root / "backend" / "app" / "config.py").write_text(
        textwrap.dedent(
            """\
            def resolve_database_url(env: dict[str, str]) -> str:
                return env["DATABASE_URL"]
            """
        ),
        encoding="utf-8",
        newline="\n",
    )
    (export_root / "alembic.ini").write_text("[alembic]\nscript_location = alembic\n", encoding="utf-8", newline="\n")
    (export_root / "tools" / "render_vm_runtime_assets.py").write_text(
        textwrap.dedent(
            """\
            from pathlib import Path
            import sys

            Path(sys.argv[2]).write_text(f"{sys.argv[1]}\\n", encoding="utf-8")
            """
        ),
        encoding="utf-8",
        newline="\n",
    )
    backup_script = export_root / "infra" / "vm" / "backup_postgres.sh"
    backup_script.write_text("#!/usr/bin/env bash\nset -euo pipefail\nexit 0\n", encoding="utf-8", newline="\n")
    backup_script.chmod(0o755)

    runtime_env.write_text(
        "\n".join(
            [
                "AUTH_PROVIDER=google_oidc",
                "AUTH_OIDC_CLIENT_ID=test-client-id",
                "AUTH_ALLOWED_EMAIL_DOMAIN=example.com",
                "DB_MODE=local_postgres",
                "DB_NAME=gxp_qlcl",
                "DB_USER=gxp_app",
                "DB_PASSWORD=secret",
                "DB_HOST=127.0.0.1",
                "DB_PORT=5432",
                "STORAGE_CLASS=synology_smb",
                "STORAGE_INSPECTION_ROOT=//synology/inspection",
                "STORAGE_DKKD_ROOT=//synology/dkkd",
                "STORAGE_TEMPLATE_ROOT=//synology/templates",
                "SMB_USERNAME=smb-user",
                "SMB_PASSWORD=smb-password",
                f"VM_APP_ROOT={_bash_style(tmp_path)}",
                "VM_APP_USER=gxp",
                "VM_APP_GROUP=gxp",
                "VM_PYTHON_SERIES=3.12",
                f"VM_PYTHON_BIN={_bash_style(fake_bin / 'vm-python')}",
                f"VM_SRC_DIR={_bash_style(ROOT)}",
                f"VM_BACKEND_RELEASES_DIR={_bash_style(backend_releases_dir)}",
                f"VM_BACKEND_VENV_RELEASES_DIR={_bash_style(backend_venvs_dir)}",
                f"VM_CURRENT_BACKEND_RELEASE_LINK={_bash_style(tmp_path / 'current-backend')}",
                f"VM_CURRENT_BACKEND_VENV_LINK={_bash_style(tmp_path / 'current-venv')}",
                f"VM_FRONTEND_DIST_DIR={_bash_style(frontend_dist_dir)}",
                f"VM_FRONTEND_RELEASES_DIR={_bash_style(frontend_releases_dir)}",
                f"VM_RELEASE_METADATA_FILE={_bash_style(release_metadata_file)}",
                "VM_RELEASE_RETENTION_COUNT=3",
                "SYSTEMD_SERVICE_NAME=gxp-web",
                "NGINX_SITE_NAME=gxp-web",
                "PUBLIC_BASE_URL=https://example.com",
                f"VM_TLS_CERT_PATH={_bash_style(tls_cert_path)}",
                f"VM_TLS_KEY_PATH={_bash_style(tls_key_path)}",
                "VM_TLS_PROVISIONING_MODE=existing_files",
                "VM_NODE_MAJOR=22",
                "VM_NODE_MIN_VERSION=22.12.0",
                "VM_COREPACK_VERSION=0.31.0",
                "VM_NODE_PACKAGE_MANAGER=pnpm@11.19.0",
                "VM_NODE_BUILD_OPTIONS=--max-old-space-size=512",
                "VM_SUPPORTED_POSTGRES_MAJORS=17,18",
                "VM_SWAP_SIZE_GB=4",
                "VM_SWAPPINESS=10",
                "PG_SHARED_BUFFERS_MB=256",
                "PG_EFFECTIVE_CACHE_SIZE_MB=768",
                "PG_WORK_MEM_MB=4",
                "PG_MAINTENANCE_WORK_MEM_MB=64",
                "PG_AUTOVACUUM_WORK_MEM_MB=64",
                "PG_MAX_CONNECTIONS=30",
                "BACKUP_GCS_BUCKET=gs://gxp-backups",
            ]
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )

    python3_impl = tmp_path / "python3_impl.py"
    python3_impl.write_text(
        textwrap.dedent(
            f"""\
            import subprocess
            import sys
            from pathlib import Path

            real_python = r"{python_sh}"
            log_path = Path(r"{command_log.as_posix()}")
            args = sys.argv[1:]
            stdin_payload = sys.stdin.read()
            has_backend_import = "from backend.app.config import resolve_database_url" in stdin_payload
            with log_path.open("a", encoding="utf-8") as fh:
                fh.write(f"system-python args={{args!r}} backend_import={{has_backend_import}}\\n")
            if has_backend_import:
                sys.stderr.write("ModuleNotFoundError: No module named 'sqlalchemy'\\n")
                raise SystemExit(1)
            completed = subprocess.run([real_python, *args], input=stdin_payload, text=True, capture_output=True, check=False)
            sys.stdout.write(completed.stdout.replace("\\r\\n", "\\n"))
            sys.stderr.write(completed.stderr.replace("\\r\\n", "\\n"))
            raise SystemExit(completed.returncode)
            """
        ),
        encoding="utf-8",
        newline="\n",
    )
    _write_executable(fake_bin / "python3", f"#!/usr/bin/env bash\nexec \"{python_sh}\" \"{python3_impl.as_posix()}\" \"$@\"\n")

    vm_python_impl = tmp_path / "vm_python_impl.py"
    vm_python_impl.write_text(
        (
            "import os\n"
            "import stat\n"
            "import sys\n"
            "from pathlib import Path\n"
            f'log_path = Path(r"{command_log.as_posix()}")\n'
            f'real_python = r"{python_sh}"\n'
            "args = sys.argv[1:]\n"
            'if args[:2] != ["-m", "venv"] or len(args) != 3:\n'
            "    raise SystemExit(2)\n"
            "venv_dir = Path(args[2])\n"
            'bin_dir = venv_dir / "bin"\n'
            "bin_dir.mkdir(parents=True, exist_ok=True)\n"
            'runtime_flag = venv_dir / ".runtime-installed"\n'
            'python_impl = bin_dir / "python_impl.py"\n'
            "python_impl.write_text(\n"
            "    (\n"
            '        "import os\\n"\n'
            '        "import sys\\n"\n'
            '        "from pathlib import Path\\n"\n'
            f'        \'log_path = Path(r"{command_log.as_posix()}")\\n\'\n'
            '        "runtime_flag = Path(sys.argv[1])\\n"\n'
            '        "stdin_payload = sys.stdin.read()\\n"\n'
            '        "if \\"from backend.app.config import resolve_database_url\\" in stdin_payload:\\n"\n'
            '        "    with log_path.open(\\"a\\", encoding=\\"utf-8\\") as fh:\\n"\n'
            '        "        fh.write(\\n"\n'
            '        "            f\\"venv-python action=resolve cwd={Path.cwd().as_posix()} pythonpath={os.environ.get(\'PYTHONPATH\', \'\')} runtime_ready={runtime_flag.exists()}\\\\n\\"\\n"\n'
            '        "        )\\n"\n'
            '        "    if not runtime_flag.exists():\\n"\n'
            '        "        sys.stderr.write(\\"runtime dependencies missing\\\\n\\")\\n"\n'
            '        "        raise SystemExit(1)\\n"\n'
            '        "    sys.stdout.write(\\"postgresql+psycopg://gxp_app:secret@127.0.0.1:5432/gxp_qlcl\\\\n\\")\\n"\n'
            '        "    raise SystemExit(0)\\n"\n'
            '        "raise SystemExit(0)\\n"\n'
            "    ),\n"
            '    encoding="utf-8",\n'
            '    newline="\\n",\n'
            ")\n"
            'pip_impl = bin_dir / "pip_impl.py"\n'
            "pip_impl.write_text(\n"
            "    (\n"
            '        "import sys\\n"\n'
            '        "from pathlib import Path\\n"\n'
            f'        \'log_path = Path(r"{command_log.as_posix()}")\\n\'\n'
            '        "runtime_flag = Path(sys.argv[1])\\n"\n'
            '        "args = sys.argv[2:]\\n"\n'
            '        \'with log_path.open("a", encoding="utf-8") as fh:\\n\'\n'
            '        \'    fh.write(f"venv-pip args={args!r}\\\\n")\\n\'\n'
            '        \'if "-r" in args:\\n\'\n'
            '        \'    runtime_flag.write_text("ready\\\\n", encoding="utf-8")\\n\'\n'
            '        \'    with log_path.open("a", encoding="utf-8") as fh:\\n\'\n'
            '        \'        fh.write("venv-pip install-runtime\\\\n")\\n\'\n'
            '        "raise SystemExit(0)\\n"\n'
            "    ),\n"
            '    encoding="utf-8",\n'
            '    newline="\\n",\n'
            ")\n"
            'alembic_impl = bin_dir / "alembic_impl.py"\n'
            "alembic_impl.write_text(\n"
            "    (\n"
            '        "import os\\n"\n'
            '        "import sys\\n"\n'
            '        "from pathlib import Path\\n"\n'
            f'        \'log_path = Path(r"{command_log.as_posix()}")\\n\'\n'
            '        "with log_path.open(\\"a\\", encoding=\\"utf-8\\") as fh:\\n"\n'
            '        "    fh.write(f\\"venv-alembic database_url={os.environ.get(\'DATABASE_URL\', \'\')} args={sys.argv[1:]!r}\\\\n\\")\\n"\n'
            '        "raise SystemExit(0)\\n"\n'
            "    ),\n"
            '    encoding="utf-8",\n'
            '    newline="\\n",\n'
            ")\n"
            "wrappers = {\n"
            "    \"python\": '#!/usr/bin/env bash\\nexec \"' + real_python + '\" \"' + python_impl.as_posix() + '\" \"' + runtime_flag.as_posix() + '\" \"$@\"\\n',\n"
            "    \"pip\": '#!/usr/bin/env bash\\nexec \"' + real_python + '\" \"' + pip_impl.as_posix() + '\" \"' + runtime_flag.as_posix() + '\" \"$@\"\\n',\n"
            "    \"alembic\": '#!/usr/bin/env bash\\nexec \"' + real_python + '\" \"' + alembic_impl.as_posix() + '\" \"$@\"\\n',\n"
            "}\n"
            "for name, content in wrappers.items():\n"
            "    wrapper = bin_dir / name\n"
            '    wrapper.write_text(content, encoding="utf-8", newline="\\n")\n'
            "    wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)\n"
            'with log_path.open("a", encoding="utf-8") as fh:\n'
            '    fh.write(f"vm-python create-venv path={venv_dir.as_posix()}\\n")\n'
            "raise SystemExit(0)\n"
        ),
        encoding="utf-8",
        newline="\n",
    )
    _write_executable(fake_bin / "vm-python", f"#!/usr/bin/env bash\nexec \"{python_sh}\" \"{vm_python_impl.as_posix()}\" \"$@\"\n")
    _write_executable(
        fake_bin / "runuser",
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            set -euo pipefail
            [[ "$1" == "-u" ]] || exit 2
            shift 2
            [[ "$1" == "--" ]] || exit 2
            shift
            cmd="$1"
            shift
            if [[ "$cmd" == "git" ]]; then
              exec "{(fake_bin / 'git').as_posix()}" "$@"
            fi
            exec "$cmd" "$@"
            """
        ),
    )
    git_impl = tmp_path / "git_impl.py"
    git_impl.write_text(
        textwrap.dedent(
            f"""\
            import sys
            import tarfile
            from pathlib import Path

            export_root = Path(r"{export_root.as_posix()}")
            log_path = Path(r"{command_log.as_posix()}")
            release_sha = "{release_sha}"
            args = sys.argv[1:]
            if len(args) >= 2 and args[0] == "-C":
                args = args[2:]
            with log_path.open("a", encoding="utf-8") as fh:
                fh.write(f"git args={{args!r}}\\n")
            if args[:2] == ["status", "--porcelain"]:
                raise SystemExit(0)
            if args[:2] == ["fetch", "origin"]:
                raise SystemExit(0)
            if args[:2] == ["rev-parse", "--verify"]:
                sys.stdout.write(release_sha + "\\n")
                raise SystemExit(0)
            if args[:2] == ["archive", "--format=tar"]:
                with tarfile.open(fileobj=sys.stdout.buffer, mode="w|") as tar:
                    for path in sorted(export_root.rglob("*")):
                        tar.add(path, arcname=path.relative_to(export_root).as_posix(), recursive=False)
                raise SystemExit(0)
            raise SystemExit(1)
            """
        ),
        encoding="utf-8",
        newline="\n",
    )
    _write_executable(fake_bin / "git", f"#!/usr/bin/env bash\nexec \"{python_sh}\" \"{git_impl.as_posix()}\" \"$@\"\n")
    _write_executable(
        fake_bin / "node",
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            set -euo pipefail
            if [[ "${1:-}" == "-p" && "${2:-}" == "process.versions.node" ]]; then
              printf '22.12.0\n'
              exit 0
            fi
            cat >/dev/null
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
            printf 'pnpm %s path=%s\\n' "$*" "$PATH" >> "{command_log.as_posix()}"
            if [[ "${{1:-}}" == "--version" ]]; then
              printf '11.22.0\\n'
              exit 0
            fi
            if [[ "${{1:-}}" == "build" ]]; then
              printf 'frontend build intentionally stopped after DATABASE_URL resolution\\n' >&2
              exit 42
            fi
            exit 0
            """
        ),
    )
    _write_executable(
        fake_bin / "corepack",
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            set -euo pipefail
            printf 'corepack %s prompt=%s path=%s\\n' "$*" "${{COREPACK_ENABLE_DOWNLOAD_PROMPT:-}}" "$PATH" >> "{command_log.as_posix()}"
            if [[ "${{1:-}}" == "pnpm" && "${{2:-}}" == "--version" ]]; then
              printf '11.19.0\\n'
              exit 0
            fi
            if [[ "${{1:-}}" == "pnpm" ]]; then
              shift
              exec "{(fake_bin / 'pnpm').as_posix()}" "$@"
            fi
            exit 0
            """
        ),
    )
    _write_executable(
        fake_bin / "install",
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            set -euo pipefail
            if [[ "${1:-}" == "-d" ]]; then
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
            exit 0
            """
        ),
    )
    _write_executable(fake_bin / "systemctl", "#!/usr/bin/env bash\nset -euo pipefail\nexit 0\n")
    _write_executable(fake_bin / "curl", "#!/usr/bin/env bash\nset -euo pipefail\nexit 0\n")
    _write_executable(fake_bin / "nginx", "#!/usr/bin/env bash\nset -euo pipefail\nexit 0\n")
    _write_executable(fake_bin / "pg_dump", "#!/usr/bin/env bash\nset -euo pipefail\nexit 0\n")
    _write_executable(fake_bin / "rsync", "#!/usr/bin/env bash\nset -euo pipefail\nexit 0\n")
    _write_executable(fake_bin / "chown", "#!/usr/bin/env bash\nset -euo pipefail\nexit 0\n")

    env = _base_env(fake_bin, runtime_env)
    env["DEPLOY_PROD_UNSAFE_SKIP_ROOT_CHECK"] = "1"
    env["HOME"] = _bash_style(fake_home)

    completed = _run_bash(f'PATH="{fake_bin_bash}:$PATH" ./infra/vm/deploy_prod.sh', env=env, cwd=ROOT)

    assert completed.returncode != 0
    assert "Deploy failed during stage: build_frontend" in completed.stderr
    assert "ModuleNotFoundError: No module named 'sqlalchemy'" not in (completed.stdout + completed.stderr)
    log_text = command_log.read_text(encoding="utf-8")
    assert "system-python args=" in log_text
    assert "backend_import=True" not in log_text
    assert "venv-pip install-runtime" in log_text
    assert "venv-python action=resolve" in log_text
    assert "corepack pnpm --version prompt=0" in log_text
    assert "corepack pnpm install --frozen-lockfile prompt=0" in log_text
    assert "corepack pnpm build prompt=0" in log_text
    assert "pnpm build path=" in log_text
    expected_release_dir = _bash_style(backend_releases_dir / release_sha)
    assert f"cwd={expected_release_dir}" in log_text or f"cwd={(backend_releases_dir / release_sha).as_posix()}" in log_text
    assert f"pythonpath={expected_release_dir}" in log_text or f"pythonpath={(backend_releases_dir / release_sha).as_posix()}" in log_text
    expected_venv_bin = _bash_style(backend_venvs_dir / release_sha / "bin")
    assert f"path={expected_venv_bin}:" in log_text or f"path={(backend_venvs_dir / release_sha / 'bin').as_posix()}:" in log_text
    assert fake_bin_bash in log_text or fake_bin.as_posix() in log_text
    assert log_text.index("venv-pip install-runtime") < log_text.index("venv-python action=resolve")


def test_deploy_script_prepares_frontend_staging_dir_for_app_user_rsync(tmp_path: Path):
    def _bash_style(path: Path) -> str:
        value = path.as_posix()
        if os.name == "nt" and len(value) >= 3 and value[1:3] == ":/":
            return f"/{value[0].lower()}{value[2:]}"
        return value

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    runtime_env = tmp_path / "runtime.env"
    export_root = tmp_path / "export-root"
    command_log = tmp_path / "command.log"
    python_sh = sys.executable.replace("\\", "/")
    release_sha = "fedcba9876543210fedcba9876543210fedcba98"
    backend_releases_dir = tmp_path / "backend-releases"
    backend_venvs_dir = tmp_path / "backend-venvs"
    frontend_releases_dir = tmp_path / "frontend-releases"
    frontend_dist_dir = tmp_path / "frontend-dist"
    release_metadata_file = tmp_path / "current-release.json"
    tls_cert_path = tmp_path / "tls.crt"
    tls_key_path = tmp_path / "tls.key"
    mktemp_state_dir = tmp_path / "mktemp-state"
    mktemp_state_dir.mkdir()
    fake_bin_bash = _bash_style(fake_bin)
    (fake_home / ".bash_profile").write_text(
        f'export PATH="{fake_bin_bash}:$PATH"\n',
        encoding="utf-8",
        newline="\n",
    )
    (fake_home / ".profile").write_text(
        f'export PATH="{fake_bin_bash}:$PATH"\n',
        encoding="utf-8",
        newline="\n",
    )

    (export_root / "backend" / "app").mkdir(parents=True)
    (export_root / "frontend").mkdir(parents=True)
    (export_root / "infra" / "vm").mkdir(parents=True)
    (export_root / "tools").mkdir(parents=True)
    (export_root / "backend" / "requirements.runtime.vm.lock.txt").write_text("", encoding="utf-8", newline="\n")
    (export_root / "frontend" / "package.json").write_text(
        json.dumps({"name": "frontend", "packageManager": "pnpm@11.19.0"}) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (export_root / "backend" / "app" / "__init__.py").write_text("", encoding="utf-8")
    (export_root / "backend" / "app" / "config.py").write_text(
        textwrap.dedent(
            """\
            def resolve_database_url(env: dict[str, str]) -> str:
                return env["DATABASE_URL"]
            """
        ),
        encoding="utf-8",
        newline="\n",
    )
    (export_root / "alembic.ini").write_text("[alembic]\nscript_location = alembic\n", encoding="utf-8", newline="\n")
    (export_root / "tools" / "render_vm_runtime_assets.py").write_text(
        textwrap.dedent(
            """\
            from pathlib import Path
            import sys

            Path(sys.argv[2]).write_text(f"{sys.argv[1]}\\n", encoding="utf-8")
            """
        ),
        encoding="utf-8",
        newline="\n",
    )
    backup_script = export_root / "infra" / "vm" / "backup_postgres.sh"
    backup_script.write_text("#!/usr/bin/env bash\nset -euo pipefail\nexit 0\n", encoding="utf-8", newline="\n")
    backup_script.chmod(0o755)
    tls_cert_path.write_text("cert\n", encoding="utf-8", newline="\n")
    tls_key_path.write_text("key\n", encoding="utf-8", newline="\n")

    runtime_env.write_text(
        "\n".join(
            [
                "AUTH_PROVIDER=google_oidc",
                "AUTH_OIDC_CLIENT_ID=test-client-id",
                "AUTH_ALLOWED_EMAIL_DOMAIN=example.com",
                "DB_MODE=local_postgres",
                "DB_NAME=gxp_qlcl",
                "DB_USER=gxp_app",
                "DB_PASSWORD=secret",
                "DB_HOST=127.0.0.1",
                "DB_PORT=5432",
                "STORAGE_CLASS=synology_smb",
                "STORAGE_INSPECTION_ROOT=//synology/inspection",
                "STORAGE_DKKD_ROOT=//synology/dkkd",
                "STORAGE_TEMPLATE_ROOT=//synology/templates",
                "SMB_USERNAME=smb-user",
                "SMB_PASSWORD=smb-password",
                f"VM_APP_ROOT={_bash_style(tmp_path)}",
                "VM_APP_USER=gxp",
                "VM_APP_GROUP=gxp",
                "VM_PYTHON_SERIES=3.12",
                f"VM_PYTHON_BIN={_bash_style(fake_bin / 'vm-python')}",
                f"VM_SRC_DIR={_bash_style(ROOT)}",
                f"VM_BACKEND_RELEASES_DIR={_bash_style(backend_releases_dir)}",
                f"VM_BACKEND_VENV_RELEASES_DIR={_bash_style(backend_venvs_dir)}",
                f"VM_CURRENT_BACKEND_RELEASE_LINK={_bash_style(tmp_path / 'current-backend')}",
                f"VM_CURRENT_BACKEND_VENV_LINK={_bash_style(tmp_path / 'current-venv')}",
                f"VM_FRONTEND_DIST_DIR={_bash_style(frontend_dist_dir)}",
                f"VM_FRONTEND_RELEASES_DIR={_bash_style(frontend_releases_dir)}",
                f"VM_RELEASE_METADATA_FILE={_bash_style(release_metadata_file)}",
                "VM_RELEASE_RETENTION_COUNT=3",
                "SYSTEMD_SERVICE_NAME=gxp-web",
                "NGINX_SITE_NAME=gxp-web",
                "PUBLIC_BASE_URL=https://example.com",
                f"VM_TLS_CERT_PATH={_bash_style(tls_cert_path)}",
                f"VM_TLS_KEY_PATH={_bash_style(tls_key_path)}",
                "VM_TLS_PROVISIONING_MODE=existing_files",
                "VM_NODE_MAJOR=22",
                "VM_NODE_MIN_VERSION=22.12.0",
                "VM_COREPACK_VERSION=0.31.0",
                "VM_NODE_PACKAGE_MANAGER=pnpm@11.19.0",
                "VM_NODE_BUILD_OPTIONS=--max-old-space-size=512",
                "VM_SUPPORTED_POSTGRES_MAJORS=17,18",
                "VM_SWAP_SIZE_GB=4",
                "VM_SWAPPINESS=10",
                "PG_SHARED_BUFFERS_MB=256",
                "PG_EFFECTIVE_CACHE_SIZE_MB=768",
                "PG_WORK_MEM_MB=4",
                "PG_MAINTENANCE_WORK_MEM_MB=64",
                "PG_AUTOVACUUM_WORK_MEM_MB=64",
                "PG_MAX_CONNECTIONS=30",
                "BACKUP_GCS_BUCKET=gs://gxp-backups",
                f"TEST_MKTEMP_STATE_DIR={_bash_style(mktemp_state_dir)}",
            ]
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )

    python3_impl = tmp_path / "python3_impl.py"
    python3_impl.write_text(
        textwrap.dedent(
            f"""\
            import subprocess
            import sys
            from pathlib import Path

            real_python = r"{python_sh}"
            log_path = Path(r"{command_log.as_posix()}")
            args = sys.argv[1:]
            stdin_payload = sys.stdin.read()
            has_backend_import = "from backend.app.config import resolve_database_url" in stdin_payload
            with log_path.open("a", encoding="utf-8") as fh:
                fh.write(f"system-python args={{args!r}} backend_import={{has_backend_import}}\\n")
            completed = subprocess.run([real_python, *args], input=stdin_payload, text=True, capture_output=True, check=False)
            sys.stdout.write(completed.stdout.replace("\\r\\n", "\\n"))
            sys.stderr.write(completed.stderr.replace("\\r\\n", "\\n"))
            raise SystemExit(completed.returncode)
            """
        ),
        encoding="utf-8",
        newline="\n",
    )
    _write_executable(fake_bin / "python3", f"#!/usr/bin/env bash\nexec \"{python_sh}\" \"{python3_impl.as_posix()}\" \"$@\"\n")

    vm_python_impl = tmp_path / "vm_python_impl.py"
    vm_python_impl.write_text(
        (
            "import os\n"
            "import stat\n"
            "import sys\n"
            "from pathlib import Path\n"
            f'log_path = Path(r"{command_log.as_posix()}")\n'
            f'real_python = r"{python_sh}"\n'
            "args = sys.argv[1:]\n"
            'if args[:2] != ["-m", "venv"] or len(args) != 3:\n'
            "    raise SystemExit(2)\n"
            "venv_dir = Path(args[2])\n"
            'bin_dir = venv_dir / "bin"\n'
            "bin_dir.mkdir(parents=True, exist_ok=True)\n"
            'runtime_flag = venv_dir / ".runtime-installed"\n'
            'python_impl = bin_dir / "python_impl.py"\n'
            "python_impl.write_text(\n"
            "    (\n"
            '        "import os\\n"\n'
            '        "import sys\\n"\n'
            '        "from pathlib import Path\\n"\n'
            f'        \'log_path = Path(r"{command_log.as_posix()}")\\n\'\n'
            '        "runtime_flag = Path(sys.argv[1])\\n"\n'
            '        "stdin_payload = sys.stdin.read()\\n"\n'
            '        "if \\"from backend.app.config import resolve_database_url\\" in stdin_payload:\\n"\n'
            '        "    with log_path.open(\\"a\\", encoding=\\"utf-8\\") as fh:\\n"\n'
            '        "        fh.write(f\\"venv-python action=resolve cwd={Path.cwd().as_posix()} pythonpath={os.environ.get(\'PYTHONPATH\', \'\')} runtime_ready={runtime_flag.exists()}\\\\n\\")\\n"\n'
            '        "    if not runtime_flag.exists():\\n"\n'
            '        "        raise SystemExit(1)\\n"\n'
            '        "    sys.stdout.write(\\"postgresql+psycopg://gxp_app:secret@127.0.0.1:5432/gxp_qlcl\\\\n\\")\\n"\n'
            '        "    raise SystemExit(0)\\n"\n'
            '        "raise SystemExit(0)\\n"\n'
            "    ),\n"
            '    encoding="utf-8",\n'
            '    newline="\\n",\n'
            ")\n"
            'pip_impl = bin_dir / "pip_impl.py"\n'
            "pip_impl.write_text(\n"
            "    (\n"
            '        "import sys\\n"\n'
            '        "from pathlib import Path\\n"\n'
            f'        \'log_path = Path(r"{command_log.as_posix()}")\\n\'\n'
            '        "runtime_flag = Path(sys.argv[1])\\n"\n'
            '        "args = sys.argv[2:]\\n"\n'
            '        \'with log_path.open("a", encoding="utf-8") as fh:\\n\'\n'
            '        \'    fh.write(f"venv-pip args={args!r}\\\\n")\\n\'\n'
            '        \'if "-r" in args:\\n\'\n'
            '        \'    runtime_flag.write_text("ready\\\\n", encoding="utf-8")\\n\'\n'
            '        "raise SystemExit(0)\\n"\n'
            "    ),\n"
            '    encoding="utf-8",\n'
            '    newline="\\n",\n'
            ")\n"
            "wrappers = {\n"
            "    \"python\": '#!/usr/bin/env bash\\nexec \"' + real_python + '\" \"' + python_impl.as_posix() + '\" \"' + runtime_flag.as_posix() + '\" \"$@\"\\n',\n"
            "    \"pip\": '#!/usr/bin/env bash\\nexec \"' + real_python + '\" \"' + pip_impl.as_posix() + '\" \"' + runtime_flag.as_posix() + '\" \"$@\"\\n',\n"
            "    \"alembic\": '#!/usr/bin/env bash\\necho unexpected alembic >&2\\nexit 99\\n',\n"
            "}\n"
            "for name, content in wrappers.items():\n"
            "    wrapper = bin_dir / name\n"
            '    wrapper.write_text(content, encoding="utf-8", newline="\\n")\n'
            "    wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)\n"
            'with log_path.open("a", encoding="utf-8") as fh:\n'
            '    fh.write(f"vm-python create-venv path={venv_dir.as_posix()}\\n")\n'
            "raise SystemExit(0)\n"
        ),
        encoding="utf-8",
        newline="\n",
    )
    _write_executable(fake_bin / "vm-python", f"#!/usr/bin/env bash\nexec \"{python_sh}\" \"{vm_python_impl.as_posix()}\" \"$@\"\n")
    _write_executable(
        fake_bin / "runuser",
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            set -euo pipefail
            [[ "$1" == "-u" ]] || exit 2
            shift 2
            [[ "$1" == "--" ]] || exit 2
            shift
            cmd="$1"
            shift
            if [[ "$cmd" == "git" ]]; then
              exec "{(fake_bin / 'git').as_posix()}" "$@"
            fi
            exec "$cmd" "$@"
            """
        ),
    )
    git_impl = tmp_path / "git_impl.py"
    git_impl.write_text(
        textwrap.dedent(
            f"""\
            import sys
            import tarfile
            from pathlib import Path

            export_root = Path(r"{export_root.as_posix()}")
            log_path = Path(r"{command_log.as_posix()}")
            release_sha = "{release_sha}"
            args = sys.argv[1:]
            if len(args) >= 2 and args[0] == "-C":
                args = args[2:]
            with log_path.open("a", encoding="utf-8") as fh:
                fh.write(f"git args={{args!r}}\\n")
            if args[:2] == ["status", "--porcelain"]:
                raise SystemExit(0)
            if args[:2] == ["fetch", "origin"]:
                raise SystemExit(0)
            if args[:2] == ["rev-parse", "--verify"]:
                sys.stdout.write(release_sha + "\\n")
                raise SystemExit(0)
            if args[:2] == ["archive", "--format=tar"]:
                with tarfile.open(fileobj=sys.stdout.buffer, mode="w|") as tar:
                    for path in sorted(export_root.rglob("*")):
                        tar.add(path, arcname=path.relative_to(export_root).as_posix(), recursive=False)
                raise SystemExit(0)
            raise SystemExit(1)
            """
        ),
        encoding="utf-8",
        newline="\n",
    )
    _write_executable(fake_bin / "git", f"#!/usr/bin/env bash\nexec \"{python_sh}\" \"{git_impl.as_posix()}\" \"$@\"\n")
    _write_executable(
        fake_bin / "mktemp",
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            set -euo pipefail
            state_dir="{mktemp_state_dir.as_posix()}"
            counter_file="${{state_dir}}/counter"
            count=0
            if [[ -f "${{counter_file}}" ]]; then
              count="$(cat "${{counter_file}}")"
            fi
            next=$((count + 1))
            printf '%s' "${{next}}" > "${{counter_file}}"
            if [[ "${{1:-}}" == "-d" ]]; then
              path="${{state_dir}}/tmpdir-${{next}}"
              mkdir -p "${{path}}"
              chmod 0700 "${{path}}"
              printf 'mktemp -d path=%s\\n' "${{path}}" >> "{command_log.as_posix()}"
              printf '%s\\n' "${{path}}"
              exit 0
            fi
            path="${{state_dir}}/tmpfile-${{next}}"
            : > "${{path}}"
            chmod 0600 "${{path}}"
            printf 'mktemp path=%s\\n' "${{path}}" >> "{command_log.as_posix()}"
            printf '%s\\n' "${{path}}"
            """
        ),
    )
    _write_executable(
        fake_bin / "node",
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            set -euo pipefail
            printf 'node %s\\n' "$*" >> "{command_log.as_posix()}"
            if [[ "${{1:-}}" == "-p" && "${{2:-}}" == "process.versions.node" ]]; then
              printf '22.23.2\\n'
              exit 0
            fi
            cat >/dev/null
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
            printf 'pnpm %s cwd=%s path=%s\\n' "$*" "$PWD" "$PATH" >> "{command_log.as_posix()}"
            if [[ "${{1:-}}" == "--version" ]]; then
              printf '11.22.0\\n'
              exit 0
            fi
            if [[ "${{1:-}}" == "build" ]]; then
              mkdir -p "$PWD/dist"
              printf 'built\\n' > "$PWD/dist/index.html"
              exit 0
            fi
            exit 0
            """
        ),
    )
    _write_executable(
        fake_bin / "corepack",
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            set -euo pipefail
            printf 'corepack %s prompt=%s cwd=%s\\n' "$*" "${{COREPACK_ENABLE_DOWNLOAD_PROMPT:-}}" "$PWD" >> "{command_log.as_posix()}"
            if [[ "${{1:-}}" == "pnpm" && "${{2:-}}" == "--version" ]]; then
              if [[ "$PWD" == */frontend ]]; then
                printf '11.19.0\\n'
              else
                printf '11.22.0\\n'
              fi
              exit 0
            fi
            if [[ "${{1:-}}" == "pnpm" ]]; then
              shift
              exec "{(fake_bin / 'pnpm').as_posix()}" "$@"
            fi
            exit 0
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
            if [[ "${{1:-}}" == "-d" ]]; then
              shift
              mode=""
              owner=""
              group=""
              while [[ $# -gt 0 ]]; do
                case "$1" in
                  -m)
                    mode="$2"
                    shift 2
                    ;;
                  -o)
                    owner="$2"
                    shift 2
                    ;;
                  -g)
                    group="$2"
                    shift 2
                    ;;
                  *)
                    mkdir -p "$1"
                    [[ -n "${{mode}}" ]] && chmod "${{mode}}" "$1"
                    if [[ "${{mode}}" == "0750" && "${{owner}}" == "gxp" && "${{group}}" == "gxp" ]]; then
                      : > "$1/.app-writable"
                    fi
                    shift
                    ;;
                esac
              done
              exit 0
            fi
            exit 0
            """
        ),
    )
    _write_executable(
        fake_bin / "rsync",
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            set -euo pipefail
            src="${{@: -2:1}}"
            dest="${{@: -1}}"
            src_dir="${{src%/}}"
            dest_dir="${{dest%/}}"
            printf 'rsync src=%s dest=%s cwd=%s\\n' "${{src}}" "${{dest}}" "$PWD" >> "{command_log.as_posix()}"
            if [[ "${{src_dir}}" == */frontend/dist ]]; then
              if [[ ! -f "${{dest_dir}}/.app-writable" ]]; then
                printf 'rsync: [Receiver] change_dir#1 "%s/" failed: Permission denied (13)\\n' "${{dest_dir}}" >&2
                exit 13
              fi
              [[ -f "${{src_dir}}/index.html" ]] || exit 14
              : > "${{dest_dir}}/.app-copy-succeeded"
              exit 0
            fi
            if [[ -f "${{src_dir}}/.app-copy-succeeded" ]]; then
              printf 'frontend staging copied successfully\\n' >&2
              exit 44
            fi
            exit 0
            """
        ),
    )
    for name in ["systemctl", "curl", "nginx", "pg_dump", "chown"]:
        _write_executable(fake_bin / name, "#!/usr/bin/env bash\nset -euo pipefail\nexit 0\n")

    env = _base_env(fake_bin, runtime_env)
    env["DEPLOY_PROD_UNSAFE_SKIP_ROOT_CHECK"] = "1"
    env["HOME"] = _bash_style(fake_home)

    completed = _run_bash(f'PATH="{fake_bin_bash}:$PATH" ./infra/vm/deploy_prod.sh', env=env, cwd=ROOT)

    assert completed.returncode != 0
    assert "Deploy failed during stage: build_frontend" in completed.stderr
    assert "Permission denied (13)" not in completed.stderr
    assert "frontend staging copied successfully" in completed.stderr
    log_text = command_log.read_text(encoding="utf-8")
    assert "mktemp -d path=" in log_text
    assert "install -d -m 0750 -o gxp -g gxp" in log_text
    assert "corepack pnpm build prompt=0" in log_text
    assert "rsync src=" in log_text
    assert ".app-copy-succeeded" not in completed.stderr


def _run_deploy_render_runtime_assets_case(
    tmp_path: Path,
    *,
    systemd_verify_exit: int,
    uvicorn_present: bool = True,
    baseline_mode: str = "clean_first_deploy",
) -> tuple[subprocess.CompletedProcess[str], Path]:
    def _bash_style(path: Path) -> str:
        value = path.as_posix()
        if os.name == "nt" and len(value) >= 3 and value[1:3] == ":/":
            return f"/{value[0].lower()}{value[2:]}"
        return value

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    runtime_env = tmp_path / "runtime.env"
    export_root = tmp_path / "export-root"
    command_log = tmp_path / "command.log"
    python_sh = sys.executable.replace("\\", "/")
    release_sha = "00112233445566778899aabbccddeeff00112233"
    backend_releases_dir = tmp_path / "backend-releases"
    backend_venvs_dir = tmp_path / "backend-venvs"
    frontend_releases_dir = tmp_path / "frontend-releases"
    frontend_dist_dir = tmp_path / "frontend-dist"
    release_metadata_file = tmp_path / "current-release.json"
    tls_cert_path = tmp_path / "tls.crt"
    tls_key_path = tmp_path / "tls.key"
    mktemp_state_dir = tmp_path / "mktemp-state"
    mktemp_state_dir.mkdir()
    fake_bin_bash = _bash_style(fake_bin)
    (fake_home / ".bash_profile").write_text(
        f'export PATH="{fake_bin_bash}:$PATH"\n',
        encoding="utf-8",
        newline="\n",
    )
    (fake_home / ".profile").write_text(
        f'export PATH="{fake_bin_bash}:$PATH"\n',
        encoding="utf-8",
        newline="\n",
    )

    (export_root / "backend" / "app").mkdir(parents=True)
    (export_root / "frontend").mkdir(parents=True)
    (export_root / "infra" / "vm").mkdir(parents=True)
    (export_root / "tools").mkdir(parents=True)
    (export_root / "backend" / "requirements.runtime.vm.lock.txt").write_text("", encoding="utf-8", newline="\n")
    (export_root / "frontend" / "package.json").write_text(
        json.dumps({"name": "frontend", "packageManager": "pnpm@11.19.0"}) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (export_root / "backend" / "app" / "__init__.py").write_text("", encoding="utf-8")
    (export_root / "backend" / "app" / "config.py").write_text(
        textwrap.dedent(
            """\
            def resolve_database_url(env: dict[str, str]) -> str:
                return env["DATABASE_URL"]
            """
        ),
        encoding="utf-8",
        newline="\n",
    )
    (export_root / "alembic.ini").write_text("[alembic]\nscript_location = alembic\n", encoding="utf-8", newline="\n")
    (export_root / "tools" / "render_vm_runtime_assets.py").write_text(
        textwrap.dedent(
            f"""\
            import os
            from pathlib import Path
            import sys

            log_path = Path(r"{command_log.as_posix()}")
            target = Path(sys.argv[2])
            if sys.argv[1] == "service":
                working_directory = os.environ.get("VM_SERVICE_WORKING_DIRECTORY", os.environ["VM_CURRENT_BACKEND_RELEASE_LINK"])
                service_executable = os.environ.get("VM_SERVICE_EXECUTABLE", os.environ["VM_CURRENT_BACKEND_VENV_LINK"] + "/bin/uvicorn")
                service_environment_file = os.environ["VM_SERVICE_ENVIRONMENT_FILE"]
                rendered = (
                    "[Service]\\n"
                    f"WorkingDirectory={{working_directory}}\\n"
                    f"EnvironmentFile={{service_environment_file}}\\n"
                    f"ExecStart={{service_executable}} backend.app.main:app --host 127.0.0.1 --port 8000\\n"
                )
                log_path.open("a", encoding="utf-8").write(
                    f"render service -> {{target.as_posix()}} working={{working_directory}} envfile={{service_environment_file}} exec={{service_executable}}\\n"
                )
            else:
                rendered = "server {{}}\\n"
                log_path.open("a", encoding="utf-8").write(f"render nginx -> {{target.as_posix()}}\\n")
            target.write_text(rendered, encoding="utf-8")
            """
        ),
        encoding="utf-8",
        newline="\n",
    )
    backup_script = export_root / "infra" / "vm" / "backup_postgres.sh"
    backup_script.write_text(
        f"#!/usr/bin/env bash\nset -euo pipefail\necho backup reached >> \"{command_log.as_posix()}\"\nexit 46\n",
        encoding="utf-8",
        newline="\n",
    )
    backup_script.chmod(0o755)
    tls_cert_path.write_text("cert\n", encoding="utf-8", newline="\n")
    tls_key_path.write_text("key\n", encoding="utf-8", newline="\n")

    runtime_env.write_text(
        "\n".join(
            [
                "AUTH_PROVIDER=google_oidc",
                "AUTH_OIDC_CLIENT_ID=test-client-id",
                "AUTH_ALLOWED_EMAIL_DOMAIN=example.com",
                "DB_MODE=local_postgres",
                "DB_NAME=gxp_qlcl",
                "DB_USER=gxp_app",
                "DB_PASSWORD=secret",
                "DB_HOST=127.0.0.1",
                "DB_PORT=5432",
                "DATABASE_URL=postgresql+psycopg://gxp_app:secret@127.0.0.1:5432/gxp_qlcl",
                "STORAGE_CLASS=synology_smb",
                "STORAGE_INSPECTION_ROOT=//synology/inspection",
                "STORAGE_DKKD_ROOT=//synology/dkkd",
                "STORAGE_TEMPLATE_ROOT=//synology/templates",
                "SMB_USERNAME=smb-user",
                "SMB_PASSWORD=smb-password",
                f"VM_APP_ROOT={_bash_style(tmp_path)}",
                "VM_APP_USER=gxp",
                "VM_APP_GROUP=gxp",
                "VM_PYTHON_SERIES=3.12",
                f"VM_PYTHON_BIN={_bash_style(fake_bin / 'vm-python')}",
                f"VM_SRC_DIR={_bash_style(ROOT)}",
                f"VM_BACKEND_RELEASES_DIR={_bash_style(backend_releases_dir)}",
                f"VM_BACKEND_VENV_RELEASES_DIR={_bash_style(backend_venvs_dir)}",
                f"VM_CURRENT_BACKEND_RELEASE_LINK={_bash_style(tmp_path / 'current-backend')}",
                f"VM_CURRENT_BACKEND_VENV_LINK={_bash_style(tmp_path / 'current-venv')}",
                f"VM_FRONTEND_DIST_DIR={_bash_style(frontend_dist_dir)}",
                f"VM_FRONTEND_RELEASES_DIR={_bash_style(frontend_releases_dir)}",
                f"VM_RELEASE_METADATA_FILE={_bash_style(release_metadata_file)}",
                "VM_RELEASE_RETENTION_COUNT=3",
                "SYSTEMD_SERVICE_NAME=gxp-web",
                "NGINX_SITE_NAME=gxp-web",
                "PUBLIC_BASE_URL=https://example.com",
                f"VM_TLS_CERT_PATH={_bash_style(tls_cert_path)}",
                f"VM_TLS_KEY_PATH={_bash_style(tls_key_path)}",
                "VM_TLS_PROVISIONING_MODE=existing_files",
                "VM_NODE_MAJOR=22",
                "VM_NODE_MIN_VERSION=22.12.0",
                "VM_COREPACK_VERSION=0.31.0",
                "VM_NODE_PACKAGE_MANAGER=pnpm@11.19.0",
                "VM_NODE_BUILD_OPTIONS=--max-old-space-size=512",
                "VM_SUPPORTED_POSTGRES_MAJORS=17,18",
                "VM_SWAP_SIZE_GB=4",
                "VM_SWAPPINESS=10",
                "PG_SHARED_BUFFERS_MB=256",
                "PG_EFFECTIVE_CACHE_SIZE_MB=768",
                "PG_WORK_MEM_MB=4",
                "PG_MAINTENANCE_WORK_MEM_MB=64",
                "PG_AUTOVACUUM_WORK_MEM_MB=64",
                "PG_MAX_CONNECTIONS=30",
                "BACKUP_GCS_BUCKET=gs://gxp-backups",
            ]
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    current_backend_path = tmp_path / "current-backend"
    current_venv_path = tmp_path / "current-venv"
    current_frontend_path = tmp_path / "frontend-dist"
    previous_backend_release = backend_releases_dir / "prev-sha"
    previous_backend_venv = backend_venvs_dir / "prev-sha"
    previous_frontend_release = frontend_releases_dir / "prev-sha"
    if baseline_mode not in {"clean_first_deploy", "matching_metadata", "mixed_without_metadata", "mismatched_metadata"}:
        raise AssertionError(f"Unsupported baseline_mode: {baseline_mode}")
    if baseline_mode in {"matching_metadata", "mismatched_metadata"}:
        previous_backend_release.mkdir(parents=True, exist_ok=True)
        (previous_backend_venv / "bin").mkdir(parents=True, exist_ok=True)
        previous_frontend_release.mkdir(parents=True, exist_ok=True)
        current_backend_path.write_text(_bash_style(previous_backend_release), encoding="utf-8", newline="\n")
        current_venv_path.write_text(_bash_style(previous_backend_venv), encoding="utf-8", newline="\n")
        current_frontend_path.write_text(_bash_style(previous_frontend_release), encoding="utf-8", newline="\n")
        release_metadata_file.write_text(
            json.dumps(
                {
                    "current_sha": "prev-sha",
                    "backend_release_dir": (
                        _bash_style(backend_releases_dir / "different-sha")
                        if baseline_mode == "mismatched_metadata"
                        else _bash_style(previous_backend_release)
                    ),
                    "backend_venv_dir": _bash_style(previous_backend_venv),
                    "frontend_release_dir": _bash_style(previous_frontend_release),
                }
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
    elif baseline_mode == "mixed_without_metadata":
        current_backend_path.mkdir(parents=True, exist_ok=True)
        (current_venv_path / "bin").mkdir(parents=True, exist_ok=True)
        current_frontend_path.mkdir(parents=True, exist_ok=True)
        current_uvicorn = current_venv_path / "bin" / "uvicorn"
        current_uvicorn.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8", newline="\n")
        current_uvicorn.chmod(0o755)
    uvicorn_create_snippet = ""
    uvicorn_wrapper_entry = ""
    if uvicorn_present:
        uvicorn_create_snippet = (
            "uvicorn_impl = bin_dir / \"uvicorn_impl.py\"\n"
            "uvicorn_impl.write_text(\"raise SystemExit(0)\\\\n\", encoding=\"utf-8\", newline=\"\\\\n\")\n"
        )
        uvicorn_wrapper_entry = (
            "    \"uvicorn\": '#!/usr/bin/env bash\\nexec \"' + real_python + '\" \"' + uvicorn_impl.as_posix() + '\" \"$@\"\\n',\n"
        )

    python3_impl = tmp_path / "python3_impl.py"
    python3_impl.write_text(
        textwrap.dedent(
            f"""\
            import json
            import subprocess
            import sys
            from pathlib import Path

            real_python = r"{python_sh}"
            log_path = Path(r"{command_log.as_posix()}")
            args = sys.argv[1:]
            stdin_payload = sys.stdin.read()
            with log_path.open("a", encoding="utf-8") as fh:
                fh.write(f"system-python args={{args!r}}\\n")
            if args[:1] == ["-"] and "No successful deploy baseline metadata exists yet" in stdin_payload:
                metadata_path = Path(args[1])
                managed_paths = {{
                    "VM_CURRENT_BACKEND_RELEASE_LINK": Path(args[2]),
                    "VM_CURRENT_BACKEND_VENV_LINK": Path(args[3]),
                    "VM_FRONTEND_DIST_DIR": Path(args[4]),
                }}
                if not metadata_path.exists():
                    existing = {{name: path for name, path in managed_paths.items() if path.exists()}}
                    if existing:
                        details = ", ".join(f"{{name}}={{path}}" for name, path in existing.items())
                        sys.stderr.write(
                            "No successful deploy baseline metadata exists yet, but managed runtime paths are already present: "
                            + details
                            + ". Remove the mixed first-deploy baseline or restore a valid previous release before retrying.\\n"
                        )
                        raise SystemExit(1)
                    raise SystemExit(0)
                payload = json.loads(metadata_path.read_text(encoding="utf-8"))
                expected_targets = {{
                    "VM_CURRENT_BACKEND_RELEASE_LINK": str(payload.get("backend_release_dir", "")).strip(),
                    "VM_CURRENT_BACKEND_VENV_LINK": str(payload.get("backend_venv_dir", "")).strip(),
                    "VM_FRONTEND_DIST_DIR": str(payload.get("frontend_release_dir", "")).strip(),
                }}
                for name, expected_target in expected_targets.items():
                    current_path = managed_paths[name]
                    if not current_path.exists():
                        sys.stderr.write(
                            f"{{name}} must be a symlink matching {{metadata_path}}, but current path is missing or not a symlink: {{current_path}}\\n"
                        )
                        raise SystemExit(1)
                    actual_target = current_path.read_text(encoding="utf-8").strip()
                    if actual_target != expected_target:
                        sys.stderr.write(
                            f"{{name}} does not match release metadata {{metadata_path}}. Expected {{expected_target}}, got {{actual_target}}.\\n"
                        )
                        raise SystemExit(1)
                raise SystemExit(0)
            completed = subprocess.run([real_python, *args], input=stdin_payload, text=True, capture_output=True, check=False)
            sys.stdout.write(completed.stdout.replace("\\r\\n", "\\n"))
            sys.stderr.write(completed.stderr.replace("\\r\\n", "\\n"))
            raise SystemExit(completed.returncode)
            """
        ),
        encoding="utf-8",
        newline="\n",
    )
    _write_executable(fake_bin / "python3", f"#!/usr/bin/env bash\nexec \"{python_sh}\" \"{python3_impl.as_posix()}\" \"$@\"\n")

    vm_python_impl = tmp_path / "vm_python_impl.py"
    vm_python_impl_lines = [
        "import os",
        "import stat",
        "import sys",
        "from pathlib import Path",
        "",
        f'real_python = r"{python_sh}"',
        f'log_path = Path(r"{command_log.as_posix()}")',
        "args = sys.argv[1:]",
        'if args[:2] != ["-m", "venv"] or len(args) != 3:',
        "    raise SystemExit(2)",
        "",
        "venv_dir = Path(args[2])",
        'bin_dir = venv_dir / "bin"',
        "bin_dir.mkdir(parents=True, exist_ok=True)",
        'runtime_flag = venv_dir / ".runtime-installed"',
        "",
        'python_impl = bin_dir / "python_impl.py"',
        'python_impl.write_text(',
        '    (',
        '        "import os\\n"',
        '        "import sys\\n"',
        '        "from pathlib import Path\\n"',
        '        "runtime_flag = Path(sys.argv[1])\\n"',
        '        "stdin_payload = sys.stdin.read()\\n"',
        '        "if \\"from backend.app.config import resolve_database_url\\" in stdin_payload:\\n"',
        '        "    if not runtime_flag.exists():\\n"',
        '        "        raise SystemExit(1)\\n"',
        '        "    sys.stdout.write(os.environ[\\"DATABASE_URL\\"] + \\"\\\\n\\")\\n"',
        '        "    raise SystemExit(0)\\n"',
        '        "raise SystemExit(0)\\n"',
        '    ),',
        '    encoding="utf-8",',
        '    newline="\\n",',
        ')',
        "",
        'pip_impl = bin_dir / "pip_impl.py"',
        'pip_impl.write_text(',
        '    (',
        '        "import sys\\n"',
        '        "from pathlib import Path\\n"',
        '        "runtime_flag = Path(sys.argv[1])\\n"',
        '        "args = sys.argv[2:]\\n"',
        '        "if \\"-r\\" in args:\\n"',
        '        "    runtime_flag.write_text(\\"ready\\\\n\\", encoding=\\"utf-8\\")\\n"',
        '        "raise SystemExit(0)\\n"',
        '    ),',
        '    encoding="utf-8",',
        '    newline="\\n",',
        ')',
        "",
        'alembic_impl = bin_dir / "alembic_impl.py"',
        'alembic_impl.write_text("raise SystemExit(99)\\n", encoding="utf-8", newline="\\n")',
    ]
    if uvicorn_present:
        vm_python_impl_lines.extend(
            [
                'uvicorn_impl = bin_dir / "uvicorn_impl.py"',
                'uvicorn_impl.write_text("raise SystemExit(0)\\n", encoding="utf-8", newline="\\n")',
            ]
        )
    vm_python_impl_lines.extend(
        [
            "wrappers = {",
            '    "python": \'#!/usr/bin/env bash\\nexec "\' + real_python + \'" "\' + python_impl.as_posix() + \'" "\' + runtime_flag.as_posix() + \'" "$@"\\n\',',
            '    "pip": \'#!/usr/bin/env bash\\nexec "\' + real_python + \'" "\' + pip_impl.as_posix() + \'" "\' + runtime_flag.as_posix() + \'" "$@"\\n\',',
            '    "alembic": \'#!/usr/bin/env bash\\nexec "\' + real_python + \'" "\' + alembic_impl.as_posix() + \'" "$@"\\n\',',
        ]
    )
    if uvicorn_present:
        vm_python_impl_lines.append(
            '    "uvicorn": \'#!/usr/bin/env bash\\nexec "\' + real_python + \'" "\' + uvicorn_impl.as_posix() + \'" "$@"\\n\','
        )
    vm_python_impl_lines.extend(
        [
            "}",
            "for name, content in wrappers.items():",
            "    wrapper = bin_dir / name",
            '    wrapper.write_text(content, encoding="utf-8", newline="\\n")',
            "    wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)",
            "",
            'with log_path.open("a", encoding="utf-8") as fh:',
            '    fh.write(f"vm-python create-venv path={venv_dir.as_posix()}\\n")',
            "raise SystemExit(0)",
        ]
    )
    vm_python_impl.write_text("\n".join(vm_python_impl_lines) + "\n", encoding="utf-8", newline="\n")
    _write_executable(fake_bin / "vm-python", f"#!/usr/bin/env bash\nexec \"{python_sh}\" \"{vm_python_impl.as_posix()}\" \"$@\"\n")

    _write_executable(
        fake_bin / "runuser",
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            set -euo pipefail
            [[ "$1" == "-u" ]] || exit 2
            shift 2
            [[ "$1" == "--" ]] || exit 2
            shift
            cmd="$1"
            shift
            if [[ "$cmd" == "git" ]]; then
              exec "{(fake_bin / 'git').as_posix()}" "$@"
            fi
            exec "$cmd" "$@"
            """
        ),
    )
    git_impl = tmp_path / "git_impl.py"
    git_impl.write_text(
        textwrap.dedent(
            f"""\
            import sys
            import tarfile
            from pathlib import Path

            export_root = Path(r"{export_root.as_posix()}")
            release_sha = "{release_sha}"
            args = sys.argv[1:]
            if len(args) >= 2 and args[0] == "-C":
                args = args[2:]
            if args[:2] == ["status", "--porcelain"]:
                raise SystemExit(0)
            if args[:2] == ["fetch", "origin"]:
                raise SystemExit(0)
            if args[:2] == ["rev-parse", "--verify"]:
                sys.stdout.write(release_sha + "\\n")
                raise SystemExit(0)
            if args[:2] == ["archive", "--format=tar"]:
                with tarfile.open(fileobj=sys.stdout.buffer, mode="w|") as tar:
                    for path in sorted(export_root.rglob("*")):
                        tar.add(path, arcname=path.relative_to(export_root).as_posix(), recursive=False)
                raise SystemExit(0)
            raise SystemExit(1)
            """
        ),
        encoding="utf-8",
        newline="\n",
    )
    _write_executable(fake_bin / "git", f"#!/usr/bin/env bash\nexec \"{python_sh}\" \"{git_impl.as_posix()}\" \"$@\"\n")
    _write_executable(
        fake_bin / "mktemp",
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            set -euo pipefail
            state_dir="{mktemp_state_dir.as_posix()}"
            counter_file="${{state_dir}}/counter"
            count=0
            if [[ -f "${{counter_file}}" ]]; then
              count="$(cat "${{counter_file}}")"
            fi
            next=$((count + 1))
            printf '%s' "${{next}}" > "${{counter_file}}"
            if [[ "${{1:-}}" == "-d" ]]; then
              path="${{state_dir}}/tmpdir-${{next}}"
              mkdir -p "${{path}}"
              printf 'mktemp -d path=%s\\n' "${{path}}" >> "{command_log.as_posix()}"
              printf '%s\\n' "${{path}}"
              exit 0
            fi
            path="${{state_dir}}/tmpfile-${{next}}"
            : > "${{path}}"
            printf 'mktemp path=%s\\n' "${{path}}" >> "{command_log.as_posix()}"
            printf '%s\\n' "${{path}}"
            """
        ),
    )
    _write_executable(
        fake_bin / "node",
        "#!/usr/bin/env bash\nset -euo pipefail\nif [[ \"${1:-}\" == \"-p\" && \"${2:-}\" == \"process.versions.node\" ]]; then printf '22.23.2\\n'; exit 0; fi\ncat >/dev/null\n",
    )
    _write_executable(
        fake_bin / "pnpm",
        "#!/usr/bin/env bash\nset -euo pipefail\nif [[ \"${1:-}\" == \"--version\" ]]; then printf '11.22.0\\n'; exit 0; fi\nif [[ \"${1:-}\" == \"build\" ]]; then mkdir -p \"$PWD/dist\"; printf 'built\\n' > \"$PWD/dist/index.html\"; exit 0; fi\nexit 0\n",
    )
    _write_executable(
        fake_bin / "corepack",
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            set -euo pipefail
            if [[ "${1:-}" == "pnpm" && "${2:-}" == "--version" ]]; then
              if [[ "$PWD" == */frontend ]]; then
                printf '11.19.0\n'
              else
                printf '11.22.0\n'
              fi
              exit 0
            fi
            if [[ "${1:-}" == "pnpm" ]]; then
              shift
              exec pnpm "$@"
            fi
            exit 0
            """
        ),
    )
    _write_executable(
        fake_bin / "install",
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            set -euo pipefail
            if [[ "${1:-}" == "-d" ]]; then
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
            exit 0
            """
        ),
    )
    _write_executable(
        fake_bin / "rsync",
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            set -euo pipefail
            src="${@: -2:1}"
            dest="${@: -1}"
            src_dir="${src%/}"
            dest_dir="${dest%/}"
            mkdir -p "${dest_dir}"
            if [[ -d "${src_dir}" ]]; then
              cp -R "${src_dir}/." "${dest_dir}/"
            fi
            exit 0
            """
        ),
    )
    _write_executable(fake_bin / "systemctl", "#!/usr/bin/env bash\nset -euo pipefail\nexit 0\n")
    _write_executable(fake_bin / "curl", "#!/usr/bin/env bash\nset -euo pipefail\nexit 0\n")
    _write_executable(fake_bin / "nginx", "#!/usr/bin/env bash\nset -euo pipefail\nexit 0\n")
    _write_executable(fake_bin / "pg_dump", "#!/usr/bin/env bash\nset -euo pipefail\nexit 0\n")
    _write_executable(fake_bin / "chown", "#!/usr/bin/env bash\nset -euo pipefail\nexit 0\n")
    _write_executable(
        fake_bin / "systemd-analyze",
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            set -euo pipefail
            printf 'systemd-analyze %s\\n' "$*" >> "{command_log.as_posix()}"
            [[ "${{1:-}}" == "verify" ]] || exit 2
            target="${{2:-}}"
            if [[ "${{target}}" != *.service ]]; then
              printf 'Failed to prepare filename %s: Invalid argument\\n' "${{target}}" >&2
              exit 1
            fi
            grep -q "WorkingDirectory=.*/backend-releases/{release_sha}" "${{target}}" || {{ echo "validation unit missing immutable WorkingDirectory" >&2; exit 21; }}
            grep -q "ExecStart=.*/backend-venvs/{release_sha}/bin/uvicorn " "${{target}}" || {{ echo "validation unit missing immutable ExecStart" >&2; exit 22; }}
            if [[ {systemd_verify_exit} -ne 0 ]]; then
              printf 'synthetic unit validation failure for %s\\n' "${{target}}" >&2
              exit {systemd_verify_exit}
            fi
            exit 0
            """
        ),
    )

    env = _base_env(fake_bin, runtime_env)
    env["DEPLOY_PROD_UNSAFE_SKIP_ROOT_CHECK"] = "1"
    env["HOME"] = _bash_style(fake_home)

    completed = _run_bash(f'PATH="{fake_bin_bash}:$PATH" ./infra/vm/deploy_prod.sh', env=env, cwd=ROOT)
    return completed, command_log


def test_deploy_script_render_runtime_assets_uses_service_suffix_and_reaches_backup_on_verify_pass(tmp_path: Path):
    completed, command_log = _run_deploy_render_runtime_assets_case(tmp_path, systemd_verify_exit=0)

    assert completed.returncode != 0
    assert "Deploy failed during stage: database_backup" in completed.stderr
    assert "Failed to prepare filename" not in completed.stderr
    log_text = command_log.read_text(encoding="utf-8")
    current_backend = (tmp_path / "current-backend").as_posix()
    current_venv = (tmp_path / "current-venv").as_posix()
    render_lines = [line for line in log_text.splitlines() if line.startswith("render service -> ")]
    final_service_line = next(line for line in render_lines if "gxp-web.validation.service" not in line)
    validation_service_line = next(line for line in render_lines if "gxp-web.validation.service" in line)
    assert not (tmp_path / "current-backend").exists()
    assert not (tmp_path / "current-venv").exists()
    assert "render service -> " in log_text
    assert "gxp-web.service" in log_text
    assert "gxp-web.validation.service" in log_text
    assert "envfile=" in log_text
    assert "runtime.systemd.env" in log_text
    assert "render nginx -> " in log_text
    assert ".conf" in log_text
    assert "systemd-analyze verify" in log_text
    assert f"working={current_backend}" in log_text
    assert f"exec={current_venv}/bin/uvicorn" in log_text
    assert "envfile=" in final_service_line
    assert "runtime.systemd.env" in final_service_line
    assert str(tmp_path / "mktemp-state" / "tmpdir-2" / "runtime.systemd.env").replace("\\", "/") not in final_service_line
    assert str(tmp_path / "mktemp-state" / "tmpdir-2" / "runtime.systemd.env").replace("\\", "/") in validation_service_line
    assert ".validation.service working=" in log_text
    assert "backend-releases/00112233445566778899aabbccddeeff00112233" in log_text
    assert "backend-venvs/00112233445566778899aabbccddeeff00112233/bin/uvicorn" in log_text
    assert "backup reached" in log_text


def test_deploy_script_render_runtime_assets_fails_closed_on_systemd_verify_error(tmp_path: Path):
    completed, command_log = _run_deploy_render_runtime_assets_case(tmp_path, systemd_verify_exit=17)

    assert completed.returncode != 0
    assert "Deploy failed during stage: render_runtime_assets" in completed.stderr
    assert "synthetic unit validation failure" in completed.stderr
    assert "backup reached" not in command_log.read_text(encoding="utf-8")


def test_deploy_script_render_runtime_assets_rejects_missing_new_release_uvicorn(tmp_path: Path):
    completed, command_log = _run_deploy_render_runtime_assets_case(tmp_path, systemd_verify_exit=0, uvicorn_present=False)

    assert completed.returncode != 0
    assert "Deploy failed during stage: render_runtime_assets" in completed.stderr
    assert "New backend release venv is missing an executable uvicorn before service validation" in completed.stderr
    log_text = command_log.read_text(encoding="utf-8")
    assert "systemd-analyze verify" not in log_text
    assert "backup reached" not in log_text


def test_deploy_script_render_runtime_assets_existing_runtime_paths_still_verify_validation_unit(tmp_path: Path):
    completed, command_log = _run_deploy_render_runtime_assets_case(
        tmp_path,
        systemd_verify_exit=0,
        baseline_mode="matching_metadata",
    )

    assert completed.returncode != 0
    assert "Deploy failed during stage: database_backup" in completed.stderr
    log_text = command_log.read_text(encoding="utf-8")
    current_backend = (tmp_path / "current-backend").as_posix()
    current_venv = (tmp_path / "current-venv").as_posix()
    assert f"working={current_backend}" in log_text
    assert f"exec={current_venv}/bin/uvicorn" in log_text
    assert "gxp-web.validation.service" in log_text
    assert "backend-releases/00112233445566778899aabbccddeeff00112233" in log_text


def test_deploy_script_render_runtime_assets_rejects_mixed_first_deploy_baseline_without_metadata(tmp_path: Path):
    completed, command_log = _run_deploy_render_runtime_assets_case(
        tmp_path,
        systemd_verify_exit=0,
        baseline_mode="mixed_without_metadata",
    )

    assert completed.returncode != 0
    assert "Deploy failed during stage: pre_deploy_consistency_gate" in completed.stderr
    assert "No successful deploy baseline metadata exists yet" in completed.stderr
    assert "render service -> " not in command_log.read_text(encoding="utf-8")


def test_deploy_script_render_runtime_assets_rejects_metadata_mismatch_before_mutation(tmp_path: Path):
    completed, command_log = _run_deploy_render_runtime_assets_case(
        tmp_path,
        systemd_verify_exit=0,
        baseline_mode="mismatched_metadata",
    )

    assert completed.returncode != 0
    assert "Deploy failed during stage: pre_deploy_consistency_gate" in completed.stderr
    assert "does not match release metadata" in completed.stderr
    assert "render service -> " not in command_log.read_text(encoding="utf-8")


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
    createdb_impl = tmp_path / "createdb_impl.py"
    createdb_impl.write_text(
        (
            "import json\n"
            "import sys\n"
            "from pathlib import Path\n"
            f'state_path = Path(r"{state_file.as_posix()}")\n'
            f'log_path = Path(r"{command_log.as_posix()}")\n'
            'state = {"roles": {}, "databases": {}, "createdb_calls": 0}\n'
            "if state_path.exists():\n"
            '    state.update(json.loads(state_path.read_text(encoding="utf-8")))\n'
            "args = sys.argv[1:]\n"
            "owner = None\n"
            "db_name = None\n"
            "i = 0\n"
            "while i < len(args):\n"
            '    if args[i] == "--owner":\n'
            "        owner = args[i + 1]\n"
            "        i += 2\n"
            "        continue\n"
            "    db_name = args[i]\n"
            "    i += 1\n"
            'if owner not in state["roles"]:\n'
            '    sys.stderr.write(f"createdb:\\nERROR: role \\"{owner}\\" does not exist\\n")\n'
            "    raise SystemExit(1)\n"
            "if db_name is None:\n"
            "    raise SystemExit(2)\n"
            'state["createdb_calls"] = int(state.get("createdb_calls", 0)) + 1\n'
            'state["databases"][db_name] = {"owner": owner}\n'
            'state_path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")\n'
            'with log_path.open("a", encoding="utf-8") as fh:\n'
            '    fh.write(f"createdb {owner} {db_name}\\n")\n'
        ),
        encoding="utf-8",
        newline="\n",
    )
    _write_executable(fake_bin / "createdb", f"#!/usr/bin/env bash\nexec \"{python_sh}\" \"{createdb_impl.as_posix()}\" \"$@\"\n")
    psql_impl = tmp_path / "psql_impl.py"
    psql_impl.write_text(
        (
            "import json\n"
            "import os\n"
            "import sys\n"
            "from pathlib import Path\n"
            f'state_path = Path(r"{state_file.as_posix()}")\n'
            f'log_path = Path(r"{command_log.as_posix()}")\n'
            "def load_state() -> dict:\n"
            "    if state_path.exists():\n"
            '        return json.loads(state_path.read_text(encoding="utf-8"))\n'
            '    return {"roles": {}, "databases": {}, "createdb_calls": 0}\n'
            "def save_state(state: dict) -> None:\n"
            '    state_path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")\n'
            "def arg_value(args: list[str], option: str) -> str | None:\n"
            "    for index, arg in enumerate(args):\n"
            "        if arg == option and index + 1 < len(args):\n"
            "            return args[index + 1]\n"
            '        prefix = option + "="\n'
            "        if arg.startswith(prefix):\n"
            "            return arg[len(prefix):]\n"
            "    return None\n"
            "def set_values(args: list[str]) -> dict[str, str]:\n"
            "    values: dict[str, str] = {}\n"
            "    for index, arg in enumerate(args):\n"
            '        if arg == "--set" and index + 1 < len(args):\n'
            '            key, _, value = args[index + 1].partition("=")\n'
            "            values[key] = value\n"
            '        elif arg.startswith("--set="):\n'
            '            key, _, value = arg[len("--set="):].partition("=")\n'
            "            values[key] = value\n"
            "    return values\n"
            "args = sys.argv[1:]\n"
            "stdin_sql = sys.stdin.read()\n"
            'command_sql = ""\n'
            'if "-Atqc" in args:\n'
            '    command_sql = args[args.index("-Atqc") + 1]\n'
            'elif "-tc" in args:\n'
            '    command_sql = args[args.index("-tc") + 1]\n'
            'elif "-c" in args:\n'
            '    command_sql = args[args.index("-c") + 1]\n'
            "sets = set_values(args)\n"
            "on_error_stop = False\n"
            "for index, arg in enumerate(args):\n"
            '    if arg == "-v" and index + 1 < len(args) and args[index + 1] == "ON_ERROR_STOP=1":\n'
            "        on_error_stop = True\n"
            'with log_path.open("a", encoding="utf-8") as fh:\n'
            '    fh.write(f"psql args={args!r} stdin={stdin_sql!r} sql={command_sql!r}\\n")\n'
            "if not on_error_stop:\n"
            '    sys.stderr.write("missing ON_ERROR_STOP\\n")\n'
            "    raise SystemExit(1)\n"
            "state = load_state()\n"
            'if os.environ.get("PSQL_FORCE_ROLE_SQL_ERROR") == "1" and "CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD %L" in stdin_sql:\n'
            '    sys.stderr.write("ERROR: synthetic role setup failure\\n")\n'
            "    raise SystemExit(1)\n"
            'if "CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD %L" in stdin_sql:\n'
            '    db_user = sets["db_user"]\n'
            '    db_password = sets["db_password"]\n'
            '    state["roles"].setdefault(db_user, {})\n'
            '    state["roles"][db_user].update({"password": db_password, "login": True, "superuser": False, "createdb": False, "createrole": False})\n'
            "    save_state(state)\n"
            "    raise SystemExit(0)\n"
            'if "SELECT 1 FROM pg_database WHERE datname = :\'db_name\';" in stdin_sql:\n'
            '    if sets.get("db_name") in state["databases"]:\n'
            '        sys.stdout.write("1\\n")\n'
            "    raise SystemExit(0)\n"
            'if "SELECT 1 FROM pg_database WHERE datname = :\'target_db\';" in stdin_sql:\n'
            '    if sets.get("target_db") in state["databases"]:\n'
            '        sys.stdout.write("1\\n")\n'
            "    raise SystemExit(0)\n"
            'if command_sql == "SHOW server_version_num":\n'
            '    sys.stdout.write("180005\\n")\n'
            "    raise SystemExit(0)\n"
            'if "SELECT current_database() || E\'\\\\t\' || current_user" in command_sql:\n'
            '    db_name = arg_value(args, "--dbname")\n'
            '    db_user = arg_value(args, "--username")\n'
            '    db_host = arg_value(args, "--host")\n'
            '    db_port = arg_value(args, "--port")\n'
            '    role = state["roles"].get(db_user)\n'
            '    database = state["databases"].get(db_name)\n'
            '    if db_host != "127.0.0.1" or db_port != "5432" or role is None or database is None:\n'
            "        raise SystemExit(1)\n"
            '    if database["owner"] != db_user or role["password"] != os.environ.get("PGPASSWORD"):\n'
            "        raise SystemExit(1)\n"
            '    sys.stdout.write(f"{db_name}\\t{db_user}\\n")\n'
            "    raise SystemExit(0)\n"
            'if "SELECT version_num FROM alembic_version" in command_sql:\n'
            '    sys.stdout.write("123\\n")\n'
            "    raise SystemExit(0)\n"
            'if "SELECT current_database(), current_user;" in command_sql:\n'
            '    sys.stdout.write("ok\\n")\n'
            "    raise SystemExit(0)\n"
            "raise SystemExit(0)\n"
        ),
        encoding="utf-8",
        newline="\n",
    )
    _write_executable(fake_bin / "psql", f"#!/usr/bin/env bash\nexec \"{python_sh}\" \"{psql_impl.as_posix()}\" \"$@\"\n")
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
