#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
# shellcheck source=infra/vm/common.sh
source "${SCRIPT_DIR}/common.sh"

PLAN_JSON="$(mktemp)"
FRONTEND_BUILD_DIR=""
RUNTIME_ASSET_STAGING_DIR="$(mktemp -d)"
STAGED_SERVICE_FILE=""
VALIDATION_SERVICE_FILE=""
STAGED_NGINX_FILE=""
STAGED_SYSTEMD_ENV_FILE=""
PREVIOUS_SERVICE_FILE=""
PREVIOUS_NGINX_FILE=""
PREVIOUS_SYSTEMD_ENV_FILE=""
PREVIOUS_RELEASE_METADATA_FILE=""
SUCCESS=0
SWITCHED_RELEASES=0
SWITCHED_CONFIG=0
CURRENT_STAGE="bootstrap"
NEW_SHA=""
NEW_BACKEND_RELEASE=""
NEW_BACKEND_VENV=""
NEW_FRONTEND_RELEASE=""
ORIGINAL_FRONTEND_TARGET=""
ORIGINAL_BACKEND_RELEASE_TARGET=""
ORIGINAL_BACKEND_VENV_TARGET=""
FRONTEND_DIST_EXISTED_BEFORE=0
BACKEND_RELEASE_LINK_EXISTED_BEFORE=0
BACKEND_VENV_LINK_EXISTED_BEFORE=0
SYSTEMD_SERVICE_FILE_EXISTED_BEFORE=0
NGINX_SITE_FILE_EXISTED_BEFORE=0
NGINX_SITE_ENABLED_LINK_EXISTED_BEFORE=0
NGINX_SITE_ENABLED_LINK_TARGET_BEFORE=""
SYSTEMD_ENV_FILE_EXISTED_BEFORE=0
RELEASE_METADATA_FILE_EXISTED_BEFORE=0

restore_managed_symlink() {
  local path="$1"
  local existed_before="$2"
  local target_before="$3"
  local owner="$4"
  local group="$5"
  if [[ "${existed_before}" == "1" ]]; then
    ln -sfn "${target_before}" "${path}" || true
    chown -h "${owner}:${group}" "${path}" || true
  else
    rm -rf "${path}" || true
  fi
}

wait_for_http_endpoint() {
  local path="$1"
  local deadline_seconds="$2"
  local service_name="$3"
  local deadline=$((SECONDS + deadline_seconds))
  while (( SECONDS < deadline )); do
    local service_state
    service_state="$(systemctl is-active "${service_name}" 2>/dev/null || true)"
    case "${service_state}" in
      active|activating) ;;
      *)
        systemctl status --no-pager --lines=0 "${service_name}" >&2 || true
        fail "Service ${service_name} entered state ${service_state:-unknown} while waiting for ${path}. Hint: journalctl -u ${service_name} -n 100 --no-pager"
        ;;
    esac
    if curl -fsS "http://127.0.0.1:${APP_PORT}${path}" >/dev/null; then
      return 0
    fi
    sleep 1
  done
  systemctl status --no-pager --lines=0 "${service_name}" >&2 || true
  fail "Timed out waiting for ${path} on ${service_name}. Hint: journalctl -u ${service_name} -n 100 --no-pager"
}

render_runtime_asset() {
  local kind="$1"
  local output_path="$2"
  shift 2
  env \
    PUBLIC_BASE_URL="${PUBLIC_BASE_URL}" \
    NGINX_SERVER_NAME="${NGINX_SERVER_NAME}" \
    VM_APP_USER="${VM_APP_USER}" \
    VM_APP_GROUP="${VM_APP_GROUP}" \
    VM_CURRENT_BACKEND_RELEASE_LINK="${VM_CURRENT_BACKEND_RELEASE_LINK}" \
    VM_CURRENT_BACKEND_VENV_LINK="${VM_CURRENT_BACKEND_VENV_LINK}" \
    VM_RUNTIME_ENV_FILE="${RUNTIME_ENV_FILE}" \
    APP_PORT="${APP_PORT}" \
    GXP_FRONTEND_DIST_ROOT="${GXP_FRONTEND_DIST_ROOT}" \
    VM_TLS_CERT_PATH="${VM_TLS_CERT_PATH}" \
    VM_TLS_KEY_PATH="${VM_TLS_KEY_PATH}" \
    "$@" \
    python3 "${NEW_BACKEND_RELEASE}/tools/render_vm_runtime_assets.py" "${kind}" "${output_path}"
}

