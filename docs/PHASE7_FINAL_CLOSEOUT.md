# Phase 7 Final Closeout

## Purpose
Record the truthful final Phase 7 state after cutover and post-go-live archive work.

## Status
Phase 7 is **not closed** in the current repository state.
It is **blocked** because the pre-switch conditions and post-go-live archive evidence are not yet complete.

Cutover readiness is not final closeout: the first seven required conditions can make the runtime switch ready while `excel_read_only_archive_mode` remains pending. Final closeout remains pending until all eight checklist rows and the Phase 7b operational pack are complete.

## Current blockers
- Phase 6 desktop/private-share evidence is still blocked.
- Legacy write-freeze execution is still pending.
- Rollback-window execution approval is still pending.

## Outputs
The release contains only the immutable [checklist template](/D:/GXP-QLCL/artifacts/phase7/cutover_execution_checklist.template.json). Operator-mutated evidence and every generated Phase 7 output belong in the same explicit external evidence directory. From `/opt/gxp/current-backend`, set `PY=/opt/gxp/current-venv/bin/python` and `PYTHONPATH=/opt/gxp/current-backend`, then invoke `"$PY" -m tools.init_phase7_execution --output-dir <absolute-external-path>` followed by the other `"$PY" -m tools.<module>` commands with `--evidence-dir <same-path>`.

The external directory contains:
- `cutover_execution_checklist.json`
- `cutover_readiness.json` and `cutover_readiness.md`
- `cutover_checklist_summary.json` and `cutover_checklist_summary.md`
- `cutover_operational_pack.json`, `cutover_operational_pack.csv`, and `cutover_operational_pack.md`
- `phase7_final_closeout.json` and `phase7_final_closeout.md`

## Meaning
The repo now has a deterministic cutover gate and runbook.
What it does **not** have yet is the evidence needed to declare the system ready to replace legacy writes in production.
