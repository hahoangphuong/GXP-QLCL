# ADR 0020: Output Document Version Allocation And Write Contract

## Status
Approved

## Context
Phase 5 can already:
- prepare document-generation requests
- resolve source dependencies
- persist generation attempts
- open exact source binaries when locators are known

The next missing step before introducing a render adapter is:
- reserving an exact output binary location for the new document version
- attaching that output version to the generation run
- defining how a rendered binary is written and finalized through `StorageService`

## Decision
- Add an output-allocation step that:
  - locks the persisted `document_generation_run` row with `SELECT ... FOR UPDATE` and refreshes any preloaded ORM identity before reading `output_document_version_id`, so concurrent callers for the same run cannot allocate twice from stale state
  - validates persisted generation-run/document/variant lineage against the prepared persisted state before storage resolution or output-version mutation; reused allocations fail closed on the same lineage mismatch
  - locks the persisted `document_variant` row with `SELECT ... FOR UPDATE` before folder resolution, occupancy checks, and `max(version_no)+1` assignment so concurrent allocations for the same variant serialize
  - resolves the target storage folder through `StorageService`
  - creates a new `document_version` with the next `version_no`
  - persists exact output locator fields before rendering starts
  - links that `document_version` to `document_generation_run.output_document_version_id`
- Add a write-finalization step that:
  - requires the generation run to be `pending` before any output I/O; `failed`, `cancelled`, and `succeeded` runs fail closed, and a retry must be explicitly re-claimed to `pending` by the workflow owner first
  - locks the persisted `document_variant` row with `SELECT ... FOR UPDATE` before output I/O so concurrent finalizers for the same variant serialize before changing current-version state
  - writes the rendered binary through `StorageService.write_stream(..., overwrite=False)` so a target that appears after allocation cannot be overwritten
  - treats an existing target as a fail-closed storage conflict and does not delete that pre-existing file during render cleanup
  - computes checksum through `StorageService.checksum`
  - marks the allocated version current
  - marks prior versions for the same variant non-current
  - marks the generation run succeeded

## Consequences
- The render adapter will receive a preallocated output target instead of inventing file paths.
- `DocumentService` remains the owner of document-version lineage and success semantics.
- `StorageService` remains the owner of file IO only.

## Deferred
- naming policy automation beyond caller-supplied exact filename
- non-inspection output scopes such as `support_document`
- rollback/cleanup policy for allocated-but-never-written versions
