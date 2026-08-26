# Production Deployment

## Scope
This document defines the repository-owned production deployment contract for `GXP-QLCL`.

Current production baseline entrypoint:

```bash
sudo -E ./infra/vm/deploy_prod.sh
```

Dormant optional entrypoint retained in source:

```bash
infra/cloudrun/deploy_prod.sh
```

## Current production baseline

```text
GitHub
  -> Compute Engine VM
  -> git fetch / target commit resolution / staged release export
  -> frontend build on VM
  -> staged backend runtime install on VM
  -> local PostgreSQL
  -> StorageService
  -> SMB
  -> Tailscale
  -> Synology DS115j
```

Application file binaries remain on Synology only. Structured data remains in PostgreSQL only.

## Standard production resource mapping
The VM baseline standardizes these names unless you explicitly override them in `/etc/gxp/runtime.env`.

- VM source checkout: `/opt/gxp/src/GXP-QLCL`
- staged backend releases: `/opt/gxp/backend-releases/<git_sha>`
- staged backend venvs: `/opt/gxp/backend-venvs/<git_sha>`
- current backend release symlink: `/opt/gxp/current-backend`
- current backend venv symlink: `/opt/gxp/current-venv`
- VM frontend dist: `/opt/gxp/frontend-dist`
- VM runtime env file: `/etc/gxp/runtime.env`
- VM systemd service: `gxp-web`
- Nginx site: `gxp-web`
- local PostgreSQL database: `gxp_qlcl`
- local PostgreSQL application user: `gxp_app`
- Synology inspection root: `\\100.95.45.127\Hồ sơ nội bộ\01 - Kiểm tra GPs`
- Synology DDKD root: `\\100.95.45.127\Hồ sơ nội bộ\01 - Kiểm tra GPs\Chứng nhận ĐĐKKDD`
- Synology template root: `\\100.95.45.127\Hồ sơ nội bộ\01 - Kiểm tra GPs\Templates`

## Dormant Cloud Run mapping
The repository still standardizes these names for the dormant Cloud Run path unless you explicitly override them before calling `infra/cloudrun/deploy_prod.sh`.

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
- Bridge runtime service account: `gxp-storage-bridge@gxp-qlcl.iam.gserviceaccount.com`

Image format:

```text
asia-southeast1-docker.pkg.dev/gxp-qlcl/gxp-qlcl/gxp-web:prod-<timestamp>-<shortsha>
```

## Frontend topology
Current production baseline:

```text
Nginx static frontend + /api reverse proxy to FastAPI
```

- Vite frontend is built on the VM during deploy.
- Nginx serves the built frontend static assets.
- Browser API calls stay same-origin by default.
- No production dev server is allowed.

## Storage topology
Current application deployment baseline:

