# Phase 16 Storage Strategy Decision Pack

## Goal
Turn the storage-mode fork from Phase 15 into an explicit, evidence-backed planning decision for the next implementation phases.

## Delivered
- strategy report builder: [build_phase16_storage_strategy_report.py](/D:/GXP-QLCL/tools/build_phase16_storage_strategy_report.py)
- strategy report test: [test_phase16_storage_strategy_report.py](/D:/GXP-QLCL/tests/test_phase16_storage_strategy_report.py)
- strategy comparison doc: [STORAGE_DEPLOYMENT_OPTIONS.md](/D:/GXP-QLCL/docs/STORAGE_DEPLOYMENT_OPTIONS.md)
- bridge contract doc: [STORAGE_BRIDGE_CONTRACT.md](/D:/GXP-QLCL/docs/STORAGE_BRIDGE_CONTRACT.md)
- alternate bootstrap example: [service_bootstrap.external_bridge.example.json](/D:/GXP-QLCL/infra/cloudrun/service_bootstrap.external_bridge.example.json)
- ADR: [0044-phase16-planning-assumption-prefers-external-bridge.md](/D:/GXP-QLCL/docs/ADR/0044-phase16-planning-assumption-prefers-external-bridge.md)

## What changed
- The repo now distinguishes between:
  - the business-visible `StorageService` contract
  - PoC A application-level transport validation
  - PoC B dedicated bridge-host fallback
  - optional experimental NFS transport
- The project now has a documented bridge contract so future storage-adapter work can proceed without pushing storage semantics into business services.
- Phase 15 bootstrap validation now also checks the required fields for `external_bridge` mode.
- A generated Phase 16 report now keeps the transport tradeoffs visible instead of leaving them as verbal reasoning only.

## Why this phase exists
Without this phase, the project risks quietly sliding into `nfs_volume` as the de facto production choice simply because it is easier to bootstrap first.

That would be misleading because:
- `nfs_volume` is easier to execute now
- transport-swappability remains a hard architectural requirement
- Cloud Run NFS has documented no-lock semantics, which must not silently become production file semantics
- the project prefers not to provision a separate bridge host until evidence proves it is needed

## Scope boundary
- This phase does not implement the storage bridge runtime yet.
- This phase does not remove NFS bootstrap support.
- This phase does not change backend business logic or document-generation rules.

## Current interpretation after ADR 0047
- Do not treat `nfs_volume` as the production baseline.
- Continue application/storage-contract work without provisioning a bridge host yet.
- Run PoC A first:
  - `Cloud Run -> Tailscale userspace networking -> Synology`
  - behind `BridgeStorageAdapter`
- Only if PoC A fails reliability, performance, or security goals, move to PoC B with a dedicated bridge host.

## Google Cloud references
Reviewed on August 20, 2026:
- [Configure NFS volume mounts for Cloud Run services](https://docs.cloud.google.com/run/docs/configuring/services/nfs-volume-mounts)
- [Compare Direct VPC egress and VPC connectors](https://docs.cloud.google.com/run/docs/configuring/connecting-vpc)
- [Connect to a VPC network](https://docs.cloud.google.com/vpc/docs/configure-serverless-vpc-access)