validate_pre_deploy_runtime_baseline() {
  python3 - \
    "${VM_RELEASE_METADATA_FILE}" \
    "${VM_CURRENT_BACKEND_RELEASE_LINK}" \
    "${VM_CURRENT_BACKEND_VENV_LINK}" \
    "${VM_FRONTEND_DIST_DIR}" <<'PY'
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

metadata_path = Path(sys.argv[1])
managed_paths = {
    "VM_CURRENT_BACKEND_RELEASE_LINK": Path(sys.argv[2]),
    "VM_CURRENT_BACKEND_VENV_LINK": Path(sys.argv[3]),
    "VM_FRONTEND_DIST_DIR": Path(sys.argv[4]),
}

def path_present(path: Path) -> bool:
    return path.exists() or path.is_symlink()

if not metadata_path.exists():
    existing = {name: path for name, path in managed_paths.items() if path_present(path)}
    if existing:
        details = ", ".join(f"{name}={path}" for name, path in existing.items())
        raise SystemExit(
            "No successful deploy baseline metadata exists yet, but managed runtime paths are already present: "
            f"{details}. Remove the mixed first-deploy baseline or restore a valid previous release before retrying."
        )
    raise SystemExit(0)

try:
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
except json.JSONDecodeError as exc:
    raise SystemExit(f"Invalid release metadata JSON at {metadata_path}: {exc}") from exc

expected_targets = {
    "VM_CURRENT_BACKEND_RELEASE_LINK": str(payload.get("backend_release_dir", "")).strip(),
    "VM_CURRENT_BACKEND_VENV_LINK": str(payload.get("backend_venv_dir", "")).strip(),
    "VM_FRONTEND_DIST_DIR": str(payload.get("frontend_release_dir", "")).strip(),
}

missing_keys = [name for name, value in expected_targets.items() if not value]
if missing_keys:
    raise SystemExit(
        f"Release metadata {metadata_path} is missing required target entries for: {', '.join(missing_keys)}."
    )

for name, path in managed_paths.items():
    if not path.is_symlink():
      raise SystemExit(f"{name} must be a symlink matching {metadata_path}, but current path is missing or not a symlink: {path}")
    actual_target = os.readlink(path)
    expected_target = expected_targets[name]
    if actual_target != expected_target:
        raise SystemExit(
            f"{name} does not match release metadata {metadata_path}. Expected {expected_target}, got {actual_target}."
        )
PY
}

validate_current_release_state() {
  python3 - \
    "${VM_CURRENT_BACKEND_RELEASE_LINK}" \
    "${VM_CURRENT_BACKEND_VENV_LINK}" \
    "${VM_FRONTEND_DIST_DIR}" \
    "${VM_SYSTEMD_ENV_FILE}" \
    "${VM_RELEASE_METADATA_FILE}" \
    "${NEW_SHA}" \
    "${DEPLOYMENT_GIT_SHORT_SHA}" \
    "${DEPLOYMENT_BRANCH}" \
    "${NEW_BACKEND_RELEASE}" \
    "${NEW_BACKEND_VENV}" \
    "${NEW_FRONTEND_RELEASE}" <<'PY'
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

ROOT = Path.cwd()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.env_utils import parse_systemd_env_file

backend_link = Path(sys.argv[1])
venv_link = Path(sys.argv[2])
frontend_link = Path(sys.argv[3])
systemd_env_file = Path(sys.argv[4])
release_metadata_file = Path(sys.argv[5])
expected_sha = sys.argv[6]
expected_short_sha = sys.argv[7]
expected_branch = sys.argv[8]
expected_backend_target = sys.argv[9]
expected_venv_target = sys.argv[10]
expected_frontend_target = sys.argv[11]

for path, expected_target in (
    (backend_link, expected_backend_target),
    (venv_link, expected_venv_target),
    (frontend_link, expected_frontend_target),
):
    if not path.is_symlink():
        raise SystemExit(f"Managed release path is missing or not a symlink: {path}")
    actual_target = os.readlink(path)
    if actual_target != expected_target:
        raise SystemExit(f"Managed release path {path} expected {expected_target}, got {actual_target}.")

runtime_values = parse_systemd_env_file(systemd_env_file)
if runtime_values.get("DEPLOYMENT_GIT_SHA", "").strip() != expected_sha:
    raise SystemExit(
        f"Runtime deployment metadata mismatch in {systemd_env_file}: expected DEPLOYMENT_GIT_SHA={expected_sha}."
    )
if runtime_values.get("DEPLOYMENT_GIT_SHORT_SHA", "").strip() != expected_short_sha:
    raise SystemExit(
        f"Runtime deployment metadata mismatch in {systemd_env_file}: expected DEPLOYMENT_GIT_SHORT_SHA={expected_short_sha}."
    )
if runtime_values.get("DEPLOYMENT_BRANCH", "").strip() != expected_branch:
    raise SystemExit(
        f"Runtime deployment metadata mismatch in {systemd_env_file}: expected DEPLOYMENT_BRANCH={expected_branch}."
    )

payload = json.loads(release_metadata_file.read_text(encoding="utf-8"))
if str(payload.get("current_sha", "")).strip() != expected_sha:
    raise SystemExit(f"Release metadata {release_metadata_file} current_sha does not match expected {expected_sha}.")
PY
}

