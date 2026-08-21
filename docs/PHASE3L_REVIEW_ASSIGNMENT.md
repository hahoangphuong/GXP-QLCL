# Phase 3l Review Assignment

## Purpose
Split the external-evidence review queue into balanced work lanes so multiple reviewers can work in parallel without fragmenting site context.

This phase groups related rows together, assigns them into review lanes, and produces a progress tracker template for execution management.

## Historical note
This review-lane assignment belongs to the superseded external-review branch.

After Phase 3q, it should not be treated as the current assignment plan for the already-confirmed blanked-row scope.

## Inputs
- `artifacts/phase3k/prioritized_review_queue.json`

## Outputs
- `artifacts/phase3l/review_assignment_summary.json`
- `artifacts/phase3l/review_assignment_summary.md`
- `artifacts/phase3l/review_lane_assignments.json`
- `artifacts/phase3l/review_lane_assignments.csv`
- `artifacts/phase3l/review_progress_tracker.template.json`
- `artifacts/phase3l/review_progress_tracker.template.csv`

## Assignment Rules
- keep same-site rows together when possible;
- assign heavier bundles first;
- balance effort points across `lane_alpha`, `lane_bravo`, and `lane_charlie`;
- keep hard-unresolved bundles visible rather than hiding them inside larger lanes.

## Current Baseline
As of Thursday, August 13, 2026, the queue still contains `137` actionable rows and no submitted external decision file.

## Recommended Next Step
Historical next step at the time:
- fill assignee names into the Phase 3l tracker, execute review by lane, then submit the first real `external_evidence_decisions.json` for Phase 3j gating.

Current successor state:
- this assignment plan is historical unless a new review queue is explicitly opened for a different unresolved population.
