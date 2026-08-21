# Cloud Run Operations Runbook

## Purpose
This runbook defines the minimum operator flow for deploying and validating the backend on Google Cloud Run without changing business/storage ownership boundaries.

## Inputs
- service bootstrap config: [service_bootstrap.example.json](/D:/GXP-QLCL/infra/cloudrun/service_bootstrap.example.json)
- secret bindings: [secret_bindings.example.json](/D:/GXP-QLCL/infra/cloudrun/secret_bindings.example.json)
- backend env contract: [.env.cloudrun.example](/D:/GXP-QLCL/backend/.env.cloudrun.example)
- deploy script: [deploy_backend.ps1](/D:/GXP-QLCL/infra/cloudrun/deploy_backend.ps1)

## Pre-deploy checks
1. Confirm Cloud SQL instance exists and the connection name matches both bootstrap config and backend env file.
2. Confirm the runtime service account exists and has the minimum required access for Cloud Run, Secret Manager, and Cloud SQL connectivity.
3. Confirm `AUTH_IAP_EXPECTED_AUDIENCE` matches the real IAP-protected entrypoint design.
4. Confirm secrets are populated in Secret Manager instead of committed values in git.
5. Confirm storage mode is intentional:
   - `external_bridge` if storage-touching behavior is delegated behind the bridge adapter contract.
   - `nfs_volume` only for experimental or comparison validation, not as the default production baseline.
   - `disabled` only for non-storage rollout validation.
6. Do not use in-container SMB/Tailscale mount plans for Cloud Run.

## Dry-run validation
```powershell
python tools/validate_phase15_service_bootstrap.py infra/cloudrun/service_bootstrap.example.json
powershell -File infra/cloudrun/deploy_backend.ps1 -ConfigPath infra/cloudrun/service_bootstrap.example.json -DryRun
```

## Deploy
```powershell
powershell -File infra/cloudrun/deploy_backend.ps1 -ConfigPath infra/cloudrun/service_bootstrap.example.json
```

## Post-deploy checks
1. Open `/healthz` and verify:
   - `ok=true`
   - expected `deployment_platform`
   - `storage_configured` matches intended storage mode
2. Open `/app/status` and verify:
   - expected `auth_mode`
   - expected phase visibility
3. Verify authenticated read APIs return data for an authorized operator.
4. If storage mode is `nfs_volume`, treat the rollout as experimental and verify storage lookup endpoints plus file-operation invariants before allowing business mutations.
5. If document generation is in scope for this rollout, verify at least one known-good family through the document prepare/render path.

## Promotion notes
- Prefer explicit secret versions for production rollout instead of `:latest`.
- Keep staging and production bootstrap configs separate.
- Any storage-mode change should be treated as an operational architecture change, not a casual config edit.

## Known gate
Cloud Run's current runtime contract does not support mounting SMB/CIFS or Tailscale-driven network file systems from inside the container. If Synology access is needed from Cloud Run, keep business code behind `StorageService`; use a bridge-backed integration path by default, and treat native NFS volume mounts as experimental only unless their semantics are separately proven.