cleanup() {
  if [[ "${SUCCESS}" != "1" && "${SWITCHED_CONFIG}" == "1" ]]; then
    if [[ "${SYSTEMD_SERVICE_FILE_EXISTED_BEFORE}" == "1" && -s "${PREVIOUS_SERVICE_FILE}" ]]; then
      cp "${PREVIOUS_SERVICE_FILE}" "/etc/systemd/system/${SYSTEMD_SERVICE_NAME}.service" || true
    else
      rm -f "/etc/systemd/system/${SYSTEMD_SERVICE_NAME}.service" || true
    fi
    if [[ "${NGINX_SITE_FILE_EXISTED_BEFORE}" == "1" && -s "${PREVIOUS_NGINX_FILE}" ]]; then
      cp "${PREVIOUS_NGINX_FILE}" "/etc/nginx/sites-available/${NGINX_SITE_NAME}.conf" || true
    else
      rm -f "/etc/nginx/sites-available/${NGINX_SITE_NAME}.conf" || true
    fi
    if [[ "${NGINX_SITE_ENABLED_LINK_EXISTED_BEFORE}" == "1" ]]; then
      ln -sfn "${NGINX_SITE_ENABLED_LINK_TARGET_BEFORE}" "/etc/nginx/sites-enabled/${NGINX_SITE_NAME}.conf" || true
    else
      rm -f "/etc/nginx/sites-enabled/${NGINX_SITE_NAME}.conf" || true
    fi
    if [[ "${SYSTEMD_ENV_FILE_EXISTED_BEFORE}" == "1" && -s "${PREVIOUS_SYSTEMD_ENV_FILE}" ]]; then
      cp "${PREVIOUS_SYSTEMD_ENV_FILE}" "${VM_SYSTEMD_ENV_FILE}" || true
      chown "root:${VM_APP_GROUP}" "${VM_SYSTEMD_ENV_FILE}" || true
      chmod 0640 "${VM_SYSTEMD_ENV_FILE}" || true
    else
      rm -f "${VM_SYSTEMD_ENV_FILE}" || true
    fi
    if [[ "${RELEASE_METADATA_FILE_EXISTED_BEFORE}" == "1" && -s "${PREVIOUS_RELEASE_METADATA_FILE}" ]]; then
      cp "${PREVIOUS_RELEASE_METADATA_FILE}" "${VM_RELEASE_METADATA_FILE}" || true
    else
      rm -f "${VM_RELEASE_METADATA_FILE}" || true
    fi
    systemctl daemon-reload >/dev/null 2>&1 || true
  fi
  if [[ "${SUCCESS}" != "1" && "${SWITCHED_RELEASES}" == "1" ]]; then
    restore_managed_symlink "${VM_FRONTEND_DIST_DIR}" "${FRONTEND_DIST_EXISTED_BEFORE}" "${ORIGINAL_FRONTEND_TARGET}" "${VM_APP_USER}" "${VM_APP_GROUP}"
    restore_managed_symlink "${VM_CURRENT_BACKEND_RELEASE_LINK}" "${BACKEND_RELEASE_LINK_EXISTED_BEFORE}" "${ORIGINAL_BACKEND_RELEASE_TARGET}" "${VM_APP_USER}" "${VM_APP_GROUP}"
    restore_managed_symlink "${VM_CURRENT_BACKEND_VENV_LINK}" "${BACKEND_VENV_LINK_EXISTED_BEFORE}" "${ORIGINAL_BACKEND_VENV_TARGET}" "${VM_APP_USER}" "${VM_APP_GROUP}"
    systemctl restart "${SYSTEMD_SERVICE_NAME}" >/dev/null 2>&1 || true
    systemctl restart nginx >/dev/null 2>&1 || true
  fi
  rm -f "${PLAN_JSON}"
  if [[ -n "${RUNTIME_ASSET_STAGING_DIR}" ]]; then
    rm -rf "${RUNTIME_ASSET_STAGING_DIR}"
  fi
  if [[ -n "${FRONTEND_BUILD_DIR}" ]]; then
    rm -rf "${FRONTEND_BUILD_DIR}"
  fi
  if [[ "${SUCCESS}" != "1" ]]; then
    echo "Deploy failed during stage: ${CURRENT_STAGE}" >&2
  fi
}
trap cleanup EXIT

cd "${REPO_ROOT}"
if [[ "${DEPLOY_PROD_UNSAFE_SKIP_ROOT_CHECK:-0}" != "1" ]]; then
  require_root
fi

json_query() {
  local expr="$1"
  python3 - "$PLAN_JSON" "$expr" <<'PY'
import json
import sys

payload = json.loads(open(sys.argv[1], encoding="utf-8").read())["plan"]
value = payload
for part in sys.argv[2].split("."):
    if not part:
        continue
    value = value[part]
if isinstance(value, bool):
    print("true" if value else "false")
else:
    print(value)
PY
}

normalize_repo_path() {
  python3 - "$1" <<'PY'
from pathlib import PurePosixPath, PureWindowsPath
import sys

value = sys.argv[1].strip()
if len(value) >= 3 and value[0] == "/" and value[2] == "/" and value[1].isalpha():
    value = f"{value[1].upper()}:{value[2:]}"
if len(value) >= 2 and value[1] == ":":
    print(PureWindowsPath(value).as_posix().lower())
else:
    print(PurePosixPath(value).as_posix().lower())
PY
}

readlink_safe() {
  local path="$1"
  if [[ -L "${path}" ]]; then
    readlink "${path}"
  else
    return 1
  fi
}

