# ADR 0045: Phase 17 external bridge runtime baseline

## Status
Approved

## Context
Phase 16 established a bridge-oriented storage direction, but the repository still had no runnable runtime baseline for that option. Without a runnable baseline, the project would still be biased toward direct filesystem-style transports simply because those paths had executable artifacts.

The project needs a baseline that proves:
- the main app can instantiate a storage adapter that is not filesystem-local
- the bridge contract can be represented as real HTTP operations
- deployment inputs for `external_bridge` can be validated
- future Google Cloud or private-host rollout can be prepared without rewriting business logic

## Decision
- Add `ExternalBridgeStorageService` as a main-app client adapter.
- Add a minimal bridge FastAPI app entrypoint backed by the existing filesystem storage adapter.
- Keep bridge auth at the infrastructure boundary; for Cloud Run-to-Cloud Run usage, use private service-to-service authentication rather than browser-visible credentials.
- Add a separate env example for the main app when it runs in `external_bridge` mode.
- Add a dedicated bridge container baseline and deployment runbook.

## Consequences
- The bridge path is now a runnable baseline rather than only a planning note.
- The repo can validate both:
  - direct NFS bootstrap
  - external bridge bootstrap
- Storage adapter evolution can continue without moving transport concerns into workflow or document services.
- ADR 0047 later clarified that this runtime baseline does not force immediate bridge-host deployment; it also supports PoC-first transport evaluation while preserving the same business boundary.
