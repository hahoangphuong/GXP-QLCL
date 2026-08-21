# Phase 5 DDKD Appendix/Decision Selection Baseline

## Scope
This step fixes owner-layer selection identity for `DDKD_APPENDIX_OR_DECISION` so the active appendix and issuance-decision templates are no longer hidden behind one synthetic template placeholder.

## Delivered
- registry split in `artifacts/phase5/template_registry.curated.json`
- seed split in `artifacts/phase5/template_seed.curated.json`
- payload-builder dedup support in `backend/app/document/seed_contract.py`
- selection smoke: `tools/smoke_phase5_ddkd_appendix_decision_selection.py`

## Active selection contract
- `family_code = DDKD_APPENDIX_OR_DECISION`
- `legacy_mode = appendix` -> `z3. Phụ lục GCN ĐĐKKDD.dotx`
- `legacy_mode = issuance_decision` -> `z4. QĐ cấp ĐĐKKDD.dotx`
- missing `legacy_mode` -> fail closed with ambiguous selection

## Important boundary
- This step does not promote the family into runtime bookmark-contract rendering.
- Field adjudication now separates the unresolved tail:
  - `All` has enough evidence to be treated as a safe `All{GP}` prefix group.
  - `GCN_GMP` and `QD_GMP` are still written by the shared case 3/4 VBA path, but the active `z3` and `z4` templates do not expose matching bookmarks.
- Additional adjudication is still required before safe render-side field expansion can be enabled.

## Smoke evidence
- `tools/smoke_phase5_ddkd_appendix_decision_selection.py`
  - without `legacy_mode`: `DocumentTemplateSelectionError`
  - with `appendix`: selects `z3. Phụ lục GCN ĐĐKKDD.dotx`
  - with `issuance_decision`: selects `z4. QĐ cấp ĐĐKKDD.dotx`
- `tools/build_phase5_ddkd_appendix_field_adjudication.py`
  - emits adjudication artifacts for `All`, `GCN_GMP`, and `QD_GMP`

## Next recommended task
Choose whether `GCN_GMP` and `QD_GMP` should remain blocked or be explicitly modeled as tolerated missing-bookmark writes for this family before promoting it from selection-safe to render-safe.
