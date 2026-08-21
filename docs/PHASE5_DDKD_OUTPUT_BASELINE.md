# Phase 5 DDKD Output Baseline

## Scope
This step extends document output allocation and template-aware render so a DDKD family can complete end-to-end generation into the `dkkd` storage root while respecting the concrete active template variant.

## Delivered
- `dkkd_folder` support in `backend/app/document/output_version.py`
- end-to-end smoke for `DDKD_CERTIFICATE`
- explicit ADR for exact DDKD output locators without inspection-style binding
- variant-specific runtime contract detection for concrete DDKD templates

## Behavior
- `inspection_folder` outputs still allocate through resolved inspection bindings.
- `dkkd_folder` outputs now allocate through live DDKD folder resolution.
- DDKD outputs persist:
  - `storage_root = "dkkd"`
  - exact `storage_relative_path`
  - `storage_binding_id = NULL`
- DDKD render now validates payload fields against the concrete selected DOCX template, not only the family-level union contract.

## Smoke evidence
- tool: `tools/smoke_phase5_dkkd_certificate_render.py`
- family: `DDKD_CERTIFICATE`
- result:
  - runtime contract mode stayed `contract_variant_exact`
  - concrete template variant resolved as `ddkd_certificate_new`
  - rendered DOCX was written successfully under the resolved DDKD folder
  - `document_version` became current with `storage_root = dkkd`
- guard tool: `tools/smoke_phase5_dkkd_variant_guard.py`
- guard result:
  - render failed closed when payload field `Cap_lan` was sent against the `ddkd_certificate_new` template
  - failure type was `TemplateContractRuntimeError`

## Important nuance
- The `DDKD_CERTIFICATE` family-level reconciliation remains exact only as a union across active variants.
- Runtime no longer trusts that family-level union blindly.
- The concrete DOCX bookmark set is now used to detect whether the selected template is `ddkd_certificate_new` or `ddkd_certificate_adjustment`.
- Payload fields are validated against the detected variant before XML mutation starts.

## Next recommended task
Extend the same concrete-template contract pattern to the next active family where multiple live template binaries share one logical family but differ in physical bookmark surface.
