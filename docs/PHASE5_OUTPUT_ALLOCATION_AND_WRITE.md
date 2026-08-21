# Phase 5 Output Allocation And Write

## Scope
This step prepares exact output document versions before render and defines how rendered binaries are finalized through `StorageService`.

## Delivered
- output document-version allocation for inspection-folder flows
- output document-version allocation for DDKD-folder flows
- generation-run linkage to `output_document_version_id`
- write-finalization contract through `StorageService`
- smoke flows for allocation-only and allocation-plus-write

## Python modules
- `backend/app/document/output_version.py`

## Main flow
1. Prepare document generation plan.
2. Resolve target storage folder through `StorageService`.
3. Allocate new `document_version` with exact output locator.
4. Link the allocated version to `document_generation_run`.
5. After render produces bytes, write through `StorageService`.
6. Compute checksum and mark the version current.
7. Mark the generation run succeeded.

## Current limits
- exact output filename must still be supplied explicitly by the caller
- current implementation supports `inspection_folder` and `dkkd_folder`
- render adapter itself is still deferred

## Tooling
- `tools/smoke_phase5_output_allocation.py`
- `tools/smoke_phase5_output_write.py`
- `tools/smoke_phase5_dkkd_certificate_render.py`
