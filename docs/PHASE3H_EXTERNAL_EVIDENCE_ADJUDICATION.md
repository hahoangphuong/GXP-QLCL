# Phase 3h External Evidence Adjudication

## Purpose
Turn the unresolved remediation tail from Phase 3g into a controlled human-review workflow that can use Synology documents, Word outputs, and business chronology without weakening deterministic migration rules.

This phase does not scan Synology directly and does not mutate migrated data by itself. It prepares the actionable review queue, validates reviewer decisions, and merges only evidence-backed approvals into a new override bundle.

## Historical note
This workflow was designed before the August 14, 2026 confirmation that every row in `artifacts/phase3_review/anomaly_review_report.*` is an intended blanked legacy row.

Therefore:
- the old actionable queue should be treated as historical review machinery;
- any current reuse must first exclude the Phase 3q confirmed blanked scope.

## Inputs
- `artifacts/phase3g/accepted_overrides_baseline.json`
- `artifacts/phase3g/unresolved_review_pack.json`

## Outputs
- `artifacts/phase3h/external_evidence_queue.json`
- `artifacts/phase3h/external_evidence_queue.csv`
- `artifacts/phase3h/external_evidence_decisions.template.json`
- `artifacts/phase3h/external_evidence_summary.json`
- `artifacts/phase3h/external_evidence_summary.md`
- `artifacts/phase3h/adjudicated_overrides.external.json`
- `artifacts/phase3h/merged_overrides.external.json`

## Review Scope
Only rows classified in Phase 3g as:
- `needs_external_evidence`
- `hard_unresolved`

Rows classified as `archival_placeholder` remain excluded from this queue because the workbook itself already indicates they are structurally incomplete or non-business placeholders.

## Decision Model
Supported reviewer decisions:
- `approve_override`
- `exclude_legacy_row`
- `legacy_only_record`
- `defer`

Validation rules:
- every non-`defer` decision requires `evidence_source`, `evidence_reference`, `decision_rationale`, `reviewer`, and `reviewed_on`;
- `approve_override` requires `selected_legacy_id`;
- when candidate IDs exist, `selected_legacy_id` must be one of the candidate IDs already enumerated from the legacy evidence pack;
- rows with no inferred override field cannot be force-approved.

## Guardrails
- No approval based only on text similarity or guessed chronology.
- No use of folder display names as authoritative business identity.
- No Synology rename, move, delete, or metadata mutation.
- No change to baseline accepted overrides unless the new adjudication decision validates cleanly.

## Operator Workflow
1. Review `external_evidence_queue.csv` or `external_evidence_queue.json`.
2. Gather supporting evidence from Synology paths, generated Word/PDF documents, and known chronology.
3. Copy `external_evidence_decisions.template.json` to `external_evidence_decisions.json`.
4. Fill only evidence-backed decisions.
5. Re-run the analyzer to validate decisions and produce merged overrides.

## Current Baseline
As of August 13, 2026:
- accepted baseline overrides: `11`
- actionable external-evidence rows: `137`
- of which `134` are `needs_external_evidence`
- and `3` are `hard_unresolved`

Superseded interpretation:
- this baseline does not represent the current importer truth after Phase 3q and the updated Phase 2 reconciliation;
- the confirmed review-report rows are now excluded in the importer baseline instead of remaining active open anomalies.

## Recommended Next Step
Once reviewer decisions exist and validate cleanly, the next safe step is a Phase 3i rerun that consumes `merged_overrides.external.json` and produces a new reconciliation report without changing any storage behavior.