```text
Compute Engine VM application
  -> StorageService
  -> SmbStorageAdapter
  -> SMB
  -> Tailscale
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
The dormant Cloud Run path remains bridge-based and optional.

## Production env contract
Minimal current VM runtime variables:

```text
APP_ENV
DEPLOYMENT_PLATFORM
FRONTEND_TOPOLOGY
AUTH_PROVIDER
AUTH_ROLE_SOURCE
AUTH_OIDC_CLIENT_ID
AUTH_ALLOWED_EMAIL_DOMAIN
DB_MODE
DB_NAME
DB_USER
DB_PASSWORD
DB_HOST
DB_PORT
STORAGE_CLASS
STORAGE_INSPECTION_ROOT
STORAGE_DKKD_ROOT
STORAGE_TEMPLATE_ROOT
SMB_USERNAME
SMB_PASSWORD
PUBLIC_BASE_URL
BACKUP_GCS_BUCKET
VM_RUNTIME_ENV_FILE
VM_PYTHON_SERIES
VM_PYTHON_BIN
VM_SRC_DIR
VM_BACKEND_RELEASES_DIR
VM_BACKEND_VENV_RELEASES_DIR
VM_CURRENT_BACKEND_RELEASE_LINK
VM_CURRENT_BACKEND_VENV_LINK
VM_FRONTEND_DIST_DIR
VM_FRONTEND_RELEASES_DIR
VM_RELEASE_RETENTION_COUNT
SYSTEMD_SERVICE_NAME
NGINX_SITE_NAME
NGINX_SERVER_NAME
VM_TLS_CERT_PATH
VM_TLS_KEY_PATH
VM_TLS_PROVISIONING_MODE
VM_NODE_MAJOR
VM_NODE_MIN_VERSION
VM_COREPACK_VERSION
VM_NODE_PACKAGE_MANAGER
VM_NODE_BUILD_OPTIONS
VM_POSTGRES_MAJOR
VM_POSTGRES_CLUSTER_NAME
VM_SUPPORTED_POSTGRES_MAJORS
VM_EXPECTED_PROJECT_ID
VM_EXPECTED_INSTANCE_NAME
VM_EXPECTED_ZONE
VM_SWAP_SIZE_GB
VM_SWAPPINESS
PG_SHARED_BUFFERS_MB
PG_EFFECTIVE_CACHE_SIZE_MB
PG_WORK_MEM_MB
PG_MAINTENANCE_WORK_MEM_MB
PG_AUTOVACUUM_WORK_MEM_MB
PG_MAX_CONNECTIONS
```

Optional VM deploy controls:

```text
DEPLOY_GIT_SHA
DEPLOY_BRANCH
VM_APP_ROOT
VM_SRC_DIR
VM_FRONTEND_DIST_DIR
VM_RELEASE_METADATA_FILE
SYSTEMD_SERVICE_NAME
NGINX_SITE_NAME
BACKUP_LOCAL_STAGING_DIR
```

Current template:

- [backend/.env.vm.production.example](D:/GXP-QLCL/backend/.env.vm.production.example)

## VM deploy flow
`infra/vm/deploy_prod.sh` enforces this order:

1. load and validate `/etc/gxp/runtime.env`
2. verify required local commands
3. verify clean git working tree
4. `git fetch origin`
5. resolve target commit from `DEPLOY_GIT_SHA` or `origin/$DEPLOY_BRANCH`
6. export the target commit into a staged backend release directory
7. build a staged backend venv from `backend/requirements.runtime.vm.lock.txt`
8. build frontend with pinned `pnpm`
9. stage frontend dist into a per-release directory
10. verify TLS files exist and render staged systemd/Nginx assets into temporary files
11. run PostgreSQL backup
12. run `alembic upgrade head` from the staged venv
13. install active systemd/Nginx config from staged files and preserve previous active config for rollback
14. switch backend/frontend symlinks atomically enough for the service restart
15. restart backend and Nginx
16. verify `/healthz` and `/readyz`
17. record successful release metadata only after the new release is healthy
18. prune old staged releases with bounded retention

If the working tree is dirty:

```text
DEPLOY FAIL
```

No production deploy path may silently merge, stash, or `git reset --hard`.

If deploy fails before service restart:

```text
current running process stays on the old release
new staged backend/frontend artifacts remain offline
```

If deploy fails after the symlink switch or health checks fail:

```text
prior systemd/Nginx config is restored
prior backend/frontend symlinks are restored
services are restarted against the previous known-good release
release metadata stays on the previous known-good release
database migrations are not automatically downgraded
```

## Database contract
- Current production DB baseline is `DB_MODE=local_postgres`.
- PostgreSQL listens only on local/private address.
- Application runtime user must not be `postgres`.
- Normal deploy order is:
  - backup
  - migration
  - restart
  - readiness verification
- `DB_MODE=cloud_sql` remains supported as a dormant rollback/future mode.

## Legacy structured-data import contract
Canonical production import uses the existing legacy importer owner layer plus a production-safe operator CLI:

- importer owner: `backend/app/domain/phase2_import.py`
- Windows snapshot exporter: `tools/export_legacy_snapshot.py`
- production CLI: `tools/import_legacy_production.py`

The production VM import path consumes the exported snapshot JSON, not Excel COM:

- Windows workbook: `legacy/Danh sách Kiểm tra GPs.xlsb`
- exported snapshot: `artifacts/phase3c/legacy_snapshot.json`

Canonical validation dry-run:

```bash
cd /opt/gxp/src/GXP-QLCL
python3 tools/import_legacy_production.py \
  --snapshot artifacts/phase3c/legacy_snapshot.json \
  --runtime-env /etc/gxp/runtime.env \
  --import-mode validation \
  --dry-run
```

Canonical rehearsal refresh:

```bash
cd /opt/gxp/src/GXP-QLCL
python3 tools/import_legacy_production.py \
  --snapshot artifacts/phase3c/legacy_snapshot.json \
  --runtime-env /etc/gxp/runtime.env \
  --import-mode rehearsal \
  --target-db gxp_legacy_rehearsal \
  --reset-from-snapshot \
  --apply
