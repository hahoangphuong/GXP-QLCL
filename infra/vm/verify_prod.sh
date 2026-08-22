#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=infra/vm/common.sh
source "${SCRIPT_DIR}/common.sh"

load_runtime_env "${VM_RUNTIME_ENV_FILE:-/etc/gxp/runtime.env}"
need_cmd python3
need_cmd systemctl
need_cmd tailscale
need_cmd curl

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

swapon --show
df -h /
echo "VM production verification passed."
