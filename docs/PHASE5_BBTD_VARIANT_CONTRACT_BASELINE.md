# Phase 5 BBTD Variant Contract Baseline

## Scope
This step promotes `INSPECTION_BBTD_HOSO_DK` from generic payload passthrough to a concrete-template variant contract based on active legacy template bookmark sets.

## Delivered
- variant artifact builder: `tools/build_phase5_bbtd_variant_contracts.py`
- runtime support in `backend/app/document/template_contract_runtime.py`
- smoke render: `tools/smoke_phase5_bbtd_variant_render.py`
- smoke guard: `tools/smoke_phase5_bbtd_variant_guard.py`
- generated artifacts:
  - `artifacts/phase5/bbtd_template_variants.json`
  - `artifacts/phase5/bbtd_template_variants.md`

## Evidence summary
- 8 live BBTD templates reduce to 4 exact bookmark sets.
- The runtime-relevant surfaces are:
  - `bbtd_hoso_dk_line_1`
  - `bbtd_hoso_dk_line_2`
  - `bbtd_hoso_dk_line_3`
  - `bbtd_hoso_dk_all_lines`
- Payload fields remain business-facing:
  - `Daychuyen`
  - `Diachicoso`
  - `Fulldate`
  - `Tencoso`

## Runtime behavior
- Runtime detects the concrete BBTD template from the actual DOCX bookmark set.
- The detected variant expands each payload field into the exact numbered bookmark targets for that template.
- Example:
  - `bbtd_hoso_dk_line_1` maps to `DayChuyen1`, `DiaChiCoSo1`, `Fulldate1`, `TenCoSo1`
  - `bbtd_hoso_dk_all_lines` maps each payload field across `*1`, `*2`, and `*3`
- Unknown bookmark sets fail closed before XML mutation starts.

## Smoke evidence
- `tools/smoke_phase5_bbtd_variant_render.py`
  - `1. BBTD Ho so DK - GLP - Moi.dotx` resolved to `bbtd_hoso_dk_line_1`
  - `1. BBTD Ho so DK - GMP - Moi.dotx` resolved to `bbtd_hoso_dk_all_lines`
  - both renders completed with `scalar_replacement_mode = contract_variant_exact`
- `tools/smoke_phase5_bbtd_variant_guard.py`
  - synthetic unknown bookmark set failed closed with `TemplateContractRuntimeError`

## Next recommended task
Promote the next family where concrete template variants still share one logical family but require either numbered bookmark fan-out or variant-specific field allowance.
