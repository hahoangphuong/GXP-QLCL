# Phase 3i External Reimport

## Purpose
Consume the externally adjudicated override bundle from Phase 3h, rerun the workbook import deterministically, and compare the result against the Phase 3f baseline.

This phase is the first point where reviewer decisions can affect migrated counts, but only through the validated override bundle generated from Phase 3h.

## Historical note
This rerun path belongs to the pre-Phase-3q external-adjudication branch.

After the confirmed blanked-row decision:
- the `151` rows from `artifacts/phase3_review/anomaly_review_report.*` are no longer active open anomalies;
- therefore this document should be read as historical workflow context, not as the current next step for that anomaly population.

## Inputs
- `artifacts/phase3h/merged_overrides.external.json`
- `artifacts/phase3h/external_evidence_summary.json`
- `artifacts/phase3f/reconciliation_final.json`

## Outputs
- `artifacts/phase3i/staging_external.db`
- `artifacts/phase3i/reconciliation_external.json`
- `artifacts/phase3i/reconciliation_external.md`
- `artifacts/phase3i/external_reimport_summary.json`
- `artifacts/phase3i/external_reimport_summary.md`

## Behavior
- Reimports the legacy workbook into a fresh SQLite staging database.
- Uses only `merged_overrides.external.json` as the remediation input.
- Compares Phase 3i against the last adjudicated baseline from Phase 3f.
- Reports deltas in target counts, skipped rows, and derived counts.

## Guardrails
- No direct edits to the workbook.
- No Synology mutation.
- No implicit override inference during rerun.
- Any business-data change must trace back to a validated external-evidence decision from Phase 3h.

## Current Result
As of August 13, 2026, no external-evidence decisions have been submitted yet, so Phase 3i is expected to reproduce the Phase 3f baseline exactly.

## Recommended Next Step
Historical next step at the time:
- once `external_evidence_decisions.json` is filled and validated, rerun Phase 3h analysis and then rerun Phase 3i to measure the exact reduction in open anomalies.

Current successor state:
- use the updated Phase 2 baseline and Phase 3q/3r closeout as the current source of truth;
- do not continue this rerun branch for the confirmed blanked-row scope.
