# Read-only DDK GxP source-token candidate classification — 14 Oct 2026

## Scope

Code: `tools/audit_ddk_gxp_canonical_candidates_readonly.py`. Owner:
backend PR #7; no schema changes, no mutations, no approved links, no
frontend API changes. This tool supplements persisted original Excel
`db.dkkd` source groups and per-token evidence, which remain immutable
source observations.

On rehearsal VM `gxp-web-prod`, as verified by the operator on 14 Oct:

- Actual web runtime `97182e58c3a673938d1b263c7eeaab41d28147b4`.
- Schema `20261012_0023`, database `gxp_legacy_rehearsal`.
- 3,120 source groups and 861 ID CC tokens, imported from accepted original
  XLSB SHA-256 `c12537ea5a5c9f470e42fb5bdbe214f36983e310fceac7c560ad38885209fe3d`.
- 780 actual DDK version rows, 780 distinct DDK aggregates; no multiple
  persisted DDK versions and no canonical `business_eligibility_certificate_link` rows.
- Prior owner baseline flags five cross-Site source references and one
  DDK 626 company inconsistency. This tool must **measure**, not
  normalize or approve, those observations.

## Analysis semantics

Every physical Excel `source_group / source_row_number / token_index`
observation is preserved. The audit checks SHA-bound four-field source
digests, distinct GMP/GLP/GSP/GDP physical columns, four-group completeness,
token raw values/ordinal, and accepted corpus counts. It compares each
*legacy integer* ID CC against canonical Certificate.legacy_certificate_id
with dimensions:

- candidate found / absent (no canonical ID invented);
- exact GxP type / different type (no GMPbb remapping);
- same / different Site UUID (no Site ownership rescue);
- DDK company compared against DDK Site owning company;
- repeated legacy references counted without deduplication;
- potential cross-Site same-company evidence reported but not promoted.

`SOURCE_OBSERVATION_NOT_APPROVED` is present for **every token**, even if
all observed IDs/type/Site match. No "safe-to-link", "eligible", "auto-match",
regulatory status, version selection or scope assignment is exposed.
Existing canonical link count is read as a separate observation, not altered.

## VM command after this commit CI passes

Run from the checked-out validated backend PR #7 source tree. Use the
current VM runtime env, without printing DSN or credentials:

```bash
sudo -H -u gxp /opt/gxp/current-venv/bin/python \
  -m tools.audit_ddk_gxp_canonical_candidates_readonly \
  --expected-workbook-sha256 c12537ea5a5c9f470e42fb5bdbe214f36983e310fceac7c560ad38885209fe3d \
  --expected-groups 3120 --expected-tokens 861
```

The command uses `/etc/gxp/runtime.env` and verifies
`DB_MODE=local_postgres`, `DB_NAME=gxp_legacy_rehearsal`,
`DB_USER=gxp_app`, and local host with no overriding URI parameters.
The connection starts with PostgreSQL
`default_transaction_read_only=on`, the transaction verifies `READ ONLY`,
correct database and expected Alembic revision. It cannot insert, link or
modify existing source/Certificate tables.

For a private **token-level** JSON report, specify
`--output-json /var/tmp/gxp-ddk-private/candidate-audit-20261014.json`.
The file is written mode 0600 and cannot overwrite an existing file. Never
copy original source/report records to public GitHub, CI logs, or a frontend
API response; the CLI stdout prints aggregate counts only.

The source baseline acceptance waived Excel COM verification for this
development-only corpus. The tool does not claim independent COM validation.
Any future canonical links or DDK version mappings require explicit owner
adjudication of cross-Site/Company, version and regulatory scope.

## Verified operator baseline and exception evidence (14 Oct 2026)

Owner VM stdout for actual read-only candidate audit confirmed: **861/861** raw source
IDs resolve to a canonical Certificate, **861/861** exact type, 856 same-Site,
**five cross-Site** (all sharing DDK owning Company), 779/780 DDK Site/Company
consistent with **one owner mismatch**, 301 repeated occurrences beyond the
560 distinct referenced legacy Certificate IDs, **zero** recorded canonical
BusinessEligibilityCertificateLink rows. Source 3,120 groups/861 tokens and
backend running SHA 97182e5 were unchanged. These are observed candidate
identities, NOT approved links or proof of CertificateVersion scope coverage.