```

Canonical final candidate rebuild:

```bash
cd /opt/gxp/src/GXP-QLCL
python3 tools/import_legacy_production.py \
  --snapshot artifacts/phase3c/legacy_snapshot.json \
  --runtime-env /etc/gxp/runtime.env \
  --import-mode final \
  --target-db gxp_qlcl_candidate \
  --reset-from-snapshot \
  --apply
```

The CLI must:

- reuse the canonical runtime env parser and resolved production DB contract
- fail closed if `APP_ENV != production` or `DB_MODE != local_postgres`
- require `--dry-run` to stay `--import-mode validation`
- require `--apply` to declare `--import-mode rehearsal` or `--import-mode final`
- require `--reset-from-snapshot` for rehearsal/final apply
- reject any rehearsal/final target DB that matches canonical production DB `gxp_qlcl`
- rebuild rehearsal/final targets from a clean database instead of incrementally merging newer snapshots
- require current Alembic revision to equal repository head for validation/import execution
- compute and record the snapshot SHA-256
- record `import_mode`, `target_database`, deployment SHA, and snapshot metadata when present
- keep `--dry-run` zero-mutation by importing inside a transaction and rolling it back
- allow rehearsal refreshes against a dedicated non-production target such as `gxp_legacy_rehearsal`
- allow final cutover preparation against a candidate DB such as `gxp_qlcl_candidate`
- run the canonical PostgreSQL backup gate before final candidate rebuild
- write reports under `artifacts/legacy-production/<timestamp>/`

This import path does not fabricate or import document rows, storage bindings, or environment-specific RBAC users.
It does initialize the static RBAC baseline for rebuilt rehearsal/final databases so roles, permissions, and role-permission mappings exist before explicit user provisioning.

Detailed operator steps live in:

- [docs/LEGACY_PRODUCTION_IMPORT.md](D:/GXP-QLCL/docs/LEGACY_PRODUCTION_IMPORT.md)

## Auth contract
- Current VM production auth baseline is `AUTH_PROVIDER=google_oidc`.
- Production RBAC remains database-backed.
- `header_stub`, `AUTH_ROLE_MAP`, and trusted-header fallback remain non-production only.
- `AUTH_PROVIDER=google_iap_jwt` remains supported for dormant Cloud Run mode.

## Backup contract
- Required minimum backup is nightly logical PostgreSQL backup:
  - `pg_dump --format=custom`
  - sha256 sidecar
  - upload to Cloud Storage
- Repository scripts:
  - [infra/vm/backup_postgres.sh](D:/GXP-QLCL/infra/vm/backup_postgres.sh)
  - [infra/vm/restore_postgres.sh](D:/GXP-QLCL/infra/vm/restore_postgres.sh)
- Restore is manual, confirmed, and fail-closed.

## Cloud SQL rollback option
- Do not delete Cloud SQL immediately.
- After VM production is verified, operator may stop the instance to reduce recurring cost:

```bash
gcloud sql instances patch gxp-db \
  --project=gxp-qlcl \
  --activation-policy=NEVER
```

- If rollback is required, restore a logical dump back into Cloud SQL and switch runtime config back to `DB_MODE=cloud_sql`.

## Dormant Cloud Run path
Cloud Run + Cloud SQL + external storage bridge remain in-repo for rollback/future reactivation:

```text
infra/cloudrun/
Cloud SQL support
external_bridge_http adapter
google_iap_jwt auth support
Cloud Run bootstrap/deploy validators and scripts
```

Those resources must not block VM production deploy when `DB_MODE=local_postgres` and `STORAGE_CLASS=synology_smb` are active.

## One-time VM prerequisites
These are not created silently by normal deploy.

### Bootstrap host packages

```bash
sudo env \
  VM_EXPECTED_PROJECT_ID=gxp-qlcl-vm \
  VM_EXPECTED_INSTANCE_NAME=gxp-web-prod \
  VM_EXPECTED_ZONE=asia-southeast1-a \
  VM_POSTGRES_MAJOR=18 \
  VM_SWAP_SIZE_GB=4 \
  VM_SWAPPINESS=10 \
  ./infra/vm/bootstrap_vm.sh
