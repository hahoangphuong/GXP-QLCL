#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PLAN_JSON="$(mktemp)"
RUNTIME_ENV_FILE="$(mktemp)"
SERVICE_DESCRIBE_JSON="$(mktemp)"
SERVICE_DESCRIBE_TEXT="$(mktemp)"
cleanup() {
  rm -f "${PLAN_JSON}" "${RUNTIME_ENV_FILE}" "${SERVICE_DESCRIBE_JSON}" "${SERVICE_DESCRIBE_TEXT}"
}
trap cleanup EXIT

cd "${REPO_ROOT}"

log() {
  printf '%s\n' "$*"
}

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Required command not found in PATH: $1"
}

resolve_cmd() {
  local candidate
  for candidate in "$@"; do
    if command -v "${candidate}" >/dev/null 2>&1; then
      printf '%s\n' "${candidate}"
      return 0
    fi
  done
  return 1
}

json_query() {
  local expr="$1"
  "${PYTHON_BIN}" - "$PLAN_JSON" "$expr" <<'PY'
import json
import sys

path = sys.argv[1]
expr = sys.argv[2]
payload = json.loads(open(path, encoding="utf-8").read())
value = payload
for part in expr.split("."):
    if not part:
        continue
    if isinstance(value, dict):
        value = value[part]
    else:
        raise SystemExit(f"Cannot descend into non-dict value for {expr!r}")
if isinstance(value, bool):
    print("true" if value else "false")
elif value is None:
    print("")
else:
    print(value)
PY
}

json_to_env_file() {
  "${PYTHON_BIN}" - "$PLAN_JSON" "$RUNTIME_ENV_FILE" <<'PY'
import json
import sys

plan = json.loads(open(sys.argv[1], encoding="utf-8").read())["plan"]
runtime_env = plan["runtime_env"]
with open(sys.argv[2], "w", encoding="utf-8") as fh:
    for key in sorted(runtime_env):
        value = str(runtime_env[key]).replace("\\", "\\\\").replace('"', '\\"')
        fh.write(f'{key}: "{value}"\n')
PY
}

json_to_secret_flags() {
  "${PYTHON_BIN}" - "$PLAN_JSON" <<'PY'
import json
import sys

plan = json.loads(open(sys.argv[1], encoding="utf-8").read())["plan"]
pairs = [f"{key}={value}" for key, value in sorted(plan["secret_env"].items())]
print(",".join(pairs))
PY
}

json_to_labels() {
  "${PYTHON_BIN}" - "$PLAN_JSON" <<'PY'
import json
import sys

plan = json.loads(open(sys.argv[1], encoding="utf-8").read())["plan"]
pairs = [f"{key}={value}" for key, value in sorted(plan["labels"].items())]
print(",".join(pairs))
PY
}

PYTHON_BIN="$(resolve_cmd python3 python)" || fail "python3 or python is required."
need_cmd git
need_cmd gcloud

if command -v pnpm >/dev/null 2>&1; then
  PNPM_CMD=(pnpm)
elif command -v corepack >/dev/null 2>&1; then
  PNPM_CMD=(corepack pnpm)
elif command -v npx >/dev/null 2>&1; then
  PNPM_CMD=(npx pnpm)
else
  fail "pnpm, corepack, or npx is required to run frontend checks."
fi

"${PYTHON_BIN}" tools/validate_prod_deploy.py >"${PLAN_JSON}" || {
  cat "${PLAN_JSON}" >&2
  fail "Production deploy env validation failed."
}

if [[ "$(json_query ok)" != "true" ]]; then
  cat "${PLAN_JSON}" >&2
  fail "Production deploy plan is invalid."
fi

json_to_env_file
SECRET_FLAGS="$(json_to_secret_flags)"
LABEL_FLAGS="$(json_to_labels)"

PROJECT_ID="$(json_query plan.project_id)"
REGION="$(json_query plan.region)"
SQL_INSTANCE="$(json_query plan.sql_instance)"
CLOUD_SQL_CONNECTION_NAME="$(json_query plan.cloud_sql_connection_name)"
DB_NAME="$(json_query plan.db_name)"
DB_USER="$(json_query plan.db_user)"
SERVICE_NAME="$(json_query plan.service_name)"
MIGRATION_JOB_NAME="$(json_query plan.migration_job_name)"
ARTIFACT_REGISTRY_REPO="$(json_query plan.artifact_registry_repo)"
IMAGE_URI="$(json_query plan.image_uri)"
RUNTIME_SERVICE_ACCOUNT="$(json_query plan.runtime_service_account)"
DRY_RUN_FLAG="$(json_query plan.dry_run)"

CPU="${CPU:-1}"
MEMORY="${MEMORY:-1Gi}"
CONCURRENCY="${CONCURRENCY:-20}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-300}"
MIN_INSTANCES="${MIN_INSTANCES:-0}"
MAX_INSTANCES="${MAX_INSTANCES:-3}"
INGRESS="${INGRESS:-all}"

