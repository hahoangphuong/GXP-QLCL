# Phase 4.2 - Storage Lookup And Environment Configuration

## Goal
Move `StorageService` closer to real deployment behavior by:
- loading storage roots from environment
- preferring persisted `storage_binding`
- falling back to live folder resolution only when needed

## Scope completed on August 13, 2026
- Added environment-based storage config loader.
- Added `create_storage_service_from_env(...)`.
- Added application-level `StorageBindingLookupService`.
- Lookup flow now:
  1. query `storage_binding` by stable triplet
  2. if bound path still exists, return it directly
  3. otherwise fall back to live resolution
  4. if live resolution succeeds, refresh the binding

## Files
- [backend/app/storage/factory.py](/D:/GXP-QLCL/backend/app/storage/factory.py)
- [backend/app/storage/binding_lookup.py](/D:/GXP-QLCL/backend/app/storage/binding_lookup.py)
- [tests/test_phase4_storage_binding_lookup.py](/D:/GXP-QLCL/tests/test_phase4_storage_binding_lookup.py)

## Environment contract
- `STORAGE_INSPECTION_ROOT` required
- `STORAGE_DKKD_ROOT` optional
- `STORAGE_CLASS` optional, defaults to `local_filesystem_fake`

This allows a non-production private share or UNC path to be injected through configuration without changing business code.

## Important behavior
- A persisted binding is trusted only if the bound path still exists under the configured root.
- Missing or stale bindings do not fail open.
- Live resolution remains the source of truth for refreshing stale bindings.

## Next recommended step
1. Add an API or application service dependency provider that builds storage from environment once per app lifecycle.
2. Add dedicated non-production operational runbook for private-share testing.
3. Confirm DDKD folder contract before extending binding-first lookup to DDKD.
