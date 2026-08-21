# ADR 0005: Migration anomaly row-key fallback

## Status
Approved

## Date
2026-08-13

## Context
The legacy workbook contains anomaly-bearing rows in `db.ktra` and `db.cc` where the business `ID` column is blank.

Those rows are still real worksheet rows and still affect migration:
- they can carry unresolved foreign keys
- they can be skipped by import
- they can require manual remediation

Relying only on `legacy_row_id` makes those anomalies hard to replay deterministically, because the remediation system has no stable key for overrides.

At the same time, worksheet row position must not be confused with business identity.

## Decision
- Every anomaly row must expose a `source_row_key`.
- If the legacy row has a business `ID`, `source_row_key` equals that `ID`.
- If the legacy row has no business `ID`, `source_row_key` falls back to `row:<excel_row_number>`.
- Remediation override files may target either kind of `source_row_key`.
- `legacy_row_id` remains nullable and continues to represent only the original business `ID` column.
- Fallback row keys are replay identifiers only and must not be promoted into domain identity, foreign keys, or long-term business references.

## Consequences
Positive:
- all current anomalies can be represented in deterministic override files
- remediation backlog no longer drops rows that have no business `ID`
- reruns remain stable for the same workbook snapshot

Negative:
- remediation tooling must distinguish business identity from replay identity
- row-number fallback can change if the legacy workbook structure changes, so overrides are valid for a specific workbook snapshot and must be regenerated after sheet layout changes

## Follow-up
- Keep remediation tooling keyed by `source_row_key`
- Keep business models keyed by normalized domain identifiers, not worksheet row numbers
