#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-gxp-qlcl}"
REGION="${REGION:-asia-southeast1}"
SERVICE_NAME="${SERVICE_NAME:-gxp-web}"

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "ERROR: missing command: $1" >&2
    exit 1
  }
}

need_cmd gcloud

PROJECT_NUMBER="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')"
[[ -n "${PROJECT_NUMBER}" ]] || {
  echo "ERROR: could not resolve project number for ${PROJECT_ID}" >&2
  exit 1
}

EXPECTED_AUDIENCE="/projects/${PROJECT_NUMBER}/locations/${REGION}/services/${SERVICE_NAME}"
IAP_SERVICE_AGENT="service-${PROJECT_NUMBER}@gcp-sa-iap.iam.gserviceaccount.com"

cat <<EOF
Project ID: ${PROJECT_ID}
Project Number: ${PROJECT_NUMBER}
Region: ${REGION}
Service Name: ${SERVICE_NAME}

AUTH_IAP_EXPECTED_AUDIENCE=${EXPECTED_AUDIENCE}
IAP_SERVICE_AGENT=${IAP_SERVICE_AGENT}

One-time bootstrap commands:

gcloud services enable iap.googleapis.com --project "${PROJECT_ID}"

gcloud run services add-iam-policy-binding "${SERVICE_NAME}" \\
  --project "${PROJECT_ID}" \\
  --region "${REGION}" \\
  --member "serviceAccount:${IAP_SERVICE_AGENT}" \\
  --role "roles/run.invoker"

Your production deploy then keeps Cloud Run IAP enabled by deploying the service with --iap.

Application-level allowed domain model:
- AUTH_IAP_ALLOWED_EMAIL_DOMAIN should be your real Google Workspace operator domain, for example: example.com
- The app still fails closed for unprovisioned users because RBAC ownership remains in AppUser/AppUserRole/RbacRole.
EOF
