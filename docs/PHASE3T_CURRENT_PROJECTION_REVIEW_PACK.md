# Phase 3t Current Projection Review Pack

## Purpose
Provide a reviewer-friendly pack for the `14` unresolved current-projection conflicts from Phase 3s.

This phase does not decide winners automatically.
It consolidates the evidence already present in Phase 3p, Phase 3s, and legacy duplicate-current analysis into one operational review surface.

## Delivered
- review pack builder: [tools/build_phase3t_projection_conflict_review_pack.py](/D:/GXP-QLCL/tools/build_phase3t_projection_conflict_review_pack.py)
- review pack outputs:
  - [current_projection_conflict_review_pack.json](/D:/GXP-QLCL/artifacts/phase3t/current_projection_conflict_review_pack.json)
  - [current_projection_conflict_review_pack.csv](/D:/GXP-QLCL/artifacts/phase3t/current_projection_conflict_review_pack.csv)
  - [current_projection_conflict_review_pack.md](/D:/GXP-QLCL/artifacts/phase3t/current_projection_conflict_review_pack.md)

## What the pack adds
- one consolidated row per conflict
- candidate legacy IDs
- current decision status from Phase 3s
- review focus and explicit decision question
- evidence summary
- candidate-level detail:
  - for certificate conflicts: certificate number, issue date, expiry date
  - for case conflicts: progress and linked certificate ID

## Intended workflow
1. Review [current_projection_conflict_review_pack.md](/D:/GXP-QLCL/artifacts/phase3t/current_projection_conflict_review_pack.md) or the CSV.
2. Record the decision into [current_projection_conflict_decisions.template.json](/D:/GXP-QLCL/artifacts/phase3s/current_projection_conflict_decisions.template.json).
3. Re-run [tools/validate_phase3s_projection_conflict_decisions.py](/D:/GXP-QLCL/tools/validate_phase3s_projection_conflict_decisions.py) to update the blocking summary.
