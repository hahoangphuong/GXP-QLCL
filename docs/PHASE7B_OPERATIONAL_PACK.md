# Phase 7b Operational Pack

## Purpose
Package the remaining non-code cutover work into an operator-friendly handoff.

This phase does not claim cutover is ready.
It turns the remaining pending items into explicit execution/evidence tasks.

## Delivered
- operational pack builder: [tools/build_phase7b_operational_pack.py](/D:/GXP-QLCL/tools/build_phase7b_operational_pack.py)
- operational pack outputs:
  - [cutover_operational_pack.json](/D:/GXP-QLCL/artifacts/phase7b/cutover_operational_pack.json)
  - [cutover_operational_pack.csv](/D:/GXP-QLCL/artifacts/phase7b/cutover_operational_pack.csv)
  - [cutover_operational_pack.md](/D:/GXP-QLCL/artifacts/phase7b/cutover_operational_pack.md)

## What the pack contains
- current blocked gates
- current outstanding checklist items
- execution notes per remaining cutover item
- required evidence fields per remaining cutover item

## Intended workflow
1. Use `"$PY" -m tools.build_phase7b_operational_pack --evidence-dir "$EVIDENCE_DIR"` after post-go-live archive evidence is captured.
2. Collect evidence for each remaining item.
3. Update the external execution checklist, then rerun readiness before validation because validation consumes `cutover_readiness.json`:
   - `"$PY" -m tools.build_phase7_cutover_readiness --evidence-dir "$EVIDENCE_DIR"`
   - `"$PY" -m tools.validate_phase7_cutover_checklist --evidence-dir "$EVIDENCE_DIR"`
   - `"$PY" -m tools.build_phase7_final_closeout --evidence-dir "$EVIDENCE_DIR"`

All commands run from `/opt/gxp/current-backend` with `PY=/opt/gxp/current-venv/bin/python` and `PYTHONPATH=/opt/gxp/current-backend`.

## Scope boundary
This pack does not replace the live operational work.
It only makes the remaining cutover actions explicit, auditable, and easier to hand off.
