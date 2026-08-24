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
Dry-run:

```bash
cd /opt/gxp/src/GXP-QLCL
python3 tools/import_legacy_production.py \
  --snapshot artifacts/phase3c/legacy_snapshot.json \
  --runtime-env /etc/gxp/runtime.env \
  --dry-run
```

Apply:

```bash
cd /opt/gxp/src/GXP-QLCL
python3 tools/import_legacy_production.py \
  --snapshot artifacts/phase3c/legacy_snapshot.json \
  --runtime-env /etc/gxp/runtime.env \
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
2. Run the canonical PostgreSQL backup gate:

```bash
cd /opt/gxp/src/GXP-QLCL
sudo VM_RUNTIME_ENV_FILE=/etc/gxp/runtime.env ./infra/vm/backup_postgres.sh
```

3. Run the dry-run:

```bash
cd /opt/gxp/src/GXP-QLCL
python3 tools/import_legacy_production.py \
  --snapshot artifacts/phase3c/legacy_snapshot.json \
  --runtime-env /etc/gxp/runtime.env \
  --dry-run
```

4. Review `artifacts/legacy-production/<timestamp>/report.json` and `report.md`.
5. If the import validation passes, run the apply command.
6. Rebuild/read the Phase 7 gate:

```bash
cd /opt/gxp/src/GXP-QLCL
python3 tools/build_phase7_cutover_readiness.py
```

7. Verify runtime health:

```bash
cd /opt/gxp/src/GXP-QLCL
sudo VM_RUNTIME_ENV_FILE=/etc/gxp/runtime.env ./infra/vm/verify_prod.sh
```

## Safety contract
- `APP_ENV` must be `production`.
- `DB_MODE` must be `local_postgres`.
- Target DB must remain `gxp_qlcl` owned by `gxp_app`.
- Current Alembic revision must equal repository head.
- `--apply` always runs the canonical PostgreSQL backup script first.
- Snapshot hash is recorded in the import report.
- Dry-run uses the same importer logic as apply and rolls back the transaction.
- Apply is transactional and must fail closed on collisions, unresolved anomalies, Alembic mismatch, or backup failure.
- Current Phase 7 gate is reported but not auto-bypassed or auto-resolved by the importer.
- Missing or invalid Phase 3/4/5/6/3p historical artifacts must become blocked Phase 7 gates, not Python tracebacks.
- Bounded `VARCHAR(N)` compatibility is preflight-validated before insert; free-form narrative fields owned by the schema use `TEXT` and must not be truncated.

## Boundaries unchanged
This path does not import or synthesize:

- document rows
- storage bindings
- RBAC/app users

Those remain separate phases and must not be fabricated just to balance counts.
