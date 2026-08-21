# Phase 4.3 - Storage App Integration

## Goal
Wire storage lookup into the read-only app lifecycle so storage behavior can be exercised end-to-end through dependency injection and environment configuration.

## Scope completed on August 13, 2026
- Added app-level storage initialization.
- Added a read-only inspection folder probe endpoint.
- Added dependency wiring for:
  - DB session
  - configured storage lookup service
- Exposed storage configuration status through `/healthz`.

## Endpoint
- `GET /storage/inspection-folder`
- `GET /storage/dkkd-folder`

Query params:
- `year`
- `site_legacy_id`
- `inspection_legacy_code`
- optional `case_id`

Response includes:
- resolution `status`
- `source` = `binding` or `live_resolution`
- root-relative path only
- candidate count
- detail
- current adapter storage class
- current binding payload when present

For DDKD:
- lookup is live-resolution only in the current baseline;
- the resolver uses the durable `(<site_id>)` token and never treats the full folder display name as business identity.

## Guardrails
- The endpoint stays read-only.
- It does not expose absolute UNC paths.
- It does not expose NAS credentials.
- It uses binding-first lookup with live fallback.

## Files
- [backend/app/main.py](/D:/GXP-QLCL/backend/app/main.py)
- [backend/app/read_models.py](/D:/GXP-QLCL/backend/app/read_models.py)
- [tests/test_phase4_storage_api.py](/D:/GXP-QLCL/tests/test_phase4_storage_api.py)

## Next recommended step
1. Keep the operational runbook and probe CLI as the primary non-production validation path.
2. Add a dedicated Synology/private-share adapter class if the filesystem adapter no longer matches operational needs closely enough.
3. Keep DDKD binding persistence deferred until a dedicated DDKD binding-key model is approved.
