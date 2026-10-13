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

## Post-migration independent read-only certification (prepared)

After a **separately authorized** and successful 0022→0023 schema-only
migration, run the exact new SQL script on the VM. It needs only psql and
the SQL file from PR #7, not Python, SQLAlchemy or Alembic:

```bash
sudo -u postgres psql -X -v ON_ERROR_STOP=1 \
  -h /var/run/postgresql -U postgres -d gxp_legacy_rehearsal \
  -f /tmp/verify_ddk_gxp_0023_postflight_readonly.sql
```

The file is `scripts/verify_ddk_gxp_0023_postflight_readonly.sql`
in the PR #7 checkout; copy **only** that reviewed SQL file to the
specified temporary path rather than changing the runtime worktree.

The independently executed `REPEATABLE READ READ ONLY` transaction
fails closed unless ALL hold:

- exact database `gxp_legacy_rehearsal`, read-only isolation verified;
- exactly one Alembic revision row: `20261012_0023`;
- the two source-only tables exist as ordinary PostgreSQL base tables;
- group table has exactly 17 columns, token table exactly 7;
- exact PostgreSQL column types and `NOT NULL` constraints, including
  raw four-field source values, SHA-256 fingerprints and token fields;
- group and reference primary/unique/check constraints, source natural
  key and ordered-token unique key, exactly one token-to-group FK, no
  foreign keys from group to Certificate/Case/Site/Version;
- both migration-defined lookup indexes exist;
- **0 source-group rows and 0 token-evidence rows**.

Only this successful independent query may be reported as
`PASS_SCHEMA_0023_SOURCE_ONLY_EMPTY`. A successful schema-only apply
does not establish that 3,120 source groups or 861 token records have been
loaded. This SQL expressly refuses any nonempty source-only tables and
is **not** intended as a post-*data-load* check.

Do not run postflight if migration has not been authorized and applied:
the prior observed VM state is still Alembic `0022` with both tables
absent. In that state the postflight must fail as designed; this is not
an instruction to auto-apply schema.

## Mandatory runtime-compatibility checkpoint before any 0023 database write

The application's `/readyz` endpoint computes `expected_revision` from the
**migration files available to the running backend**, then compares it to the
database's actual `alembic_version`. If the VM's currently running backend
still expects `20261008_0022` and uses `gxp_legacy_rehearsal`, applying
`20261012_0023` to that database may cause the service to return 503.
Therefore **do not use the schema-only `--apply` command until this
readiness/connection-owner risk is classified**.

`scripts/check_gxp_runtime_db_target_readonly.py` uses only Python 3
standard library, reads the `gxp-web` systemd MainPID's `/proc` environment
*in memory*, and calls localhost `/readyz`. It outputs only the sanitized
database name, revision status and decision; it never outputs connection
URLs, usernames, passwords or full process environment, and it does not
modify the service or database. Local `/readyz` itself performs its normal
read-only DB check.

Copy only this script from the **immutable PR #7 commit** into an independent
file outside the runtime repository; check its Git blob with
`git hash-object /tmp/check_gxp_runtime_db_target_readonly.py` against the
corresponding GitHub file blob SHA. No `git config --global safe.directory`
and no global Python package installation are needed.

Run in the VM:

```bash
sudo python3 /tmp/check_gxp_runtime_db_target_readonly.py
```

**Stop if the result is** `BLOCK_ACTIVE_SERVICE_TARGETS_REHEARSAL`,
`BLOCK_UNKNOWN_RUNTIME_TARGET`,
`BLOCK_RUNTIME_READINESS_OR_REVISION_DRIFT`, or
`BLOCK_RUNTIME_INSPECTION_ERROR`. Only
`OBSERVED_SERVICE_TARGET_DIFFERENT_FROM_REHEARSAL` means the observed
MainPID target differs from rehearsal and readiness is currently green;
it is **not** permission to migrate and is not a guarantee about child
process overrides, later restarts or other services. Independently check
`pg_stat_activity` and the exact migration guard before any later apply.

### Failed runtime preflight: stage-limited diagnostics

The first verified VM read-only probe returned
`BLOCK_RUNTIME_INSPECTION_ERROR` without any failure-stage metadata. The
source file SHA-1 matched the GitHub blob
`4f2810efc9b7f2421db10ea302e2f6f7b6c5fa9d`; **this proves the
download was unmodified, but does not establish the current service DB
target**. The migration `0023` remains BLOCKED.

The revised `check_gxp_runtime_db_target_readonly.py` emits only
`failed_stage` and `error_category` on exceptions. Possible stages are
`SYSTEMD_MAINPID`, `MAINPID_PROC_ENVIRONMENT`,
`SAFE_DB_NAME_EXTRACTION`, `LOCALHOST_READYZ`, and `ASSESS_RUNTIME`.
No error message, URL, password, raw environment or process details are
returned. The operator must verify the new exact Git blob SHA before
running it. A failure at any stage is a STOP decision, not an instruction
to install packages or change the systemd service. Do not print
`systemctl show ... Environment` or `/proc/<pid>/environ` directly.

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
