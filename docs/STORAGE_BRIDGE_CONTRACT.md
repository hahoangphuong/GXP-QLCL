# Storage Bridge Contract

## Purpose
This contract defines what a bridge-backed Synology integration is and is not allowed to own, whether the transport is a direct Cloud Run application-level client path or a later dedicated bridge host.

## Ownership
- The bridge is an infrastructure adapter only.
- It implements the same storage-facing responsibilities currently assigned to `StorageService`.
- It does not own workflow rules, document-family decisions, or authorization policy.
- `BridgeStorageAdapter` is the only business-visible client surface; transport specifics stay below it.

## Required operations
- `resolve_inspection_folder`
- `resolve_dkkd_folder`
- `list`
- `stat`
- `read_stream`
- `write_stream`
- `create_folder`
- `exists`
- `copy`
- `move`
- `rename`
- `checksum`

## Non-responsibilities
- template selection
- bookmark mutation
- source-document dependency choice
- certificate issuance semantics
- case workflow transitions
- frontend/operator identity

## Request identity
- Cloud Run should call the bridge using service-to-service identity.
- Browser clients must never call the bridge directly.
- NAS credentials, if any are needed by the bridge host, must remain bridge-side only.

## Data expectations
- Every write response should include enough metadata for the caller to persist exact document-version lineage:
  - storage root
  - relative path
  - original filename
  - checksum
  - byte size
- Reads should support streaming rather than requiring full file buffering in memory for every request.

## Failure model
- The bridge must fail closed when:
  - folder resolution is ambiguous
  - target paths escape the configured root
  - underlying Synology storage is unavailable
  - checksum verification fails where required
- The bridge must not silently fall back to alternate cloud file storage.

## Transport posture
- The bridge may use Tailscale now and site-to-site VPN later.
- That transport change must not require business-layer changes in Cloud Run.
- The first integration PoC may use Cloud Run with application-level transport over Tailscale without introducing a dedicated bridge host yet.
- If that PoC fails, a dedicated bridge host near Synology is the fallback infrastructure shape.

## HMAC bridge-token integrity

When `BRIDGE_AUTH_MODE=hmac_jwt` is enabled, the bridge accepts only the
token format produced by `issue_bridge_token`: canonical unpadded Base64URL
components, an `HS256` JWT header, a JSON-object payload and an exact HMAC
signature. Identity claims (`iss`, `aud`, `sub`) must match the configured
service identity. Integer `iat` and `exp` claims must describe a bounded,
not-yet-expired lifetime within `STORAGE_BRIDGE_TOKEN_TTL_SECONDS`, with a
small tolerance for issuance clock skew.

Malformed, tampered, unsupported, expired or out-of-contract tokens return
HTTP 401 and must never expose storage contents or produce an unhandled
server error. These checks are owned by the bridge authentication adapter;
the business workflow, frontend and storage backends do not duplicate JWT
validation. Google OIDC verification remains a separate explicit auth mode.

## Collision safety of storage file operations

`copy`, `move` and `rename` do not have an overwrite flag and therefore
must reject an existing destination with `StorageTargetExistsError`
(HTTP 409 through the storage bridge). The pre-existing content and source
remain unchanged. The only explicit overwrite operation is
`write_stream(overwrite=True)`, whose caller must already own that action.
Storage adapters must never silently turn a collision into a rename into an
existing directory or a replaced document. Exclusive creation is used for
copy destinations; moves and renames check destination occupancy before
invoking their backend-specific operation.

## No-replace atomicity after destination preflight

An existence check alone is never the safety boundary for `move` or
`rename`: another writer may create the destination between the check and
the operation. On Linux, the filesystem-backed adapter requires
`renameat2(RENAME_NOREPLACE)`; on Windows it uses non-replacing
`os.rename`. If a platform, kernel, filesystem or mount cannot guarantee
no-replace, the adapter fails closed instead of falling back to potentially
overwriting `shutil.move` or POSIX `os.rename`. On SMB, `smbclient.rename`
uses `replace_if_exists=False` server-side; destination collisions returned
as generic SMB OSErrors are mapped to `StorageTargetExistsError` (HTTP 409).
The no-replace operation prevents implicit replacement. It does not provide
a multi-file transaction, version ownership, or document-business locking.

