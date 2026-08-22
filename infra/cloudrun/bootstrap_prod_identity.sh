#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-gxp-qlcl}"
REGION="${REGION:-asia-southeast1}"
SERVICE_NAME="${SERVICE_NAME:-gxp-web}"
ALLOWED_EMAIL_DOMAIN="${AUTH_IAP_ALLOWED_EMAIL_DOMAIN:-}"
IAP_ACCESS_PRINCIPAL="${IAP_ACCESS_PRINCIPAL:-}"

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
ACTIVE_ACCOUNT="$(gcloud config get-value account 2>/dev/null || true)"
PARENT_TYPE="$(gcloud projects describe "${PROJECT_ID}" --format='value(parent.type)' 2>/dev/null || true)"

if gcloud services list --enabled --project "${PROJECT_ID}" --filter='config.name=iap.googleapis.com' --format='value(config.name)' | grep -Fx 'iap.googleapis.com' >/dev/null; then
  IAP_API_STATUS="enabled"
else
  IAP_API_STATUS="disabled"
  if [[ "${DRY_RUN:-0}" != "1" ]]; then
    gcloud services enable iap.googleapis.com --project "${PROJECT_ID}" >/dev/null
    IAP_API_STATUS="enabled"
  fi
fi

if [[ "${PARENT_TYPE}" == "organization" ]]; then
  OAUTH_SETUP_STATUS="context-dependent"
  OAUTH_SETUP_NOTE="Project belongs to a Google organization. In-org users can typically use Google-managed OAuth; out-of-org users may still require custom OAuth configuration."
else
  OAUTH_SETUP_STATUS="manual-console-setup-required-for-first-enable"
  OAUTH_SETUP_NOTE="Projects without an organization can require first-time IAP OAuth setup in the Cloud Run Console before direct Cloud Run IAP is fully usable."
fi

if [[ -n "${IAP_ACCESS_PRINCIPAL}" ]]; then
  IAP_ACCESS_COMMAND="gcloud iap web add-iam-policy-binding --member=${IAP_ACCESS_PRINCIPAL} --role=roles/iap.httpsResourceAccessor --region=${REGION} --resource-type=cloud-run --service=${SERVICE_NAME}"
else
  IAP_ACCESS_COMMAND="gcloud iap web add-iam-policy-binding --member=user:YOUR_USER@example.com --role=roles/iap.httpsResourceAccessor --region=${REGION} --resource-type=cloud-run --service=${SERVICE_NAME}"
fi

cat <<EOF
Project ID: ${PROJECT_ID}
Project Number: ${PROJECT_NUMBER}
Region: ${REGION}
Service Name: ${SERVICE_NAME}
Active Account: ${ACTIVE_ACCOUNT:-unknown}
Project Parent Type: ${PARENT_TYPE:-none}

AUTH_IAP_EXPECTED_AUDIENCE=${EXPECTED_AUDIENCE}
IAP_SERVICE_AGENT=${IAP_SERVICE_AGENT}
IAP API status=${IAP_API_STATUS}
IAP OAuth setup status=${OAUTH_SETUP_STATUS}
IAP user access status=post-service configuration required

Console path if OAuth setup is still required:
Cloud Run -> ${SERVICE_NAME} -> Security -> under IAP choose Edit policy -> Configure in IAP -> Configure consent screen

OAuth setup note:
${OAUTH_SETUP_NOTE}

One-time bootstrap commands:

gcloud services enable iap.googleapis.com --project "${PROJECT_ID}"

After the first successful service deploy, grant IAP end-user access explicitly:
${IAP_ACCESS_COMMAND}

Application-level allowed domain model:
- AUTH_IAP_ALLOWED_EMAIL_DOMAIN should be your real Google Workspace operator domain, for example: example.com
- The app still fails closed for unprovisioned users because RBAC ownership remains in AppUser/AppUserRole/RbacRole.

Current AUTH_IAP_ALLOWED_EMAIL_DOMAIN=${ALLOWED_EMAIL_DOMAIN:-not-set}
EOF
