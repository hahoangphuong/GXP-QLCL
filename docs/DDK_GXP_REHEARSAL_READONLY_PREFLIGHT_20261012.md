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
  `SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY`, then checks the server-reported state.
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

## VM-observed baseline, 13 October 2026

The owner executed the guarded read-only SQL on `gxp-web-prod`, with the
following **actual** result (not inferred from CI):

| Field | Observed |
|---|---|
| `current_database()` | `gxp_legacy_rehearsal` |
| `transaction_read_only` | `on` |
| `transaction_isolation` | `repeatable read` |
| `public.alembic_version.version_num` | `20261008_0022` |
| `to_regclass(public.business_eligibility_gxp_source_group)` | NULL |
| `to_regclass(public.business_eligibility_gxp_reference_evidence)` | NULL |

**Classification: `SCHEMA_0023_NOT_APPLIED`**. This closes the
plan-independent remote state-discovery gate for the observed instant.
The two provenance relations did **not exist** at that time. It is not
an `EMPTY_SCHEMA_READY` result, and neither table's contents have
been compared with the 3,120-group/861-token source-only load plan.

**Next bounded preparation: offline DDL inspection, NO DB I/O.**
In a local or isolated **PR #7 checkout** containing migration
`20261012_0023` and backend dependencies:

```bash
python -m tools.preview_ddk_gxp_0023_offline_sql \
  --output /tmp/gxp-ddk-gxp-0023-review.sql

sha256sum /tmp/gxp-ddk-gxp-0023-review.sql
```

The preview invokes Alembic's own `upgrade 20261008_0022:20261012_0023
--sql` in *offline* PostgreSQL mode, with a dummy loopback URL used only for selecting the SQL dialect (never connecting).
It refuses to overwrite existing output and checks the generated SQL
only creates the two intended source-evidence tables/two indexes plus
the one expected Alembic-version update; unrelated DDL/DML fails closed.

Do **not** run `alembic upgrade head` or `alembic upgrade 20261012_0023`
on `gxp-web-prod` merely because the offline preview is successful.
The normal `alembic.ini` has a SQLite fallback if `DATABASE_URL` is
not set, and a full online migration requires a separately approved,
guarded, exact-target execution with a post-migration schema/count check.
**No schema apply or source-data load was approved by the supplied
read-only query output.**

## Guarded schema-only migration tool — prepared, NOT executed

The owner-accepted live VM preflight reports Alembic `20261008_0022`
and both new tables absent. The reviewed **source-derived** offline
migration SQL is available separately with SHA-256
`0aafa71accd6795e7e2e89c83985b63a4490463cbd7f3ee6f4aeca358fee561a`.

`scripts/apply_ddk_gxp_0023_rehearsal_guarded.py` is a Python3-standard-
library-only **explicitly gated** schema migration executor for this exact
reviewed artifact. It **defaults to NO WRITE** and rejects any source bytes
not matching the pinned SHA-256. It strips only the SQL artifact's own
`BEGIN/COMMIT`, then uses one PostgreSQL `SERIALIZABLE` transaction
containing the original Alembic SQL. A first server-side DO guard requires
the correct database, source revision `0022`, and *both provenance tables
absent*. It locks `alembic_version` while applying. A final guard requires
`0023`, both source-only tables present, and **zero rows** in both before
COMMIT. If any SQL/guard fails, `psql -v ON_ERROR_STOP=1` returns nonzero;
no success message is issued and the transaction is rolled back by PostgreSQL.
The tool uses **only** the VM-local Unix socket
`/var/run/postgresql`, PostgreSQL role `postgres`, and exact database
`gxp_legacy_rehearsal`; it has no direct access to production `gxp_qlcl`
via command parameters.

Run in an **isolated directory**, not the VM runtime worktree. Obtain only
the exact reviewed SQL artifact and script from the PR #7 checkpoint;
verify their SHA-256 locally. Neither Python packages nor Alembic are
needed on the VM for this offline-reviewed artifact.

Default no-write review:

```bash
python3 /tmp/apply_ddk_gxp_0023_rehearsal_guarded.py \
  --sql-file /tmp/GXP_DDK_0023_OFFLINE_POSTGRESQL_REVIEW.sql
```

Only after the database owner explicitly approves this **schema-only**
write, the operator may add `--apply --confirm-target gxp_legacy_rehearsal`
to the above command. This extra CLI confirmation is an execution guard,
not a substitute for authorization. **No one has executed this apply step
as part of the current PR/workflow.** Do not substitute `alembic upgrade
head` or execute the standalone SQL unguarded. A successful command
would still require an independent new read-only VM query confirming
revision `0023`, both tables present and both counts **0**. Data
population (3,120 source groups + 861 tokens) and any canonical Certificate
linkage remain separate approvals.

## Fast VM-native check without moving the source payload

Before arranging a complete plan/JSON upload to the VM, a simpler
**plan-independent PostgreSQL check** is available as
`scripts/check_ddk_gxp_provenance_rehearsal_readonly.sql`.
Run it **on the VM**, using the file from the current PR #7 checkout:

```bash
cd /opt/gxp/src/GXP-QLCL
sudo -u postgres psql -X -v ON_ERROR_STOP=1 \
  -d gxp_legacy_rehearsal \
  -f scripts/check_ddk_gxp_provenance_rehearsal_readonly.sql
```

**Prerequisite:** the exact PR #7 version of this script must already be
available in the VM worktree. Merely having an older runtime checkout does
not satisfy this; do not switch/deploy production branches just to execute
the check. An operator may copy only this audited SQL file onto the VM
and then pass its **verified local path** to `psql -f`. No DB schema changes
or Git pulls are necessary for the SQL execution itself.

This diagnostic runs within `REPEATABLE READ READ ONLY` and aborts with an
exception if connected to a database other than `gxp_legacy_rehearsal`.
It prints the Alembic revision when present; PostgreSQL catalog evidence
of the two provenance tables (or their absence), columns/nullability,
constraints, indexes, and counts if the physical tables exist. It safely
skips counts of not-yet-created tables at Alembic `0022`; it **does not**
print source text or user passwords. `ROLLBACK` closes the read-only
transaction.

**Important distinction:** this basic check does **not** compare table
contents against the 3,120/861-plan payload and is not an authorization
to migrate or load source records. If the two tables already contain
rows, use the comprehensive `tools/preflight_ddk_gxp_rehearsal.py` with
the sealed local plan to determine whether they are identical, partial
or conflicting. Report the actual SQL output rather than inferring the
database state from repository revisions or CI.

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
