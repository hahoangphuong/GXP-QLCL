# Phase 4 - StorageService Baseline

## Goal
Implement a testable `StorageService` baseline that preserves legacy folder identity rules while keeping business logic storage-agnostic.

## Scope completed on August 13, 2026
- Added a local/fake filesystem-backed `StorageService` adapter for contract testing.
- Implemented fail-closed inspection folder resolution by:
  - `year`
  - `site_legacy_id`
  - `inspection_legacy_code`
- Added provisional DDKD folder resolution by `site_legacy_id` token under a dedicated DDKD root.
- Added safe root-boundary validation and path-traversal rejection.
- Added IO helpers:
  - `list`
  - `stat`
  - `exists`
  - `read_stream`
  - `write_stream`
  - `create_folder`
  - `copy`
  - `move`
  - `rename`
  - `checksum`
- Added persistence of resolution attempts into `storage_resolution_log`.

## Files
- [backend/app/storage/types.py](/D:/GXP-QLCL/backend/app/storage/types.py)
- [backend/app/storage/local.py](/D:/GXP-QLCL/backend/app/storage/local.py)
- [backend/app/storage/__init__.py](/D:/GXP-QLCL/backend/app/storage/__init__.py)
- [tests/test_phase4_storage_service.py](/D:/GXP-QLCL/tests/test_phase4_storage_service.py)

## Important behavior
- Inspection folder resolution fails closed on `0` or `>1` matches.
- Relative paths are normalized and cannot escape the configured storage root.
- Writes use temp-file then atomic replace on the same filesystem.
- Business code can call the adapter without embedding UNC paths or network details.

## DDKD note
This baseline originally carried a provisional DDKD resolver.

Current successor state:
- search direct child folders under configured `dkkd_root`
- match the durable token `(<site_legacy_id>)`
- treat the descriptive prefix as mutable presentation text only
- fail closed on `0` or `>1` matches

The issuance-cycle subfolder `Láº§n n` remains a downstream document-placement concern rather than a resolver identity key.

## Next recommended step
1. Keep private-share execution evidence collection in the non-production runbook and probe CLI.
2. Add application-layer lookup that prefers persisted `storage_binding` before live folder scans.
3. Keep DDKD binding persistence deferred until a dedicated DDKD binding key model is approved.