log "Validated production deploy plan:"
cat "${PLAN_JSON}"

required_files=(
  "backend/Dockerfile"
  "frontend/package.json"
  "frontend/pnpm-lock.yaml"
  "alembic.ini"
  "migrations/env.py"
  "infra/cloudrun/cloudbuild.prod.yaml"
  "infra/cloudrun/deploy_prod.sh"
  "tools/validate_prod_deploy.py"
)
for path in "${required_files[@]}"; do
  [[ -f "${path}" ]] || fail "Required file missing: ${path}"
done

run_preflight_checks() {
  log "Running backend tests..."
  "${PYTHON_BIN}" -m pytest -q

  log "Running repo hygiene check..."
  "${PYTHON_BIN}" tools/check_repo_hygiene.py

  log "Running frontend lint/typecheck/test/build..."
  (
    cd frontend
    "${PNPM_CMD[@]}" lint
    "${PNPM_CMD[@]}" typecheck
    "${PNPM_CMD[@]}" test
    "${PNPM_CMD[@]}" build
  )
}

verify_gcloud_resources() {
  log "Verifying Google Cloud project..."
  gcloud projects describe "${PROJECT_ID}" --format='value(projectId)' >/dev/null

  log "Verifying required APIs..."
  gcloud services list --enabled --project "${PROJECT_ID}" --filter='config.name=iap.googleapis.com' --format='value(config.name)' | grep -Fx 'iap.googleapis.com' >/dev/null || fail "IAP API is not enabled. Run infra/cloudrun/bootstrap_prod_identity.sh first."

  log "Verifying Cloud SQL instance..."
  local sql_state
  sql_state="$(gcloud sql instances describe "${SQL_INSTANCE}" --project "${PROJECT_ID}" --format='value(state)')"
  [[ "${sql_state}" == "RUNNABLE" ]] || fail "Cloud SQL instance ${SQL_INSTANCE} is not RUNNABLE (state=${sql_state})."

  local actual_connection_name
  actual_connection_name="$(gcloud sql instances describe "${SQL_INSTANCE}" --project "${PROJECT_ID}" --format='value(connectionName)')"
  [[ "${actual_connection_name}" == "${CLOUD_SQL_CONNECTION_NAME}" ]] || fail "Cloud SQL connection name mismatch: expected ${CLOUD_SQL_CONNECTION_NAME}, got ${actual_connection_name}."

  log "Verifying Cloud SQL database and user..."
  gcloud sql databases describe "${DB_NAME}" --instance "${SQL_INSTANCE}" --project "${PROJECT_ID}" --format='value(name)' >/dev/null
  gcloud sql users list --instance "${SQL_INSTANCE}" --project "${PROJECT_ID}" --format='value(name)' | grep -Fx "${DB_USER}" >/dev/null || fail "Cloud SQL user not found: ${DB_USER}"

  log "Verifying Secret Manager secret..."
  gcloud secrets describe "$(json_query plan.db_password_secret)" --project "${PROJECT_ID}" --format='value(name)' >/dev/null

  log "Verifying Artifact Registry repository..."
  gcloud artifacts repositories describe "${ARTIFACT_REGISTRY_REPO}" --location "${REGION}" --project "${PROJECT_ID}" --format='value(name)' >/dev/null

  log "Verifying runtime service account..."
  gcloud iam service-accounts describe "${RUNTIME_SERVICE_ACCOUNT}" --project "${PROJECT_ID}" --format='value(email)' >/dev/null
}

print_execution_summary() {
  cat <<EOF
Planned image: ${IMAGE_URI}
Planned Cloud Run service: ${SERVICE_NAME}
Planned migration job: ${MIGRATION_JOB_NAME}
Artifact Registry repo: ${ARTIFACT_REGISTRY_REPO}
Cloud SQL connection: ${CLOUD_SQL_CONNECTION_NAME}
Runtime service account: ${RUNTIME_SERVICE_ACCOUNT}
Runtime env file: ${RUNTIME_ENV_FILE}
EOF
}

