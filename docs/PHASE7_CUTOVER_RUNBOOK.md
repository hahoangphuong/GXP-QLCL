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
  --phase7-evidence-dir /var/lib/gxp/phase7-execution \
  --import-mode validation \
  --dry-run
```

VM rehearsal refresh:

```bash
cd /opt/gxp/src/GXP-QLCL
python3 tools/import_legacy_production.py \
  --snapshot artifacts/phase3c/legacy_snapshot.json \
  --runtime-env /etc/gxp/runtime.env \
  --phase7-evidence-dir /var/lib/gxp/phase7-execution \
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
  --phase7-evidence-dir /var/lib/gxp/phase7-execution \
  --import-mode final \
  --target-db gxp_qlcl_candidate \
  --reset-from-snapshot \
  --apply
```

The final candidate rebuild runs the canonical PostgreSQL backup gate itself before mutation. All modes emit `report.json` and `report.md` into `artifacts/legacy-production/<timestamp>/`.

## RBAC readiness
Schema readiness alone does not make database-backed authorization ready. A rebuilt candidate has the deterministic built-in RBAC baseline, but no named human identities until operators explicitly provision them.

Before a candidate DB is allowed to become the runtime target, provision every required operator identity and verify the exact user-role assignments. `/etc/gxp/runtime.env` remains the persistent runtime target authority; deriving the candidate URL below does not modify that file or change rehearsal behavior.

```bash
cd /opt/gxp/src/GXP-QLCL

# Resolve the explicit candidate target from the existing runtime contract without printing it.
CANDIDATE_DATABASE_URL="$(
  /opt/gxp/current-venv/bin/python - <<'PY'
from pathlib import Path
from tools import import_legacy_production as production_import

contract, _ = production_import._load_runtime_database_contract(Path("/etc/gxp/runtime.env"))
print(production_import._target_database_url(contract.database_url, "gxp_qlcl_candidate"))
PY
)"

# Repeat this explicit provisioning command for every required identity.
/opt/gxp/current-venv/bin/python tools/provision_app_user.py \
  --runtime-env /etc/gxp/runtime.env \
  --target-db gxp_qlcl_candidate \
  --email "<operator-email>" \
  --username "<operator-username>" \
  --role "<role-code>"

# Repeat --require-user for every identity required at cutover.
/opt/gxp/current-venv/bin/python tools/verify_rbac_readiness.py \
  --database-url "$CANDIDATE_DATABASE_URL" \
  --require-user "<operator-email>:<role-code>"

unset CANDIDATE_DATABASE_URL
```

Archive the successful verifier output with the cutover evidence. A failed verifier is a no-go result; it never provisions users or repairs the RBAC baseline.

## Cutover sequence
Initialize and retain an external evidence directory before the change window. The path must be outside the release tree:

```bash
cd /opt/gxp/src/GXP-QLCL
/opt/gxp/current-venv/bin/python tools/init_phase7_execution.py \
  --output-dir /var/lib/gxp/phase7-execution
```

### Pre-switch
1. Confirm the Phase 6 desktop/private-share and current-projection prerequisites.
2. Approve the change window and confirm rollback contacts.
3. Announce and enforce the legacy write freeze.
4. Export a fresh `artifacts/phase3c/legacy_snapshot.json` from the frozen workbook baseline.
5. Run the canonical VM validation dry-run and review `artifacts/legacy-production/<timestamp>/report.json` and `report.md`.
6. Rebuild the final candidate database from the frozen snapshot with `--import-mode final --reset-from-snapshot`.
7. Review the candidate report:
   - snapshot SHA-256
   - target database
   - source counts
   - reconciliation/source-balance
   - deployment SHA
   - Alembic revision
8. Explicitly provision required candidate identities and run the required-user RBAC readiness verification; archive its successful output.
9. Review reconciliation outputs, obtain sign-off, update the external `cutover_execution_checklist.json`, and build the cutover readiness report:

```bash
cd /opt/gxp/src/GXP-QLCL
/opt/gxp/current-venv/bin/python tools/build_phase7_cutover_readiness.py --evidence-dir /var/lib/gxp/phase7-execution
/opt/gxp/current-venv/bin/python tools/validate_phase7_cutover_checklist.py --evidence-dir /var/lib/gxp/phase7-execution
```

`CUTOVER READY` means the seven pre-switch conditions are complete. It does not mean final Phase 7 closeout is complete; `excel_read_only_archive_mode` remains required after go-live.

### Switch
10. Switch the application to the validated candidate DB only after cutover readiness is `ready`.
11. Verify application health and retain the previous production DB for the rollback window.

### Post-go-live
12. Put the legacy Excel workflow into read-only/archive mode.
13. Capture `excel_read_only_archive_mode` evidence in the external execution checklist.
14. Build the Phase 7b operational pack.
15. Build final Phase 7 closeout only after all eight checklist rows and the operational pack are complete:

```bash
cd /opt/gxp/src/GXP-QLCL
/opt/gxp/current-venv/bin/python tools/build_phase7_cutover_readiness.py --evidence-dir /var/lib/gxp/phase7-execution
/opt/gxp/current-venv/bin/python tools/validate_phase7_cutover_checklist.py --evidence-dir /var/lib/gxp/phase7-execution
/opt/gxp/current-venv/bin/python tools/build_phase7b_operational_pack.py --evidence-dir /var/lib/gxp/phase7-execution
/opt/gxp/current-venv/bin/python tools/build_phase7_final_closeout.py --evidence-dir /var/lib/gxp/phase7-execution
```

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
- external Phase 7 readiness, checklist summary, operational pack, and final closeout outputs
- desktop/private-share validation evidence
- decision log for go/no-go
- rollback notes if rollback occurs
