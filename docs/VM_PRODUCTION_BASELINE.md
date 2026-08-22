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
  --machine-type=e2-medium \
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
sudo mkdir -p /opt/gxp/src
sudo chown -R "$USER":"$USER" /opt/gxp/src
git clone https://github.com/hahoangphuong/GXP-QLCL /opt/gxp/src/GXP-QLCL
cd /opt/gxp/src/GXP-QLCL
```

5. Bootstrap VM

```bash
sudo ./infra/vm/bootstrap_vm.sh
```

6. Prepare runtime env

```bash
sudo install -d -m 0750 /etc/gxp
sudo cp backend/.env.vm.production.example /etc/gxp/runtime.env
sudo chmod 600 /etc/gxp/runtime.env
sudoedit /etc/gxp/runtime.env
```

7. Configure PostgreSQL

```bash
set -a
source /etc/gxp/runtime.env
set +a
sudo -E ./infra/vm/configure_postgres.sh
```

8. Configure Tailscale

```bash
export TAILSCALE_AUTH_KEY='YOUR_TAILSCALE_AUTH_KEY'
sudo -E ./infra/vm/configure_tailscale.sh
```

9. Verify Synology SMB reachability

```bash
set -a
source /etc/gxp/runtime.env
set +a
python3 tools/validate_vm_prod_deploy.py
sudo -E ./infra/vm/verify_prod.sh
```

10. Migrate Cloud SQL -> local PostgreSQL

```bash
gcloud sql export sql gxp-db gs://YOUR_GXP_BACKUP_BUCKET/cloudsql-export.sql.gz \
  --project=gxp-qlcl \
  --database=gxp_qlcl

gunzip -c cloudsql-export.sql.gz | psql "postgresql://gxp_app:YOUR_PASSWORD@127.0.0.1:5432/gxp_qlcl"
```

11. Deploy app from Git

```bash
cd /opt/gxp/src/GXP-QLCL
./infra/vm/deploy_prod.sh
```

12. Enable backup

```bash
sudo crontab -e
```

Suggested nightly entry:

```text
30 1 * * * source /etc/gxp/runtime.env && /opt/gxp/src/GXP-QLCL/infra/vm/backup_postgres.sh >> /var/log/gxp-backup.log 2>&1
```

13. Stop Cloud SQL only after VM verification succeeds

```bash
gcloud sql instances patch gxp-db \
  --project=gxp-qlcl \
  --activation-policy=NEVER
```
