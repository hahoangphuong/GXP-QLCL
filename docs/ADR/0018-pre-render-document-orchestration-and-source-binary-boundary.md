# ADR 0018: Pre-render Document Orchestration And Source Binary Boundary

## Status
Approved

## Context
After Phase 5 seed and DB-backed source lookup, the system can already determine:
- which logical document family is being generated
- which payload fields are valid
- which prior source documents are required for copy-forward
- which generation attempt row should be persisted

However, source-document binary reuse still has a gap:
- `document_version` can point to a storage folder through `storage_binding_id`
- the current model does not yet record the exact file path of the source binary within that folder

## Decision
- Add a pre-render `DocumentService` orchestration module that performs:
  - payload build
  - template selection
  - source lookup request derivation
  - DB-backed source resolution
  - source-binary requirement planning
  - generation-run persistence
- Add a `SourceBinaryRequirement` contract that makes the remaining binary-access preconditions explicit.
- Keep copy-forward fail-closed:
  - a known source folder is not enough to start bookmark/table copy
  - exact source file location must be modeled or otherwise proven before render/copy-forward starts

## Consequences
- The project now has one orchestration owner for document generation before render.
- `StorageService` remains responsible only for file/folder access, not for deciding why a source document is needed.
- Render readiness is explicit instead of being inferred from partial data.

## Deferred
- persist exact source/output file path at `document_version` level
- render adapter execution
- binary source read + bookmark/table extraction
