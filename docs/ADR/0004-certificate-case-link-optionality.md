# ADR 0004: Certificate Case Link Optionality

## Status
Approved

## Context
The legacy workbook `db.cc` contains certificate rows that usually link to `db.ktra` through `ID ĐỢT KTRA`.

However, live business usage also includes:
- reissued certificates
- administratively issued certificates

These rows can legitimately have:
- a valid `ID CƠ SỞ`
- but a blank `ID ĐỢT KTRA`

Treating every blank `db.cc.ID ĐỢT KTRA` as a migration anomaly incorrectly forces certificate rows into an inspection workflow that did not actually exist.

## Decision
- `certificate.case_id` is optional in the target model.
- `certificate.site_id` remains mandatory.
- Import `db.cc` rows with resolved `ID CƠ SỞ` and blank `ID ĐỢT KTRA` as valid non-case-backed certificates.
- Preserve anomaly handling only for `db.cc` rows where `ID ĐỢT KTRA` is non-blank but unresolved.
- Track issuance semantics explicitly using `certificate.issuance_basis`.

## Consequences
### Positive
- Migration aligns with real legacy business behavior.
- Reissued/administrative certificates are no longer misclassified as broken rows.
- Web-domain design can distinguish inspection-backed certification from administrative reissuance.

### Negative
- Downstream migration and adjudication artifacts that assumed every certificate was case-backed must be reinterpreted or regenerated.
- Certificate-related UI and service layers must avoid assuming `case_id` is always present.

## Follow-up
- Re-run baseline import/reconciliation after importer change.
- Reclassify `db.cc` anomaly queues built under the older assumption.
- Reflect optional case linkage in application services and future certificate UI/API design.
