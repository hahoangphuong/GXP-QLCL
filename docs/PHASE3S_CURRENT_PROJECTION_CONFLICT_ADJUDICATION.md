# Phase 3s Current Projection Conflict Adjudication

## Purpose
Provide the decision-file and validation layer for the `14` current-projection conflicts carried forward from Phase 3p.

This phase does **not** invent winners automatically.
It closes the tooling gap so each conflict can be reviewed explicitly and auditably.

## Delivered
- decision template builder: [tools/build_phase3s_projection_conflict_decision_template.py](/D:/GXP-QLCL/tools/build_phase3s_projection_conflict_decision_template.py)
- decision validator/summary: [tools/validate_phase3s_projection_conflict_decisions.py](/D:/GXP-QLCL/tools/validate_phase3s_projection_conflict_decisions.py)
- decision template:
  - [current_projection_conflict_decisions.template.json](/D:/GXP-QLCL/artifacts/phase3s/current_projection_conflict_decisions.template.json)
  - [current_projection_conflict_decisions.template.md](/D:/GXP-QLCL/artifacts/phase3s/current_projection_conflict_decisions.template.md)
- decision summary:
  - [current_projection_conflict_decisions.summary.json](/D:/GXP-QLCL/artifacts/phase3s/current_projection_conflict_decisions.summary.json)
  - [current_projection_conflict_decisions.summary.md](/D:/GXP-QLCL/artifacts/phase3s/current_projection_conflict_decisions.summary.md)

## Decision actions
- `pending`: not reviewed yet
- `winner`: one legacy row is selected as the current projection winner
- `no_winner`: projection must remain conflict/no-current after review
- `defer`: reviewed but intentionally deferred pending external evidence or policy decision

## Validation rules
- `winner` requires:
  - selected candidate ID
  - reviewer
  - reviewed date
  - rationale
- `no_winner` and `defer` require:
  - reviewer
  - reviewed date
  - rationale
- `pending` must not carry reviewer/date/rationale or a selected candidate

## Current state
Immediately after template generation, the summary is expected to remain `blocked` because all rows start at `pending`.

## Relationship to cutover
Phase 7 should treat this decision summary as the operational proof surface for the `current_projection_conflicts` gate.
