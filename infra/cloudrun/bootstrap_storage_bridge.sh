#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
source "${SCRIPT_DIR}/iam_policy_utils.sh"

CONFIG_PATH="${1:-infra/cloudrun/storage_bridge_bootstrap.example.json}"
VALIDATION_JSON="$(mktemp)"
CONFIG_VALUES_JSON="$(mktemp)"
BOOTSTRAP_ENV_FILE="$(mktemp)"
FINAL_ENV_FILE="$(mktemp)"
cleanup() {
  rm -f "${VALIDATION_JSON}" "${CONFIG_VALUES_JSON}" "${BOOTSTRAP_ENV_FILE}" "${FINAL_ENV_FILE}"
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
ENV_FILE="$(json_config_query env_file)"
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

    if policy_member_has_role \
      "secret '${secret_name}'" \
      "serviceAccount:${SERVICE_ACCOUNT}" \
      "roles/secretmanager.secretAccessor" \
      gcloud secrets get-iam-policy "${secret_name}" --project "${PROJECT_ID}" --format=json
    then
      :
    else
      rc=$?
      case "${rc}" in
        1)
          fail_with_command \
            "Bridge service account '${SERVICE_ACCOUNT}' is missing Secret Manager access for '${secret_name}'." \
            "gcloud secrets add-iam-policy-binding ${secret_name} --project=${PROJECT_ID} --member=serviceAccount:${SERVICE_ACCOUNT} --role=roles/secretmanager.secretAccessor"
          ;;
        2|3)
          printf 'ERROR: %s\n' "${POLICY_CHECK_ERROR_MESSAGE}" >&2
          exit 1
          ;;
        *)
          printf "ERROR: Unexpected IAM policy check failure for secret '%s'.\n" "${secret_name}" >&2
          exit 1
          ;;
      esac
    fi
  done
}

verify_operator_impersonation() {
  local active_account
  local active_member
  active_account="$(gcloud config get-value account 2>/dev/null || true)"
  [[ -n "${active_account}" ]] || fail_with_command \
    "Could not determine active gcloud account for service-account impersonation." \
    "gcloud auth login"
  if [[ "${active_account}" == *".gserviceaccount.com" ]]; then
    active_member="serviceAccount:${active_account}"
  else
    active_member="user:${active_account}"
  fi

  if policy_member_has_role \
    "service account '${CALLER_SERVICE_ACCOUNT}'" \
    "${active_member}" \
    "roles/iam.serviceAccountTokenCreator" \
    gcloud iam service-accounts get-iam-policy "${CALLER_SERVICE_ACCOUNT}" --format=json
  then
    :
  else
    rc=$?
    case "${rc}" in
      1)
        fail_with_command \
          "Active operator '${active_account}' cannot impersonate '${CALLER_SERVICE_ACCOUNT}'." \
          "gcloud iam service-accounts add-iam-policy-binding ${CALLER_SERVICE_ACCOUNT} --member=${active_member} --role=roles/iam.serviceAccountTokenCreator"
        ;;
      2|3)
        printf 'ERROR: %s\n' "${POLICY_CHECK_ERROR_MESSAGE}" >&2
        exit 1
        ;;
      *)
        printf "ERROR: Unexpected IAM policy check failure for service account '%s'.\n" "${CALLER_SERVICE_ACCOUNT}" >&2
        exit 1
        ;;
    esac
  fi
}

prepare_env_files() {
  python3 - "${REPO_ROOT}/${ENV_FILE}" "${BOOTSTRAP_ENV_FILE}" "${FINAL_ENV_FILE}" <<'PY'
from pathlib import Path
import sys

source_path = Path(sys.argv[1])
bootstrap_path = Path(sys.argv[2])
final_path = Path(sys.argv[3])

lines = source_path.read_text(encoding="utf-8").splitlines()
bootstrap_lines: list[str] = []
final_lines: list[str] = []
for line in lines:
    if line.startswith("STORAGE_BRIDGE_AUTH_AUDIENCE="):
        continue
    if line.startswith("BRIDGE_BOOTSTRAP_ALLOW_UNCONFIGURED_AUTH="):
        continue
    bootstrap_lines.append(line)
    final_lines.append(line)
bootstrap_lines.append("BRIDGE_BOOTSTRAP_ALLOW_UNCONFIGURED_AUTH=1")
bootstrap_path.write_text("\n".join(bootstrap_lines).strip() + "\n", encoding="utf-8")
final_path.write_text("\n".join(final_lines).strip() + "\n", encoding="utf-8")
PY
}

verify_preflight_resources
verify_operator_impersonation
prepare_env_files

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

DEPLOY_CMD_BOOTSTRAP=("${DEPLOY_CMD[@]}")
for i in "${!DEPLOY_CMD_BOOTSTRAP[@]}"; do
  if [[ "${DEPLOY_CMD_BOOTSTRAP[$i]}" == "${ENV_FILE}" ]]; then
    DEPLOY_CMD_BOOTSTRAP[$i]="${BOOTSTRAP_ENV_FILE}"
  fi
done
"${DEPLOY_CMD_BOOTSTRAP[@]}"
"${INVOKER_CMD[@]}"

BRIDGE_URL="$(gcloud run services describe "${SERVICE_NAME}" --project "${PROJECT_ID}" --region "${REGION}" --format='value(status.url)')"
[[ -n "${BRIDGE_URL}" ]] || {
  echo "ERROR: bridge URL is blank after deploy." >&2
  exit 1
}

python3 - "${FINAL_ENV_FILE}" "${BRIDGE_URL}" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
bridge_url = sys.argv[2]
lines = path.read_text(encoding="utf-8").splitlines()
lines = [line for line in lines if not line.startswith("STORAGE_BRIDGE_AUTH_AUDIENCE=") and not line.startswith("BRIDGE_BOOTSTRAP_ALLOW_UNCONFIGURED_AUTH=")]
lines.append(f"STORAGE_BRIDGE_AUTH_AUDIENCE={bridge_url}")
path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
PY

DEPLOY_CMD_FINAL=("${DEPLOY_CMD[@]}")
for i in "${!DEPLOY_CMD_FINAL[@]}"; do
  if [[ "${DEPLOY_CMD_FINAL[$i]}" == "${ENV_FILE}" ]]; then
    DEPLOY_CMD_FINAL[$i]="${FINAL_ENV_FILE}"
  fi
done
"${DEPLOY_CMD_FINAL[@]}"

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

BRIDGE_TOKEN="$(gcloud auth print-identity-token --impersonate-service-account="${CALLER_SERVICE_ACCOUNT}" --audiences="${BRIDGE_URL}" --include-email)"
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
  BRIDGE_URL="${BRIDGE_URL}" CALLER_SERVICE_ACCOUNT="${CALLER_SERVICE_ACCOUNT}" TEST_INSPECTION_RELATIVE_PATH="${TEST_INSPECTION_RELATIVE_PATH}" TEST_FILE_RELATIVE_PATH="${TEST_FILE_RELATIVE_PATH:-}" \
    "${SCRIPT_DIR}/smoke_test_storage_bridge.sh"
else
  printf '\nOptional authenticated smoke test (recommended before real dossiers):\n'
  printf 'BRIDGE_URL=%s CALLER_SERVICE_ACCOUNT=%s TEST_INSPECTION_RELATIVE_PATH=2026/TEST_STORAGE %s/smoke_test_storage_bridge.sh\n' "${BRIDGE_URL}" "${CALLER_SERVICE_ACCOUNT}" "${SCRIPT_DIR}"
fi
