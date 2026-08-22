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
need_cmd psql

python3 tools/validate_vm_prod_deploy.py >/tmp/gxp-vm-validate.json
systemctl is-active --quiet "${SYSTEMD_SERVICE_NAME:-gxp-web}"
systemctl is-active --quiet nginx
systemctl is-active --quiet postgresql
tailscale status >/dev/null
curl -fsS "http://127.0.0.1:${APP_PORT:-8000}/healthz" >/dev/null
curl -fsS "http://127.0.0.1:${APP_PORT:-8000}/readyz" >/dev/null

PG_VERSION_NUM="$(PGPASSWORD="${DB_PASSWORD:-}" psql --host "${DB_HOST:-127.0.0.1}" --port "${DB_PORT:-5432}" --username "${DB_USER:-gxp_app}" --dbname "${DB_NAME:-gxp_qlcl}" -Atqc 'SHOW server_version_num')"
PG_MAJOR="${PG_VERSION_NUM:0:${#PG_VERSION_NUM}-4}"
case ",${VM_SUPPORTED_POSTGRES_MAJORS:-17,18}," in
  *",${PG_MAJOR},"*) ;;
  *) fail "Unsupported PostgreSQL major version ${PG_MAJOR}. Supported majors: ${VM_SUPPORTED_POSTGRES_MAJORS:-17,18}." ;;
esac

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
