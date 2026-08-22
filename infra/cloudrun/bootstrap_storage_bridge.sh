#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
CONFIG_PATH="${1:-infra/cloudrun/storage_bridge_bootstrap.example.json}"
VALIDATION_JSON="$(mktemp)"
CONFIG_VALUES_JSON="$(mktemp)"
cleanup() {
  rm -f "${VALIDATION_JSON}" "${CONFIG_VALUES_JSON}"
}
trap cleanup EXIT

cd "${REPO_ROOT}"

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "ERROR: missing command: $1" >&2
    exit 1
  }
}

need_cmd python3
need_cmd gcloud
need_cmd curl

python3 tools/validate_phase18_storage_bridge_bootstrap.py "${CONFIG_PATH}" >"${VALIDATION_JSON}" || {
  cat "${VALIDATION_JSON}" >&2
  echo "ERROR: storage bridge bootstrap validation failed" >&2
  exit 1
}

python3 - "${CONFIG_PATH}" >"${CONFIG_VALUES_JSON}" <<'PY'
import json
import sys
payload = json.loads(open(sys.argv[1], encoding="utf-8").read())
print(json.dumps(payload))
PY

json_config_query() {
  local key="$1"
  python3 - "${CONFIG_VALUES_JSON}" "${key}" <<'PY'
import json
import sys
payload = json.loads(open(sys.argv[1], encoding="utf-8").read())
value = payload[sys.argv[2]]
print(value)
PY
}

fail_with_command() {
  local message="$1"
  local command="$2"
  printf 'ERROR: %s\n' "${message}" >&2
  printf 'Run:\n%s\n' "${command}" >&2
  exit 1
}

python3 - "$VALIDATION_JSON" <<'PY'
import json
import sys

payload = json.loads(open(sys.argv[1], encoding="utf-8").read())
for key in ("warnings",):
    items = payload.get(key) or []
    if items:
        print(f"{key.upper()}:")
        for item in items:
            print(f"- {item}")
if not payload.get("ok"):
    raise SystemExit("validation failed")
print("BUILD:", " ".join(payload["build_command_preview"]))
print("DEPLOY:", " ".join(payload["deploy_command_preview"]))
print("INVOKER:", " ".join(payload["invoker_binding_preview"]))
print("BRIDGE_BASE_URL_SOURCE:", payload["bridge_base_url_source"])
PY

PROJECT_ID="$(json_config_query project_id)"
REGION="$(json_config_query region)"
SERVICE_NAME="$(json_config_query service_name)"
ARTIFACT_REGISTRY_REPO="$(json_config_query artifact_registry_repo)"
SERVICE_ACCOUNT="$(json_config_query service_account)"
CALLER_SERVICE_ACCOUNT="$(json_config_query caller_service_account)"
TAILSCALE_SECRET="$(json_config_query tailscale_authkey_secret)"
SMB_USERNAME_SECRET="$(json_config_query smb_username_secret)"
SMB_PASSWORD_SECRET="$(json_config_query smb_password_secret)"

verify_preflight_resources() {
  gcloud artifacts repositories describe "${ARTIFACT_REGISTRY_REPO}" \
    --project "${PROJECT_ID}" \
    --location "${REGION}" >/dev/null 2>&1 || fail_with_command \
    "Artifact Registry repo '${ARTIFACT_REGISTRY_REPO}' is missing." \
    "gcloud artifacts repositories create ${ARTIFACT_REGISTRY_REPO} --project=${PROJECT_ID} --location=${REGION} --repository-format=docker"

  gcloud iam service-accounts describe "${SERVICE_ACCOUNT}" \
    --project "${PROJECT_ID}" >/dev/null 2>&1 || fail_with_command \
    "Bridge service account '${SERVICE_ACCOUNT}' is missing." \
    "gcloud iam service-accounts create ${SERVICE_ACCOUNT%@*} --project=${PROJECT_ID} --display-name=\"GxP Storage Bridge Runtime\""

  gcloud iam service-accounts describe "${CALLER_SERVICE_ACCOUNT}" \
    --project "${PROJECT_ID}" >/dev/null 2>&1 || fail_with_command \
    "Caller service account '${CALLER_SERVICE_ACCOUNT}' is missing." \
    "gcloud iam service-accounts create ${CALLER_SERVICE_ACCOUNT%@*} --project=${PROJECT_ID} --display-name=\"GxP Web Runtime\""

  for secret_name in "${TAILSCALE_SECRET}" "${SMB_USERNAME_SECRET}" "${SMB_PASSWORD_SECRET}"; do
    gcloud secrets describe "${secret_name}" --project "${PROJECT_ID}" >/dev/null 2>&1 || fail_with_command \
      "Secret '${secret_name}' is missing." \
      "gcloud secrets create ${secret_name} --project=${PROJECT_ID} --replication-policy=automatic"

    if ! gcloud secrets get-iam-policy "${secret_name}" \
      --project "${PROJECT_ID}" \
      --format=json | python3 - "${SERVICE_ACCOUNT}" <<'PY'
import json
import sys

policy = json.load(sys.stdin)
member = f"serviceAccount:{sys.argv[1]}"
for binding in policy.get("bindings", []):
    if binding.get("role") == "roles/secretmanager.secretAccessor" and member in binding.get("members", []):
        raise SystemExit(0)
raise SystemExit(1)
PY
    then
      fail_with_command \
        "Bridge service account '${SERVICE_ACCOUNT}' is missing Secret Manager access for '${secret_name}'." \
        "gcloud secrets add-iam-policy-binding ${secret_name} --project=${PROJECT_ID} --member=serviceAccount:${SERVICE_ACCOUNT} --role=roles/secretmanager.secretAccessor"
    fi
  done
}

