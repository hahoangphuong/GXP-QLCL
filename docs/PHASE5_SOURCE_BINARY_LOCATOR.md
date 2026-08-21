# Phase 5 Source Binary Locator

## Scope
This step upgrades Phase 5 from folder-level source readiness to exact source-binary readiness.

## Delivered
- exact binary locator fields on `document_version`
- locator registration and validation runtime
- source-binary stream access through `StorageService`
- smoke flow proving `render_ready = true` when an exact source file is registered

## Python modules
- `backend/app/document/version_locator.py`
- `backend/app/document/source_binary_access.py`

## Schema impact
`document_version` now carries:
- `storage_root`
- `storage_relative_path`
- `original_filename`

## Rules
- `storage_binding` remains folder identity only.
- `document_version` owns exact file identity.
- folder hints like `4.` or `6.` are not authoritative locators.
- copy-forward may proceed only when the exact locator is persisted and binding-consistent.

## Tooling
- `tools/smoke_phase5_source_binary_access.py`
