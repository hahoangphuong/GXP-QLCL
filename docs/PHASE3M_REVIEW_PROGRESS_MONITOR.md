# Phase 3m Review Progress Monitor

## Purpose
Track operational review progress after Phase 3l assignment and detect whether the team is actually ready to submit an adjudication cycle for Phase 3j.

This phase monitors:
- completion coverage
- lane-by-lane execution
- tracker validation quality
- stale states such as completed work without decision-file updates

## Historical note
This monitor belongs to the superseded external-review branch.

It is no longer part of the current migration-critical path for the confirmed blanked-row anomaly scope.

## Inputs
- `artifacts/phase3l/review_progress_tracker.json` when present
- otherwise `artifacts/phase3l/review_progress_tracker.template.json`
- `artifacts/phase3l/review_assignment_summary.json`

## Outputs
- `artifacts/phase3m/review_progress_summary.json`
- `artifacts/phase3m/review_progress_summary.md`
- `artifacts/phase3m/review_progress_snapshot.csv`

## Monitor Rules
- tracker dates must be ISO `YYYY-MM-DD`
- tracker dates cannot be after Thursday, August 13, 2026
- `completed` rows must have assignee, started date, and completed date
- `blocked` rows must have assignee, started date, and notes
- completed rows without `decision_file_updated=true` are flagged as stale

## Current Expected Result
With the default Phase 3l template, the monitor should show:
- all rows still `not_started`
- `completion_ratio = 0.0`
- `can_submit_phase3j = false`

## Recommended Next Step
Historical next step at the time:
- replace the template tracker with a live `review_progress_tracker.json` as soon as reviewers start work, then rerun Phase 3m regularly during the adjudication cycle.

Current successor state:
- no active Phase 3 review cycle remains open for the confirmed blanked-row population.