verify_preflight_resources

if [[ "${DRY_RUN:-0}" == "1" ]]; then
  echo "DRY RUN PASS"
  exit 0
fi

mapfile -t BUILD_CMD < <(python3 - "$VALIDATION_JSON" <<'PY'
import json
import sys
for item in json.loads(open(sys.argv[1], encoding="utf-8").read())["build_command_preview"]:
    print(item)
PY
)
mapfile -t DEPLOY_CMD < <(python3 - "$VALIDATION_JSON" <<'PY'
import json
import sys
for item in json.loads(open(sys.argv[1], encoding="utf-8").read())["deploy_command_preview"]:
    print(item)
PY
)
mapfile -t INVOKER_CMD < <(python3 - "$VALIDATION_JSON" <<'PY'
import json
import sys
for item in json.loads(open(sys.argv[1], encoding="utf-8").read())["invoker_binding_preview"]:
    print(item)
PY
)

"${BUILD_CMD[@]}"
"${DEPLOY_CMD[@]}"
"${INVOKER_CMD[@]}"

BRIDGE_URL="$(gcloud run services describe "${SERVICE_NAME}" --project "${PROJECT_ID}" --region "${REGION}" --format='value(status.url)')"
[[ -n "${BRIDGE_URL}" ]] || {
  echo "ERROR: bridge URL is blank after deploy." >&2
  exit 1
}

BRIDGE_DESCRIBE_JSON="$(mktemp)"
gcloud run services describe "${SERVICE_NAME}" --project "${PROJECT_ID}" --region "${REGION}" --format=json >"${BRIDGE_DESCRIBE_JSON}"
python3 - "${BRIDGE_DESCRIBE_JSON}" <<'PY'
import json
import sys

payload = json.loads(open(sys.argv[1], encoding="utf-8").read())
status = payload.get("status") or {}
latest_ready = status.get("latestReadyRevisionName") or ""
ready = ""
for item in status.get("conditions") or []:
    if isinstance(item, dict) and item.get("type") == "Ready":
        ready = str(item.get("status") or "")
        break
if not latest_ready:
    raise SystemExit("Bridge latestReadyRevisionName is blank.")
if ready.lower() != "true":
    raise SystemExit(f"Bridge Ready condition is not True (got {ready!r}).")
PY
rm -f "${BRIDGE_DESCRIBE_JSON}"

BRIDGE_TOKEN="$(gcloud auth print-identity-token --audiences="${BRIDGE_URL}")"
curl -fsS -H "Authorization: Bearer ${BRIDGE_TOKEN}" "${BRIDGE_URL}/healthz" >/dev/null || {
  echo "ERROR: bridge /healthz check failed." >&2
  exit 1
}
curl -fsS -H "Authorization: Bearer ${BRIDGE_TOKEN}" "${BRIDGE_URL}/readyz" >/dev/null || {
  echo "ERROR: bridge /readyz check failed. Tailscale/SMB access may still be incomplete." >&2
  exit 1
}

printf '\nSet these in the main application deploy environment after bridge bootstrap:\n'
printf 'STORAGE_BRIDGE_BASE_URL=%s\n' "${BRIDGE_URL}"
printf 'STORAGE_BRIDGE_AUTH_AUDIENCE=%s\n' "${BRIDGE_URL}"

if [[ -n "${TEST_INSPECTION_RELATIVE_PATH:-}" ]]; then
  BRIDGE_URL="${BRIDGE_URL}" TEST_INSPECTION_RELATIVE_PATH="${TEST_INSPECTION_RELATIVE_PATH}" TEST_FILE_RELATIVE_PATH="${TEST_FILE_RELATIVE_PATH:-}" \
    "${SCRIPT_DIR}/smoke_test_storage_bridge.sh"
else
  printf '\nOptional authenticated smoke test (recommended before real dossiers):\n'
  printf 'BRIDGE_URL=%s TEST_INSPECTION_RELATIVE_PATH=2026/TEST_STORAGE %s/smoke_test_storage_bridge.sh\n' "${BRIDGE_URL}" "${SCRIPT_DIR}"
fi
