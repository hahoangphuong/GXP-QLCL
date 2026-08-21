# Phase 4.6 - DDKD Storage Contract

## Goal
Close the remaining DDKD storage ambiguity in Phase 4 without pulling document-generation logic forward from Phase 5.

## Scope completed on August 14, 2026
- Reconciled the DDKD resolver with reverse-engineered VBA evidence.
- Standardized the DDKD site-folder resolver on the durable token `(<site_legacy_id>)`.
- Added read-only app lookup for DDKD folders.
- Added probe CLI support for DDKD site-folder validation.
- Kept DDKD binding persistence explicitly out of scope.

## Proven contract
- Resolver input:
  - `site_legacy_id`
- Resolver behavior:
  - search direct child folders under configured `dkkd_root`
  - match `(<site_legacy_id>)`
  - fail closed on `0` or `>1` matches
- Non-identity fields:
  - company/site display-name prefix
  - address text in folder label
  - `Lần n` issuance-cycle child folder

## Why this is enough for Phase 4
- It preserves the legacy rule that site ID, not display name, is the durable key.
- It lets the storage layer resolve the correct site folder safely.
- It leaves issuance-cycle and exact output placement to later DDKD document/issuance logic.

## Files
- [backend/app/storage/local.py](/D:/GXP-QLCL/backend/app/storage/local.py)
- [backend/app/storage/binding_lookup.py](/D:/GXP-QLCL/backend/app/storage/binding_lookup.py)
- [backend/app/main.py](/D:/GXP-QLCL/backend/app/main.py)
- [tools/probe_phase4_storage_nonprod.py](/D:/GXP-QLCL/tools/probe_phase4_storage_nonprod.py)
- [tests/test_phase4_storage_service.py](/D:/GXP-QLCL/tests/test_phase4_storage_service.py)
- [tests/test_phase4_storage_binding_lookup.py](/D:/GXP-QLCL/tests/test_phase4_storage_binding_lookup.py)
- [tests/test_phase4_storage_api.py](/D:/GXP-QLCL/tests/test_phase4_storage_api.py)
- [tests/test_phase4_probe_tool.py](/D:/GXP-QLCL/tests/test_phase4_probe_tool.py)

## Deliberate non-goals
- No DDKD binding row persistence yet.
- No DDKD file-slot generation logic here.
- No automatic `Lần n` creation logic here.
- No document-family placement logic here.
