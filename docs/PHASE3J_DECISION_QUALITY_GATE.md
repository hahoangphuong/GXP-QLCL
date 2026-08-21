# Phase 3j Decision Quality Gate

## Purpose
Block unsafe or low-quality external adjudication decisions before they are allowed to feed Phase 3i reruns.

Phase 3h already validates structural correctness of a submitted decision file. Phase 3j adds an operational quality gate so the team can distinguish:
- a syntactically valid decision file
- from a decision file that is complete and trustworthy enough to change migrated data

## Historical note
This gate was designed for the pre-Phase-3q external-review branch.

For the rows now confirmed as blanked legacy rows:
- this gate is no longer part of the current migration path;
- keep it only as historical workflow machinery or for any future non-blanked review population.

## Inputs
- `artifacts/phase3h/external_evidence_queue.json`
- `artifacts/phase3h/external_evidence_decisions.json`

## Outputs
- `artifacts/phase3j/decision_quality_gate.json`
- `artifacts/phase3j/decision_quality_gate.md`

## Quality Rules
- duplicate `review_key` submissions are not allowed;
- `reviewed_on` must be ISO `YYYY-MM-DD`;
- `reviewed_on` cannot be after August 13, 2026;
- non-`defer` evidence sources must come from the approved registry;
- `decision_rationale` must not be trivial;
- `approve_override` is blocked when the queue row has `candidate_count = 0`;
- `defer` still requires reviewer, date, and rationale for auditability.

## Approved Evidence Source Registry
- `synology_doc`
- `word_output`
- `signed_pdf`
- `business_chronology`
- `legacy_register`
- `email_confirmation`

## Gate Semantics
- `status = pass`: Phase 3i rerun may proceed using the current external decision file.
- `status = blocked`: Phase 3i rerun should not be treated as a business-significant adjudication result.

## Current Expected Result
As of August 13, 2026, no `external_evidence_decisions.json` has been submitted yet, so the gate is expected to remain blocked with reason `missing_decision_file`.

## Recommended Next Step
Historical next step at the time:
- when the business review team submits `external_evidence_decisions.json`, run Phase 3j first. Only if it passes should the team rerun Phase 3h and Phase 3i as the next adjudicated migration cycle.

Current successor state:
- do not treat this gate as the current blocker for the already-confirmed blanked-row anomaly scope.
