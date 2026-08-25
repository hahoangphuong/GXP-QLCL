# Phase 3b - Remediation Queue And Deterministic Reimport

## Goal
Turn legacy migration anomalies into a first-class remediation backlog instead of leaving them only in ad hoc JSON summaries.

## Historical note
This document remains useful as the first deterministic remediation baseline, but its interpretation of the `151` Phase 2 anomalies has been superseded for the specific review-report scope confirmed on August 14, 2026.

Current truth for that scope:
- every row currently listed in `artifacts/phase3_review/anomaly_review_report.*` is a confirmed blanked legacy row;
- those rows are now tracked as `excluded_confirmed_blanked`, not as open remediation backlog;
- see [PHASE3Q_CONFIRMED_BLANKED_ROWS.md](/D:/GXP-QLCL/docs/PHASE3Q_CONFIRMED_BLANKED_ROWS.md).

## What changed
- Phase 2 import now persists each unresolved or override-resolved foreign-key anomaly into `migration_anomaly`.
- The importer accepts deterministic overrides keyed by source sheet and `source_row_key`.
- Reconciliation output now includes:
  - `anomaly_rows`
  - `applied_override_count`
  - `remediation_override_keys`
  - `derived_counts.migration_anomaly`
- A remediation template generator now converts Phase 2 findings into an override skeleton.
- A dedicated Phase 3b reimport runner now rebuilds a remediated staging database from the override file.

## Files and artifacts
- Import logic: [backend/app/domain/phase2_import.py](/D:/GXP-QLCL/backend/app/domain/phase2_import.py)
- Template generator: [tools/generate_phase3b_remediation_template.py](/D:/GXP-QLCL/tools/generate_phase3b_remediation_template.py)
- Reimport runner: [tools/run_phase3b_reimport.py](/D:/GXP-QLCL/tools/run_phase3b_reimport.py)
- Baseline reconciliation: [artifacts/phase2/reconciliation.json](/D:/GXP-QLCL/artifacts/phase2/reconciliation.json)
- Remediation template: [artifacts/phase3b/remediation_overrides.template.json](/D:/GXP-QLCL/artifacts/phase3b/remediation_overrides.template.json)
- Remediation candidates: [artifacts/phase3b/remediation_candidates.json](/D:/GXP-QLCL/artifacts/phase3b/remediation_candidates.json)
- Unkeyed anomalies: [artifacts/phase3b/remediation_unkeyed_anomalies.json](/D:/GXP-QLCL/artifacts/phase3b/remediation_unkeyed_anomalies.json)
- Reimport output: [artifacts/phase3b/reconciliation.json](/D:/GXP-QLCL/artifacts/phase3b/reconciliation.json)

## Current baseline
From the regenerated Phase 2 reconciliation on August 13, 2026:

- Open anomalies persisted: `151`
- Applied overrides: `0`
- Skipped rows: `151`
- Missing company FK rows in `db.cso`: `3`
- Missing site FK rows in `db.ktra`: `47`
- Missing site FK rows in `db.cc`: `26`
- Missing case FK rows in `db.cc`: `1`
- Missing site FK rows in `db.dkkd`: `50`
- Missing site FK rows in `db.Tdoi`: `22`
- Missing change-request FK rows in `db.Tdoi2`: `2`

These counts currently match between:
- persisted `migration_anomaly` rows
- reconciliation `anomaly_rows`
- skipped-row totals in the import report

The previous `db.cc`-heavy case-adjudication queue was based on an outdated assumption that blank `ID ĐỢT KTRA` always meant a broken inspection link. That assumption is no longer valid after the certificate linkage correction approved on August 13, 2026.

## Row-key status
All `151` open anomalies now have a stable `source_row_key` and can be represented directly in the override template.
- `134` use their legacy business `ID`
- `17` use fallback keys of the form `row:<excel_row_number>`

The fallback row key is a replay identity only. It must not be promoted to business identity or domain foreign key.

`artifacts/phase3b/remediation_unkeyed_anomalies.json` is now expected to be empty for the current workbook snapshot.

## Remediation workflow
1. Regenerate the baseline Phase 2 import.
2. Generate `remediation_overrides.template.json`.
3. Fill in only evidence-backed overrides in `remediation_overrides.json`.
4. Run the Phase 3b reimport.
5. Compare the remediated reconciliation against the baseline.
6. Keep overrides under version control once they are reviewed and justified.

## Superseded interpretation
- The `151` rows described in this baseline should no longer be read as the current unresolved remediation backlog.
- After the confirmed blanked-row decision and importer update, that population is excluded intentionally rather than left open.

## Override contract
Overrides are keyed as:

```json
{
  "db.cso": {
    "271": {
      "company_legacy_id": 12
    }
  },
  "db.ktra": {
    "row:1162": {
      "site_legacy_id": 85
    }
  }
}
```

Keying rules:
- prefer legacy business `ID` when present
- use `row:<excel_row_number>` only when the legacy row has no `ID`

Supported override keys:
- `company_legacy_id`
- `site_legacy_id`
- `case_legacy_id`
- `change_request_legacy_id`

## Guardrails
- Overrides only substitute missing or unresolved legacy foreign keys.
- Overrides do not silently rewrite source workbook values.
- If an override points to a non-existent imported legacy ID, the anomaly remains open.
- Reimports are deterministic for the same workbook snapshot plus the same override file.
- `row:<excel_row_number>` is valid for remediation replay only and is not a business key.
- This phase does not modify Synology binaries or legacy workbook files.
- Rows already covered by `confirmed_blanked_rows.json` must not be revived through this generic override channel; use the explicit resurrection contract in [PHASE3S_CONFIRMED_BLANKED_RESURRECTION_CONTRACT.md](/D:/GXP-QLCL/docs/PHASE3S_CONFIRMED_BLANKED_RESURRECTION_CONTRACT.md).

## Next recommended step
Historical next step at the time:
- work through [artifacts/phase3b/remediation_candidates.json](/D:/GXP-QLCL/artifacts/phase3b/remediation_candidates.json), resolve evidence-backed foreign keys, and produce the first non-empty `remediation_overrides.json` for replay.

Current successor state:
- for the confirmed review-report scope, use `exclude_from_business_import` rather than FK remediation;
- use later phases only as historical evidence of how the team originally investigated this queue.
