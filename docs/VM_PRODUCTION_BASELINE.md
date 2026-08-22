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

## Required runtime files
- application source checkout: `/opt/gxp/src/GXP-QLCL`
- Python venv: `/opt/gxp/venv`
- frontend dist: `/opt/gxp/frontend-dist`
- runtime env file: `/etc/gxp/runtime.env`
- release metadata: `/opt/gxp/current-release.json`

## Exact operator checklist

1. Create VM

```bash
gcloud compute instances create gxp-web-prod \
  --project=gxp-qlcl \
  --zone=asia-southeast1-b \
  --machine-type=e2-small \
  --image-family=ubuntu-2404-lts-amd64 \
  --image-project=ubuntu-os-cloud
```

2. Attach appropriate service account and scopes

```bash
gcloud compute instances set-service-account gxp-web-prod \
  --project=gxp-qlcl \
  --zone=asia-southeast1-b \
  --service-account=YOUR_VM_SERVICE_ACCOUNT@gxp-qlcl.iam.gserviceaccount.com \
  --scopes=https://www.googleapis.com/auth/cloud-platform
```

3. SSH into VM

```bash
gcloud compute ssh gxp-web-prod --project=gxp-qlcl --zone=asia-southeast1-b
```

4. Clone repo

```bash
git clone https://github.com/hahoangphuong/GXP-QLCL ~/GXP-QLCL-bootstrap
cd ~/GXP-QLCL-bootstrap
```

5. Bootstrap VM

```bash
sudo ./infra/vm/bootstrap_vm.sh
```

Expected fresh-machine result:
- Ubuntu LTS host packages for Python, PostgreSQL, Nginx, rsync, Git, Node.js, Corepack, and `gcloud`
- `/swapfile` provisioned at 4 GB by default with `vm.swappiness=10`
- non-root application user/group `gxp`
- prepared paths under `/opt/gxp`, `/etc/gxp`, and `/var/backups/gxp-temp`

6. Create the final application checkout owned by `gxp`

```bash
sudo -u gxp git clone https://github.com/hahoangphuong/GXP-QLCL /opt/gxp/src/GXP-QLCL
cd /opt/gxp/src/GXP-QLCL
```

7. Prepare runtime env

```bash
sudo install -d -m 0750 /etc/gxp
sudo cp backend/.env.vm.production.example /etc/gxp/runtime.env
sudo chmod 600 /etc/gxp/runtime.env
sudoedit /etc/gxp/runtime.env
```

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

9. Configure Tailscale

```bash
export TAILSCALE_AUTH_KEY='YOUR_TAILSCALE_AUTH_KEY'
sudo -E ./infra/vm/configure_tailscale.sh
```

10. Verify Synology SMB reachability

```bash
python3 tools/validate_vm_prod_deploy.py
sudo -E ./infra/vm/verify_prod.sh
```

11. Migrate Cloud SQL -> local PostgreSQL

```bash
gcloud sql export sql gxp-db gs://YOUR_GXP_BACKUP_BUCKET/cloudsql-export.sql.gz \
  --project=gxp-qlcl \
  --database=gxp_qlcl

gunzip -c cloudsql-export.sql.gz | psql "postgresql://gxp_app:YOUR_PASSWORD@127.0.0.1:5432/gxp_qlcl"
```

12. Deploy app from Git

```bash
cd /opt/gxp/src/GXP-QLCL
sudo -E ./infra/vm/deploy_prod.sh
```

Deployment privilege model:
- repository checkout and build artifacts are owned by `gxp:gxp`
- backend service runs as non-root `gxp`
- `deploy_prod.sh` requires `root` only for controlled operations:
  - systemd unit installation/reload
  - Nginx site installation/reload
  - release symlink switch under `/opt/gxp`
- the deploy script fetches origin, resolves the approved commit, checks it out in detached mode, backs up PostgreSQL, runs Alembic, then restarts services
- if deploy fails before restart, the script restores the previous frontend symlink and attempts to return the checkout to the prior state

13. Enable backup

```bash
sudo crontab -e
```

Suggested nightly entry:

```text
30 1 * * * /opt/gxp/src/GXP-QLCL/infra/vm/backup_postgres.sh >> /var/log/gxp-backup.log 2>&1
```

14. Stop Cloud SQL only after VM verification succeeds

```bash
gcloud sql instances patch gxp-db \
  --project=gxp-qlcl \
  --activation-policy=NEVER
```