New optional `--exception-dossier-json` creates a separate mode-0600 private
file containing only flagged token observations, distinct DDK Company ownership
conflicts, and exact repeated-source token positions. For flagged candidate
Certificates it also records originating Case identity/Site/GxP, observed
issuance basis, CertificateVersion UUIDs and **per-version** scope UUID/order/
SHA-256 fingerprints, never substituted scopes from a newer version.
A Case Site or type discrepancy is a separate observation, not site-coverage
adjudication; administrative certificates without a Case are not automatically
classified as invalid. No false regulatory clearance/approval statuses.

Execute, only on VM after exact-HEAD CI passes:

```bash
sudo -H -u gxp /opt/gxp/current-venv/bin/python \\
  -m tools.audit_ddk_gxp_canonical_candidates_readonly \\
  --expected-workbook-sha256 c12537ea5a5c9f470e42fb5bdbe214f36983e310fceac7c560ad38885209fe3d \\
  --expected-groups 3120 --expected-tokens 861 \\
  --exception-dossier-json /var/tmp/gxp-ddk-private/ddk-idcc-exceptions-20261014.json
```

Share only CLI aggregate JSON output in GitHub conversations. The original
source cells, all row-level UUIDs and exception dossiers stay on the VM.
The two files' outputs are separate: no official SourceGroup/Certificate
canonical linkage is made, and neither source nor canonical tables are written.

## Offline private dossier overlap count (14 October 2026)

Existing verified VM private dossier: /var/tmp/gxp-ddk-private/ddk-idcc-exceptions-20261014.json.
To determine token-level intersections between 5 Certificate-vs-DDK Site exceptions,
3 Certificate-vs-origin Case Site exceptions, and the 1 DDK Company owner exception,
use the aggregate-only local file reader:

```bash
cd /opt/gxp/src/GXP-QLCL
sudo -H -u gxp /opt/gxp/current-venv/bin/python -m tools.summarize_ddk_gxp_exception_overlap --dossier-json /var/tmp/gxp-ddk-private/ddk-idcc-exceptions-20261014.json
```

Read-only JSON parsing; no DB connection or SQL, no original XLSB read,
no output file or mutations. Strict checks on aggregate, flags and repeated
reference cardinality fail closed if the private dossier is corrupted.
Standard output is aggregate-only: no DDK/Certificate IDs, Case UUIDs, private
source cells or dossier rows. Token overlap is not proof of grant/coverage.


## Read-only manual review queue from existing private dossier

After the operator's offline overlap (real VM, 14 Oct 2026):
- Exactly **7 source token positions** have Certificate-vs-DDK Site and/or
  Certificate-vs-origin Case Site conflicts: four Certificate/DDK only,
  two Case/Certificate only, and one position bearing both flags.
- **One further token position** has a DDK Site owning-Company mismatch,
  separate from those Site/Case positions.
- **One DDK Company ownership review** is recorded independently of token
  observations. No additional fake Certificate or version is inferred.
- All seven Site/Case token positions have saved version/scope evidence,
  but only nullable lifecycle states; no grant/coverage may be assumed.
- 228 referenced Certificate legacy IDs occur in multiple DDKs; repeated
  references are NOT automatic errors or link permissions.

New `tools/build_ddk_gxp_manual_review_queue.py` reads the **existing**
mode-0600 private dossier and reuses the overlap validator. It writes
**one new** private JSON review queue (mode 0600) in the same protected
directory; source file is unchanged. Original token, Case, Certificate,
Site, version and scope evidence are retained verbatim as private
observations. Manual review check requirements are prompts, NOT legal
decisions; each source token and Company record stays NOT_APPROVED and
PENDING_INDEPENDENT_EVIDENCE. Only anonymous aggregate counts and input
digest go to stdout. No database service or source importer is invoked.

After exact-HEAD CI is green, on the VM with checked-out backend branch:

