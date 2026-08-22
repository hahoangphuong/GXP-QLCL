#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
RUNTIME_ENV_HELPER="${REPO_ROOT}/tools/runtime_env.py"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Required command not found in PATH: $1"
}

require_root() {
  [[ "${EUID}" -eq 0 ]] || fail "This script must be run as root."
}

load_runtime_env() {
  local env_file="${1:-${VM_RUNTIME_ENV_FILE:-/etc/gxp/runtime.env}}"
  [[ -f "${env_file}" ]] || fail "Runtime env file not found: ${env_file}"
  [[ -r "${env_file}" ]] || fail "Runtime env file is not readable by user $(id -un): ${env_file}"
  need_cmd python3
  while IFS= read -r -d '' pair; do
    export "$pair"
  done < <(python3 "${RUNTIME_ENV_HELPER}" export-null "${env_file}")
}

run_as_app_user() {
  local app_user="${VM_APP_USER:-${GXP_USER:-gxp}}"
  runuser -u "${app_user}" -- "$@"
}

run_as_app_bash() {
  local app_user="${VM_APP_USER:-${GXP_USER:-gxp}}"
  local script="$1"
  runuser -u "${app_user}" -- bash -lc "set -euo pipefail; ${script}"
}