```

Fresh Ubuntu baseline after bootstrap:
- fails closed if run from Google Cloud Shell instead of the target Compute Engine VM
- validates Compute Engine metadata against any configured `VM_EXPECTED_*` values before package mutation
- installs minimal bootstrap prerequisites first: `ca-certificates`, `curl`, `gnupg`
- provisions `/swapfile` with `VM_SWAP_SIZE_GB=4` and `VM_SWAPPINESS=10` before Node and other heavier package work
- installs explicit PostgreSQL packages for the configured production major, currently `postgresql-18` and `postgresql-client-18`
- requires exactly the intended PostgreSQL cluster, currently `18/main`, and fails closed on stray clusters
- installs Python 3.12, PostgreSQL, Nginx, Git, rsync, Node.js, Corepack, pinned pnpm, and `gcloud`
- creates non-root app user/group `gxp`
- prepares `/opt/gxp`, `/etc/gxp`, backend/frontend release directories, and backup staging
- fails closed if the host image does not provide Python 3.12 packages natively

### Configure local PostgreSQL

```bash
sudo -E ./infra/vm/configure_postgres.sh
```

`configure_postgres.sh` loads `/etc/gxp/runtime.env` through the repository parser; do not `source` the file directly.
Current small-VM default tuning baseline:
- `shared_buffers=256MB`
- `effective_cache_size=768MB`
- `work_mem=4MB`
- `maintenance_work_mem=64MB`
- `autovacuum_work_mem=64MB`
- `max_connections=30`
- supported PostgreSQL majors: `17,18`
- current production cluster contract: `VM_POSTGRES_MAJOR=18`, `VM_POSTGRES_CLUSTER_NAME=main`
- role/bootstrap SQL uses `psql` stdin with `ON_ERROR_STOP=1`; do not place `:'psql_variables'` inside `DO $$ ... $$` bodies or rely on `-c` interpolation for database existence checks
- local administrative creation stays `runuser -u postgres`
- post-configuration readiness now includes an authenticated `psql` login probe to `127.0.0.1:5432`, not only `pg_isready`

### Configure Tailscale

```bash
export TAILSCALE_AUTH_KEY='YOUR_TAILSCALE_AUTH_KEY'
sudo -E ./infra/vm/configure_tailscale.sh
```

### Verify runtime and Synology reachability

```bash
sudo -E ./infra/vm/verify_prod.sh
```

This verification path checks:
- systemd backend service
- Nginx
- local PostgreSQL
- PostgreSQL major support contract
- Tailscale
- `/healthz` and `/readyz`
- storage root reachability through the configured storage adapter
- swap and disk visibility

## One-time dormant Cloud Run prerequisites
These remain relevant only if you intentionally reactivate the Cloud Run path later.

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
Dormant Cloud Run auth mode is `google_iap_jwt`.

Cloud Run direct IAP is the dormant repository baseline for that path. The repository bootstrap helper is:

```bash
infra/cloudrun/bootstrap_prod_identity.sh
```

It derives the exact audience format from official IAP signed-header guidance:

```text
/projects/{PROJECT_NUMBER}/locations/{REGION}/services/{SERVICE_NAME}
```

For this repository baseline, the concrete value is expected to be:

```text
/projects/<PROJECT_NUMBER>/locations/asia-southeast1/services/gxp-web
```

`AUTH_IAP_ALLOWED_EMAIL_DOMAIN` is your real Google Workspace operator domain, for example `example.com`.

Cloud Run deploys should keep IAP enabled directly on the service.

Important:
- `AUTH_IAP_ALLOWED_EMAIL_DOMAIN` is only the application-layer allowlist.
- It does not grant IAP access by itself.
- Explicit IAP user/group access still must be granted with `roles/iap.httpsResourceAccessor`.

After the service exists, example command:

```bash
gcloud iap web add-iam-policy-binding \
  --member=user:YOUR_USER@example.com \
  --role=roles/iap.httpsResourceAccessor \
  --region=asia-southeast1 \
  --resource-type=cloud-run \
  --service=gxp-web
```

If the project is not part of a Google organization, first-time direct Cloud Run IAP can still require one-time Cloud Console OAuth setup.
Console path:

```text
Cloud Run -> gxp-web -> Security -> IAP -> Edit policy -> Configure in IAP -> Configure consent screen
```

### Storage bridge
The dormant Cloud Run baseline expects:

```text
STORAGE_CLASS=external_bridge_http
```

The bridge bootstrap helper is:

```bash
infra/cloudrun/bootstrap_storage_bridge.sh
```

Bridge topology is now:

```text
Cloud Run main app
  -> authenticated HTTPS
  -> Cloud Run storage bridge
  -> Tailscale userspace SOCKS5
  -> SMB
  -> Synology DS115j