## Filesystem copy publication and metadata rollback

Local filesystem `copy` stages the complete byte copy and metadata in a
temporary file within the destination directory. Only after both succeed
does it publish via the same atomic no-replace primitive as `move` and
`rename`. An error cleans up the private temporary path only, never an
already published destination: this preserves data written by a concurrent
actor during a metadata failure or late target collision. Unsupported
atomic publication fails closed; business code must not replace it with
an overwrite/copy fallback. SMB copy retains its independent exclusive
create (`xb`) contract; no SMB semantics change in this patch.

## Exclusive write publication

The filesystem adapter now stages all `write_stream` content before exposing
the requested path. `overwrite=False` publishes by atomic no-replace and
returns `StorageTargetExistsError` (HTTP 409) if another writer won the
destination. A failed stream or unsupported no-replace operation cleans up
only the private staging file. `overwrite=True` retains its intentional
atomic `os.replace` behavior. This guarantee applies to the local/mounted
filesystem adapter; the SMB-native adapter's exclusive stream operation
requires separate parity review.

## SMB exclusive-write publication parity

Native SMB `write_stream(overwrite=False)` stages a complete file on the
same share using exclusive mode `xb`, then publishes with
`smbclient.rename` (server-side `replace_if_exists=False`).
Collisions return `StorageTargetExistsError` (HTTP 409). Interrupted writes
only remove their private staging file, never another writer's destination.
The final requested path is not exposed until the write completes.
`overwrite=True` retains its existing intentional SMB replace behavior.

## Read-only staging candidate inventory

Successful writes publish a fully completed temporary file. Unexpected
process death may leave unpublished private staging files on Synology.
New filesystem and native SMB staging files use a distinct
`.gxp-stage-<random>.tmp` name. A bounded, read-only operator command can
inventory their metadata:

`python -m tools.audit_storage_staging --root inspection --max-directories 250 --max-entries 10000 --max-depth 8`

Add `--root dkkd` and/or `--root template` only when authorized and
configured. Output contains candidate paths/sizes and a mandatory
`truncated` indicator with the limit reached; an incomplete scan is not
proof of no staging files. There is **no automatic deletion**, age-based
purge, background task or mutation endpoint. A matching name does not prove
orphan ownership: an active transfer or an ordinary similarly named file
may exist. Operator review and external ownership verification are required
before any separately approved cleanup.

Old SMB `<target>.tmp-<32 hex>` paths are reported as
`legacy_smb_candidate`. Older filesystem-backed `tmpXXXXXX` files
cannot be reliably distinguished from unrelated files using their names,
so they are intentionally **not** classified or deleted. This inventory
does not assert exhaustive recovery of earlier staging artifacts.

## Audit failure and recovery boundaries

The metadata-only staging inventory reports `truncated=true` and
`incomplete_reason=storage_access_failed` if the NAS becomes unavailable,
a scanned path becomes unreadable, or an adapter rejects a path. Earlier
candidate metadata is retained in the report, together with the failed
logical root and relative folder, but the scan **stops immediately**.
No underlying exception messages, SMB credential values or UNC connection
details are included. A storage adapter initialization failure reports
`storage_setup_failed`, zero scanned entries and an incomplete result.

CLI exit status: `0` for a complete inventory, `2` for a scan budget
limit, and `3` for storage setup/access failure. A successful command
execution is not evidence that an unreported folder has no staging files.
Directories whose names look like staging files are not staging-file
candidates. The scanner does not retry, create folders, read binary
contents, delete files or attempt recovery after a connection outage.

The entry budget limits **processed** entries, but the current
`StorageService.list` contract materializes one complete directory listing
per call. Therefore, it does not guarantee bounded NAS enumeration cost or
RAM for a single exceptionally large directory. Any future streaming
enumeration must be implemented at the storage adapter owner, not by
silent client-side post-filtering.

## Streaming, budgeted staging inventory

