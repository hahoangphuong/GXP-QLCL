# Phase 5 Template Contract Reconciliation

## Scope
This step reconciles the curated VBA-derived payload registry with the real active template bookmarks discovered under `legacy/Templates`.

## Delivered
- reconciliation tool: `tools/build_phase5_template_contract_reconciliation.py`
- artifact JSON: `artifacts/phase5/template_contract_reconciled.json`
- artifact Markdown: `artifacts/phase5/template_contract_reconciled.md`

## Reconciliation rules
- `exact`: the curated payload field matches a real template bookmark exactly.
- `case_insensitive_exact`: only casing differs.
- `signature_exact`: punctuation or separator differences collapse to the same alphanumeric signature.
- `prefix_variant_group`: the real template uses numbered or suffixed variants of the same bookmark stem.
- `unresolved`: no safe automatic mapping is proven.

## Main findings
- `DDKD_CERTIFICATE` is the first family with full exact reconciliation from payload field to real template bookmark.
- `INSPECTION_CAPA_LAN_1` and `INSPECTION_CAPA_LAN_2` also reconcile cleanly at the scalar bookmark level, but still need copy-forward behavior for full parity.
- Several core inspection families now show a clear 1-to-many pattern where one curated field maps to multiple real template bookmarks, for example:
  - `Tencoso` -> `Tencoso1`, `Tencoso2`, ...
  - `Diachicoso` -> `Diachicoso1`, `Diachicoso2`, ...
  - `NoWHO_Del` -> `NoWHO_Del1`, `NoWHO_Del2`, ...
- Support-document families hosted by `ExtRecordForm.CreateFile` remain highly under-resolved because the old registry captured a broad shared builder footprint, while each real template only uses a narrow subset.
- `CHANGE_REPORT_ROUTE_LETTER` remains structurally suspicious: the active real template bookmarks align more with assessment-style content than with the current curated family meaning.

## Design implications
- The payload registry should now be treated as canonical business-field input, not as the final physical bookmark list.
- A future runtime adapter should read a reconciled template contract and expand one business field into one or more physical bookmark writes where evidence supports it.
- Families with many `unresolved` fields should not be auto-enabled for template-aware render until their contract is manually adjudicated.
- Support-document families need family-specific payload narrowing before they are safe to expose in the target app.

## Next recommended task
Introduce a runtime-readable template contract layer that sits between payload builders and DOCX render, using the reconciled artifact as its evidence source for exact and 1-to-many bookmark expansion.
