# Phase 6b Operator Pack

## Purpose
Package the remaining Phase 6 desktop/private-share blocker into an operator-friendly handoff.

Phase 6 is already complete as repository tooling.
What remains is live execution on a machine that can actually reach the approved Synology private share.

## Delivered
- operator pack builder: [tools/build_phase6b_operator_pack.py](/D:/GXP-QLCL/tools/build_phase6b_operator_pack.py)
- operator pack outputs:
  - [desktop_operator_pack.json](/D:/GXP-QLCL/artifacts/phase6b/desktop_operator_pack.json)
  - [desktop_operator_pack.csv](/D:/GXP-QLCL/artifacts/phase6b/desktop_operator_pack.csv)
  - [desktop_operator_pack.md](/D:/GXP-QLCL/artifacts/phase6b/desktop_operator_pack.md)

## What the pack contains
- current Phase 6 blocker summary
- local environment snapshot from the last probe
- one execution row per required scenario
- expected evidence fields for each scenario
- concise execution instructions for the operator

## Intended workflow
1. Open [desktop_operator_pack.md](/D:/GXP-QLCL/artifacts/phase6b/desktop_operator_pack.md) or CSV on the operator machine.
2. Run each required scenario against the approved scratch/test area on the active private share.
3. Fill the evidence fields into a follow-up captured artifact or update the Phase 6 matrix with the observed outcomes.
4. Re-run:
   - [tools/validate_phase6_desktop_evidence.py](/D:/GXP-QLCL/tools/validate_phase6_desktop_evidence.py)
   - [tools/build_phase6_final_closeout.py](/D:/GXP-QLCL/tools/build_phase6_final_closeout.py)

## Scope boundary
This pack does not fake or simulate NAS evidence.
It only makes the remaining operational work explicit and auditable.