Direct local/mounted-filesystem and SMB adapters expose a dedicated
`iter_entries_for_audit` generator. It reuses their path validation and
entry-metadata ownership, but does not sort/materialize an entire directory.
The staging scanner closes that generator on completion, error or budget
exhaustion. At most `max_entries + 1` entry metadata records may be
inspected for budget detection, even for a large single directory.
Normal application `list()` behavior and API contracts are unchanged.
Only direct storage adapters are supported by the operator CLI. Other
protocol implementations fall back to `list()` and retain its per-folder
enumeration/memory limitation.

Mid-stream NAS errors stop the audit with `storage_access_failed`,
preserving metadata found earlier in the scan while making the report
explicitly incomplete. Candidate results are sorted for reproducible
JSON output; scan limits count entries encountered, not filesystem order.

## Staging-to-lineage evidence (read only)

`backend.app.storage.staging_lineage.reconcile_staging_lineage(session, inventory)`
queries only exact `(storage_root, storage_relative_path)` pairs in
`document_version` and `template_definition`. An inspection
`storage_binding.relative_path` is reported separately **only as folder
scope**, not proof of file ownership. The output always has
`status=review_only` and has no cleanup or deletion operation. Neither
similar basenames nor a numeric legacy ID are sufficient to infer a file
reference.

The function issues SELECTs with SQLAlchemy `no_autoflush`, does not commit,
and requires a caller-owned **read-only** database session/role. It does
not open a production database connection by itself. A partial staging
inventory remains explicitly partial in the cross-check output.
`no_exact_locator_evidence` means only that the exact registered locator
pair was absent from the queried registry. It does not prove that a
staging candidate is abandoned, unowned, or safe to delete; legacy paths,
in-progress writes and unregistered source files may still be relevant.
Any future production integration must enforce a read-only transaction
and obtain operator authorization separately.

## Opt-in operator reconciliation against PostgreSQL metadata

After creating a staging inventory JSON with the read-only
`tools.audit_storage_staging` command, a separate operator can compare its
candidates with exact DB locators. This is not part of startup, requests,
scheduled jobs, or production deployment.

1. Obtain a **dedicated metadata read-only PostgreSQL credential** approved
   for this purpose and assign it to the environment variable
   `GXP_STORAGE_LINEAGE_READONLY_DATABASE_URL`. It must not be the runtime,
   owner, or migration credential. Do not put the URL in command arguments,
   shell history, the input JSON, logs, or source control.
2. Run `python -m tools.reconcile_storage_staging_lineage --inventory-json staging.json`
   in a separately authorized environment. Without the dedicated environment
   variable, the command refuses to connect.
3. The command verifies PostgreSQL, executes `SET TRANSACTION READ ONLY`
   and `SHOW transaction_read_only`, runs SELECT-only lineage reconciliation,
   then rolls back even a successful transaction. A failed query emits a
   generic incomplete report, without database exceptions or credentials.
4. Review exact document-version and template-definition references and
   inspection-folder binding hints. The output always states `review_only`
   and never declares any file safe to delete. Exit status `0` means the
   supplied storage inventory was complete, `2` means it was incomplete,
   and `3` means the lineage audit could not complete.

The command **does not access NAS**, mutate PostgreSQL, or clean staging
files. Real-world credential/permissions and Synology checks remain separate
operator-controlled UAT; neither is performed by GitHub CI.

### PostgreSQL driver compatibility

The VM dependency lock supplies `psycopg` version 3. The optional
reconciliation CLI accepts `postgresql+psycopg://` explicitly, or the
generic `postgresql://` form which it maps in memory to the psycopg3
driver. Other PostgreSQL dialect/driver identifiers are rejected before
connecting. The URL, including credentials, is never printed.

## Shared exact-locator evidence

When two or more `document_version` or `template_definition` records
refer to the same exact `(storage_root, storage_relative_path)`, the
read-only report marks the candidate
`multiple_exact_locator_references` and includes *all* matching IDs.
This is **not** an automatic consistency violation: distinct logical
documents and templates may legitimately refer to the same binary.
It is a review signal, never a winner-selection, orphan classification,
database correction or cleanup authorization. Registry overlap is
distinct from an `inspection` `storage_binding` folder hint.

