#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
# shellcheck source=infra/vm/common.sh
source "${SCRIPT_DIR}/common.sh"
PLAN_JSON="$(mktemp)"
FRONTEND_BUILD_DIR="$(mktemp -d)"
SUCCESS=0
OLD_REF="DETACHED"
OLD_SHA=""
NEW_SHA=""
ORIGINAL_FRONTEND_TARGET=""
cleanup() {
  if [[ "${SUCCESS}" != "1" && -n "${OLD_SHA}" ]]; then
    if [[ -n "${ORIGINAL_FRONTEND_TARGET}" ]]; then
      ln -sfn "${ORIGINAL_FRONTEND_TARGET}" "${VM_FRONTEND_DIST_DIR:-/opt/gxp/frontend-dist}" || true
    fi
    if [[ "${OLD_REF}" == "DETACHED" ]]; then
      run_as_app_user git -C "${REPO_ROOT}" checkout --detach "${OLD_SHA}" >/dev/null 2>&1 || true
    else
      run_as_app_user git -C "${REPO_ROOT}" checkout "${OLD_REF}" >/dev/null 2>&1 || true
    fi
  fi
  rm -f "${PLAN_JSON}"
  rm -rf "${FRONTEND_BUILD_DIR}"
}
trap cleanup EXIT

cd "${REPO_ROOT}"
require_root

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

RUNTIME_ENV_FILE="${VM_RUNTIME_ENV_FILE:-/etc/gxp/runtime.env}"
load_runtime_env "${RUNTIME_ENV_FILE}"

need_cmd python3
need_cmd git
need_cmd systemctl
need_cmd curl
need_cmd nginx
need_cmd pg_dump
need_cmd rsync
need_cmd node
need_cmd corepack

python3 tools/validate_vm_prod_deploy.py >"${PLAN_JSON}" || {
  cat "${PLAN_JSON}" >&2
  fail "VM production deploy validation failed."
}

VM_APP_USER="${VM_APP_USER:-$(json_query app_user)}"
VM_APP_GROUP="${VM_APP_GROUP:-$(json_query app_group)}"
APP_PORT="${APP_PORT:-$(json_query app_port)}"
VM_VENV_DIR="$(json_query vm_venv_dir)"
VM_FRONTEND_DIST_DIR="$(json_query vm_frontend_dist_dir)"
VM_FRONTEND_RELEASES_DIR="$(json_query vm_frontend_releases_dir)"
SYSTEMD_SERVICE_NAME="$(json_query systemd_service_name)"
NGINX_SITE_NAME="$(json_query nginx_site_name)"
VM_RELEASE_METADATA_FILE="$(json_query vm_release_metadata_file)"
VM_SRC_DIR="$(json_query vm_src_dir)"
NODE_MIN_VERSION="$(json_query node_min_version)"
NODE_PACKAGE_MANAGER="$(json_query node_package_manager)"
NODE_BUILD_OPTIONS="$(json_query node_build_options)"
GXP_FRONTEND_DIST_ROOT="${GXP_FRONTEND_DIST_ROOT:-${VM_FRONTEND_DIST_DIR}}"
export GXP_FRONTEND_DIST_ROOT
[[ "${REPO_ROOT}" == "${VM_SRC_DIR}" ]] || fail "deploy_prod.sh must run from VM_SRC_DIR=${VM_SRC_DIR}, but current checkout is ${REPO_ROOT}."
DATABASE_URL="$(
  python3 - <<'PY'
from backend.app.config import resolve_database_url
import os

print(resolve_database_url(dict(os.environ)))
PY
)"
[[ -n "${DATABASE_URL}" ]] || fail "DATABASE_URL could not be resolved for Alembic."

run_as_app_user git -C "${REPO_ROOT}" status --porcelain --untracked-files=no | grep -q '^' && fail "Working tree is dirty. Refusing deploy."

OLD_SHA="$(run_as_app_user git -C "${REPO_ROOT}" rev-parse HEAD)"
OLD_REF="$(run_as_app_user git -C "${REPO_ROOT}" symbolic-ref -q --short HEAD 2>/dev/null || true)"
OLD_REF="${OLD_REF:-DETACHED}"
if [[ -L "${VM_FRONTEND_DIST_DIR}" ]]; then
  ORIGINAL_FRONTEND_TARGET="$(readlink "${VM_FRONTEND_DIST_DIR}")"
elif [[ -d "${VM_FRONTEND_DIST_DIR}" ]]; then
  ORIGINAL_FRONTEND_TARGET="${VM_FRONTEND_DIST_DIR}"
fi

TARGET_SHA="${DEPLOY_GIT_SHA:-}"
DEPLOY_BRANCH="${DEPLOY_BRANCH:-$(json_query deploy_branch)}"

run_as_app_user git -C "${REPO_ROOT}" fetch origin
if [[ -z "${TARGET_SHA}" ]]; then
  TARGET_SHA="$(run_as_app_user git -C "${REPO_ROOT}" rev-parse --verify "origin/${DEPLOY_BRANCH}^{commit}")" || fail "Could not resolve origin/${DEPLOY_BRANCH}."