assert_tls_files_exist() {
  [[ -f "${VM_TLS_CERT_PATH}" ]] || fail "TLS certificate file not found: ${VM_TLS_CERT_PATH}. Provision HTTPS certificates before the first deploy."
  [[ -f "${VM_TLS_KEY_PATH}" ]] || fail "TLS private key file not found: ${VM_TLS_KEY_PATH}. Provision HTTPS certificates before the first deploy."
}

prune_release_dirs() {
  local root_dir="$1"
  local retention_count="$2"
  shift 2
  local protected_names=("$@")
  local protected_csv
  protected_csv="$(IFS=,; echo "${protected_names[*]}")"
  python3 - "$root_dir" "$retention_count" "$protected_csv" <<'PY'
from __future__ import annotations

from pathlib import Path
import os
import shutil
import sys

root = Path(sys.argv[1])
retention = int(sys.argv[2])
protected = {item for item in sys.argv[3].split(",") if item}
if not root.exists():
    raise SystemExit(0)

entries = [item for item in root.iterdir() if item.is_dir()]
entries.sort(key=lambda item: item.stat().st_mtime, reverse=True)
keep: set[str] = set(protected)
for item in entries:
    if len(keep) >= retention:
        break
    keep.add(item.name)

for item in entries:
    if item.name in keep:
        continue
    shutil.rmtree(item)
PY
}

RUNTIME_ENV_FILE="${VM_RUNTIME_ENV_FILE:-/etc/gxp/runtime.env}"
load_runtime_env "${RUNTIME_ENV_FILE}"

need_cmd python3
need_cmd git
need_cmd tar
need_cmd systemctl
need_cmd curl
need_cmd nginx
need_cmd pg_dump
need_cmd rsync
need_cmd node
need_cmd pnpm
need_cmd corepack

CURRENT_STAGE="validate_runtime_contract"
python3 tools/validate_vm_prod_deploy.py >"${PLAN_JSON}" || {
  cat "${PLAN_JSON}" >&2
  fail "VM production deploy validation failed."
}

VM_APP_USER="${VM_APP_USER:-$(json_query app_user)}"
VM_APP_GROUP="${VM_APP_GROUP:-$(json_query app_group)}"
APP_PORT="${APP_PORT:-$(json_query app_port)}"
VM_PYTHON_BIN="${VM_PYTHON_BIN:-$(json_query python_bin)}"
VM_SRC_DIR="$(json_query vm_src_dir)"
VM_BACKEND_RELEASES_DIR="$(json_query vm_backend_releases_dir)"
VM_BACKEND_VENV_RELEASES_DIR="$(json_query vm_backend_venv_releases_dir)"
VM_CURRENT_BACKEND_RELEASE_LINK="$(json_query vm_current_backend_release_link)"
VM_CURRENT_BACKEND_VENV_LINK="$(json_query vm_current_backend_venv_link)"
VM_FRONTEND_DIST_DIR="$(json_query vm_frontend_dist_dir)"
VM_FRONTEND_RELEASES_DIR="$(json_query vm_frontend_releases_dir)"
VM_SYSTEMD_ENV_FILE="$(json_query vm_systemd_env_file)"
VM_RELEASE_METADATA_FILE="$(json_query vm_release_metadata_file)"
VM_RELEASE_RETENTION_COUNT="$(json_query vm_release_retention_count)"
SYSTEMD_SERVICE_NAME="$(json_query systemd_service_name)"
NGINX_SITE_NAME="$(json_query nginx_site_name)"
NGINX_SERVER_NAME="$(json_query nginx_server_name)"
NODE_MIN_VERSION="$(json_query node_min_version)"
NODE_PACKAGE_MANAGER="$(json_query node_package_manager)"
NODE_BUILD_OPTIONS="$(json_query node_build_options)"
RUNTIME_REQUIREMENTS_LOCK_FILE="$(json_query runtime_requirements_lock_file)"
VM_TLS_CERT_PATH="$(json_query tls_cert_path)"
VM_TLS_KEY_PATH="$(json_query tls_key_path)"
GXP_FRONTEND_DIST_ROOT="${GXP_FRONTEND_DIST_ROOT:-${VM_FRONTEND_DIST_DIR}}"
export GXP_FRONTEND_DIST_ROOT
FRONTEND_BUILD_DIR="$(mktemp -d)"
install -d -m 0750 -o "${VM_APP_USER}" -g "${VM_APP_GROUP}" "${FRONTEND_BUILD_DIR}"
STAGED_SERVICE_FILE="${RUNTIME_ASSET_STAGING_DIR}/${SYSTEMD_SERVICE_NAME}.service"
VALIDATION_SERVICE_FILE="${RUNTIME_ASSET_STAGING_DIR}/${SYSTEMD_SERVICE_NAME}.validation.service"
STAGED_NGINX_FILE="${RUNTIME_ASSET_STAGING_DIR}/${NGINX_SITE_NAME}.conf"
STAGED_SYSTEMD_ENV_FILE="${RUNTIME_ASSET_STAGING_DIR}/$(basename "${VM_SYSTEMD_ENV_FILE}")"
PREVIOUS_SERVICE_FILE="${RUNTIME_ASSET_STAGING_DIR}/${SYSTEMD_SERVICE_NAME}.previous.service"
PREVIOUS_NGINX_FILE="${RUNTIME_ASSET_STAGING_DIR}/${NGINX_SITE_NAME}.previous.conf"
PREVIOUS_SYSTEMD_ENV_FILE="${RUNTIME_ASSET_STAGING_DIR}/$(basename "${VM_SYSTEMD_ENV_FILE}").previous"
PREVIOUS_RELEASE_METADATA_FILE="${RUNTIME_ASSET_STAGING_DIR}/$(basename "${VM_RELEASE_METADATA_FILE}").previous.json"

