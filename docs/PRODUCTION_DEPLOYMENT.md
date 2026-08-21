# Production Deployment

## Scope
This document defines the repository-owned production deployment contract for `GXP-QLCL`.

Operator entrypoint:

```bash
~/deploy_gxp_prod_git.sh
```

Wrapper responsibility:
- verify Google Cloud access
- verify base production resources
- pull `main` from GitHub
- export deployment variables
- call repository script:

```bash
infra/cloudrun/deploy_prod.sh
```

## Standard production resource mapping
The repository now standardizes these names unless you explicitly override them with environment variables before calling `infra/cloudrun/deploy_prod.sh`.

- Google Cloud project: `gxp-qlcl`
- Region: `asia-southeast1`
- Cloud SQL instance: `gxp-db`
- Cloud SQL connection name: `gxp-qlcl:asia-southeast1:gxp-db`
- Cloud SQL database name: `gxp_qlcl`
- Cloud SQL application user: `gxp_app`
- Secret Manager DB password secret: `gxp-db-password`
- Cloud Run service: `gxp-web`
- Cloud Run migration job: `gxp-web-migrate`
- Artifact Registry repository: `gxp-qlcl`
- Image name: `gxp-web`
- Runtime service account: `gxp-web-runtime@gxp-qlcl.iam.gserviceaccount.com`

Image format:

```text
asia-southeast1-docker.pkg.dev/gxp-qlcl/gxp-qlcl/gxp-web:prod-<timestamp>-<shortsha>
```

## Frontend topology
Current production baseline:

```text
single Cloud Run service/image
```

- Vite frontend is built inside the production container image.
- FastAPI serves the built frontend static assets.
- Browser API calls stay same-origin by default.

## Storage topology
Current application deployment baseline:

```text
Cloud Run application
  -> StorageService
  -> BridgeStorageAdapter
  -> authenticated bridge API
  -> Synology
```

Inspector desktop workflow remains separate:

```text
Inspector laptop
  -> Tailscale
  -> SMB
  -> Synology
```

This repository does not promote Cloud Run NFS `no-lock` to production baseline.

## Production env contract
Minimal wrapper-exported variables:

```text
PROJECT_ID
REGION
SQL_INSTANCE
CLOUD_SQL_CONNECTION_NAME
DB_PASSWORD_SECRET
DEPLOY_GIT_SHA
DEPLOY_GIT_SHORT_SHA
DEPLOY_BRANCH
DRY_RUN
```

Additional required non-secret production variables:

```text
AUTH_IAP_EXPECTED_AUDIENCE
AUTH_IAP_ALLOWED_EMAIL_DOMAIN
STORAGE_BRIDGE_BASE_URL
STORAGE_BRIDGE_AUTH_AUDIENCE
```

Optional overrides:

```text
SERVICE_NAME
MIGRATION_JOB_NAME
ARTIFACT_REGISTRY_REPO
IMAGE_NAME
RUNTIME_SERVICE_ACCOUNT
DB_NAME
DB_USER
CPU
MEMORY
CONCURRENCY
TIMEOUT_SECONDS
MIN_INSTANCES
MAX_INSTANCES
INGRESS
BRIDGE_AUTH_MODE
```

Template:
- [backend/.env.cloudrun.production.example](D:/GXP-QLCL/backend/.env.cloudrun.production.example)

## Deploy flow
`infra/cloudrun/deploy_prod.sh` enforces this order:

1. validate wrapper env and deployment plan
2. run preflight quality gates
3. verify required Google Cloud resources
4. build immutable image with Cloud Build
5. deploy/update Cloud Run migration job
6. run `alembic upgrade head`
7. stop immediately if migration fails
8. deploy Cloud Run service
9. verify `/healthz`
10. verify `/readyz`

## One-time prerequisites you may still need
These are not created silently by normal deploy.

### Artifact Registry
If repository `gxp-qlcl` does not already exist:

```bash
gcloud artifacts repositories create gxp-qlcl \
  --project=gxp-qlcl \
  --location=asia-southeast1 \
  --repository-format=docker
```

### Runtime service account
If `gxp-web-runtime@gxp-qlcl.iam.gserviceaccount.com` does not already exist:

```bash
gcloud iam service-accounts create gxp-web-runtime \
  --project=gxp-qlcl \
  --display-name="GxP Web Runtime"
```

Grant minimum roles:

```bash
gcloud projects add-iam-policy-binding gxp-qlcl \
  --member="serviceAccount:gxp-web-runtime@gxp-qlcl.iam.gserviceaccount.com" \
  --role="roles/cloudsql.client"

gcloud projects add-iam-policy-binding gxp-qlcl \
  --member="serviceAccount:gxp-web-runtime@gxp-qlcl.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

gcloud projects add-iam-policy-binding gxp-qlcl \
  --member="serviceAccount:gxp-web-runtime@gxp-qlcl.iam.gserviceaccount.com" \
  --role="roles/logging.logWriter"

gcloud projects add-iam-policy-binding gxp-qlcl \
  --member="serviceAccount:gxp-web-runtime@gxp-qlcl.iam.gserviceaccount.com" \
  --role="roles/monitoring.metricWriter"
```

### Cloud SQL database and user
The application now assumes:

- database: `gxp_qlcl`
- user: `gxp_app`

If they do not already exist, create them explicitly:

```bash
gcloud sql databases create gxp_qlcl \
  --project=gxp-qlcl \
  --instance=gxp-db

gcloud sql users create gxp_app \
  --project=gxp-qlcl \
  --instance=gxp-db \
  --password="$(gcloud secrets versions access latest --secret=gxp-db-password --project=gxp-qlcl)"
```

### IAP / external identity
Production auth mode is `google_iap_jwt`.

You must provide a real IAP audience in:

```text
AUTH_IAP_EXPECTED_AUDIENCE
```

If the HTTPS Load Balancer / IAP backend service is not ready yet, direct end-user production access is not ready yet either, even if Cloud Run revision deployment succeeds.

### Storage bridge
The current production baseline expects:

```text
STORAGE_CLASS=external_bridge_http
```

So you must provide:

```text
STORAGE_BRIDGE_BASE_URL
STORAGE_BRIDGE_AUTH_AUDIENCE
```

If bridge transport has not been finalized yet, application deployment can still be validated structurally, but file operations are not ready for production use.

## Dry run
Use:

```bash
DRY_RUN=1 ~/deploy_gxp_prod_git.sh
```

Expected dry-run behavior:
- validates deploy env
- runs tests/preflight checks
- verifies required files
- verifies Google Cloud resources
- prints resolved image/service/job/config
- does not build image
- does not run migration
- does not deploy Cloud Run
- does not modify Synology

Success terminator:

```text
DRY RUN PASS
```

## Exact first production deploy command
After one-time prerequisites are complete and wrapper exports the required variables:

```bash
~/deploy_gxp_prod_git.sh
```

That command is expected to:

```text
pull latest approved main
-> validate config/resources
-> build immutable image
-> migrate safely
-> deploy Cloud Run
-> verify health/readiness
```
