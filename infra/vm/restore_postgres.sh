#!/usr/bin/env bash
set -euo pipefail

BACKUP_FILE="${1:-}"
TARGET_DB="${TARGET_DB:-gxp_qlcl_restore}"
CONFIRM_RESTORE="${CONFIRM_RESTORE:-}"
PGPASSWORD_VALUE="${DB_PASSWORD:-${PGPASSWORD:-}}"

[[ -n "${BACKUP_FILE}" ]] || {
  echo "Usage: $0 /path/to/backup.dump" >&2
  exit 1
}
[[ "${CONFIRM_RESTORE}" == "RESTORE_${TARGET_DB}" ]] || {
  echo "ERROR: Set CONFIRM_RESTORE=RESTORE_${TARGET_DB} to continue." >&2
  exit 1
}

command -v pg_restore >/dev/null 2>&1 || {
  echo "ERROR: pg_restore is required." >&2
  exit 1
}
command -v psql >/dev/null 2>&1 || {
  echo "ERROR: psql is required." >&2
  exit 1
}

psql postgres -tc "SELECT 1 FROM pg_database WHERE datname = '${TARGET_DB}'" | grep -q 1 || createdb "${TARGET_DB}"
PGPASSWORD="${PGPASSWORD_VALUE}" pg_restore --clean --if-exists --no-owner --dbname "${TARGET_DB}" "${BACKUP_FILE}"
PGPASSWORD="${PGPASSWORD_VALUE}" psql "${TARGET_DB}" -c "SELECT current_database(), current_user;"

echo "Manual restore completed into ${TARGET_DB}."
