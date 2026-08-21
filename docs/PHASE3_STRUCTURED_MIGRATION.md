# Phase 3 Structured Migration

## Goal
Turn the Phase 2 read-only prototype into a deterministic structured migration baseline:
- export normalized target entities
- classify skipped-row anomalies
- define remediation rules before deeper document and storage migration

## Current migration baseline
- Database snapshot: `artifacts/phase2/staging_readonly.db`
- Reconciliation inputs: `artifacts/phase2/reconciliation.md`, `artifacts/phase2/reconciliation.json`
- Structured exports: `artifacts/phase3/*.json`, `artifacts/phase3/*.csv`
- Anomaly summary: `artifacts/phase3/anomaly_summary.json`

## Observed anomaly classes
- `missing_company_fk`
- `missing_site_fk`
- `missing_case_fk`
- `missing_change_request_fk`

These are not importer bugs by default. They are migration-shaping findings and must be handled explicitly.

## Historical baseline on August 13, 2026
- Total anomalies: `151`
- Open anomalies at that time: `151`
- `db.cso`: `3` rows, all `missing_company_fk`
- `db.ktra`: `47` rows, all `missing_site_fk`
- `db.cc`: `27` rows
  - `26` `missing_site_fk`
  - `1` `missing_case_fk`
- `db.dkkd`: `50` rows, all `missing_site_fk`
- `db.Tdoi`: `22` rows, all `missing_site_fk`
- `db.Tdoi2`: `2` rows, all `missing_change_request_fk`

This replaces the older interim assumption that `db.cc` had a large `missing_case_fk` queue. After ADR `0004`, blank `db.cc.ID ĐỢT KTRA` with a resolved `ID CƠ SỞ` is treated as a valid non-case-backed certificate, not as an anomaly.

## Anomaly identity contract
All `151` anomalies now carry a deterministic `source_row_key`.
- If the legacy row has a business `ID`, `source_row_key` equals that `ID`.
- If the legacy row has no business `ID`, `source_row_key` falls back to `row:<excel_row_number>`.

This row key is a replay identity only. It exists so remediation and rerun can be deterministic. It is not a business identity and must not be promoted into the target domain model.

## Phase 3 rulebook
### Companies
- Import directly when `legacy_company_id` exists.
- Blank or missing company ID requires manual reconciliation before downstream entities can attach.

### Sites
- If `ID Cty` is blank, do not auto-attach to a guessed company.
- Keep row in anomaly queue until a deterministic company mapping exists.

### Cases / inspections
- If `ID CƠ SỞ` is blank or unresolved, do not synthesize a site.
- Preserve anomaly identity for manual resolution using `source_row_key`.

### Certificates
- If `ID ĐỢT KTRA` is blank but `ID CƠ SỞ` resolves, import the certificate as a valid non-case-backed certificate.
- Do not manufacture a case link for blank `ID ĐỢT KTRA`.
- If `ID CƠ SỞ` is blank, do not attach by name matching.
- If `ID ĐỢT KTRA` is non-blank but unresolved, keep the row in the anomaly queue.

### DDKD
- If site or company link is blank, hold row out of structured import.
- Relationship to certificate remains many-to-many and must never be flattened back to a single FK.

### Change requests
- If linked site is unresolved, keep request in anomaly queue.
- If `db.Tdoi2.ID Gốc` is unresolved, do not attach detail to a guessed request.

## Recommended next hardening steps
1. Keep all remediation tooling keyed by `source_row_key`.
2. Add deterministic operator-reviewed mapping inputs for unresolved FKs.
3. Re-run Phase 2 import after remediation and verify mismatch deltas shrink toward zero.
4. Only then begin broader certificate and document lineage migration.

## Current confirmed interpretation for the review-report scope
On August 14, 2026, the business owner confirmed that every row currently listed in `artifacts/phase3_review/anomaly_review_report.md` is an intended blanked legacy row.

Meaning:
- the row was logically deleted by the operator;
- but the worksheet row itself was kept because legacy Excel `INDEX` formulas still depended on row position;
- therefore the row should be treated as archival/excluded, not as a business record awaiting FK remediation.

For that confirmed report scope, Phase 3 anomaly handling should prefer:
- `exclude_from_business_import`
- replay/audit trace retention only
- no external-evidence review

## Current importer baseline after Phase 3q integration
- `total_anomalies`: `151`
- `open_anomalies`: `0`
- `excluded_confirmed_blanked_anomalies`: `151`
- `effective_mismatches`: `0`

Meaning:
- the previously reported `151` anomaly rows are no longer current unresolved migration errors;
- they are now a fully explained exclusion set.
