# Phase 3g Closeout

## Purpose
Freeze the accepted remediation baseline after Phase 3f and export the remaining unresolved legacy rows into a review pack with explicit evidence classes.

This phase does not introduce new migration behavior. It packages the current migration state so the next step can focus on stakeholder adjudication and external-document review instead of further heuristic matching.

## Historical note
This closeout reflects the pre-Phase-3q interpretation of the unresolved queue.

For rows now covered by [PHASE3Q_CONFIRMED_BLANKED_ROWS.md](/D:/GXP-QLCL/docs/PHASE3Q_CONFIRMED_BLANKED_ROWS.md):
- `archival_placeholder` should now be read as confirmed blanked legacy rows;
- they are no longer current open anomalies in the importer baseline.

## Inputs
- `artifacts/phase3f/reconciliation_final.json`
- `artifacts/phase3f/final_merged_overrides.json`
- `artifacts/phase3c/remediation_analysis.json`
- `artifacts/phase3d/manual_review_queue.json`

## Outputs
- `artifacts/phase3g/accepted_overrides_baseline.json`
- `artifacts/phase3g/unresolved_review_pack.json`
- `artifacts/phase3g/closeout_summary.json`
- `artifacts/phase3g/closeout_summary.md`

## Closeout Baseline
- Accepted overrides frozen: `11`
- Open anomalies after Phase 3f: `282`

Classification of remaining open anomalies:
- `archival_placeholder`: `145`
- `needs_external_evidence`: `134`
- `hard_unresolved`: `3`

Per-source distribution:
- `db.cso`: `3` archival placeholders
- `db.ktra`: `47` archival placeholders
- `db.cc`: `24` archival placeholders, `134` needs external evidence, `2` hard unresolved
- `db.dkkd`: `49` archival placeholders, `1` hard unresolved
- `db.Tdoi`: `21` archival placeholders
- `db.Tdoi2`: `1` archival placeholder

## Review Semantics
- `archival_placeholder`: legacy row is structurally incomplete or intentionally blank in the source workbook and should not be auto-mapped into business entities.
- `needs_external_evidence`: candidate matches exist, but the workbook data is insufficient to choose a safe target without chronology, file evidence, or business confirmation.
- `hard_unresolved`: no safe candidate path was found from current workbook evidence and prior review queues.

## Guardrails
- No new override should be added without evidence stronger than workbook-text similarity alone.
- Folder names remain non-authoritative display data; business identity must continue to use stable IDs.
- No file move, rename, or Synology mutation is part of this phase.
- The unresolved pack is a review artifact, not an instruction to auto-link records.

## Recommended Next Step
Historical next step at the time:
- proceed with an external-evidence adjudication workflow:
- review the `needs_external_evidence` queue against Synology documents, Word outputs, and business chronology;
- confirm whether the `hard_unresolved` rows should remain excluded, be manually mapped, or be represented as archived legacy-only records;
- keep `accepted_overrides_baseline.json` as the deterministic baseline for reruns until a new adjudication pack is approved.

Current successor state:
- do not treat the entire old unresolved-review pack as active backlog without first removing rows superseded by Phase 3q.
