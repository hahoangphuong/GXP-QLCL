# Phase 5 Runtime Template Contract Baseline

## Scope
This step introduces the first runtime-readable template contract layer between payload builders and template-aware DOCX render.

## Delivered
- runtime loader and planner: `backend/app/document/template_contract_runtime.py`
- renderer integration: `backend/app/document/docx_template_render.py`
- smoke tool: `tools/smoke_phase5_runtime_template_contract.py`
- DDKD variant contract artifact: `artifacts/phase5/dkkd_template_variants.json`
- BBTD variant contract artifact: `artifacts/phase5/bbtd_template_variants.json`

## Runtime policy
- `contract_exact`: only used when every scalar field in a family has an exact real-template reconciliation.
- `contract_variant_exact`: used when a family is exact only after concrete template variant detection.
- `payload_passthrough`: used for every other family until more evidence is adjudicated.

## Current enabled families
- `INSPECTION_CAPA_LAN_1`
- `INSPECTION_CAPA_LAN_2`

## Current family-specific nuance
- `DDKD_CERTIFICATE` no longer runs on plain family-level `contract_exact`.
- It now detects the concrete template variant from the actual DOCX bookmark set and enforces a variant-specific allowed payload surface.
- Current curated variant keys:
  - `ddkd_certificate_new`
  - `ddkd_certificate_adjustment`
- `DDKD_APPENDIX_OR_DECISION` is now selection-safe but not yet render-safe.
- The family is split at registry/seed level into:
  - `legacy_mode = appendix`
  - `legacy_mode = issuance_decision`
- Field audit now shows:
  - `All` is promotable as a safe `All{GP}` prefix group
  - `GCN_GMP` and `QD_GMP` are still written by the explicit shared VBA path for case 3/4, but the active templates do not expose matching bookmarks
- Full runtime bookmark-contract promotion is still blocked until the missing-bookmark policy is adjudicated.
- `INSPECTION_BBTD_HOSO_DK` now detects the concrete template variant and expands one business-facing field into the exact numbered bookmark slots present in that template.
- Current curated variant keys:
  - `bbtd_hoso_dk_line_1`
  - `bbtd_hoso_dk_line_2`
  - `bbtd_hoso_dk_line_3`
  - `bbtd_hoso_dk_all_lines`

## What this changes
- The renderer no longer assumes payload field names are always the final physical bookmark names.
- Exact-safe families now flow through a dedicated contract layer before XML mutation.
- Variant-sensitive families can fail closed on concrete template drift or illegal variant-only fields.
- Variant-sensitive families can also expand one business payload field into multiple physical bookmarks when the real template requires numbered slots.
- Unresolved families keep current baseline behavior and are not auto-expanded.

## What this does not change
- No copy-forward behavior is implemented yet.
- No 1-to-many runtime expansion is enabled yet, even though the reconciliation artifact proves many candidates.
- No unresolved family is promoted automatically.

## Next recommended task
Promote adjudicated 1-to-many mappings into the runtime contract for one core inspection family, starting with a narrow family where the unresolved tail is small enough to review safely and no hidden variant branching remains.
