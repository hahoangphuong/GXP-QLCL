# db.ktra Batch 4 Rehearsal Apply

`tools/apply_db_ktra_reconciliation.py` is intentionally inert unless the
operator passes exactly one explicit mode, an exact plan path, and that plan's
SHA-256. `--dry-run-rehearsal` executes the same preflight and live fences but
always rolls back; `--apply-rehearsal` is the only committing mode. It is not
part of the production importer.

The tool accepts only a compared plan for `gxp_legacy_rehearsal` at Alembic
revision `20260912_0012`. It replays every source value from the committed
snapshot, validates source hashes and parser output, locks the required rows,
preflights the complete approved write envelope, then commits once. Any live
conflict aborts the entire transaction.

The allowed subset is split Q. định fields, B. bản minutes date/time/raw
provenance, final evaluation, compliance due date, and exact-copy wrong-owner
cleanup. It excludes teams, approvals, certificates, period fields/segments,
CAPA, and case state. A rerun of the same plan recognizes already-applied
values and does not increment row versions.

The independent operator command must provide the audited plan SHA explicitly:

```powershell
$env:DATABASE_URL = '<approved rehearsal PostgreSQL URL>'
py -m tools.apply_db_ktra_reconciliation --apply-rehearsal `
  --plan <audited-plan.json> `
  --expected-plan-sha256 <audited-plan-sha256> `
  --report-output <external-immutable-evidence-path>
```

For an independently reviewable rehearsal with no commit, replace
`--apply-rehearsal` with `--dry-run-rehearsal`. Both modes write an evidence
report when `--report-output` is supplied, including a failure report if a
fence prevents the transaction.

Do not run this command until independent review authorizes the exact plan.
