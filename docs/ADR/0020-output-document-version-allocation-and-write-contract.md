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
  - requires the locked generation run to be `pending` before creating or reusing an output allocation; `failed` runs must be explicitly reclaimed to `pending` by the workflow owner first, while `cancelled` and `succeeded` runs fail closed without output-version mutation
  - validates persisted generation-run/document/variant lineage against the prepared persisted state before storage resolution or output-version mutation; reused allocations fail closed on the same lineage mismatch
  - locks the persisted `document_variant` row with `SELECT ... FOR UPDATE` before folder resolution, occupancy checks, and `max(version_no)+1` assignment so concurrent allocations for the same variant serialize
  - resolves the target storage folder through `StorageService`
  - creates a new `document_version` with the next `version_no`
  - persists exact output locator fields before rendering starts
  - links that `document_version` to `document_generation_run.output_document_version_id`
- Enforce the canonical PostgreSQL persistence invariant with a partial unique index on `document_version(document_variant_id) WHERE is_current`; the migration refuses to proceed when duplicate-current lineage already exists and does not auto-repair historical data. SQLite remains a test/development surface where runtime guards can exercise corrupt legacy states.
- When rolling back an uncommitted finalized render, restore prior current lineage only when the allocated version was actually promoted current; a pre-finalization failure must not reactivate a stale snapshot of the previous current. When restoration is required, clear the newly-current version in the database before reactivating the single previous current version, so rollback never crosses the PostgreSQL uniqueness boundary transiently; if corrupt legacy state reports multiple previous currents, do not auto-repair them.
- Require current-binary readers to fail closed when one persisted `document_variant` has more than one `is_current=true` version; readers must not rank through or repair that lineage corruption.
- Add a write-finalization step that:
  - locks and refreshes the persisted `document_generation_run` row with `SELECT ... FOR UPDATE` before evaluating finalizability, so a preloaded ORM identity cannot hide a concurrent lifecycle change and another transaction cannot change run status while finalization proceeds into output I/O
  - requires the generation run to be `pending` before any output I/O; `failed`, `cancelled`, and `succeeded` runs fail closed, and a retry must be explicitly re-claimed to `pending` by the workflow owner first
  - locks the persisted `document_variant` row with `SELECT ... FOR UPDATE` after the generation-run lock and before output I/O, preserving the mutation lock order `DocumentGenerationRun -> DocumentVariant` while concurrent finalizers for the same variant serialize before changing current-version state
  - requires the allocated version to still be the highest persisted `version_no` for the locked variant before output I/O; retries of older allocations fail closed instead of rewinding document-version lineage
  - requires the locked variant to have at most one pre-existing `is_current=true` version before output I/O; duplicate-current lineage fails closed instead of being normalized by the new write
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
