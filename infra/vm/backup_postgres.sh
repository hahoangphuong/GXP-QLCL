#!/usr/bin/env bash
set -euo pipefail

DB_NAME="${DB_NAME:-gxp_qlcl}"
DB_USER="${DB_USER:-gxp_app}"
DB_PASSWORD="${DB_PASSWORD:-}"
DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_PORT:-5432}"
BACKUP_GCS_BUCKET="${BACKUP_GCS_BUCKET:-}"
BACKUP_LOCAL_STAGING_DIR="${BACKUP_LOCAL_STAGING_DIR:-/var/backups/gxp-temp}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUTPUT_FILE="${BACKUP_LOCAL_STAGING_DIR}/gxp-db-${TIMESTAMP}.dump"

[[ -n "${BACKUP_GCS_BUCKET}" ]] || {
  echo "ERROR: BACKUP_GCS_BUCKET is required." >&2
  exit 1
}

command -v pg_dump >/dev/null 2>&1 || {
  echo "ERROR: pg_dump is required." >&2
  exit 1
}
command -v gcloud >/dev/null 2>&1 || {
  echo "ERROR: gcloud is required for Cloud Storage backup upload." >&2
  exit 1
}

install -d -m 0700 "${BACKUP_LOCAL_STAGING_DIR}"
PGPASSWORD="${DB_PASSWORD}" \
  pg_dump \
  --format=custom \
  --compress=9 \
  --host "${DB_HOST}" \
  --port "${DB_PORT}" \
  --username "${DB_USER}" \
  --dbname "${DB_NAME}" \
  --file "${OUTPUT_FILE}"
sha256sum "${OUTPUT_FILE}" > "${OUTPUT_FILE}.sha256"
gcloud storage cp "${OUTPUT_FILE}" "${OUTPUT_FILE}.sha256" "${BACKUP_GCS_BUCKET}/"

echo "Backup uploaded:"
echo "${BACKUP_GCS_BUCKET}/$(basename "${OUTPUT_FILE}")"
