# VM Production Baseline

## Current production baseline

```text
Compute Engine VM
├─ Nginx
├─ FastAPI backend
├─ PostgreSQL local
├─ Tailscale
└─ SMB -> Synology DS115j
```

Application dossiers remain on Synology. PostgreSQL stores structured business data only.

## Runtime modes
- `DB_MODE=local_postgres` is the current production default.
- `DB_MODE=cloud_sql` remains a dormant rollback/future option.
- `STORAGE_CLASS=synology_smb` is the current production default.
- `STORAGE_CLASS=external_bridge_http` remains a dormant Cloud Run path.
- `AUTH_PROVIDER=google_oidc` is the current VM baseline.
- `AUTH_PROVIDER=google_iap_jwt` remains a dormant Cloud Run path.

## Current migration-specific production identifiers
These are the actual current migration environment identifiers as of August 22, 2026:

- project: `gxp-qlcl-vm`
- VM: `gxp-web-prod`
- zone: `asia-southeast1-a`
- machine type: `e2-small`
- VM service account: `gxp-vm-runtime@gxp-qlcl-vm.iam.gserviceaccount.com`
- PostgreSQL backup bucket: `gs://gxp-qlcl-vm-postgres-backup`

Parameterize scripts where appropriate, but operator guidance for this migration should assume these are the live identifiers unless intentionally overridden.

## Supported host baseline
- Supported production OS/image baseline: Ubuntu 24.04 LTS or another image that ships Python 3.12 packages natively.
- Official production Python baseline: `3.12.x` only.
- Debian 13 / Python 3.13 is unsupported for the current production baseline.
- Do not compile Python from source or add `pyenv`/`conda` as a production workaround.
- Supported PostgreSQL majors for the current app baseline: `17` and `18`.
- Current production bootstrap default: PostgreSQL `18/main`.

## Required runtime paths
- operator source checkout: `/opt/gxp/src/GXP-QLCL`
- staged backend releases: `/opt/gxp/backend-releases/<git_sha>`
- staged backend venvs: `/opt/gxp/backend-venvs/<git_sha>`
- current backend release symlink: `/opt/gxp/current-backend`
- current backend venv symlink: `/opt/gxp/current-venv`
- current frontend release symlink: `/opt/gxp/frontend-dist`
- runtime env file: `/etc/gxp/runtime.env`
- release metadata: `/opt/gxp/current-release.json`

## Exact operator checklist

1. Create VM

```bash
gcloud compute instances create gxp-web-prod \
  --project=gxp-qlcl-vm \
  --zone=asia-southeast1-a \
  --machine-type=e2-small \
  --image-family=ubuntu-2404-lts-amd64 \
  --image-project=ubuntu-os-cloud
```

2. Attach the runtime service account

```bash
gcloud compute instances set-service-account gxp-web-prod \
  --project=gxp-qlcl-vm \
  --zone=asia-southeast1-a \
  --service-account=gxp-vm-runtime@gxp-qlcl-vm.iam.gserviceaccount.com \
  --scopes=https://www.googleapis.com/auth/cloud-platform
```

3. SSH into the VM

```bash
gcloud compute ssh gxp-web-prod --project=gxp-qlcl-vm --zone=asia-southeast1-a
```

4. Clone the bootstrap checkout

```bash
git clone https://github.com/hahoangphuong/GXP-QLCL ~/GXP-QLCL-bootstrap
cd ~/GXP-QLCL-bootstrap
```

5. Bootstrap the VM

Confirm the shell prompt is the VM itself, not Google Cloud Shell.

Wrong:

```text
hahoangphuong@cloudshell:...
```

Right:

```text
hahoangphuong@gxp-web-prod:...
```

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

Expected result:
- bootstrap fails closed if it detects Google Cloud Shell instead of the target Compute Engine VM
- bootstrap verifies Compute Engine metadata against the expected project, instance, and zone before package mutation
- Python 3.12 host interpreter is present and validated exactly
- minimal bootstrap prerequisites are installed first: `ca-certificates`, `curl`, `gnupg`
- `/swapfile` is activated at 4 GB with `vm.swappiness=10` before heavier Node / package work
- PostgreSQL 18 is installed deterministically from explicit packages when required:
  - `postgresql-18`
  - `postgresql-client-18`
- PostgreSQL cluster ownership is explicit: `18/main`
- bootstrap fails closed if stray PostgreSQL clusters already exist instead of silently upgrading, dropping, or selecting the wrong cluster
- Node 22, Corepack, pinned pnpm, PostgreSQL, Nginx, rsync, Git, and `gcloud` are available
- `/swapfile` is active at 4 GB with `vm.swappiness=10`
- non-root app user/group `gxp` exists
- `/opt/gxp`, `/etc/gxp`, and `/var/backups/gxp-temp` are prepared
- bootstrap fails closed if the image does not provide Python 3.12 packages natively

6. Create the final application checkout owned by `gxp`