```bash
sudo -H -u gxp env PYTHONDONTWRITEBYTECODE=1 \
  /opt/gxp/current-venv/bin/python \
  -m tools.build_ddk_gxp_manual_review_queue \
  --dossier-json /var/tmp/gxp-ddk-private/ddk-idcc-exceptions-20261014.json \
  --queue-json /var/tmp/gxp-ddk-private/ddk-idcc-manual-review-20261014.json
```

Output must not pre-exist. It cannot be placed in a different or
public directory. Do not commit or upload private queue/dossier data to
GitHub. Do not merge this evidence queue with actual
BusinessEligibilityCertificateLink records.


## Metadata-only evidence coverage for the 8 flagged ID CC tokens (14 October 2026)

Owner: `tools/audit_ddk_gxp_review_document_coverage.py`. It does not
change the import or legal adjudication. The reader reconstructs the review
queue from its original private dossier and refuses any modified queue,
including unapproved token/cardinality drift.

It reads `Document`, `DocumentVariant`, and `DocumentVersion`
for three **independently identified canonical parents**: the ĐĐK itself,
the referenced GxP Certificate and its originating Case (when present).
The link from original source token to canonical identity remains unapproved.
Metadata classes are `NO_DOCUMENT_METADATA`,
`DOCUMENT_METADATA_WITHOUT_STORAGE_LOCATOR` and
`STORAGE_LOCATOR_RECORDED_UNVERIFIED`. A locator does not imply that
the file exists or has been verified, and no metadata is proof of grant,
legal scope, approved version, or cross-Site coverage.

Use on VM after CI SUCCESS, with runtime still operating unchanged:

```bash
cd /opt/gxp/src/GXP-QLCL
sudo -H -u gxp env PYTHONDONTWRITEBYTECODE=1 \
  /opt/gxp/current-venv/bin/python \
  -m tools.audit_ddk_gxp_review_document_coverage \
  --dossier-json /var/tmp/gxp-ddk-private/ddk-idcc-exceptions-20261014.json \
  --queue-json /var/tmp/gxp-ddk-private/ddk-idcc-manual-review-20261014.json \
  --details-json /var/tmp/gxp-ddk-private/ddk-idcc-document-metadata-20261014.json
```

Private details are create-exclusive mode 0600. Console prints only
aggregate classifications and an input hash. Database connections are
validated to the local PostgreSQL rehearsal database / schema 0023 and
enforced read-only at both connection and transaction levels. No storage
path or actual binary is probed and no file metadata is rendered publicly.


## Proven lookup-input readiness for flagged DDK/Case identities

14 Oct 2026 — `tools/audit_ddk_gxp_storage_identity_readiness.py`.

Before any NAS/file probing, this guarded read-only inventory checks whether
each private review record has the exact **legacy inputs** required by
approved storage contracts. DDKD folder owner: stable original
`Site.legacy_site_id` used only by the existing
`StorageService.resolve_dkkd_folder` matcher; no display-name
or generation-folder guessing. Inspection folder owner: **originating
Case.site_id**, that Site's legacy site ID, exact
`Case.legacy_inspection_code`, and separately preserved physical
`db.ktra` year evidence in
`LegacyInspectionStorageAnchor`.
Do not substitute Certificate Site or DDK Site for the originating Case Site.
Source registration-year conflicts remain unresolved even when another year
field is usable. Missing anchor/code/site ID is explicit, not rescued.

Classification `*_INPUT_AVAILABLE_UNPROBED` means a future
authorized resolver *may* be called; it does NOT report a found folder.
Existing `StorageBinding` rows are unverified historical metadata,
never a filesystem assertion. No attempt is made to infer a file location
for an individual Certificate from a Site ID.

The script regenerates the private review queue from its original dossier
and verifies exact accepted population and source-bound UUID identities
before using strictly REPEATABLE READ / READ ONLY rehearsal PostgreSQL
(schema 0023). No NAS access, binary read, web API, importer, schema
migration or database write. Optional private report created exclusively
with mode 0600; CLI prints only aggregate status flags.

Run on VM from exact validated source SHA after CI succeeds:

```bash
sudo -H -u gxp env PYTHONDONTWRITEBYTECODE=1 \
  /opt/gxp/current-venv/bin/python \
  -m tools.audit_ddk_gxp_storage_identity_readiness \
  --dossier-json /var/tmp/gxp-ddk-private/ddk-idcc-exceptions-20261014.json \
  --queue-json /var/tmp/gxp-ddk-private/ddk-idcc-manual-review-20261014.json \
  --details-json /var/tmp/gxp-ddk-private/ddk-idcc-storage-readiness-20261014.json
```