else
  run_as_app_user git -C "${REPO_ROOT}" rev-parse --verify "${TARGET_SHA}^{commit}" >/dev/null 2>&1 || fail "DEPLOY_GIT_SHA is not a valid commit: ${TARGET_SHA}"
fi
run_as_app_user git -C "${REPO_ROOT}" checkout --detach "${TARGET_SHA}"
NEW_SHA="$(run_as_app_user git -C "${REPO_ROOT}" rev-parse HEAD)"

node - "${NODE_MIN_VERSION}" <<'PY'
import sys
import subprocess

current = tuple(int(part) for part in subprocess.check_output(["node", "-p", "process.versions.node"], text=True).strip().split("."))
required = tuple(int(part) for part in sys.argv[1].split("."))
raise SystemExit(0 if current >= required else 1)
PY

run_as_app_user python3 -m venv "${VM_VENV_DIR}"
run_as_app_user "${VM_VENV_DIR}/bin/pip" install --upgrade pip
run_as_app_user "${VM_VENV_DIR}/bin/pip" install --no-cache-dir -r "${REPO_ROOT}/backend/requirements.runtime.vm.txt"

run_as_app_bash "
  export NODE_OPTIONS='${NODE_BUILD_OPTIONS}'
  export PATH=\"${VM_VENV_DIR}/bin:\$PATH\"
  cd '${REPO_ROOT}/frontend'
  corepack enable
  corepack prepare '${NODE_PACKAGE_MANAGER}' --activate
  pnpm install --frozen-lockfile
  pnpm build
  rsync -a --delete '${REPO_ROOT}/frontend/dist/' '${FRONTEND_BUILD_DIR}/'
"

install -d -m 0755 -o "${VM_APP_USER}" -g "${VM_APP_GROUP}" "${VM_FRONTEND_RELEASES_DIR}"
NEW_FRONTEND_RELEASE="${VM_FRONTEND_RELEASES_DIR}/${NEW_SHA}"
rm -rf "${NEW_FRONTEND_RELEASE}"
install -d -m 0755 -o "${VM_APP_USER}" -g "${VM_APP_GROUP}" "${NEW_FRONTEND_RELEASE}"
rsync -a --delete "${FRONTEND_BUILD_DIR}/" "${NEW_FRONTEND_RELEASE}/"

python3 "${REPO_ROOT}/tools/render_vm_runtime_assets.py" service "/etc/systemd/system/${SYSTEMD_SERVICE_NAME}.service"
python3 "${REPO_ROOT}/tools/render_vm_runtime_assets.py" nginx "/etc/nginx/sites-available/${NGINX_SITE_NAME}.conf"
ln -sfn "/etc/nginx/sites-available/${NGINX_SITE_NAME}.conf" "/etc/nginx/sites-enabled/${NGINX_SITE_NAME}.conf"
rm -f /etc/nginx/sites-enabled/default
systemctl daemon-reload
systemctl enable "${SYSTEMD_SERVICE_NAME}" >/dev/null
systemctl enable nginx >/dev/null
nginx -t

run_as_app_user "${SCRIPT_DIR}/backup_postgres.sh"
run_as_app_user env DATABASE_URL="${DATABASE_URL}" "${VM_VENV_DIR}/bin/alembic" -c "${REPO_ROOT}/alembic.ini" upgrade head

ln -sfn "${NEW_FRONTEND_RELEASE}" "${VM_FRONTEND_DIST_DIR}"
chown -h "${VM_APP_USER}:${VM_APP_GROUP}" "${VM_FRONTEND_DIST_DIR}"

install -d -m 0755 "$(dirname "${VM_RELEASE_METADATA_FILE}")"
python3 - "${VM_RELEASE_METADATA_FILE}" "${OLD_SHA}" "${NEW_SHA}" <<'PY'
import json
import sys

payload = {"previous_sha": sys.argv[2], "current_sha": sys.argv[3]}
with open(sys.argv[1], "w", encoding="utf-8") as fh:
    json.dump(payload, fh, ensure_ascii=True, indent=2)
PY

systemctl restart "${SYSTEMD_SERVICE_NAME}"
systemctl restart nginx

curl -fsS "http://127.0.0.1:${APP_PORT}/healthz" >/dev/null
curl -fsS "http://127.0.0.1:${APP_PORT}/readyz" >/dev/null

run_as_app_bash "
  rm -rf '${REPO_ROOT}/frontend/node_modules' '${REPO_ROOT}/frontend/dist' '${REPO_ROOT}/.pytest_cache'
  find '${REPO_ROOT}/backend' -type d -name '__pycache__' -prune -exec rm -rf {} +
"

SUCCESS=1
echo "VM deploy succeeded: ${OLD_SHA} -> ${NEW_SHA}"
