# Phase 17 External Bridge Runtime Baseline

## Goal
Make the bridge-backed storage contract a runnable path in the repository, without forcing immediate bridge-host deployment.

## Delivered
- main-app bridge adapter: [external_bridge.py](/D:/GXP-QLCL/backend/app/storage/external_bridge.py)
- bridge app entrypoint: [storage_bridge_main.py](/D:/GXP-QLCL/backend/storage_bridge_main.py)
- bridge container baseline: [Dockerfile.storage_bridge](/D:/GXP-QLCL/backend/Dockerfile.storage_bridge)
- external-bridge app env example: [.env.cloudrun.external_bridge.example](/D:/GXP-QLCL/backend/.env.cloudrun.external_bridge.example)
- bridge deployment runbook: [STORAGE_BRIDGE_DEPLOYMENT_RUNBOOK.md](/D:/GXP-QLCL/docs/STORAGE_BRIDGE_DEPLOYMENT_RUNBOOK.md)
- ADR: [0045-phase17-external-bridge-runtime-baseline.md](/D:/GXP-QLCL/docs/ADR/0045-phase17-external-bridge-runtime-baseline.md)

## What changed
- The main application can now build a storage adapter using `STORAGE_CLASS=external_bridge_http`.
- The repository now includes a standalone bridge HTTP surface that exposes the `StorageService` contract through FastAPI.
- Phase 14 validation now understands `external_bridge_http` storage env requirements.
- Phase 15 bootstrap validation now has a concrete external-bridge config example to validate against.
- Existing binding lookup no longer assumes an on-disk absolute path is always available when a persisted binding is reused.
- This runtime now serves two purposes:
  - PoC A client/contract evolution without changing business code
  - PoC B fallback if a dedicated bridge host becomes necessary later

## Scope boundary
- This phase does not yet deploy the bridge anywhere.
- This phase does not yet add full bridge observability, retry policy, or circuit-breaking.
- This phase does not yet add app-level authorization inside the bridge process because the intended production boundary is infrastructure-level private service-to-service auth.
- This phase does not require provisioning a dedicated bridge host yet.

## Google Cloud note
Reviewed on August 20, 2026:
- Cloud Run private service-to-service access should use an ID token and `roles/run.invoker` on the receiving service.
- If you want to test the bridge-host fallback path on Google Cloud later, the artifacts created in this phase remain usable.
