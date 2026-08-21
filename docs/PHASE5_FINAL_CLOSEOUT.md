# Phase 5 Final Closeout

## Purpose
Declare Phase 5 complete as the document-contract, template-audit, and executable render-baseline phase for the migration.

This closeout does **not** claim full legacy-faithful parity for every document family.
It closes Phase 5 at the point where:
- the document domain model is explicit;
- template selection and binary lineage are first-class;
- runtime-safe families can render deterministically through server-side DOCX mutation;
- unresolved families are identified and kept fail-closed rather than guessed.

## What Phase 5 now covers
- logical document / variant / version / generation-run model
- curated family registry and template seed artifacts
- DB-backed source candidate resolution and exact source-binary locator readiness
- output allocation and write finalization through `StorageService`
- template-aware DOCX bookmark replacement in body, header, and footer
- narrow table-region repeated-row rendering
- runtime template-contract gate between business payload and physical bookmarks
- concrete-template variant detection for:
  - `DDKD_CERTIFICATE`
  - `INSPECTION_BBTD_HOSO_DK`
- registry-level selection split for `DDKD_APPENDIX_OR_DECISION`
- real-template audit and reconciliation against active binaries in `legacy/Templates`

## Current executable status
### Contract-variant-exact and end-to-end render-proven
- `DDKD_CERTIFICATE`
- `INSPECTION_BBTD_HOSO_DK`

### Contract-exact at scalar replacement layer
- `INSPECTION_CAPA_LAN_1`
- `INSPECTION_CAPA_LAN_2`

### Selection-safe but not render-safe
- `DDKD_APPENDIX_OR_DECISION`

### Still intentionally not promoted
- families that remain on `payload_passthrough`
- families that still need copy-forward semantics from prior documents
- families whose real template bookmark surface still has unresolved or suspicious mappings

## Important boundaries
- PowerPoint-backed legacy output remains excluded from the current migration scope.
- Excel-backed support-document families are still separate from the Word render-safe baseline.
- Copy-forward parity is not complete yet for families that depend on prior bookmark/table transplant.
- Conditional-delete behavior with missing active bookmarks is not auto-enabled unless explicitly adjudicated.

## Outputs
- [phase5_final_closeout.json](/D:/GXP-QLCL/artifacts/phase5/phase5_final_closeout.json)
- [phase5_final_closeout.md](/D:/GXP-QLCL/artifacts/phase5/phase5_final_closeout.md)

## Hand-off
From this point:
- Phase 6 owns real desktop workflow validation with Explorer + Word + direct save on private networking.
- Later document-family expansion should promote one unresolved family at a time from `payload_passthrough` into explicit runtime contract, never by inference.
