# Phase 7 Cutover Runbook

## Purpose
Provide the execution surface for the real cutover window once all preconditions are met.

## Pre-cutover requirements
1. Phase 6 desktop/private-share evidence must be closed.
2. Current-projection conflicts must be adjudicated.
3. A change window must be approved.
4. Rollback owners and contact paths must be confirmed.
5. Final reconciliation rerun must complete without unresolved hard errors.
6. Canonical legacy production import dry-run must have completed from `artifacts/phase3c/legacy_snapshot.json` and produced a report under `artifacts/legacy-production/<timestamp>/`.

## Canonical import commands
Windows snapshot export:

```bash
python tools/export_legacy_snapshot.py
```

VM dry-run:

```bash
cd /opt/gxp/src/GXP-QLCL
python3 tools/import_legacy_production.py \
  --snapshot artifacts/phase3c/legacy_snapshot.json \
  --runtime-env /etc/gxp/runtime.env \
  --dry-run
```

VM apply:

```bash
cd /opt/gxp/src/GXP-QLCL
python3 tools/import_legacy_production.py \
  --snapshot artifacts/phase3c/legacy_snapshot.json \
  --runtime-env /etc/gxp/runtime.env \
  --apply
```

The apply command runs the canonical PostgreSQL backup gate itself before mutating production data. Both modes emit `report.json` and `report.md` into `artifacts/legacy-production/<timestamp>/`.

## Cutover sequence
1. Announce legacy write-freeze start time.
2. Disable or administratively block new legacy business writes.
3. Export a fresh `artifacts/phase3c/legacy_snapshot.json` from the frozen workbook baseline.
4. Run the canonical VM dry-run and review `artifacts/legacy-production/<timestamp>/report.json` and `report.md`.
5. If validation passes, run the canonical VM apply command.
6. Rebuild Phase 7 readiness with `python3 tools/build_phase7_cutover_readiness.py`.
7. Review reconciliation outputs and obtain sign-off.
8. Switch web system to authoritative mode.
9. Put legacy Excel workflow into read-only/archive mode.
10. Monitor the first production operations closely.

## Rollback trigger examples
- unresolved reconciliation mismatch
- operator workflow failure on active private-share path
- document-generation failure on a must-have family
- storage/network outage that blocks required business operations

## Rollback sequence
1. Stop authoritative use of the web system for business mutation.
2. Re-enable legacy operational writes if the freeze window is being abandoned.
3. Preserve all cutover-window audit artifacts.
4. Record exact stop/go times and issue summary.

## Required evidence to archive
- final reconciliation artifacts
- final cutover checklist
- desktop/private-share validation evidence
- decision log for go/no-go
- rollback notes if rollback occurs
