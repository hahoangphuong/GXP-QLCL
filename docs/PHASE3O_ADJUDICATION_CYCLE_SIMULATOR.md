# Phase 3o Adjudication Cycle Simulator

## Purpose
Run a synthetic end-to-end adjudication cycle on a small safe sample before the business team starts a real review cycle at scale.

This phase simulates:
- completed tracker updates
- externally adjudicated decisions
- Phase 3j-style decision validation
- merged override generation
- rerun import into an isolated staging database

## Historical note
This simulator belongs to the same superseded external-review branch as Phases 3h-3n.

After the Phase 3q confirmation, it should be kept only as historical pipeline proofing, not as part of the current required Phase 3 completion path.

## Inputs
- `artifacts/phase3h/external_evidence_decisions.template.json`
- `artifacts/phase3l/review_progress_tracker.json`
- `artifacts/phase3g/accepted_overrides_baseline.json`
- `artifacts/phase3f/reconciliation_final.json`

## Outputs
- `artifacts/phase3o/simulation_summary.json`
- `artifacts/phase3o/simulation_summary.md`
- `artifacts/phase3o/simulated_external_evidence_decisions.json`
- `artifacts/phase3o/simulated_review_progress_tracker.json`
- `artifacts/phase3o/staging_simulated.db`
- `artifacts/phase3o/reconciliation_simulated.json`
- `artifacts/phase3o/reconciliation_simulated.md`

## Guardrails
- synthetic decisions are not business approvals;
- simulator outputs must not be copied into the real decision file without evidence;
- all simulator artifacts remain under `artifacts/phase3o/`;
- no Synology mutation and no legacy file mutation occur in this phase.

## Current Intent
Use a few B1 rows with 1-3 candidates to prove that the adjudication pipeline can:
- accept a well-formed decision set;
- produce merged overrides;
- rerun import deterministically;
- emit measurable reconciliation deltas.

## Recommended Next Step
Historical next step at the time:
- after the simulator passes, the next safe step is a Phase 3p live-cycle readiness check using the real tracker and the first genuine `external_evidence_decisions.json` submission.

Current successor state:
- Phase 3 has moved on to conflict-contract and confirmed-exclusion closure rather than continuing this simulator branch.