REPO_ROOT_NORMALIZED="$(normalize_repo_path "${REPO_ROOT}")"
VM_SRC_DIR_NORMALIZED="$(normalize_repo_path "${VM_SRC_DIR}")"
[[ "${REPO_ROOT_NORMALIZED}" == "${VM_SRC_DIR_NORMALIZED}" ]] || fail "deploy_prod.sh must run from VM_SRC_DIR=${VM_SRC_DIR}, but current checkout is ${REPO_ROOT}."
[[ -x "${VM_PYTHON_BIN}" ]] || fail "Supported production Python interpreter not found: ${VM_PYTHON_BIN}"

CURRENT_STAGE="clean_git_check"
if [[ -n "$(run_as_app_user git -C "${REPO_ROOT}" status --porcelain)" ]]; then
  fail "Working tree is dirty or contains untracked non-ignored files. Refusing deploy."
fi

CURRENT_STAGE="pre_deploy_consistency_gate"
validate_pre_deploy_runtime_baseline

CURRENT_STAGE="resolve_release_targets"
if [[ -L "${VM_FRONTEND_DIST_DIR}" ]]; then
  FRONTEND_DIST_EXISTED_BEFORE=1
  ORIGINAL_FRONTEND_TARGET="$(readlink_safe "${VM_FRONTEND_DIST_DIR}" || true)"
fi
if [[ -L "${VM_CURRENT_BACKEND_RELEASE_LINK}" ]]; then
  BACKEND_RELEASE_LINK_EXISTED_BEFORE=1
  ORIGINAL_BACKEND_RELEASE_TARGET="$(readlink_safe "${VM_CURRENT_BACKEND_RELEASE_LINK}" || true)"
fi
if [[ -L "${VM_CURRENT_BACKEND_VENV_LINK}" ]]; then
  BACKEND_VENV_LINK_EXISTED_BEFORE=1
  ORIGINAL_BACKEND_VENV_TARGET="$(readlink_safe "${VM_CURRENT_BACKEND_VENV_LINK}" || true)"
fi
if [[ -f "/etc/systemd/system/${SYSTEMD_SERVICE_NAME}.service" ]]; then
  SYSTEMD_SERVICE_FILE_EXISTED_BEFORE=1
fi
if [[ -f "/etc/nginx/sites-available/${NGINX_SITE_NAME}.conf" ]]; then
  NGINX_SITE_FILE_EXISTED_BEFORE=1
fi
if [[ -L "/etc/nginx/sites-enabled/${NGINX_SITE_NAME}.conf" ]]; then
  NGINX_SITE_ENABLED_LINK_EXISTED_BEFORE=1
  NGINX_SITE_ENABLED_LINK_TARGET_BEFORE="$(readlink_safe "/etc/nginx/sites-enabled/${NGINX_SITE_NAME}.conf" || true)"
fi
if [[ -f "${VM_SYSTEMD_ENV_FILE}" ]]; then
  SYSTEMD_ENV_FILE_EXISTED_BEFORE=1
fi
if [[ -f "${VM_RELEASE_METADATA_FILE}" ]]; then
  RELEASE_METADATA_FILE_EXISTED_BEFORE=1
fi

TARGET_SHA="${DEPLOY_GIT_SHA:-}"
DEPLOY_BRANCH="${DEPLOY_BRANCH:-$(json_query deploy_branch)}"

CURRENT_STAGE="git_fetch"
run_as_app_user git -C "${REPO_ROOT}" fetch origin
if [[ -z "${TARGET_SHA}" ]]; then
  TARGET_SHA="$(run_as_app_user git -C "${REPO_ROOT}" rev-parse --verify "origin/${DEPLOY_BRANCH}^{commit}")" || fail "Could not resolve origin/${DEPLOY_BRANCH}."
else
  run_as_app_user git -C "${REPO_ROOT}" rev-parse --verify "${TARGET_SHA}^{commit}" >/dev/null 2>&1 || fail "DEPLOY_GIT_SHA is not a valid commit: ${TARGET_SHA}"
fi
NEW_SHA="${TARGET_SHA}"
DEPLOYMENT_GIT_SHA="${NEW_SHA}"
DEPLOYMENT_GIT_SHORT_SHA="${NEW_SHA:0:7}"
DEPLOYMENT_BRANCH="${DEPLOY_BRANCH}"
NEW_BACKEND_RELEASE="${VM_BACKEND_RELEASES_DIR}/${NEW_SHA}"
NEW_BACKEND_VENV="${VM_BACKEND_VENV_RELEASES_DIR}/${NEW_SHA}"
NEW_FRONTEND_RELEASE="${VM_FRONTEND_RELEASES_DIR}/${NEW_SHA}"

