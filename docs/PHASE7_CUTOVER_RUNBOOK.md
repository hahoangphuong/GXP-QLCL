# Phase 7 Cutover Runbook

## Purpose
Provide the execution surface for the real cutover window once all preconditions are met.

## Pre-cutover requirements
1. Phase 6 desktop/private-share evidence must be closed.
2. Current-projection conflicts must be adjudicated.
3. A change window must be approved.
4. Rollback owners and contact paths must be confirmed.
5. Final reconciliation rerun must complete without unresolved hard errors.
6. Canonical legacy validation dry-run must have completed from `artifacts/phase3c/legacy_snapshot.json` and produced a report under `artifacts/legacy-production/<timestamp>/`.
7. At least one rehearsal refresh must have rebuilt a non-production target DB from snapshot and passed reconciliation review.

## Canonical import commands
Windows snapshot export:

```bash
python tools/export_legacy_snapshot.py
```

VM validation dry-run:

```bash
cd /opt/gxp/src/GXP-QLCL
python3 tools/import_legacy_production.py \
  --snapshot artifacts/phase3c/legacy_snapshot.json \
  --runtime-env /etc/gxp/runtime.env \
  --import-mode validation \
  --dry-run
```

VM rehearsal refresh:

```bash
cd /opt/gxp/src/GXP-QLCL
python3 tools/import_legacy_production.py \
  --snapshot artifacts/phase3c/legacy_snapshot.json \
  --runtime-env /etc/gxp/runtime.env \
  --import-mode rehearsal \
  --target-db gxp_legacy_rehearsal \
  --reset-from-snapshot \
  --apply
```

VM final candidate rebuild:

```bash
cd /opt/gxp/src/GXP-QLCL
python3 tools/import_legacy_production.py \
  --snapshot artifacts/phase3c/legacy_snapshot.json \
  --runtime-env /etc/gxp/runtime.env \
  --import-mode final \
  --target-db gxp_qlcl_candidate \
  --reset-from-snapshot \
  --apply
```

The final candidate rebuild runs the canonical PostgreSQL backup gate itself before mutation. All modes emit `report.json` and `report.md` into `artifacts/legacy-production/<timestamp>/`.

## Cutover sequence
1. Announce legacy write-freeze start time.
2. Disable or administratively block new legacy business writes.
3. Export a fresh `artifacts/phase3c/legacy_snapshot.json` from the frozen workbook baseline.
4. Run the canonical VM validation dry-run and review `artifacts/legacy-production/<timestamp>/report.json` and `report.md`.
5. Rebuild the final candidate database from the frozen snapshot with `--import-mode final --reset-from-snapshot`.
6. Review the candidate report:
   - snapshot SHA-256
   - target database
   - source counts
   - reconciliation/source-balance
   - deployment SHA
   - Alembic revision
7. Rebuild Phase 7 readiness with `python3 tools/build_phase7_cutover_readiness.py`.
8. Review reconciliation outputs and obtain sign-off.
9. Switch the application to the validated candidate DB only after all gates pass.
10. Retain the previous production DB for the rollback window.
11. Put legacy Excel workflow into read-only/archive mode.
12. Monitor the first production operations closely.

## Rollback trigger examples
- unresolved reconciliation mismatch
- operator workflow failure on active private-share path
- document-generation failure on a must-have family
- storage/network outage that blocks required business operations

## Rollback sequence
1. Stop authoritative use of the web system for business mutation.
2. Re-enable legacy operational writes if the freeze window is being abandoned.
3. Keep the previous production DB intact for rollback; do not drop it during the initial rollback window.
4. Preserve all cutover-window audit artifacts.
5. Record exact stop/go times and issue summary.

## Required evidence to archive
- final reconciliation artifacts
- final cutover checklist
- desktop/private-share validation evidence
- decision log for go/no-go
- rollback notes if rollback occurs
