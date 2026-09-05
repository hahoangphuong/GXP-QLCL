# Phase 7 Cutover Baseline

## Goal
Prepare a truthful, evidence-driven cutover gate for switching authority from legacy Excel/VBA to the web system.

## Delivered
- cutover readiness builder: [tools/build_phase7_cutover_readiness.py](/D:/GXP-QLCL/tools/build_phase7_cutover_readiness.py)
- execution checklist validator: [tools/validate_phase7_cutover_checklist.py](/D:/GXP-QLCL/tools/validate_phase7_cutover_checklist.py)
- final closeout builder: [tools/build_phase7_final_closeout.py](/D:/GXP-QLCL/tools/build_phase7_final_closeout.py)
- checklist template: [cutover_execution_checklist.template.json](/D:/GXP-QLCL/artifacts/phase7/cutover_execution_checklist.template.json)

## External Execution Evidence
The tracked checklist is an immutable release template, not live operator evidence. Before the cutover window, initialize one external absolute directory that is outside `/opt/gxp/src/GXP-QLCL` and retain it across releases:

```bash
/opt/gxp/current-venv/bin/python tools/init_phase7_execution.py \
  --output-dir /var/lib/gxp/phase7-execution
```

Operators update only `/var/lib/gxp/phase7-execution/cutover_execution_checklist.json`. All Phase 7 generated outputs are written back to that same directory and every operational tool requires the explicit directory:

```bash
/opt/gxp/current-venv/bin/python tools/build_phase7_cutover_readiness.py --evidence-dir /var/lib/gxp/phase7-execution
/opt/gxp/current-venv/bin/python tools/validate_phase7_cutover_checklist.py --evidence-dir /var/lib/gxp/phase7-execution
/opt/gxp/current-venv/bin/python tools/build_phase7b_operational_pack.py --evidence-dir /var/lib/gxp/phase7-execution
/opt/gxp/current-venv/bin/python tools/build_phase7_final_closeout.py --evidence-dir /var/lib/gxp/phase7-execution
```

`/var/lib/gxp/phase7-execution` is an example only; deployment configuration does not hardcode an evidence path. Missing, malformed, or release-local evidence is rejected without fallback to the template.

## Gate model
Phase 7 separates:
- readiness gates derived from prior phase artifacts
- operational checklist items that must be executed during the cutover window

## Current blocking facts
- Phase 6 is still blocked on private-share/desktop operational evidence.
- Current-projection conflicts were adjudicated in Phase 3s on August 16, 2026.
- Legacy write-freeze execution and rollback approvals have not happened yet.

## Consequence
Phase 7 is expected to remain `blocked` in the current repository state.
That is the correct result: cutover should not be declared ready merely because prior design/code baselines are mature.