## Mandatory metadata-reader privilege gate

Before querying lineage, the optional CLI confirms the transaction is
read-only **and** queries PostgreSQL role attributes/effective grants.
The role must have SELECT on `document_version`,
`template_definition`, and `storage_binding`, but no INSERT, UPDATE,
DELETE, TRUNCATE, REFERENCES or TRIGGER rights on those tables; it must
also lack elevated PostgreSQL role attributes and database/schema CREATE.
This check includes inherited table grants and refuses superuser,
runtime/migration or inadequately provisioned identities. A failure
returns a generic incomplete audit and rolls back. Transaction read-only
is an additional control, not a substitute for this permission gate.

The CLI also rejects roles with effective write grants on **any** table,
partitioned table, view, foreign table, or materialized view in the active
application schema. This prevents a general application writer from being
mistaken for a dedicated metadata reader merely because the three lineage
tables themselves are SELECT-only. External cross-schema privileges and
role membership remain operator IAM responsibilities; this check does not
certify the absence of every possible database privilege outside the
application schema.

### Pinned PostgreSQL lineage schema

The app's migrated lineage tables reside in schema `public`. Before
performing role checks or ORM SELECTs, the CLI sets a transaction-local
search path to `pg_catalog, public, pg_temp`; temporary tables cannot
shadow `public.document_version`, `public.template_definition` or
`public.storage_binding`. The privilege gate also checks the explicitly
qualified `public` tables and schema rather than whatever schema a
connection URL may put first. An installation intentionally using a
different application schema is not supported by this audit until a
separately reviewed contract is introduced. The search-path change is
transaction-local and is rolled back with the audit.

### Consistent metadata snapshot

The optional PostgreSQL CLI uses a transaction at `REPEATABLE READ, READ
ONLY` isolation and explicitly verifies both session settings before
performing lineage reads. This gives the entire batched audit a single
database snapshot instead of mixing rows committed at different times
under `READ COMMITTED`. The transaction is rolled back after use.
The NAS inventory and this database snapshot are **not** an atomic
cross-system snapshot, so neither source can authorize staging cleanup.

### Staging inventory input validation (fail closed)

The opt-in lineage CLI treats inventory JSON as untrusted operator input.
Before **any** PostgreSQL connection it enforces a bounded 8 MiB read,
rejects repeated JSON keys and unknown fields, requires exact scalar
types (particularly boolean `truncated` and nonnegative integer counters
and sizes), ensures truncation/reason/failure-path consistency and forbids
duplicate or unsafe logical locators. Every candidate must have a
scanner-recognized filename matching its declared category. Malformed
input returns the existing generic `lineage_audit_failed` response with
exit code 3, without exposing input contents, file paths or DB credentials.
Direct service callers also validate safe inventory structure before
running SELECT statements.

These checks establish **structural plausibility only**. A caller can
still fabricate a well-formed JSON audit; there is no signed capture,
authenticated provenance, cross-system snapshot or proof of orphan
ownership. `review_only` therefore remains mandatory, and the command
must never authorize cleanup.

### Explicit inventory root scope

New read-only scanner exports include `requested_roots`, a de-duplicated
array of the logical roots requested by the operator (`inspection`,
`dkkd`, `template`). The opt-in lineage CLI requires this field and
rejects missing, empty, duplicated or unknown roots, any candidate outside
the declared roots, and inconsistent failed-root metadata. A purportedly
complete scan with no directory examined, or fewer directories than
requested roots, is invalid. A failed storage setup still carries the
requested roots but is always marked truncated and cannot be interpreted
as clean.

The lineage report propagates `input_requested_roots` independently of
its `status=review_only`; e.g. a valid, empty `inspection` inventory
does **not** make statements about `dkkd` or `template`. Older JSON
exports without explicit root scope are refused by the operator CLI:
regenerate an inventory rather than fabricating scope metadata. In-memory
callers may retain legacy/unknown scope (`requested_roots=()`) for
compatibility; the report preserves that unknown scope rather than
inventing one.

The scope field remains **self-declared, not authenticated**. It does
not prove that NAS enumeration finished, that no files changed since
scanning, or that a file is safe to delete.