CURRENT_STAGE="release_directories"
install -d -m 0755 -o "${VM_APP_USER}" -g "${VM_APP_GROUP}" \
  "${VM_BACKEND_RELEASES_DIR}" \
  "${VM_BACKEND_VENV_RELEASES_DIR}" \
  "${VM_FRONTEND_RELEASES_DIR}"
run_as_app_bash "
  rm -rf '${NEW_BACKEND_RELEASE}' '${NEW_BACKEND_VENV}' '${NEW_FRONTEND_RELEASE}'
  mkdir -p '${NEW_BACKEND_RELEASE}' '${NEW_FRONTEND_RELEASE}'
"

CURRENT_STAGE="export_backend_release"
run_as_app_bash "
  cd '${REPO_ROOT}'
  git archive --format=tar '${TARGET_SHA}' | tar -xf - -C '${NEW_BACKEND_RELEASE}'
"

[[ -f "${NEW_BACKEND_RELEASE}/${RUNTIME_REQUIREMENTS_LOCK_FILE}" ]] || fail "Release lockfile missing: ${NEW_BACKEND_RELEASE}/${RUNTIME_REQUIREMENTS_LOCK_FILE}"
[[ -f "${NEW_BACKEND_RELEASE}/frontend/package.json" ]] || fail "Release frontend package manifest missing: ${NEW_BACKEND_RELEASE}/frontend/package.json"

CURRENT_STAGE="node_version_check"
CURRENT_NODE_VERSION="$(node -p 'process.versions.node')" || fail "Could not determine the active Node.js runtime version."
CURRENT_NODE_VERSION="$(
  python3 - "${CURRENT_NODE_VERSION}" "${NODE_MIN_VERSION}" <<'PY'
import sys

current_text = sys.argv[1]
required_text = sys.argv[2]
required = tuple(int(part) for part in required_text.split("."))
current = tuple(int(part) for part in current_text.split("."))
if current < required:
    raise SystemExit(f"Node.js version {current_text} is lower than required minimum {required_text}.")
print(current_text)
PY
)" || fail "Node.js version check failed."
FRONTEND_PACKAGE_MANAGER="$(
  python3 - "${NEW_BACKEND_RELEASE}/frontend/package.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as fh:
    payload = json.load(fh)
package_manager = payload.get("packageManager", "")
if not isinstance(package_manager, str):
    raise SystemExit(1)
print(package_manager)
PY
)" || fail "Could not read frontend/package.json packageManager."
[[ -n "${FRONTEND_PACKAGE_MANAGER}" ]] || fail "frontend/package.json must declare packageManager."
[[ "${FRONTEND_PACKAGE_MANAGER}" == "${NODE_PACKAGE_MANAGER}" ]] || fail "frontend/package.json packageManager mismatch. Expected ${NODE_PACKAGE_MANAGER}, got ${FRONTEND_PACKAGE_MANAGER}."
CURRENT_PNPM_VERSION="$(
  cd "${NEW_BACKEND_RELEASE}/frontend"
  command -v node >/dev/null || fail "Node.js is not available in the frontend release directory."
  command -v corepack >/dev/null || fail "Corepack is not available in the frontend release directory."
  command -v pnpm >/dev/null || fail "pnpm is not available in the frontend release directory."
  COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack pnpm --version
)" || fail "Could not determine the Corepack-managed pnpm version in the frontend release directory."
[[ "${CURRENT_PNPM_VERSION}" == "${NODE_PACKAGE_MANAGER#pnpm@}" ]] || fail "pnpm version mismatch in frontend release directory. Expected ${NODE_PACKAGE_MANAGER#pnpm@}, got ${CURRENT_PNPM_VERSION}."

CURRENT_STAGE="build_backend_venv"
run_as_app_user "${VM_PYTHON_BIN}" -m venv "${NEW_BACKEND_VENV}"
run_as_app_user "${NEW_BACKEND_VENV}/bin/pip" install --upgrade pip
run_as_app_user "${NEW_BACKEND_VENV}/bin/pip" install --no-cache-dir -r "${NEW_BACKEND_RELEASE}/${RUNTIME_REQUIREMENTS_LOCK_FILE}"

CURRENT_STAGE="resolve_database_url"
DATABASE_URL="$(
  run_as_app_bash "
    cd '${NEW_BACKEND_RELEASE}'
    env -u PYTHONHOME PYTHONPATH='${NEW_BACKEND_RELEASE}' '${NEW_BACKEND_VENV}/bin/python' - <<'PY'
from backend.app.config import resolve_database_url
import os

print(resolve_database_url(dict(os.environ)))
PY
  "
)"
[[ -n "${DATABASE_URL}" ]] || fail "DATABASE_URL must resolve non-empty before deploy."
case "${DATABASE_URL}" in
  postgresql://*|postgresql+*://*) ;;
  sqlite:*) fail "DATABASE_URL must not resolve to SQLite in production." ;;
  *) fail "DATABASE_URL must resolve to PostgreSQL before deploy." ;;
