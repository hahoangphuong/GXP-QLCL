#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=infra/vm/common.sh
source "${SCRIPT_DIR}/common.sh"

load_runtime_env "${VM_RUNTIME_ENV_FILE:-/etc/gxp/runtime.env}"
DB_NAME="${DB_NAME:-gxp_qlcl}"
DB_USER="${DB_USER:-gxp_app}"
DB_PASSWORD="${DB_PASSWORD:-}"
DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_PORT:-5432}"
BACKUP_GCS_BUCKET="${BACKUP_GCS_BUCKET:-}"
BACKUP_LOCAL_STAGING_DIR="${BACKUP_LOCAL_STAGING_DIR:-/var/backups/gxp-temp}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUTPUT_FILE="${BACKUP_LOCAL_STAGING_DIR}/gxp-db-${TIMESTAMP}.dump"
CHECKSUM_FILE="${OUTPUT_FILE}.sha256"

[[ -n "${BACKUP_GCS_BUCKET}" ]] || {
  echo "ERROR: BACKUP_GCS_BUCKET is required." >&2
  exit 1
}
[[ -n "${DB_PASSWORD}" ]] || {
  echo "ERROR: DB_PASSWORD is required." >&2
  exit 1
}

need_cmd pg_dump
need_cmd gcloud
need_cmd sha256sum
need_cmd curl

METADATA_SA_EMAIL="$(
  curl -fsS -H 'Metadata-Flavor: Google' \
    http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/email 2>/dev/null || true
)"
if [[ -z "${METADATA_SA_EMAIL}" ]]; then
  echo "WARNING: attached VM service account could not be resolved from metadata server." >&2
fi
ACTIVE_ACCOUNT="$(gcloud auth list --filter=status:ACTIVE --format='value(account)' 2>/dev/null | head -n 1)"
if [[ -n "${METADATA_SA_EMAIL}" && -n "${ACTIVE_ACCOUNT}" && "${ACTIVE_ACCOUNT}" != "${METADATA_SA_EMAIL}" && "${ALLOW_USER_GCLOUD_AUTH:-0}" != "1" ]]; then
  fail "gcloud is authenticated as ${ACTIVE_ACCOUNT}, not attached VM service account ${METADATA_SA_EMAIL}. Set ALLOW_USER_GCLOUD_AUTH=1 only for explicit break-glass use."
fi

mkdir -p "${BACKUP_LOCAL_STAGING_DIR}"
chmod 0700 "${BACKUP_LOCAL_STAGING_DIR}"
PGPASSWORD="${DB_PASSWORD}" \
  pg_dump \
  --format=custom \
  --compress=9 \
  --host "${DB_HOST}" \
  --port "${DB_PORT}" \
  --username "${DB_USER}" \
  --dbname "${DB_NAME}" \
  --file "${OUTPUT_FILE}"
sha256sum "${OUTPUT_FILE}" > "${CHECKSUM_FILE}"
if gcloud storage cp "${OUTPUT_FILE}" "${CHECKSUM_FILE}" "${BACKUP_GCS_BUCKET}/"; then
  gcloud storage ls "${BACKUP_GCS_BUCKET}/$(basename "${OUTPUT_FILE}")" >/dev/null
  gcloud storage ls "${BACKUP_GCS_BUCKET}/$(basename "${CHECKSUM_FILE}")" >/dev/null
  rm -f "${OUTPUT_FILE}" "${CHECKSUM_FILE}"
else
  echo "WARNING: backup upload failed; local artifacts retained at ${OUTPUT_FILE}" >&2
  exit 1
fi

echo "Backup uploaded:"
echo "${BACKUP_GCS_BUCKET}/$(basename "${OUTPUT_FILE}")"
