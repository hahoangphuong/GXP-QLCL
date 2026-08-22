#!/usr/bin/env bash
set -euo pipefail

RUNTIME_ENV_FILE="${VM_RUNTIME_ENV_FILE:-/etc/gxp/runtime.env}"
[[ -f "${RUNTIME_ENV_FILE}" ]] || {
  echo "ERROR: runtime env file not found: ${RUNTIME_ENV_FILE}" >&2
  exit 1
}

set -a
# shellcheck disable=SC1090
source "${RUNTIME_ENV_FILE}"
set +a

command -v python3 >/dev/null 2>&1 || {
  echo "ERROR: python3 is required." >&2
  exit 1
}
command -v systemctl >/dev/null 2>&1 || {
  echo "ERROR: systemctl is required." >&2
  exit 1
}
command -v tailscale >/dev/null 2>&1 || {
  echo "ERROR: tailscale is required." >&2
  exit 1
}

python3 tools/validate_vm_prod_deploy.py >/tmp/gxp-vm-validate.json
systemctl is-active --quiet "${SYSTEMD_SERVICE_NAME:-gxp-web}"
systemctl is-active --quiet nginx
systemctl is-active --quiet postgresql
tailscale status >/dev/null
curl -fsS "http://127.0.0.1:${APP_PORT:-8000}/healthz" >/dev/null
curl -fsS "http://127.0.0.1:${APP_PORT:-8000}/readyz" >/dev/null

python3 - <<'PY'
from backend.app.storage.factory import create_storage_service_from_env

service = create_storage_service_from_env()
service.list("", root="inspection")
service.list("", root="dkkd")
service.list("", root="template")
print("Storage roots reachable.")
PY

df -h /
echo "VM production verification passed."
