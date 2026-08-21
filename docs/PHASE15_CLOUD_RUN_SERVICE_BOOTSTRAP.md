# Phase 15 Cloud Run Service Bootstrap

## Goal
Add repository-owned service bootstrap artifacts and an operator runbook so Cloud Run rollout is repeatable, validated, and honest about Synology connectivity constraints.

## Delivered
- bootstrap config example: [service_bootstrap.example.json](/D:/GXP-QLCL/infra/cloudrun/service_bootstrap.example.json)
- secret bindings example: [secret_bindings.example.json](/D:/GXP-QLCL/infra/cloudrun/secret_bindings.example.json)
- deploy script: [deploy_backend.ps1](/D:/GXP-QLCL/infra/cloudrun/deploy_backend.ps1)
- validator: [validate_phase15_service_bootstrap.py](/D:/GXP-QLCL/tools/validate_phase15_service_bootstrap.py)
- tests: [test_phase15_service_bootstrap.py](/D:/GXP-QLCL/tests/test_phase15_service_bootstrap.py)
- operations runbook: [CLOUD_RUN_OPERATIONS_RUNBOOK.md](/D:/GXP-QLCL/docs/CLOUD_RUN_OPERATIONS_RUNBOOK.md)
- ADR: [0043-phase15-cloud-run-bootstrap-rejects-in-container-smb-mounts.md](/D:/GXP-QLCL/docs/ADR/0043-phase15-cloud-run-bootstrap-rejects-in-container-smb-mounts.md)

## What changed
- The repo now contains a concrete Cloud Run deploy-input model instead of relying on manual operator memory.
- The deploy path validates:
  - project/region/service/image/service account
  - backend env contract
  - Secret Manager bindings
  - Cloud SQL connection name consistency
  - storage connectivity mode
- The deploy script now prints the exact `gcloud run deploy` command preview after validation.
- The bootstrap layer explicitly rejects in-container SMB/Tailscale storage mount strategies for Cloud Run.

## Storage connectivity finding
Reviewed on August 19, 2026:
- Cloud Run currently supports managed volume mounts such as NFS.
- Cloud Run runtime restrictions explicitly reject mounting SMB/CIFS or similar network file systems from inside the container process.

That means the earlier generic assumption of "Tailscale first" is not sufficient by itself for a Cloud Run service that must directly access Synology file paths. For Cloud Run-hosted storage access, the viable modes are now documented as:
- `nfs_volume`
- `external_bridge`
- `disabled` for non-storage rollout validation

Current interpretation after ADR 0047:
- `nfs_volume` remains optional/experimental only.
- `external_bridge` remains the production-integration adapter shape.
- a dedicated bridge host is not the immediate next step; PoC A should be evaluated first behind `BridgeStorageAdapter`.

## Scope boundary
- This phase does not create Terraform or Cloud Build pipelines yet.
- This phase does not provision the Google Cloud resources automatically.
- This phase does not change the backend storage adapter ownership model.
- This phase does not resolve the final production transport; it only makes the allowed deployment shapes explicit and validated.

## Google Cloud references
Reviewed on August 19, 2026:
- [Cloud Run container runtime contract](https://docs.cloud.google.com/run/docs/container-contract)
- [Configure NFS volume mounts for Cloud Run services](https://docs.cloud.google.com/run/docs/configuring/services/nfs-volume-mounts)
- [gcloud run deploy](https://docs.cloud.google.com/sdk/gcloud/reference/run/deploy)