## Bounded direct SMB folder-name pilot (2026-10-14)

Owner's VM config-only preflight reported `STORAGE_CLASS=synology_smb`,
both storage roots configured and SMB credentials configured; **no
network/storage access was performed by that preflight**. Prior real
read-only source-identity preflight proved 9/9 DDK lookup input records
available (8 distinct DDK), 8/8 Case input records available (6 distinct
originating Cases), seven registration-year anchors and one
inspection-date-year fallback; eight records lack StorageBinding.

New `tools/audit_ddk_gxp_smb_readonly_folder_pilot.py`
reads three protected 0600 private files (original source dossier,
source-derived manual queue and source-bound storage-input readiness).
It rebuilds the queue, cross-checks that every Case is the **originating
Case** not the Certificate/DDK Site, deduplicates canonical identities,
and allows *only* direct non-mutating adapter calls:

- `SmbStorageService.resolve_dkkd_folder(site_legacy_id=...)`
- `SmbStorageService.resolve_inspection_folder(year=..., site_legacy_id=..., inspection_legacy_code=...)`

It **does not** invoke `StorageBindingService`,
`StorageBindingLookupService` or legacy phase4 probe CLI:
those can write `storage_binding` and
`storage_resolution_log`. No PostgreSQL, NAS file read,
binary checksum, SMB write, guessed Certificate-folder identity,
year+1 rescue or folder placement. The first live pilot is bounded
to **one DDK folder** and **one originating Case folder** by default;
use distinct 0600 output file name for any subsequent wider run.

Results `RESOLVED`, `NOT_FOUND`,
`AMBIGUOUS`, and `INVALID` mean folder-name
matches *within configured roots*, not approved legal or regulatory
evidence. A network or authentication error blocks the run, never
becomes `NOT_FOUND`. The 0600 private JSON contains
relative folder names; public stdout contains aggregate counts only.
No source token becomes a canonical BusinessEligibilityCertificateLink.

After exact-HEAD CI SUCCESS, on gxp-web-prod:

```bash
cd /opt/gxp/src/GXP-QLCL
sudo -H -u gxp env PYTHONDONTWRITEBYTECODE=1 \
  /opt/gxp/current-venv/bin/python \
  -m tools.audit_ddk_gxp_smb_readonly_folder_pilot \
  --dossier-json /var/tmp/gxp-ddk-private/ddk-idcc-exceptions-20261014.json \
  --queue-json /var/tmp/gxp-ddk-private/ddk-idcc-manual-review-20261014.json \
  --readiness-json /var/tmp/gxp-ddk-private/ddk-idcc-storage-readiness-20261014.json \
  --max-ddk 1 --max-cases 1 \
  --details-json /var/tmp/gxp-ddk-private/ddk-idcc-smb-pilot-20261014.json
```

Do not share raw SMB paths, UNC roots or private JSON in GitHub.
If a transport exception occurs, report the sanitized error class
only; identify network reachability/credentials through a separately
authorized infrastructure procedure, not by fabricating folder results.

## DDK root direct-child shape diagnostic after full SMB pilot (14 Oct 2026)

VM's complete direct SMB parent lookup at source SHA `71f404490f46c4c6c243875546ea5e610bab1be7` returned `DDK_NOT_FOUND=8` out of eight unique DDK parents, `CASE_RESOLVED=2` and `CASE_NOT_FOUND=4` out of six Case parents, with zero database connection, NAS writes or binary file reads. `/readyz` remained unchanged. This is a *folder-name matching result inside the configured roots*, not evidence that physical/legal source files do not exist.

The next owner-controlled read-only diagnostic `tools.audit_ddk_gxp_smb_readonly_root_shape` enumerates **only direct child metadata** of the already configured DDK SMB root, maximum 10,000 entries, and returns aggregate shape counts: root files, direct child directories, directories containing the exact VBA-derived legacy ` (<numeric site ID>)` token shape, directories with other numeric parenthesized tokens, and directories with no numeric parenthesis token. It also counts (aggregated only) how many of the 8 original legacy Site identities have zero/one/multiple exact matches, never printing private Site IDs, names, or paths.

