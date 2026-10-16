#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
# shellcheck source=infra/vm/common.sh
source "${SCRIPT_DIR}/common.sh"

CANONICAL_RUNTIME_ENV_FILE="${VM_RUNTIME_ENV_FILE:-/etc/gxp/runtime.env}"
# Pin operator approval before loading runtime env; do not let any env file
# silently replace the approved source commit or supply a missing approval.
readonly REHEARSAL_FRONTEND_OPERATOR_SHA="${REHEARSAL_APPROVED_FRONTEND_SHA:-}"
readonly REHEARSAL_BACKEND_OPERATOR_SHA="${REHEARSAL_APPROVED_BACKEND_SHA:-}"
REHEARSAL_DEPLOY_TEMP_DIR=""
REHEARSAL_RUNTIME_ENV_FILE=""
REHEARSAL_PLAN_JSON=""
PREPARE_REHEARSAL_PYTHON=""

cleanup() {
  if [[ -n "${REHEARSAL_DEPLOY_TEMP_DIR}" ]]; then
    rm -rf "${REHEARSAL_DEPLOY_TEMP_DIR}" || true
  fi
}
trap cleanup EXIT

if [[ "${DEPLOY_REHEARSAL_UNSAFE_SKIP_ROOT_CHECK:-0}" != "1" ]]; then
  require_root
fi
load_runtime_env "${CANONICAL_RUNTIME_ENV_FILE}"
# Rehearsal releases MUST explicitly name the approved frontend source commit.
# The release tool verifies its tracked frontend/ Git tree before any staging,
# backup, Alembic migration or symlink switch; cross-head CI overlay is not
# part of the deployable release archive.
[[ -n "${REHEARSAL_FRONTEND_OPERATOR_SHA}" ]] || fail "Missing REHEARSAL_APPROVED_FRONTEND_SHA; approve and integrate frontend source before rehearsal deploy."
[[ -n "${REHEARSAL_BACKEND_OPERATOR_SHA}" ]] || fail "Missing REHEARSAL_APPROVED_BACKEND_SHA; approve backend provenance before rehearsal deploy."
export VM_REQUIRE_APPROVED_FRONTEND_TREE=1
export VM_APPROVED_BACKEND_SOURCE_SHA="${REHEARSAL_BACKEND_OPERATOR_SHA}"
export VM_APPROVED_FRONTEND_SOURCE_SHA="${REHEARSAL_FRONTEND_OPERATOR_SHA}"
need_cmd mktemp
need_cmd chmod
need_cmd chown
PREPARE_REHEARSAL_PYTHON="${VM_CURRENT_BACKEND_VENV_LINK}/bin/python"
[[ -x "${PREPARE_REHEARSAL_PYTHON}" ]] || fail "Current application venv Python is missing or not executable: ${PREPARE_REHEARSAL_PYTHON}"
"${PREPARE_REHEARSAL_PYTHON}" - <<'PY' >/dev/null || fail "Current application venv Python is missing required application dependencies for rehearsal preflight."
import sqlalchemy
PY

REHEARSAL_DEPLOY_TEMP_DIR="$(mktemp -d)"
REHEARSAL_RUNTIME_ENV_FILE="${REHEARSAL_DEPLOY_TEMP_DIR}/runtime.rehearsal.env"
REHEARSAL_PLAN_JSON="${REHEARSAL_DEPLOY_TEMP_DIR}/rehearsal-plan.json"
chown "root:${VM_APP_GROUP}" "${REHEARSAL_DEPLOY_TEMP_DIR}"
chmod 0750 "${REHEARSAL_DEPLOY_TEMP_DIR}"

"${PREPARE_REHEARSAL_PYTHON}" "${REPO_ROOT}/tools/prepare_rehearsal_deploy.py" \
  --runtime-env "${CANONICAL_RUNTIME_ENV_FILE}" \
  --output-runtime-env "${REHEARSAL_RUNTIME_ENV_FILE}" >"${REHEARSAL_PLAN_JSON}" || {
  cat "${REHEARSAL_PLAN_JSON}" >&2 || true
  fail "Rehearsal deploy preflight failed."
}
chown "root:${VM_APP_GROUP}" "${REHEARSAL_RUNTIME_ENV_FILE}" "${REHEARSAL_PLAN_JSON}"
chmod 0640 "${REHEARSAL_RUNTIME_ENV_FILE}" "${REHEARSAL_PLAN_JSON}"

VM_RUNTIME_ENV_FILE="${REHEARSAL_RUNTIME_ENV_FILE}" "${SCRIPT_DIR}/deploy_prod.sh"
