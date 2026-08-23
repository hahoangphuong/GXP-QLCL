#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=infra/vm/common.sh
source "${SCRIPT_DIR}/common.sh"

load_runtime_env "${VM_RUNTIME_ENV_FILE:-/etc/gxp/runtime.env}"
BACKUP_FILE="${1:-}"
TARGET_DB="${TARGET_DB:-gxp_qlcl_restore}"
CONFIRM_RESTORE="${CONFIRM_RESTORE:-}"
DB_MODE="${DB_MODE:-local_postgres}"
DB_NAME="${DB_NAME:-gxp_qlcl}"
DB_USER="${DB_USER:-gxp_app}"
DB_PASSWORD="${DB_PASSWORD:-${PGPASSWORD:-}}"
DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_PORT:-5432}"
CHECKSUM_FILE="${BACKUP_FILE}.sha256"
POSTGRES_ADMIN_CMD="${POSTGRES_ADMIN_CMD:-}"

[[ -n "${BACKUP_FILE}" ]] || {
  echo "Usage: $0 /path/to/backup.dump" >&2
  exit 1
}
[[ -f "${BACKUP_FILE}" ]] || {
  echo "ERROR: backup file not found: ${BACKUP_FILE}" >&2
  exit 1
}
[[ "${TARGET_DB}" != "${DB_NAME}" ]] || {
  echo "ERROR: TARGET_DB must not default to the production database name (${DB_NAME})." >&2
  exit 1
}
[[ "${CONFIRM_RESTORE}" == "RESTORE_${TARGET_DB}" ]] || {
  echo "ERROR: Set CONFIRM_RESTORE=RESTORE_${TARGET_DB} to continue." >&2
  exit 1
}
[[ -n "${DB_PASSWORD}" ]] || {
  echo "ERROR: DB_PASSWORD is required." >&2
  exit 1
}

need_cmd pg_restore
need_cmd psql
need_cmd createdb
need_cmd sha256sum

postgres_admin_exec() {
  if [[ -n "${POSTGRES_ADMIN_CMD}" ]]; then
    # Explicit test/operator override for privileged local administration.
    ${POSTGRES_ADMIN_CMD} "$@"
    return
  fi
  [[ "${EUID}" -eq 0 ]] || fail "Local PostgreSQL restore that creates a missing database must be run as root."
  runuser -u postgres -- "$@"
}

if [[ -f "${CHECKSUM_FILE}" ]]; then
  (cd "$(dirname "${CHECKSUM_FILE}")" && sha256sum -c "$(basename "${CHECKSUM_FILE}")")
fi

if [[ "${DB_MODE}" == "local_postgres" ]]; then
  TARGET_DB_EXISTS="$(
    postgres_admin_exec psql -v ON_ERROR_STOP=1 --dbname=postgres --set=target_db="${TARGET_DB}" -At <<'SQL'
SELECT 1 FROM pg_database WHERE datname = :'target_db';
SQL
  )"
  [[ "${TARGET_DB_EXISTS}" == "1" ]] || postgres_admin_exec createdb --owner "${DB_USER}" "${TARGET_DB}"
else
  TARGET_DB_EXISTS="$(
    PGPASSWORD="${DB_PASSWORD}" psql \
      -v ON_ERROR_STOP=1 \
      --host "${DB_HOST}" \
      --port "${DB_PORT}" \
      --username "${DB_USER}" \
      --dbname postgres \
      --set=target_db="${TARGET_DB}" \
      -At <<'SQL'
SELECT 1 FROM pg_database WHERE datname = :'target_db';
SQL
  )"
  [[ "${TARGET_DB_EXISTS}" == "1" ]] || fail "TARGET_DB ${TARGET_DB} does not exist. Create it explicitly before restore when DB_MODE=${DB_MODE}."
fi
PGPASSWORD="${DB_PASSWORD}" pg_restore --clean --if-exists --exit-on-error --no-owner --host "${DB_HOST}" --port "${DB_PORT}" --username "${DB_USER}" --dbname "${TARGET_DB}" "${BACKUP_FILE}"
PGPASSWORD="${DB_PASSWORD}" psql -v ON_ERROR_STOP=1 --host "${DB_HOST}" --port "${DB_PORT}" --username "${DB_USER}" --dbname "${TARGET_DB}" -tc "SELECT version_num FROM alembic_version" >/dev/null
PGPASSWORD="${DB_PASSWORD}" psql -v ON_ERROR_STOP=1 --host "${DB_HOST}" --port "${DB_PORT}" --username "${DB_USER}" --dbname "${TARGET_DB}" -c "SELECT current_database(), current_user;"

echo "Manual restore completed into ${TARGET_DB}."
