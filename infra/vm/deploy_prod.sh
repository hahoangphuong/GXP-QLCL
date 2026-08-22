#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PLAN_JSON="$(mktemp)"
cleanup() {
  rm -f "${PLAN_JSON}"
}
trap cleanup EXIT

cd "${REPO_ROOT}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Required command not found in PATH: $1"
}

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
[[ -f "${RUNTIME_ENV_FILE}" ]] || fail "Runtime env file not found: ${RUNTIME_ENV_FILE}"

set -a
# shellcheck disable=SC1090
source "${RUNTIME_ENV_FILE}"
set +a

need_cmd python3
need_cmd git
need_cmd systemctl
need_cmd curl
need_cmd pg_dump

python3 tools/validate_vm_prod_deploy.py >"${PLAN_JSON}" || {
  cat "${PLAN_JSON}" >&2
  fail "VM production deploy validation failed."
}

[[ "$(git status --porcelain --untracked-files=no)" == "" ]] || fail "Working tree is dirty. Refusing deploy."

OLD_SHA="$(git rev-parse HEAD)"
TARGET_SHA="${DEPLOY_GIT_SHA:-}"
DEPLOY_BRANCH="${DEPLOY_BRANCH:-$(json_query deploy_branch)}"

git fetch origin
if [[ -n "${TARGET_SHA}" ]]; then
  git rev-parse --verify "${TARGET_SHA}^{commit}" >/dev/null 2>&1 || fail "DEPLOY_GIT_SHA is not a valid commit: ${TARGET_SHA}"
  git checkout --detach "${TARGET_SHA}"
else
  git checkout "${DEPLOY_BRANCH}"
  git merge --ff-only "origin/${DEPLOY_BRANCH}"
fi
NEW_SHA="$(git rev-parse HEAD)"

VM_VENV_DIR="$(json_query vm_venv_dir)"
VM_FRONTEND_DIST_DIR="$(json_query vm_frontend_dist_dir)"
SYSTEMD_SERVICE_NAME="$(json_query systemd_service_name)"
VM_RELEASE_METADATA_FILE="$(json_query vm_release_metadata_file)"

python3 -m venv "${VM_VENV_DIR}"
"${VM_VENV_DIR}/bin/pip" install --upgrade pip
"${VM_VENV_DIR}/bin/pip" install --no-cache-dir -r backend/requirements.runtime.vm.txt

( cd frontend && corepack enable && corepack pnpm install --frozen-lockfile && corepack pnpm build )
install -d -m 0755 "${VM_FRONTEND_DIST_DIR}"
rsync -a --delete frontend/dist/ "${VM_FRONTEND_DIST_DIR}/"

"${SCRIPT_DIR}/backup_postgres.sh"
"${VM_VENV_DIR}/bin/alembic" upgrade head

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

curl -fsS "http://127.0.0.1:${APP_PORT:-8000}/healthz" >/dev/null
curl -fsS "http://127.0.0.1:${APP_PORT:-8000}/readyz" >/dev/null

rm -rf frontend/node_modules frontend/dist .pytest_cache
find backend -type d -name "__pycache__" -prune -exec rm -rf {} +

echo "VM deploy succeeded: ${OLD_SHA} -> ${NEW_SHA}"