verify_cloud_run_service_state() {
  local project_number iap_service_agent
  gcloud run services describe "${SERVICE_NAME}" \
    --project "${PROJECT_ID}" \
    --region "${REGION}" \
    --format=json >"${SERVICE_DESCRIBE_JSON}"
  gcloud run services describe "${SERVICE_NAME}" \
    --project "${PROJECT_ID}" \
    --region "${REGION}" >"${SERVICE_DESCRIBE_TEXT}"

  "${PYTHON_BIN}" - "${SERVICE_DESCRIBE_JSON}" <<'PY'
import json
import sys

payload = json.loads(open(sys.argv[1], encoding="utf-8").read())
status = payload.get("status") or {}
latest_ready = status.get("latestReadyRevisionName") or ""
url = status.get("url") or ""
conditions = status.get("conditions") or []
ready = ""
for item in conditions:
    if isinstance(item, dict) and item.get("type") == "Ready":
        ready = str(item.get("status") or "")
        break
if not latest_ready:
    raise SystemExit("Cloud Run latestReadyRevisionName is blank.")
if not url:
    raise SystemExit("Cloud Run service URL is blank.")
if ready.lower() != "true":
    raise SystemExit(f"Cloud Run Ready condition is not True (got {ready!r}).")
print(latest_ready)
print(url)
PY

  grep -F "Iap Enabled: true" "${SERVICE_DESCRIBE_TEXT}" >/dev/null || fail "Cloud Run service does not report IAP enabled."

  project_number="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')"
  [[ -n "${project_number}" ]] || fail "Could not resolve project number while verifying IAP."
  iap_service_agent="service-${project_number}@gcp-sa-iap.iam.gserviceaccount.com"
  gcloud run services get-iam-policy "${SERVICE_NAME}" \
    --project "${PROJECT_ID}" \
    --region "${REGION}" \
    --format=json | "${PYTHON_BIN}" - "${iap_service_agent}" <<'PY'
import json
import sys

policy = json.load(sys.stdin)
member = f"serviceAccount:{sys.argv[1]}"
for binding in policy.get("bindings", []):
    if binding.get("role") == "roles/run.invoker" and member in binding.get("members", []):
        raise SystemExit(0)
raise SystemExit("IAP service agent does not have roles/run.invoker on the Cloud Run service.")
PY
}

run_preflight_checks
verify_gcloud_resources
print_execution_summary

if [[ "${DRY_RUN_FLAG}" == "true" ]]; then
  log "DRY RUN PASS"
  exit 0
fi

log "Building immutable image with Cloud Build..."
gcloud builds submit \
  --project "${PROJECT_ID}" \
  --config "infra/cloudrun/cloudbuild.prod.yaml" \
  --substitutions "_IMAGE_URI=${IMAGE_URI}" \
  .

log "Deploying migration job definition..."
gcloud run jobs deploy "${MIGRATION_JOB_NAME}" \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --image "${IMAGE_URI}" \
  --service-account "${RUNTIME_SERVICE_ACCOUNT}" \
  --tasks 1 \
  --max-retries 0 \
  --task-timeout 1800s \
  --set-env-vars-file "${RUNTIME_ENV_FILE}" \
  --set-secrets "${SECRET_FLAGS}" \
  --set-cloudsql-instances "${CLOUD_SQL_CONNECTION_NAME}" \
  --command "alembic" \
  --args "upgrade" \
  --args "head" \
  --labels "${LABEL_FLAGS}"

log "Executing migration job..."
gcloud run jobs execute "${MIGRATION_JOB_NAME}" \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --wait

log "Deploying Cloud Run service..."
gcloud run deploy "${SERVICE_NAME}" \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --image "${IMAGE_URI}" \
  --service-account "${RUNTIME_SERVICE_ACCOUNT}" \
  --cpu "${CPU}" \
  --memory "${MEMORY}" \
  --concurrency "${CONCURRENCY}" \
  --timeout "${TIMEOUT_SECONDS}s" \
  --min-instances "${MIN_INSTANCES}" \
  --max-instances "${MAX_INSTANCES}" \
  --ingress "${INGRESS}" \
  --execution-environment gen2 \
  --deploy-health-check \
  --no-allow-unauthenticated \
  --iap \
  --env-vars-file "${RUNTIME_ENV_FILE}" \
  --set-secrets "${SECRET_FLAGS}" \
  --set-cloudsql-instances "${CLOUD_SQL_CONNECTION_NAME}" \
  --labels "${LABEL_FLAGS}"

log "Granting Cloud Run invoker to the IAP service agent..."
PROJECT_NUMBER="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')"
[[ -n "${PROJECT_NUMBER}" ]] || fail "Could not resolve project number after deploy."
IAP_SERVICE_AGENT="service-${PROJECT_NUMBER}@gcp-sa-iap.iam.gserviceaccount.com"
gcloud run services add-iam-policy-binding "${SERVICE_NAME}" \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --member "serviceAccount:${IAP_SERVICE_AGENT}" \
  --role "roles/run.invoker" >/dev/null

log "Verifying Cloud Run control-plane readiness and IAP state..."
verify_cloud_run_service_state

SERVICE_URL="$(gcloud run services describe "${SERVICE_NAME}" --project "${PROJECT_ID}" --region "${REGION}" --format='value(status.url)')"
log "Cloud Run service is Ready and reports IAP enabled."
log "Manual IAP smoke test is still required after user access is granted:"
log "  Browser: ${SERVICE_URL}"
log "  If you need programmatic IAP verification, follow Google IAP programmatic auth using a real IAP token, not gcloud auth print-identity-token for Cloud Run IAM."

log "Production deploy completed successfully."
