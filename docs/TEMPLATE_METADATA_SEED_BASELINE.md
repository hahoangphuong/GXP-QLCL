# Template Metadata Seed Baseline

## Purpose
This document defines the first seedable metadata layer for document templates and bindings. It bridges the curated VBA registry into rows that later can populate `template_definition` and `template_binding`.

## Source artifacts
- `artifacts/phase5/template_registry.curated.json`
- `artifacts/phase5/template_seed.curated.json`
- `artifacts/phase5/template_seed.curated.md`
- runtime loader/upsert: `backend/app/document/seed_runtime.py`
- seed tool: `tools/seed_phase5_template_metadata.py`

## Seed rules
- `document_type_code` is derived from `family_code` deterministically.
- `template_name` is the normalized leading template pattern; when a family has multiple historical names, the baseline keeps the leading canonical pattern and preserves the full pattern in `template_pattern`.
- `variant_type` is derived from source application:
  - Word -> `editable_docx`
  - Excel -> `editable_xlsx`
- `gxp_type` and `legacy_mode` remain nullable seed selectors unless directly evidenced.

## Known unresolved areas
- Most families still need a reconciled physical bookmark contract because the real template bookmark sets drift from the original VBA-normalized registry.
- Some support families bundle multiple historical templates inside one host procedure and now require family-specific narrowing against the active binaries.
- Exact active/inactive template lifecycle is not yet modeled.

## After real-template reconciliation
- The curated seed remains useful for `family_code`, `template_name`, `binding`, and high-level lineage.
- It should not yet be treated as the final renderer bookmark contract for most families.
- See `docs/PHASE5_TEMPLATE_CONTRACT_RECONCILIATION.md` for the current family-by-family reconciliation status.

## Runtime baseline
- `template_definition` is matched by `(family_code, template_name)`.
- `template_binding` is matched by `(family_code, template_definition_id, gxp_type, legacy_mode, storage_scope)`.
- Reruns are deterministic:
  - ambiguous existing rows fail closed
  - exact matches are updated in place to curated values
  - no duplicate rows are intentionally created
