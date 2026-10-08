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
  - validates persisted generation-run/document/variant lineage (including the run's prepared `document_variant_id`) against the prepared persisted state before storage resolution or output-version mutation; reused allocations fail closed on the same lineage mismatch
  - locks the persisted `document_variant` row with `SELECT ... FOR UPDATE` for both new and reused allocations so the lock order remains `DocumentGenerationRun -> DocumentVariant` and concurrent allocation cannot supersede a reused version while it is being accepted
  - requires a reused allocation to still be the highest persisted `version_no` for the locked variant; a superseded allocation fails closed instead of proceeding into render work that finalization can never accept
  - resolves folder/occupancy and assigns `max(version_no)+1` only while holding that variant lock for new allocations
  - resolves the target storage folder through `StorageService`
  - creates a new `document_version` with the next `version_no`
  - persists exact output locator fields before rendering starts
  - links that `document_version` to `document_generation_run.output_document_version_id`
- Enforce the canonical PostgreSQL persistence invariant with a partial unique index on `document_version(document_variant_id) WHERE is_current`; the migration refuses to proceed when duplicate-current lineage already exists and does not auto-repair historical data. SQLite remains a test/development surface where runtime guards can exercise corrupt legacy states.
- The output finalizer owns compensation for failures after its exclusive physical write. It hashes the rendered payload before write, requires the stored checksum to match that payload before promoting lineage, and on any post-write finalization failure deletes the target only when the current checksum still proves ownership by that render attempt. Detected checksum drift fails closed and preserves the current target.
- The workflow service must not delete an allocated output path when finalization has not returned a checksum; pre-finalization/render failures therefore cannot delete a foreign file that merely appeared at the reserved path. After finalization returns, render-time compensation uses that returned checksum before deleting.
- On render failure after a finalized output may have been written, compensate the filesystem before attempting database lineage restoration. If SQLAlchemy has already placed the transaction in a failed/inactive state, skip further database compensation and let the request transaction roll back; do not let `PendingRollbackError` prevent deletion of a newly written output or mask the original database failure.
- If the database commit fails after a successful render, delete the rendered target only when its current checksum still matches the checksum returned by that render attempt. Missing checksum evidence or detected checksum drift fails closed and preserves the current target instead of deleting a file that may have been replaced by another actor.
- When rolling back an uncommitted finalized render, restore prior current lineage only when the allocated version was actually promoted current; a pre-finalization failure must not reactivate a stale snapshot of the previous current. When restoration is required, clear the newly-current version in the database before reactivating the single previous current version, so rollback never crosses the PostgreSQL uniqueness boundary transiently; if corrupt legacy state reports multiple previous currents, do not auto-repair them.
- Require current-binary readers to fail closed when one persisted `document_variant` has more than one `is_current=true` version; readers must not rank through or repair that lineage corruption.
- A current binary is readable only when its persisted locator and SHA-256 checksum are complete. The content endpoint verifies the exact bytes it will return against `document_version.checksum_sha256` before constructing the streaming response; missing or checksum-drifted storage content fails closed instead of being served as the current document.
- Catalog/workspace action readiness uses the same openability contract: a current version without a persisted checksum is not advertised as openable and must not suppress a create action that remains valid until current-binary integrity is complete.
- Current-binary selection acquires shared locks on all persisted `document_variant` rows for the document in stable ID order and refreshes both variants and versions with `populate_existing`. The request therefore cannot serve a stale ORM snapshot, and a concurrent finalizer's exclusive variant lock cannot promote a different current version until the reader has finished verifying/spooling the selected binary.
- Add a write-finalization step that:
  - locks and refreshes the persisted `document_generation_run` row with `SELECT ... FOR UPDATE` before evaluating finalizability, so a preloaded ORM identity cannot hide a concurrent lifecycle change and another transaction cannot change run status while finalization proceeds into output I/O
  - requires the generation run to be `pending` before any output I/O; `failed`, `cancelled`, and `succeeded` runs fail closed, and a retry must be explicitly re-claimed to `pending` by the workflow owner first
  - verifies the locked generation run's persisted `document_variant_id` is the allocated version's variant before any output I/O; missing or different lineage fails closed without promoting a different variant
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
