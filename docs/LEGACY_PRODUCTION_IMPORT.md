# Legacy Production Import

## Scope
This document defines the canonical production path for importing legacy structured data into the current VM PostgreSQL baseline.

The importer owner layer remains:

- `backend/app/domain/phase2_import.py`

The production CLI owner is:

- `tools/import_legacy_production.py`

No second ETL path is introduced.

## Source of truth
Production import on the Ubuntu VM uses the exported legacy snapshot JSON, not Excel COM:

- source workbook on Windows: `legacy/Danh sách Kiểm tra GPs.xlsb`
- Windows exporter: `python tools/export_legacy_snapshot.py`
- VM import source: `artifacts/phase3c/legacy_snapshot.json`

The VM import path does not require `legacy/*.xlsb` once the snapshot JSON is present and valid.

## Canonical commands
Validation dry-run against a clean temporary validation database derived from the canonical production runtime contract:

```bash
cd /opt/gxp/src/GXP-QLCL
python3 tools/import_legacy_production.py \
  --snapshot artifacts/phase3c/legacy_snapshot.json \
  --runtime-env /etc/gxp/runtime.env \
  --import-mode validation \
  --dry-run
```

Rehearsal refresh from snapshot into a dedicated non-production database:

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

Final cutover candidate rebuild:

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

Both commands write artifacts under:

```text
artifacts/legacy-production/<timestamp>/
```

Key outputs:

- `report.json`
- `report.md`

Each report includes:

- `snapshot_sha256`
- `import_mode`
- `target_database`
- `snapshot_exported_at` when the snapshot payload includes metadata
- `source_workbook_identity` when the snapshot payload includes metadata
- source counts
- inserted counts
- existing/idempotent counts
- anomaly and skipped counts
- source-balance reconciliation
- Alembic current/head revision
- deployment Git SHA
- Phase 7 readiness status
- schema-length preflight violations for any bounded canonical column mismatch

Missing Phase 7 historical evidence does not excuse or fabricate readiness:

- dry-run and reconciliation must still execute if import validation can run
- the report must mark Phase 7 as not cutover-ready with explicit blocked reasons
- operators must not create fake historical artifacts just to make the gate pass

## Operator flow
### Windows
1. Update `legacy/Danh sách Kiểm tra GPs.xlsb`.
2. Export the canonical snapshot:

```bash
python tools/export_legacy_snapshot.py
```

3. Verify the produced file:

```bash
python - <<'PY'
from hashlib import sha256
from pathlib import Path
path = Path("artifacts/phase3c/legacy_snapshot.json")
print(path)
print(sha256(path.read_bytes()).hexdigest())
PY
```

4. Copy `artifacts/phase3c/legacy_snapshot.json` into the VM checkout.

### VM
1. Update the repo to the intended release tooling.
2. Run validation dry-run:

```bash
cd /opt/gxp/src/GXP-QLCL
python3 tools/import_legacy_production.py \
  --snapshot artifacts/phase3c/legacy_snapshot.json \
  --runtime-env /etc/gxp/runtime.env \
  --import-mode validation \
  --dry-run
```

3. Review `artifacts/legacy-production/<timestamp>/report.json` and `report.md`.
4. Refresh the rehearsal database from the snapshot:

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

5. Review the rehearsal report and application behavior against the rehearsal target.
6. For the real cutover window only, rebuild the candidate production database from the frozen final snapshot:

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

7. Rebuild/read the Phase 7 gate:

```bash
cd /opt/gxp/src/GXP-QLCL
python3 tools/build_phase7_cutover_readiness.py
```

8. Verify runtime health:

```bash
cd /opt/gxp/src/GXP-QLCL
sudo VM_RUNTIME_ENV_FILE=/etc/gxp/runtime.env ./infra/vm/verify_prod.sh
```

## Safety contract
- `APP_ENV` must be `production`.
- `DB_MODE` must be `local_postgres`.
- Validation dry-run uses the canonical runtime database contract to derive a clean temporary validation database.
- Validation dry-run upgrades that temporary database to Alembic head, runs the canonical importer/reconciliation there, writes the report, then drops the temporary database in `finally`.
- Validation dry-run performs zero mutation on the canonical production database `gxp_qlcl`.
- Rehearsal/final apply require explicit `--import-mode` plus `--reset-from-snapshot`.
- Rehearsal/final target DB must not equal the canonical production database `gxp_qlcl`.
- Default rebuild targets are `gxp_legacy_rehearsal` for rehearsal and `gxp_qlcl_candidate` for final.
- Rehearsal/final rebuild semantics are fresh reset imports, not incremental merge.
- Validation uses a clean temporary database upgraded to repository head; rehearsal/final reset imports rebuild their own target database at repository head.
- Final candidate rebuild runs the canonical PostgreSQL backup script before mutation.
- Snapshot hash is recorded in the import report.
- Dry-run uses the same importer logic as apply, but against an ephemeral validation database rather than the canonical production database.
- Rehearsal/final apply recreate the target DB, run `alembic upgrade head`, then import transactionally.
- Apply is transactional and must fail closed on collisions, unresolved anomalies, Alembic mismatch, target DB contract violations, or backup failure.
- Current Phase 7 gate is reported but not auto-bypassed or auto-resolved by the importer.
- Missing or invalid Phase 3/4/5/6/3p historical artifacts must become blocked Phase 7 gates, not Python tracebacks.
- Bounded `VARCHAR(N)` compatibility is preflight-validated before insert; free-form narrative fields owned by the schema use `TEXT` and must not be truncated.

## Boundaries unchanged
This path does not import or synthesize:

- document rows
- storage bindings
- RBAC/app users

Those remain separate phases and must not be fabricated just to balance counts.
