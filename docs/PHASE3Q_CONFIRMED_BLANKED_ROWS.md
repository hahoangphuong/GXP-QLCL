# Phase 3q Confirmed Blanked Rows

## Purpose
Capture the business-owner confirmation that every row currently listed in `artifacts/phase3_review/anomaly_review_report.*` is an intended blanked legacy row, not a business record that should be repaired and migrated.

These rows exist because:
- the operator wanted to delete the record logically;
- but the legacy Excel workbook still used `INDEX`-based formulas that depended on row positions;
- so the row content was blanked in place instead of deleting the entire worksheet row.

## Inputs
- [anomaly_review_report.json](/D:/GXP-QLCL/artifacts/phase3_review/anomaly_review_report.json)
- business-owner review confirmation on `2026-08-14`

## Outputs
- [confirmed_blanked_rows.json](/D:/GXP-QLCL/artifacts/phase3q/confirmed_blanked_rows.json)
- [confirmed_blanked_rows.md](/D:/GXP-QLCL/artifacts/phase3q/confirmed_blanked_rows.md)

## Confirmed interpretation
- Scope: all rows currently present in `artifacts/phase3_review/anomaly_review_report.json`
- Interpretation: `confirmed_blanked_row`
- Migration action: `exclude_from_business_import`
- Retention policy: keep only replay/audit trace as needed; do not materialize as active business entities

## Current confirmed counts on August 14, 2026
- Total rows: `151`
- `missing_site_fk`: `145`
- `missing_company_fk`: `3`
- `missing_change_request_fk`: `2`
- `missing_case_fk`: `1`

## Migration rules
- Do not attempt FK repair for this confirmed set.
- Do not send this set into external-evidence review.
- Do not infer business meaning from preserved row numbers alone.
- Keep deterministic source references only for audit/reconciliation traceability.
- If the business later wants a specific row materialized again, use the explicit resurrection contract in [PHASE3S_CONFIRMED_BLANKED_RESURRECTION_CONTRACT.md](/D:/GXP-QLCL/docs/PHASE3S_CONFIRMED_BLANKED_RESURRECTION_CONTRACT.md) instead of a generic remediation override.

## Superseded interpretation
Earlier Phase 3 documents correctly detected many of these rows as placeholders heuristically, but they still left room for manual evidence review on some rows.

This phase supersedes that ambiguity for the specific report scope above:
- these rows are now confirmed as intended blanked legacy rows;
- they should be treated as archival/excluded, not unresolved business data.