esac
CURRENT_STAGE="render_systemd_runtime_env"
python3 tools/runtime_env.py write-systemd "${RUNTIME_ENV_FILE}" "${STAGED_SYSTEMD_ENV_FILE}" \
  "DEPLOYMENT_GIT_SHA=${DEPLOYMENT_GIT_SHA}" \
  "DEPLOYMENT_GIT_SHORT_SHA=${DEPLOYMENT_GIT_SHORT_SHA}" \
  "DEPLOYMENT_BRANCH=${DEPLOYMENT_BRANCH}"

CURRENT_STAGE="build_frontend"
run_as_app_bash "
  export NODE_OPTIONS='${NODE_BUILD_OPTIONS}'
  export COREPACK_ENABLE_DOWNLOAD_PROMPT=0
  export PATH=\"${NEW_BACKEND_VENV}/bin:\${PATH}\"
  cd '${NEW_BACKEND_RELEASE}/frontend'
  command -v node >/dev/null || { echo 'Node.js is not available in the app-user frontend build shell.' >&2; exit 1; }
  command -v corepack >/dev/null || { echo 'Corepack is not available in the app-user frontend build shell.' >&2; exit 1; }
  command -v pnpm >/dev/null || { echo 'pnpm is not available in the app-user frontend build shell.' >&2; exit 1; }
  command -v rsync >/dev/null || { echo 'rsync is not available in the app-user frontend build shell.' >&2; exit 1; }
  current_pnpm_version=\"\$(corepack pnpm --version)\"
  [[ \"\${current_pnpm_version}\" == '${NODE_PACKAGE_MANAGER#pnpm@}' ]] || { echo \"pnpm version mismatch in the app-user frontend build shell. Expected ${NODE_PACKAGE_MANAGER#pnpm@}, got \${current_pnpm_version}.\" >&2; exit 1; }
  corepack pnpm install --frozen-lockfile
  corepack pnpm build
  rsync -a --delete '${NEW_BACKEND_RELEASE}/frontend/dist/' '${FRONTEND_BUILD_DIR}/'
"
rsync -a --delete "${FRONTEND_BUILD_DIR}/" "${NEW_FRONTEND_RELEASE}/"
chown -R "${VM_APP_USER}:${VM_APP_GROUP}" "${NEW_FRONTEND_RELEASE}"

CURRENT_STAGE="storage_readiness_check"
run_as_app_bash "
  cd '${NEW_BACKEND_RELEASE}'
  env -u PYTHONHOME PYTHONPATH='${NEW_BACKEND_RELEASE}' '${NEW_BACKEND_VENV}/bin/python' - <<'PY'
from backend.app.storage.factory import create_storage_service_from_env
import os

service = create_storage_service_from_env(dict(os.environ))
service.list('')
PY
"

CURRENT_STAGE="render_runtime_assets"
assert_tls_files_exist
render_runtime_asset service "${STAGED_SERVICE_FILE}" \
  VM_SERVICE_ENVIRONMENT_FILE="${VM_SYSTEMD_ENV_FILE}"
[[ -d "${NEW_BACKEND_RELEASE}" ]] || fail "New backend release directory is missing before service validation: ${NEW_BACKEND_RELEASE}"
[[ -x "${NEW_BACKEND_VENV}/bin/uvicorn" ]] || fail "New backend release venv is missing an executable uvicorn before service validation: ${NEW_BACKEND_VENV}/bin/uvicorn"
render_runtime_asset service "${VALIDATION_SERVICE_FILE}" \
  VM_SERVICE_WORKING_DIRECTORY="${NEW_BACKEND_RELEASE}" \
  VM_SERVICE_EXECUTABLE="${NEW_BACKEND_VENV}/bin/uvicorn" \
  VM_SERVICE_ENVIRONMENT_FILE="${STAGED_SYSTEMD_ENV_FILE}"
render_runtime_asset nginx "${STAGED_NGINX_FILE}"
if command -v systemd-analyze >/dev/null 2>&1; then
  systemd-analyze verify "${VALIDATION_SERVICE_FILE}" >/dev/null
fi

CURRENT_STAGE="database_backup"
run_as_app_user "${NEW_BACKEND_RELEASE}/infra/vm/backup_postgres.sh"

CURRENT_STAGE="alembic_upgrade"
run_as_app_user env DATABASE_URL="${DATABASE_URL}" "${NEW_BACKEND_VENV}/bin/alembic" -c "${NEW_BACKEND_RELEASE}/alembic.ini" upgrade head

CURRENT_STAGE="switch_release_symlinks"
if [[ -f "/etc/systemd/system/${SYSTEMD_SERVICE_NAME}.service" ]]; then
  cp "/etc/systemd/system/${SYSTEMD_SERVICE_NAME}.service" "${PREVIOUS_SERVICE_FILE}"
fi
if [[ -f "/etc/nginx/sites-available/${NGINX_SITE_NAME}.conf" ]]; then
  cp "/etc/nginx/sites-available/${NGINX_SITE_NAME}.conf" "${PREVIOUS_NGINX_FILE}"
fi
if [[ -f "${VM_SYSTEMD_ENV_FILE}" ]]; then
  cp "${VM_SYSTEMD_ENV_FILE}" "${PREVIOUS_SYSTEMD_ENV_FILE}"
fi
if [[ -f "${VM_RELEASE_METADATA_FILE}" ]]; then
  cp "${VM_RELEASE_METADATA_FILE}" "${PREVIOUS_RELEASE_METADATA_FILE}"
fi
cp "${STAGED_SERVICE_FILE}" "/etc/systemd/system/${SYSTEMD_SERVICE_NAME}.service"
cp "${STAGED_NGINX_FILE}" "/etc/nginx/sites-available/${NGINX_SITE_NAME}.conf"
install -d -m 0755 "$(dirname "${VM_SYSTEMD_ENV_FILE}")"
install -m 0640 -o root -g "${VM_APP_GROUP}" "${STAGED_SYSTEMD_ENV_FILE}" "${VM_SYSTEMD_ENV_FILE}.tmp"
mv "${VM_SYSTEMD_ENV_FILE}.tmp" "${VM_SYSTEMD_ENV_FILE}"
ln -sfn "/etc/nginx/sites-available/${NGINX_SITE_NAME}.conf" "/etc/nginx/sites-enabled/${NGINX_SITE_NAME}.conf"
rm -f /etc/nginx/sites-enabled/default
systemctl daemon-reload
systemctl enable "${SYSTEMD_SERVICE_NAME}" >/dev/null
systemctl enable nginx >/dev/null
nginx -t
SWITCHED_CONFIG=1
ln -sfn "${NEW_FRONTEND_RELEASE}" "${VM_FRONTEND_DIST_DIR}"
ln -sfn "${NEW_BACKEND_RELEASE}" "${VM_CURRENT_BACKEND_RELEASE_LINK}"
ln -sfn "${NEW_BACKEND_VENV}" "${VM_CURRENT_BACKEND_VENV_LINK}"
chown -h "${VM_APP_USER}:${VM_APP_GROUP}" "${VM_FRONTEND_DIST_DIR}" "${VM_CURRENT_BACKEND_RELEASE_LINK}" "${VM_CURRENT_BACKEND_VENV_LINK}"
SWITCHED_RELEASES=1

CURRENT_STAGE="restart_services"
systemctl restart "${SYSTEMD_SERVICE_NAME}"
systemctl restart nginx

CURRENT_STAGE="post_switch_health"
wait_for_http_endpoint "/healthz" 30 "${SYSTEMD_SERVICE_NAME}"
wait_for_http_endpoint "/readyz" 30 "${SYSTEMD_SERVICE_NAME}"

CURRENT_STAGE="write_release_metadata"
install -d -m 0755 "$(dirname "${VM_RELEASE_METADATA_FILE}")"
python3 - "${VM_RELEASE_METADATA_FILE}.tmp" "${NEW_SHA}" "${DEPLOYMENT_GIT_SHORT_SHA}" "${DEPLOYMENT_BRANCH}" "${NEW_BACKEND_RELEASE}" "${NEW_BACKEND_VENV}" "${NEW_FRONTEND_RELEASE}" <<'PY'
import json
import sys

payload = {
    "current_sha": sys.argv[2],
    "current_short_sha": sys.argv[3],
    "branch": sys.argv[4],
    "backend_release_dir": sys.argv[5],
    "backend_venv_dir": sys.argv[6],
    "frontend_release_dir": sys.argv[7],
}
with open(sys.argv[1], "w", encoding="utf-8") as fh:
    json.dump(payload, fh, ensure_ascii=True, indent=2)
PY
mv "${VM_RELEASE_METADATA_FILE}.tmp" "${VM_RELEASE_METADATA_FILE}"
validate_current_release_state

CURRENT_STAGE="cleanup_transient_build_artifacts"
run_as_app_bash "
  rm -rf '${NEW_BACKEND_RELEASE}/frontend/node_modules' '${NEW_BACKEND_RELEASE}/frontend/dist'
  find '${NEW_BACKEND_RELEASE}/backend' -type d -name '__pycache__' -prune -exec rm -rf {} +
"

CURRENT_STAGE="retention"
prune_release_dirs "${VM_FRONTEND_RELEASES_DIR}" "${VM_RELEASE_RETENTION_COUNT}" \
  "${NEW_SHA}" "$(basename "${ORIGINAL_FRONTEND_TARGET:-}")"
prune_release_dirs "${VM_BACKEND_RELEASES_DIR}" "${VM_RELEASE_RETENTION_COUNT}" \
  "${NEW_SHA}" "$(basename "${ORIGINAL_BACKEND_RELEASE_TARGET:-}")"
prune_release_dirs "${VM_BACKEND_VENV_RELEASES_DIR}" "${VM_RELEASE_RETENTION_COUNT}" \
  "${NEW_SHA}" "$(basename "${ORIGINAL_BACKEND_VENV_TARGET:-}")"

SUCCESS=1
echo "VM deploy succeeded: ${NEW_SHA}"
