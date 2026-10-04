#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/iam_policy_utils.sh"

BRIDGE_URL="${BRIDGE_URL:-}"
TEST_INSPECTION_RELATIVE_PATH="${TEST_INSPECTION_RELATIVE_PATH:-}"
TEST_FILE_RELATIVE_PATH="${TEST_FILE_RELATIVE_PATH:-}"
CALLER_SERVICE_ACCOUNT="${CALLER_SERVICE_ACCOUNT:-gxp-web-runtime@gxp-qlcl.iam.gserviceaccount.com}"

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "ERROR: missing command: $1" >&2
    exit 1
  }
}

need_cmd gcloud
need_cmd curl
need_cmd python3

[[ -n "${BRIDGE_URL}" ]] || {
  echo "ERROR: BRIDGE_URL is required." >&2
  exit 1
}
[[ -n "${TEST_INSPECTION_RELATIVE_PATH}" ]] || {
  echo "ERROR: TEST_INSPECTION_RELATIVE_PATH is required." >&2
  exit 1
}

ACTIVE_ACCOUNT="$(gcloud config get-value account 2>/dev/null || true)"
[[ -n "${ACTIVE_ACCOUNT}" ]] || {
  echo "ERROR: Could not determine active gcloud account." >&2
  exit 1
}
if [[ "${ACTIVE_ACCOUNT}" == *".gserviceaccount.com" ]]; then
  ACTIVE_MEMBER="serviceAccount:${ACTIVE_ACCOUNT}"
else
  ACTIVE_MEMBER="user:${ACTIVE_ACCOUNT}"
fi

if policy_member_has_role \
  "service account '${CALLER_SERVICE_ACCOUNT}'" \
  "${ACTIVE_MEMBER}" \
  "roles/iam.serviceAccountTokenCreator" \
  gcloud iam service-accounts get-iam-policy "${CALLER_SERVICE_ACCOUNT}" --format=json
then
  :
else
  rc=$?
  case "${rc}" in
    1)
      echo "ERROR: Active operator '${ACTIVE_ACCOUNT}' cannot impersonate '${CALLER_SERVICE_ACCOUNT}'." >&2
      echo "Run:" >&2
      echo "gcloud iam service-accounts add-iam-policy-binding ${CALLER_SERVICE_ACCOUNT} --member=${ACTIVE_MEMBER} --role=roles/iam.serviceAccountTokenCreator" >&2
      exit 1
      ;;
    2|3)
      echo "ERROR: ${POLICY_CHECK_ERROR_MESSAGE}" >&2
      exit 1
      ;;
    *)
      echo "ERROR: Unexpected IAM policy check failure for service account '${CALLER_SERVICE_ACCOUNT}'." >&2
      exit 1
      ;;
  esac
fi

TOKEN="$(gcloud auth print-identity-token --impersonate-service-account="${CALLER_SERVICE_ACCOUNT}" --audiences="${BRIDGE_URL}" --include-email)"
AUTH_HEADER="Authorization: Bearer ${TOKEN}"
SMOKE_DIR="${TEST_INSPECTION_RELATIVE_PATH%/}/__bridge_smoke__"
SMOKE_FILE="${SMOKE_DIR}/smoke.txt"
SMOKE_PAYLOAD="bridge-smoke-$(date -u +%Y%m%dT%H%M%SZ)"

urlencode() {
  python3 - "$1" <<'PY'
import sys
from urllib.parse import quote

print(quote(sys.argv[1], safe=""))
PY
}

ENCODED_TEST_ROOT="$(urlencode "${TEST_INSPECTION_RELATIVE_PATH}")"
ENCODED_TEST_FILE="$(urlencode "${TEST_FILE_RELATIVE_PATH}")"
ENCODED_SMOKE_DIR="$(urlencode "${SMOKE_DIR}")"
ENCODED_SMOKE_FILE="$(urlencode "${SMOKE_FILE}")"

echo "Checking bridge health endpoints..."
curl -fsS -H "${AUTH_HEADER}" "${BRIDGE_URL}/healthz" >/dev/null
curl -fsS -H "${AUTH_HEADER}" "${BRIDGE_URL}/readyz" >/dev/null

echo "Listing test inspection root..."
curl -fsS -H "${AUTH_HEADER}" "${BRIDGE_URL}/bridge/storage/list?root=inspection&relative_path=${ENCODED_TEST_ROOT}" >/dev/null

echo "Creating smoke folder..."
curl -fsS -X POST -H "${AUTH_HEADER}" -H "Content-Type: application/json" \
  -d "{\"root\":\"inspection\",\"relative_path\":\"${SMOKE_DIR}\"}" \
  "${BRIDGE_URL}/bridge/storage/create-folder" >/dev/null

if [[ -n "${TEST_FILE_RELATIVE_PATH}" ]]; then
  echo "Stat existing test file..."
  curl -fsS -H "${AUTH_HEADER}" "${BRIDGE_URL}/bridge/storage/stat?root=inspection&relative_path=${ENCODED_TEST_FILE}" >/dev/null

  echo "Checksum existing test file..."
  curl -fsS -H "${AUTH_HEADER}" "${BRIDGE_URL}/bridge/storage/checksum?root=inspection&relative_path=${ENCODED_TEST_FILE}" >/dev/null

  echo "Read existing test file..."
  curl -fsS -H "${AUTH_HEADER}" "${BRIDGE_URL}/bridge/storage/read?root=inspection&relative_path=${ENCODED_TEST_FILE}" >/dev/null
fi

echo "Writing smoke file..."
printf '%s' "${SMOKE_PAYLOAD}" | curl -fsS -X POST \
  -H "${AUTH_HEADER}" \
  -H "Content-Type: application/octet-stream" \
  --data-binary @- \
  "${BRIDGE_URL}/bridge/storage/write?root=inspection&relative_path=${ENCODED_SMOKE_FILE}" >/dev/null

echo "Reading smoke file back..."
ROUNDTRIP_PAYLOAD="$(curl -fsS -H "${AUTH_HEADER}" "${BRIDGE_URL}/bridge/storage/read?root=inspection&relative_path=${ENCODED_SMOKE_FILE}")"
[[ "${ROUNDTRIP_PAYLOAD}" == "${SMOKE_PAYLOAD}" ]] || {
  echo "ERROR: smoke file roundtrip payload mismatch." >&2
  exit 1
}

echo "Checksumming smoke file..."
REMOTE_CHECKSUM="$(curl -fsS -H "${AUTH_HEADER}" "${BRIDGE_URL}/bridge/storage/checksum?root=inspection&relative_path=${ENCODED_SMOKE_FILE}" | python3 -c "import json,sys; print(json.load(sys.stdin)['checksum_sha256'])")"
LOCAL_CHECKSUM="$(printf '%s' "${SMOKE_PAYLOAD}" | python3 -c "import hashlib,sys; print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest())")"
[[ "${REMOTE_CHECKSUM}" == "${LOCAL_CHECKSUM}" ]] || {
  echo "ERROR: smoke file checksum mismatch." >&2
  exit 1
}

echo "Storage bridge smoke test passed."
echo "Smoke artifacts stay only under: ${SMOKE_DIR}"
