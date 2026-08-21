# ADR 0049: Storage binding persistence belongs to application layer

## Status
Approved

## Context
The original Phase 4 contract mixed physical storage resolution with database persistence by allowing filesystem-style adapters to create/update `StorageBinding` rows directly. The external bridge path exposed the inconsistency because it could resolve a folder but returned no persisted binding.

## Decision
- Storage adapters own:
  - physical folder resolution
  - file IO
- Application/storage-binding service owns:
  - persisted binding lookup/reuse
  - live resolve fallback
  - binding upsert/update
  - resolution log persistence

## Consequences
- Local filesystem and bridge-backed adapters now share one binding persistence path.
- Document generation no longer fails only because the bridge adapter itself did not write DB state.