```

So you must provide real values for:

```text
STORAGE_BRIDGE_BASE_URL
STORAGE_BRIDGE_AUTH_AUDIENCE
```

For the current baseline, both values are the actual deployed bridge service URL returned by:

```text
gcloud run services describe gxp-storage-bridge --region asia-southeast1 --format='value(status.url)'
```

Bridge bootstrap also requires one-time secrets that are not committed:

```text
gxp-tailscale-auth-key
gxp-storage-bridge-smb-username
gxp-storage-bridge-smb-password
```

The committed bridge env file remains non-secret and only captures topology/config shape.

Bridge auth bootstrap now uses two phases:

1. first deploy a bootstrap-safe revision without `STORAGE_BRIDGE_AUTH_AUDIENCE`
2. resolve the actual Cloud Run `status.url`
3. redeploy the final revision with:

```text
BRIDGE_AUTH_MODE=google_oidc
STORAGE_BRIDGE_AUTH_AUDIENCE=<actual Cloud Run bridge status.url>
```

During phase 1:
- `/healthz` may report `auth_configured=false`
- `/readyz` must still fail
- `/bridge/storage/*` operations remain fail-closed because bridge auth is not configured yet

Bridge smoke tests now impersonate the actual production caller service account:

```text
gxp-web-runtime@gxp-qlcl.iam.gserviceaccount.com
```

So the operator must also have:

```text
roles/iam.serviceAccountTokenCreator
```

on that service account.

One-time command:

```bash
gcloud iam service-accounts add-iam-policy-binding \
  gxp-web-runtime@gxp-qlcl.iam.gserviceaccount.com \
  --member=user:YOUR_USER@example.com \
  --role=roles/iam.serviceAccountTokenCreator
```

The bridge image build now uses a dedicated Cloud Build config:
- [infra/cloudrun/cloudbuild.storage_bridge.yaml](D:/GXP-QLCL/infra/cloudrun/cloudbuild.storage_bridge.yaml)

Bridge bootstrap preflight verifies before build/deploy:
- Artifact Registry repo `gxp-qlcl`
- bridge runtime service account `gxp-storage-bridge@gxp-qlcl.iam.gserviceaccount.com`
- caller runtime service account `gxp-web-runtime@gxp-qlcl.iam.gserviceaccount.com`
- secrets:
  - `gxp-tailscale-auth-key`
  - `gxp-storage-bridge-smb-username`
  - `gxp-storage-bridge-smb-password`
- bridge runtime service account has `roles/secretmanager.secretAccessor` on the required secrets

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

## One-time bootstrap order
Before the first final Cloud Run dry run, complete bootstrap in this order:

1. Run `infra/cloudrun/bootstrap_prod_identity.sh` and capture the exact `AUTH_IAP_EXPECTED_AUDIENCE`.
2. Prepare/update `AUTH_IAP_ALLOWED_EMAIL_DOMAIN` to your real operator domain.
3. Create bridge secrets for Tailscale auth key and Synology SMB credentials.
4. Update `backend/.env.storage_bridge.cloudrun.example` with the real Synology UNC roots.
5. Run `DRY_RUN=1 infra/cloudrun/bootstrap_storage_bridge.sh`.
6. Run `infra/cloudrun/bootstrap_storage_bridge.sh`.
7. Export the printed `STORAGE_BRIDGE_BASE_URL` and `STORAGE_BRIDGE_AUTH_AUDIENCE`.
8. Run `DRY_RUN=1 ~/deploy_gxp_prod_git.sh`.

If you configure `TEST_INSPECTION_RELATIVE_PATH`, bridge bootstrap now also supports a safe authenticated smoke test path through:
- [infra/cloudrun/smoke_test_storage_bridge.sh](D:/GXP-QLCL/infra/cloudrun/smoke_test_storage_bridge.sh)

## Exact first production deploy command
Current VM production first deploy command after bootstrap:

```bash
cd /opt/gxp/src/GXP-QLCL
sudo -E ./infra/vm/deploy_prod.sh
```

Exact dormant Cloud Run deploy command after its one-time prerequisites are complete and wrapper exports the required variables:

```bash
~/deploy_gxp_prod_git.sh
```

That dormant Cloud Run command is expected to:

```text
pull latest approved main
-> validate config/resources
-> build immutable image
-> migrate safely
-> deploy Cloud Run
-> verify health/readiness
```