The diagnostic regenerates the private manual-review queue from the original 0600 source dossier, matches all 8 DDK source keys from the private readiness report, checks the 0600 *full* probe as the prior observation, and refuses to proceed if evidence differs. It performs **no** source recategorization, alternate-key match, NAS subdirectory recursion, year+1 inference, DB connection or writes, file content reads, filesystem changes, or link approval. A budget breach or SMB failure aborts without claiming a complete inventory. A new 0600 private JSON is created only on success.

This resolves whether the configured root is empty, has folders but none in the proven legacy shape, or contains folders with the proven token shape but not those 8 Site IDs. Do not change root config, hardcode per-company paths or make canonical links from this metadata alone.

## Dual source-year inspection folder identity (14 Oct 2026)

The physical `db.ktra` source carries two separately qualified date columns:
`ĐĂNG KÝ / Ngày nộp` (H) and `KIỂM TRA / Ngày K.tra` (M).
A Case folder may legitimately reside under **either** independently
recorded year; registration year + 1 is *not* a source year.

The **application owner** `StorageBindingService.resolve_inspection_folder`
now resolves a non-explicit-year Case against every distinct usable source
year (registration first, inspection second), without guessing year+1.
If both are equal, it probes only once. If just one resolves, it may
persist a binding for the exact resolved year. If two different years
resolve, the result is `AMBIGUOUS`, with **no new binding**. A
conflicting source-year field is not used as a lookup candidate;
the other independent field remains eligible if usable. The original
conflict stays recorded in the immutable anchor and is never replaced
or inferred. A malformed usable year blocks automatic lookup.
Explicitly supplied year continues to use binding-first validation and
single-year lookup under the existing approved contract.

This owner change must **not** be mistaken for evidence that the
previous 6-Case read-only audit already checked both years: that
earlier SMB audit used only one selected source year per Case. A new
independent read-only validation of both original year fields is
required before reinterpreting its four Case NOT_FOUND results.
No production deploy or DB write is authorized by this change.

## Independent read-only dual-year Case SMB audit (14 Oct 2026)

`tools/audit_ddk_gxp_case_dual_year_readonly.py` can now test the six
distinct flagged originating Cases on the VM, using **both** original
physical `db.ktra` years rather than the former single selected year.
It regenerates the source queue from the protected dossier; then in a
REPEATABLE READ / READ ONLY rehearsal DB transaction revalidates the entire
previous source identity readiness report and reads original H/M anchor
years. It calls the exact same `StorageBindingService._anchor_years`
source-year policy as the application owner, closes the DB connection, and
only then uses direct non-mutating Synology SMB folder resolvers. A year
may be checked only when it is usable in the immutable source row. No
guessed year+1, NAS recursion, file stream access, DB write, binding
persistence or link approval. A Case matching folders across both
years is recorded AMBIGUOUS, not resolved. A private 0600 JSON is created
with year-specific folder observations; public stdout reports aggregates.
Previous SMB audit reports remain intact and are not reinterpreted until
new real observations exist.

## Immutable 6-Case single-vs-dual-year transition check

On 14 October, protected original SMB parent report found 2/6 originating
Cases; a read-only dual-source-year audit found 3/6 across 9 original-year
lookups (three Cases have two distinct source years). Source-year attribution
counters overlap when both input columns name the same calendar year.

An ad hoc operator comparison incorrectly expected
`readiness_report_sha256` in the *private* original SMB report; that
field had been appended **only to printed aggregate stdout** after private
JSON was persisted. This is a consumer schema mismatch, not altered evidence.

`tools.audit_ddk_gxp_case_year_transitions_readonly` now compares both
private mode-0600 reports, regenerates the review queue from the original
source dossier, validates all six exact originating-Case identities, checks
the dual report's persisted readiness SHA against actual protected readiness
bytes, compares status/path/count for each initially probed year, and
requires zero regressions in any originally RESOLVED Case. It prints only
aggregate status transitions with no IDs or folder paths, and makes no
SMB or database connection. It does not normalize missing folder claims,
approve links, or rewrite any prior evidence/report.

