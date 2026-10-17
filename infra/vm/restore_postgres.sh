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
# This entrypoint is for fresh, isolated restore drills only. A mere different
# DB name does not authorize destructive --clean on any existing database.
[[ "${TARGET_DB}" =~ ^[A-Za-z_][A-Za-z0-9_]*_restore(_[A-Za-z0-9_]+)?$ ]] ||
  fail "TARGET_DB must be a dedicated *_restore or *_restore_* disposable database."
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

# The sidecar is mandatory: no database query or creation may precede verification.
[[ -f "${CHECKSUM_FILE}" ]] || fail "SHA-256 sidecar missing for selected backup: ${CHECKSUM_FILE}"

# Bind a single manifest entry to the selected backup, never to the original
# machine's absolute pathname. Existing backups used absolute manifest paths;
# accept those only when their basename matches the selected file.
EXPECTED_BACKUP_SHA256="$(
  python3 - "${BACKUP_FILE}" "${CHECKSUM_FILE}" <<'PY_CHECKSUM'
from pathlib import Path
import re
import sys

backup = Path(sys.argv[1])
manifest = Path(sys.argv[2])
try:
    entries = manifest.read_text(encoding="utf-8").splitlines()
except (OSError, UnicodeError) as exc:
    raise SystemExit(f"Cannot read SHA-256 sidecar: {exc}") from exc
if len(entries) != 1:
    raise SystemExit("SHA-256 sidecar must contain exactly one checksum entry")
match = re.fullmatch(r"([0-9a-fA-F]{64}) ([ *])(.+)", entries[0])
if not match:
    raise SystemExit("Malformed SHA-256 sidecar entry")
recorded_name = match.group(3)
if (any(ord(ch) < 32 or ord(ch) == 127 for ch in recorded_name)
        or Path(recorded_name).name != backup.name):
    raise SystemExit("SHA-256 sidecar filename does not match selected backup")
print(match.group(1).lower())
PY_CHECKSUM
)" || fail "Invalid SHA-256 sidecar for selected backup: ${CHECKSUM_FILE}"
(
  cd "$(dirname "${BACKUP_FILE}")"
  printf '%s  %s\n' "${EXPECTED_BACKUP_SHA256}" "$(basename "${BACKUP_FILE}")" | sha256sum -c -
) || fail "Selected backup failed SHA-256 verification: ${BACKUP_FILE}"


# Remote restore and replacing pre-existing DBs require a separately reviewed
# recovery procedure. No best-effort fallthrough into pg_restore --clean.
[[ "${DB_MODE}" == "local_postgres" ]] ||
  fail "Disposable restore only supports DB_MODE=local_postgres."
TARGET_DB_EXISTS="$(
  postgres_admin_exec psql -v ON_ERROR_STOP=1 --dbname=postgres --set=target_db="${TARGET_DB}" -At <<'SQL'
SELECT 1 FROM pg_database WHERE datname = :'target_db';
SQL
)"
[[ -z "${TARGET_DB_EXISTS}" ]] || {
  if [[ "${TARGET_DB_EXISTS}" == "1" ]]; then
    fail "Refusing to overwrite an existing database: ${TARGET_DB}"
  fi
  fail "Cannot establish that disposable restore target is absent."
}
postgres_admin_exec createdb --owner "${DB_USER}" "${TARGET_DB}"
PGPASSWORD="${DB_PASSWORD}" pg_restore --clean --if-exists --exit-on-error --no-owner --host "${DB_HOST}" --port "${DB_PORT}" --username "${DB_USER}" --dbname "${TARGET_DB}" "${BACKUP_FILE}"
PGPASSWORD="${DB_PASSWORD}" psql -v ON_ERROR_STOP=1 --host "${DB_HOST}" --port "${DB_PORT}" --username "${DB_USER}" --dbname "${TARGET_DB}" -tc "SELECT version_num FROM alembic_version" >/dev/null
PGPASSWORD="${DB_PASSWORD}" psql -v ON_ERROR_STOP=1 --host "${DB_HOST}" --port "${DB_PORT}" --username "${DB_USER}" --dbname "${TARGET_DB}" -c "SELECT current_database(), current_user;"

echo "Manual restore completed into ${TARGET_DB}."
