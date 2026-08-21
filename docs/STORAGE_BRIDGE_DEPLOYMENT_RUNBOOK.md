# Storage Bridge Deployment Runbook

## Purpose
This runbook describes how to deploy and validate the storage bridge baseline introduced in Phase 17.

## Current deployment posture
- The main application remains targeted at Cloud Run.
- The storage bridge is a separate adapter runtime.
- The bridge should be deployed only on infrastructure that can actually reach Synology through an approved private path.
- After ADR 0047, this runbook is primarily a fallback path if PoC A does not satisfy requirements.

## Current baseline artifacts
- bridge app entrypoint: [storage_bridge_main.py](/D:/GXP-QLCL/backend/storage_bridge_main.py)
- bridge container baseline: [Dockerfile.storage_bridge](/D:/GXP-QLCL/backend/Dockerfile.storage_bridge)
- bridge env example: [.env.cloudrun.external_bridge.example](/D:/GXP-QLCL/backend/.env.cloudrun.external_bridge.example)
- main app external-bridge bootstrap example: [service_bootstrap.external_bridge.example.json](/D:/GXP-QLCL/infra/cloudrun/service_bootstrap.external_bridge.example.json)

## Fallback non-production path
1. Run the bridge on a host that already has trusted private connectivity to Synology.
2. Point the main app at that bridge using:
   - `STORAGE_CLASS=external_bridge_http`
   - `STORAGE_BRIDGE_BASE_URL`
   - `STORAGE_BRIDGE_AUTH_AUDIENCE`
3. Keep the bridge private; browser clients must never invoke it directly.

## If PoC B is needed on Google Cloud
When you are ready, the steps I will ask you to perform are expected to be:
1. Build and publish a bridge image from [Dockerfile.storage_bridge](/D:/GXP-QLCL/backend/Dockerfile.storage_bridge).
2. Deploy a private bridge service using a service account dedicated to bridge runtime.
3. Grant the main app service account `roles/run.invoker` on the bridge service.
4. Point the main app external-bridge env at the bridge URL/audience.

These steps depend on your chosen host for Synology reachability:
- private VM / office-connected host
- or another private runtime that can reach Synology safely

## Important constraint
This runbook does not assume the bridge itself runs on Cloud Run. If Synology connectivity is easier or safer from another private host, that host is acceptable as long as:
- the bridge stays private
- the main app calls it service-to-service
- business code still goes only through `StorageService`

## Google Cloud auth note
For Cloud Run-to-Cloud Run private calls, the current recommended model is service-to-service authentication with an ID token and `roles/run.invoker` on the receiving service.

## Phase 18 handoff
Phase 18 now adds a dedicated non-production deployment pack for the bridge itself:
- [storage_bridge_bootstrap.example.json](/D:/GXP-QLCL/infra/cloudrun/storage_bridge_bootstrap.example.json)
- [deploy_storage_bridge.ps1](/D:/GXP-QLCL/infra/cloudrun/deploy_storage_bridge.ps1)
- [validate_phase18_storage_bridge_bootstrap.py](/D:/GXP-QLCL/tools/validate_phase18_storage_bridge_bootstrap.py)
