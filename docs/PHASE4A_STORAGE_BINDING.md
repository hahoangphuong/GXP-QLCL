# Phase 4.1 - Storage Binding Persistence

## Goal
Persist successful storage resolution results into `storage_binding` so the system can remember proven folder mappings without exposing transport details to the business layer.

## Scope completed on August 13, 2026
- Added `resolve_and_bind_inspection_folder(...)`.
- Added deterministic upsert behavior for `storage_binding`.
- Kept fail-closed behavior:
  - if resolution is `NOT_FOUND`, no binding is created
  - if resolution is `AMBIGUOUS`, no binding is created
  - only `RESOLVED` results can create or update a binding
- Added `case_id` propagation into `storage_resolution_log`.

## Binding rules
- Binding identity remains:
  - `year`
  - `site_legacy_id`
  - `inspection_legacy_code`
- `relative_path` stores the root-relative path only.
- `observed_folder_label` stores the last resolved folder name.
- `storage_class` is copied from the active storage adapter config.
- Re-resolving the same legacy triplet updates the existing binding instead of creating duplicates.

## Important non-goals
- No NAS-specific adapter yet.
- No binding persistence for DDKD yet, because the DDKD folder identity contract is still provisional.
- No API exposure yet.

## Files
- [backend/app/storage/local.py](/D:/GXP-QLCL/backend/app/storage/local.py)
- [tests/test_phase4_storage_service.py](/D:/GXP-QLCL/tests/test_phase4_storage_service.py)

## Next recommended step
1. Add a Synology private-share adapter for non-production testing behind the same interface.
2. Confirm DDKD folder identity and then decide whether DDKD needs its own binding key model.
3. Add application-layer services that consult `storage_binding` first, then fall back to live resolution when needed.
