#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
# shellcheck source=infra/vm/common.sh
source "${SCRIPT_DIR}/common.sh"

CANONICAL_RUNTIME_ENV_FILE="${VM_RUNTIME_ENV_FILE:-/etc/gxp/runtime.env}"
REHEARSAL_DEPLOY_TEMP_DIR="$(mktemp -d)"
REHEARSAL_RUNTIME_ENV_FILE="${REHEARSAL_DEPLOY_TEMP_DIR}/runtime.rehearsal.env"
REHEARSAL_PLAN_JSON="${REHEARSAL_DEPLOY_TEMP_DIR}/rehearsal-plan.json"

cleanup() {
  rm -rf "${REHEARSAL_DEPLOY_TEMP_DIR}" || true
}
trap cleanup EXIT

if [[ "${DEPLOY_REHEARSAL_UNSAFE_SKIP_ROOT_CHECK:-0}" != "1" ]]; then
  require_root
fi
load_runtime_env "${CANONICAL_RUNTIME_ENV_FILE}"
need_cmd python3

python3 "${REPO_ROOT}/tools/prepare_rehearsal_deploy.py" \
  --runtime-env "${CANONICAL_RUNTIME_ENV_FILE}" \
  --output-runtime-env "${REHEARSAL_RUNTIME_ENV_FILE}" >"${REHEARSAL_PLAN_JSON}" || {
  cat "${REHEARSAL_PLAN_JSON}" >&2 || true
  fail "Rehearsal deploy preflight failed."
}

VM_RUNTIME_ENV_FILE="${REHEARSAL_RUNTIME_ENV_FILE}" "${SCRIPT_DIR}/deploy_prod.sh"
