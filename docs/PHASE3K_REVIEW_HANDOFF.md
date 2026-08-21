# Phase 3k Review Handoff

## Purpose
Prepare the external-evidence adjudication queue for business reviewers in an operationally usable form.

This phase turns the technical queue into a human-review handoff pack with:
- priority batches
- reviewer prompts
- evidence checklists
- lightweight summary artifacts

## Historical note
This handoff pack belongs to the same pre-Phase-3q review branch as Phases 3h-3j.

It should no longer be interpreted as the active handoff for the `151` rows now confirmed as blanked legacy rows.

## Inputs
- `artifacts/phase3h/external_evidence_queue.json`
- `artifacts/phase3j/decision_quality_gate.json`

## Outputs
- `artifacts/phase3k/review_handoff_summary.json`
- `artifacts/phase3k/review_handoff_summary.md`
- `artifacts/phase3k/prioritized_review_queue.json`
- `artifacts/phase3k/prioritized_review_queue.csv`
- `artifacts/phase3k/reviewer_guide.md`

## Batch Strategy
- `B1-high-confidence-adjudication`: rows with 1-3 candidates
- `B2-multi-candidate-adjudication`: rows with 4+ candidates
- `B3-hard-unresolved`: rows with no safe candidate path

## Review Rules
- Start with B1 rows to maximize early anomaly reduction.
- Keep B3 rows for senior review or explicit exclusion/legacy-only decisions.
- Record exact evidence references; do not leave generic notes.
- Do not infer identity from folder display names.

## Current Baseline
As of Thursday, August 13, 2026:
- actionable review rows: `137`
- Phase 3j gate status: `blocked`
- gate reason: `missing_decision_file`

## Recommended Next Step
Historical next step at the time:
- use the Phase 3k handoff pack with the business review team to produce the first real `external_evidence_decisions.json` submission, then rerun Phase 3j.

Current successor state:
- keep this as historical operational context only unless a new non-blanked review population is created later.
