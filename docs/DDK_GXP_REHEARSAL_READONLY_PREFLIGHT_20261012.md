# DDK GxP provenance — read-only PostgreSQL preflight

**Scope:** backend PR #7; no migration, no source load, no canonical
Certificate relationship, no production deployment.

The owner-accepted workbook/JSON source baseline (830 original `db.dkkd`
rows, 50 existing approved exclusions, 780 effective DDK rows, 3,120
group records and 861 physical ID CC tokens) has a source-only dry-run
plan. The next stage checks the **current rehearsal database** without
altering it.

The tool `tools/preflight_ddk_gxp_rehearsal.py` requires:

- A sealed `GXP_DDK_GXP_PROVENANCE_DRY_RUN_V1` plan from
  `tools/plan_ddk_gxp_provenance_load.py`, including unmodified logical
  payload SHA-256; source group and token conservation is recomputed
  before opening any connection.
- A PostgreSQL URL targeting exactly `gxp_legacy_rehearsal`, supplied
  through a local environment variable. **Do not supply passwords in the
  command, PR, CI logs or screenshots.** A restricted SELECT-only database
  role is preferred; the connection also forces
  `default_transaction_read_only=on` and executes
  `SET TRANSACTION READ ONLY`, then checks the server-reported state.
- Public-schema introspection only, with a fixed allowlist of the new
  provenance tables. It reads `public.alembic_version`, table structure,
  unique constraints, source-only FK shape, counts and original-workbook
  source rows/tokens. It does not read existing Case/Certificate records.

Read-only invocation from a local worktree with the required network access:

```powershell
# Set the secret DSN privately in your local user session, never commit it.
# $env:GXP_REHEARSAL_READONLY_DATABASE_URL = <a read-only PostgreSQL URL>

py -3 -m tools.preflight_ddk_gxp_rehearsal `
  --plan-json "D:\GXP-DDK-EVIDENCE\ddk_gxp_provenance_dry_run_20261012.json" `
  --output "D:\GXP-DDK-EVIDENCE\ddk_gxp_rehearsal_preflight_20261012.json"
```

The new output path must not exist. Neither the original plan nor an
existing report can be overwritten. The report never prints the DSN,
user name, password, raw group text or row-level certificate evidence.

## Classification of actual target state

| Read-only status | Meaning |
|---|---|
| `SCHEMA_0023_NOT_APPLIED` | DB is still at `20261008_0022` with neither provenance table |
| `SCHEMA_OR_REVISION_DRIFT_REVIEW` | Unexpected Alembic revision or missing/incomplete table/constraint/FK |
| `EMPTY_SCHEMA_READY_FOR_SEPARATE_APPLY_APPROVAL` | Both new tables exist at `20261012_0023`, have checked source-only schema and are empty |
| `SOURCE_PROVENANCE_ALREADY_MATCHES_PLAN` | Both tables already contain exactly the planned source-only rows and tokens |
| `TARGET_DATA_CONFLICT_OR_PARTIAL_REVIEW` | Some source rows/tokens missing, conflicting, extra, or another workbook already populated the tables |

The tool always reports `READ_ONLY_PREFLIGHT_NO_APPLY_AUTHORIZATION`;
even the "ready" status is **not** permission to apply schema/data
changes. It performs zero DDL/DML and creates zero canonical links.

## Limits of this checkpoint

No direct PostgreSQL connection from the ChatGPT GitHub connector has
been established. Passing GitHub CI does not prove the actual
`gxp_legacy_rehearsal` revision or empty-table count. A live report
requires execution from an authorized runtime that can reach the VM.
Only the complete JSON output can support a real-state decision; no
assumed DB counts should be presented as observed facts.

The earlier owner decision waiving Microsoft Excel COM/HasFormula checks
remains in effect. This preflight does not reopen that gate or fabricate
`COM_VALIDATED` status. It neither authorizes the subsequent source-only
data load nor approves cross-Site or historical Certificate links.