## Bounded second-level DDK SMB root shape check

VM's first-level metadata scan confirmed 287 root entries, 274 direct
subdirectories, 13 non-directories and **no** direct numeric
` (<site_id>)` legacy token. This root-level observation is
compatible with an additional directory layer; it does not authorize
altering root config or changing the production DDK resolver.

`tools.audit_ddk_gxp_smb_second_level_readonly` checks whether exact
VBA-derived source-key tokens appear **one level beneath** each of the 274
folders. It is source-bound to immutable exception dossier, queue,
readiness, full 8+6 SMB report and original private root-shape JSON.
The diagnostic enumerates only the root and each immediate parent,
with separate budgets (1,000 root entries, 500 parents and 20,000
second-level entries). All parents must be completed or audit aborts.
Root direct shape must still equal the observed private root report.
Results are aggregates only, with separate distinct Site-key coverage
and distinct DDK parent coverage. It **does not** resolve a DDK folder
under another root, change canonical Site ownership, recurse deeper,
read files, create bindings, link Certificate to DDK, or infer missing
legal source from unmatched names. No manual per-source path hardcoding.

## Evidence-limited DDKD configured-root provenance (14 Oct 2026)

Actual VM returned one-level and second-level DDK SMB metadata:
- 274 immediate folders with no numeric parenthesized Site tokens;
- 657 second-level folders also without numeric parenthesis Site tokens;
- all 274 parents inspected, 1,317 second-level entries (660 files/other);
- zero exact source key matches to seven distinct Site IDs across eight DDK
  parent records. No binary content or SQL accessed.

Contract check: `docs/ADR/0032-dkkd-site-folder-token-contract.md` and
`docs/PHASE4F_DKKD_STORAGE_CONTRACT.md` require the **direct** DDKD
site-folder token ` (<site_legacy_id>)`. `docs/FILE_STORAGE_CONTRACT.md`
and `docs/LEGACY_SYSTEM_MAP.md` describe the DDKD document area relative
to `ActiveWorkbook.Path\Chứng nhận ĐĐKKDD`, then `Lần n` as an
issuance child. The active workbook's real runtime directory has **not**
been verified on the Linux VM.

`tools.audit_ddk_gxp_smb_root_provenance_readonly` reads the protected
source/readiness/SMB root/full/second-level reports, verifies exact
report hashes and read-only populations, then evaluates configured root
path shape **without opening SMB, SQL or binaries**. It emits booleans
such as whether the configured DDKD root leaf matches the documented
`Chứng nhận ĐĐKKDD` directory, whether it equals/contains the
inspection root, and whether they share an SMB host/share. It never
prints, stores or uploads UNC strings, credential values or original
per-Site keys. A match/mismatch is an observation **only**, not an
authorized replacement location. No automatic path fallback,
recursive NAS search, binding write, root rewrite or link creation.

## Root-provenance diagnostic blocked at VM (14 Oct 2026)

At CI-passed SHA `82caba9042e988bfd069c619f6c35cfc75cb96c8`
the operator-only read-only root-provenance command exited 2 with only
`DDK_ROOT_PROVENANCE_BLOCKED: RootProvenanceBlocked`. This is **not**
proof of root mismatch: an owner guard rejected one of private report
integrity, input identity or UNC/config syntax checks. Earlier
fully completed root and second-level SMB scans remain valid.

Owner fix in `tools.audit_ddk_gxp_smb_root_provenance_readonly`
retains every fail-closed check but emits only allowlisted **static error
codes** to distinguish which contract failed. UNC strings, environment
values, credentials and private Case/Site keys remain redacted.
The parser for configured roots also strips surrounding whitespace
exactly as the approved `create_storage_service_from_env` factory.
An unrecognized exception message maps only to its type or
`OWNER_GUARD_UNCLASSIFIED`; no exception traceback or value is emitted.

Until exact-head CI succeeds and the operator repeats this read-only
check, root basename matching remains **NOT VERIFIED**. Do not
change `STORAGE_DKKD_ROOT`, guess alternate paths, weaken the
VBA-derived ` (<site_legacy_id>)` matcher or create links.