```bash
sudo -u gxp git clone https://github.com/hahoangphuong/GXP-QLCL /opt/gxp/src/GXP-QLCL
cd /opt/gxp/src/GXP-QLCL
```

7. Prepare runtime env

```bash
sudo install -d -m 0750 -o root -g gxp /etc/gxp
sudo cp backend/.env.vm.production.example /etc/gxp/runtime.env
sudo chown root:gxp /etc/gxp/runtime.env
sudo chmod 640 /etc/gxp/runtime.env
sudoedit /etc/gxp/runtime.env
```

Permission contract:
- `/etc/gxp` -> `root:gxp 0750`
- `/etc/gxp/runtime.env` -> `root:gxp 0640`
- `gxp` may read runtime secrets but may not edit them
- root/operator may edit runtime secrets

8. Configure PostgreSQL

```bash
sudo -E ./infra/vm/configure_postgres.sh
```

Default e2-small tuning profile:
- `shared_buffers=256MB`
- `effective_cache_size=768MB`
- `work_mem=4MB`
- `maintenance_work_mem=64MB`
- `autovacuum_work_mem=64MB`
- `max_connections=30`

Cluster contract:
- `configure_postgres.sh` targets only `VM_POSTGRES_MAJOR` + `VM_POSTGRES_CLUSTER_NAME`
- current production default is `18/main`
- stray extra clusters are a hard stop; the script will not auto-select by `find|sort|tail`

9. Configure Tailscale

```bash
export TAILSCALE_AUTH_KEY='YOUR_TAILSCALE_AUTH_KEY'
sudo -E ./infra/vm/configure_tailscale.sh
```

10. Verify runtime and Synology reachability

```bash
python3 tools/validate_vm_prod_deploy.py
sudo -E ./infra/vm/verify_prod.sh
```

11. Provision production TLS before first deploy

Production final state must remain HTTPS. `deploy_prod.sh` fails closed if:
- `VM_TLS_CERT_PATH` does not exist
- `VM_TLS_KEY_PATH` does not exist

Supported provisioning paths:
- install an existing certificate/key pair at the configured paths
- or provision Let’s Encrypt certificates with `certbot` after DNS points to the VM

Do not use self-signed certificates for production.
Do not add a load balancer solely for TLS.

12. Migrate legacy Cloud SQL -> local PostgreSQL only if that source data still matters

If the old Cloud SQL environment has no business data worth retaining, initialize local PostgreSQL fresh and skip this step.

Never invent the source project or instance. Set them explicitly:

```bash
SOURCE_CLOUD_SQL_PROJECT='<old-source-project>'
SOURCE_CLOUD_SQL_INSTANCE='<old-source-instance>'
DEST_BACKUP_BUCKET='gs://gxp-qlcl-vm-postgres-backup'

gcloud sql export sql "${SOURCE_CLOUD_SQL_INSTANCE}" "${DEST_BACKUP_BUCKET}/cloudsql-export.sql.gz" \
  --project="${SOURCE_CLOUD_SQL_PROJECT}" \
  --database=gxp_qlcl

gunzip -c cloudsql-export.sql.gz | psql "postgresql://gxp_app:YOUR_PASSWORD@127.0.0.1:5432/gxp_qlcl"
```

Cross-project note:
- if the Cloud SQL export runs from an older Google Cloud project into the current bucket `gs://gxp-qlcl-vm-postgres-backup`, grant the source Cloud SQL service agent permission to write into that destination bucket
- do not assume the source Cloud SQL instance exists in `gxp-qlcl-vm`

13. Deploy app from Git

```bash
cd /opt/gxp/src/GXP-QLCL
sudo -E ./infra/vm/deploy_prod.sh
```

Deployment privilege model:
- repository checkout and build artifacts are owned by `gxp:gxp`
- backend service runs as non-root `gxp`
- `deploy_prod.sh` requires root only for controlled operations:
  - systemd unit installation/reload
  - Nginx site installation/reload
  - current backend/frontend symlink switch
- deploy stages code/runtime by SHA:
  - `/opt/gxp/backend-releases/<git_sha>`
  - `/opt/gxp/backend-venvs/<git_sha>`
  - `/opt/gxp/frontend-releases/<git_sha>`
- the live service runs from:
  - `/opt/gxp/current-backend`
  - `/opt/gxp/current-venv`
  - `/opt/gxp/frontend-dist`
- pre-switch failures leave the active release untouched
- post-switch health failures trigger a safe rollback of backend/frontend symlinks and service restart
- the deploy script never auto-downgrades Alembic migrations

14. Enable backup

```bash
sudo crontab -e
```

Suggested nightly entry:

```text
30 1 * * * /opt/gxp/src/GXP-QLCL/infra/vm/backup_postgres.sh >> /var/log/gxp-backup.log 2>&1
```

15. Stop Cloud SQL only after VM verification succeeds

```bash
gcloud sql instances patch gxp-db \
  --project=gxp-qlcl-vm \
  --activation-policy=NEVER
```
