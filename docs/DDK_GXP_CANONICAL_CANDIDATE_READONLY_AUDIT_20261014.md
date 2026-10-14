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


## VM root-provenance parser/adapter parity — 14 Oct 2026

The exact-head VM operator probe on `4d8164f` reconfirmed all protected
source queue, readiness, full-SMB, root-shape and second-level JSON
integrity checks. Root configuration parsing itself succeeded, but
`assess_configured_roots` stopped with `DDKD_ROOT_UNC_INVALID`.
An independent no-network, no-DB diagnostic classified the difference:
`SmbStorageService._normalize_root` and `_server_from_root` accepted the
configured DDKD UNC; provenance `unc_components` rejected it because
splitting on backslashes produced at least one *empty component*.
This evidence does **not** identify a replacement root, nor establish
whether the legacy Windows workbook was deployed at the configured
location. It does not invalidate previously complete SMB metadata scans.

The provenance-audit owner now uses the same nonempty-component
tokenization as `SmbStorageService._server_from_root` strictly for
**read-only boolean configuration comparison**. The actual configured
root is not changed or used for an alternative SMB connection. The audit
continues to require UNC syntax, host/share, no forward slashes, and
no `.` or `..` traversal components. Regression covers repeated
backslash components, negative leaf comparison and traversal/slash
rejection. The source physical-ID-CC audit docstring was also made raw,
removing its observed invalid-escape `SyntaxWarning` from import-time
stderr. Neither change grants legal approval, changes Site token
matching, writes storage/database, or authorizes root correction.

Pending **exact-head CI and new VM run**, configured-root leaf flags
remain NOT VERIFIED; all DDK GxP canonical links stay NOT APPROVED.


## VM-configured DDK root provenance VERIFIED — 14 Oct 2026

Operator reran the hardened, exact-HEAD `a1b5646927ab5a8bf05317f8ce222f8cc34b3612`
audit after GitHub run `38546477235` completed SUCCESS:
- PR #7 OPEN/DRAFT, exact HEAD and required CI jobs: PASS;
- VM `/readyz`, process and deployed release SHA baseline/postcheck: PASS, unchanged;
- Git working tree clean, exact checkout and private evidence owner/mode/hash: PASS;
- provenance report created privately with mode `0600`, all read-only guards: PASS;
- no runtime deploy, DB/NAS write or DDK canonical link creation.

The **configured-root string comparisons** produced:
- `ddk_root_leaf_matches_legacy_ddkd_directory = true`
- `ddk_root_contains_legacy_ddkd_directory = true`
- `ddk_root_same_host_and_share_as_inspection = true`
- `ddk_root_equals_inspection_root = false`
- `ddk_root_nested_under_inspection_root = true`
- `inspection_root_nested_under_ddk_root = false`
- `template_root_configured = true`
- `ddk_root_equals_template_root = false`
- `ddk_root_has_subdirectory_after_unc_share = true`

These results supersede the earlier `NOT VERIFIED` status **only for
configuration-string provenance flags**. They do NOT demonstrate that
this location is the operational Windows `ActiveWorkbook.Path` area
or that its entries contain the eight unapproved DDK source parents.
The previously complete metadata-only scans still found zero direct or
second-level parenthesis Site tokens (274 + 657 directories inspected).
No alternate SMB root has been verified; no root rewrite or change to the
direct ` (<site_legacy_id>)` legacy matcher is justified.

Separate follow-up: three originating Cases remain `NOT_FOUND` after
all independently usable physical db.ktra submission/inspection years
were probed (six Cases, nine source-year observations, no regressions).
Use existing protected Case reports to characterize gaps before any
new bounded SMB lookup; do not use year+1 guesses or search arbitrary years.
Business eligibility links remain `NOT_APPROVED`.


## Remaining Case source-year evidence and bounded metadata discrimination (14 Oct 2026)

Exact-HEAD VM local read-only comparison of protected source queue, readiness,
original SMB report and dual-year report returned PASS:
- 6 originating Cases total, 3 RESOLVED and 3 NOT_FOUND;
- among NOT_FOUND: two with one usable physical source year each and
  one with two distinct usable physical source years;
- 4 original Case-year lookup observations across those 3 missing Cases;
- two missing Cases have submission-year provenance, all three have
  inspection-year provenance, and two have both kinds of provenance;
- no inferred year, changed Case identity, new report, SQL or SMB call.

A direct inspection SMB resolver returns NOT_FOUND when the source-year
root is absent OR when none of its direct child directories contains BOTH
the literal `(ID-<site_legacy_id>)` and
`(<inspection_legacy_code>)` tokens. The protected per-year records
cannot distinguish these cases. Absence of a complete token match is
not evidence of no physical or regulatory document.

The existing dual-year audit owner now exposes a **separate bounded
metadata-only classification function**, to use only after the original
two private reports have passed the existing transition/integrity
comparator. It examines exactly the four missing Case-year combinations
(no year guesses), caches each source-year root's immediate directory
names, and enforces at most 3,000 entries per year root and 12,000 total.
It classifies root absent, neither exact token, Site-only token,
inspection-code-only token or split tokens in distinct folders.
A newly complete matching pair, missing source/approval evidence,
unexpected case/year population, SMB fault or budget overflow aborts
rather than manufacturing a resolution. No recursive search, file
content, new alternative root, DB writes or legal approval. Public output
must stay aggregate-only; operator-only private data never enters GitHub.

**NOT VERIFIED on live Synology** until exact-head CI and a separately
checked bounded VM read-only run succeed. No production resolver,
storage configuration, binding or canonical link has been changed.

## VM source-bound missing Case-year metadata classification — VERIFIED (14 Oct 2026)

Operator executed the bounded, exact-HEAD read-only inspection-year
metadata diagnostic after GitHub CI `38549849685` completed SUCCESS at
`ea88a86ae2562eaa9ac04cdbe55cc3e8fded4e73`. The VM verified the
protected original and dual-year Case reports and exactly three still
unresolved Case parents (four independently sourced Case/year observations).
The four source-year root directories all existed, and 378 bounded
direct-child metadata entries were inspected. The new protected private
report was created by `gxp` with mode `0600` and contains per-Case/year
classification without publishing IDs, folder names or UNC paths.

Aggregate observations:
- `YEAR_ROOT_NOT_FOUND = 0`
- `NO_EXACT_TOKEN = 3`
- `SITE_TOKEN_ONLY = 0`
- `INSPECTION_CODE_ONLY = 1`
- `SPLIT_TOKENS_DIFFERENT_FOLDERS = 0`

Interpretation: one source-year directory contains the exact inspection-code
token without the **same directory name** also matching that Case's original
Site token `(ID-<site_legacy_id>)`; this is a source-vs-physical-name
identity review lead, not proof that the folder belongs to that originating
Case or another Site. The three NO_EXACT_TOKEN observations show only that
neither literal token was seen in immediate directory names in those source
year roots, not that all original documents are absent.

The actual full root-provenance flags previously passed separately and
cannot establish operational `ActiveWorkbook.Path` on a legacy Windows
machine. No guessed years, alternate roots, subfolder recursion, relaxations
of `matches_inspection_identity`, source row corrections or canonical
links are authorized from this metadata.

**Next bounded decision:** first reconcile the inspection-code-only
observation against independently retained source Site/Case evidence and
the original folder naming contract in a protected manual-review context;
treat the three zero-token observations as unresolved storage location or
naming evidence. Avoid another general SMB scan or guessed year/alternate-root
lookup. DDK/Certificate business eligibility remains `NOT_APPROVED` and
PR #7 stays DRAFT; no runtime release, PostgreSQL writes or NAS mutations.


## Single inspection-code-only folder marker diagnostic (14 Oct 2026)

The VM-protected missing-Case/year report has one code-only observation
and three without either exact inspection naming token. The one
code-only observation is now a **narrow inspection Site-token shape
question**, NOT a presumed Site re-assignment.

`tools.audit_ddk_gxp_case_dual_year_readonly.inspect_code_only_case_site_token_readonly`
is a separate **read-only metadata** diagnostic. Its operator script
must first validate the original source dossier/queue, readiness
SHA, six Case transitions, the protected four-year metadata report and
the unique code-only original Case/year against immutable records.
It then enumerates immediate directories of exactly that one verified
inspection source-year root (maximum 3,000 total entries and 20
code-matching directories), matching the original inspection-code token
literally. It characterizes those directory names as:
`NO_ID_MARKER`, `NONNUMERIC_OR_INCOMPLETE_ID_MARKER`,
`SOURCE_NUMERIC_ID_NONCANONICAL_FORMAT`, `OTHER_NUMERIC_ID_TOKEN`,
or `MULTIPLE_OTHER_NUMERIC_ID_TOKENS`.

The function does **not** relax `matches_inspection_identity`, guess
a Site, treat a numeric token found on NAS as canonical, or change the
Case/Site source relation. If the original complete Site+inspection
identity appears, the operation blocks as drift rather than promoting
to RESOLVED. Missing previously observed code-only evidence and
budget breaches also fail closed. Per-folder numeric tokens are kept
only in a new private mode-0600 report, never in public stdout or
GitHub. No file streams, recursive searching, extra years/roots, SQL
connection, SMB write, DB write or link creation.

The diagnostic's actual result remains **NOT VERIFIED** until its
exact-head CI succeeds and VM operator runs the bounded audit.
DDK–GxP certificate links remain **NOT_APPROVED**.

## One code-only Inspection Case/year marker classification — VM VERIFIED (14 Oct 2026)

On the exact-HEAD, CI-passed read-only VM audit, the protected
three-Case/four-year metadata report was validated; exactly one previously
`INSPECTION_CODE_ONLY` Case/year was selected from that immutable
source-bound population. The configured Inspection SMB root was
metadata-accessible. The diagnostic enumerated exactly one known source-year
root with 130 direct entries, identifying exactly one immediate directory
containing that inspection-code token. Its site-marker category was
`OTHER_NUMERIC_ID_TOKEN = 1`. All other marker-shape categories were zero.
The new source-bound private JSON was created as owner `gxp`, mode `0600`.
No database or NAS write, binary read, new linkage or resolver fallback
was performed.

Interpretation is strictly observational: a directory matching the
inspection-code token carries one numeric `(ID-n)` marker **different
from the Case's independently recorded source Site ID**. The observed
number has not been shown to be the legally correct Case owner,
and may represent a folder naming/legacy context discrepancy or a
different Site. Never replace the source Site ID, infer a canonical
parent, bind this directory, or repair the Case via a downstream
fallback. All three originating Cases remain unresolved by the
existing exact-source resolver (3/6 `NOT_FOUND`), and the business
eligibility GxP links remain `NOT_APPROVED`.

Next owner-level audit, if pursued, must be a *local, read-only
identity crosswalk* between the observed numeric marker held only in
the protected report and original `db.cso`/`db.ktra` source identities,
including Case inspection code and provenance. Require immutable Case
population / source hashes and distinct Site identity. First classify
whether the observed ID is a valid different source Site, absent, or
ambiguous. Keep both numbers and names private; only show aggregate
outcomes. No broader NAS scanning, alternate years/roots, automated
source rewrite or canonical link creation.

## Source-bound inspection code / alternate numeric Site crosswalk (14 Oct 2026)

The exact-HEAD, CI-passed, live metadata-only audit of one
`INSPECTION_CODE_ONLY` Case/year found one directory carrying
`OTHER_NUMERIC_ID_TOKEN = 1`, on a known source year root with 130
metadata entries. The private mode-0600 report retains the numeric
Site marker; public logs do not. This is *not* proof that the
directory belongs to the originating Case.

`tools.audit_ddk_gxp_inspection_site_crosswalk_readonly` now offers
a **pure source-lineage gate** for the protected original dossier,
queue, source-readiness report, six-Case/nine-year SMB transition,
four-year missing-Case metadata report and one code-only marker report.
It requires exactly one physically observed *different* numeric Site
token and verifies protected report SHA links and original Case/year
ownership before the number is ever used in a database comparison.

Its second owner stage uses only a guarded REPEATABLE READ / READ ONLY
transaction in `gxp_legacy_rehearsal`. It re-runs the existing
`profile_storage_lookup_inputs` against the complete previously
protected readiness document, then checks the originating canonical
Case, immutable `db.ktra` anchor row/hash and original imported Site.
The observed number is compared to the separately imported
`Site.legacy_site_id` directory and exact `Case.legacy_inspection_code`
matches, with a bounded collision count. Optional same-Company
metadata is **non-adjudicative**. Site/Case identities, observed
numeric tokens, and any linked canonical UUIDs stay in private
mode-0600 evidence; stdout may report only classes/counts.

**Evidence distinction:** imported `Site` rows are projections of
`db.cso`, and the protected `db.ktra` anchor is imported source
lineage; neither is a fresh, independent read of the original Excel
workbook. Even if the observed number corresponds to a different
imported Site or another Case using the same code, the result is
`NOT_APPROVED`. Genuine physical `db.cso`/`db.ktra` provenance
would require separately authorized, independently verified source
workbook evidence. No Site owner remap, folder fallback, DB/NAS write,
certificate link or deployment is allowed.

Live read-only crosswalk **NOT VERIFIED** pending exact-HEAD CI and
VM execution. The existing Case (3/6 NOT_FOUND) and DDK source
review populations remain unchanged.


## Imported Site crosswalk VM result and original workbook evidence gate (14 Oct 2026)

The exact-head, CI-passed, read-only VM crosswalk at
`1ca6f6a855e9efdb25bab714b55971c0474a5ff7`
verified the entire protected six-Case / nine-source-year lineage, one
`OTHER_NUMERIC_ID_TOKEN` observation and the immutable imported
`db.ktra` Case anchor under a REPEATABLE READ / READ ONLY
`gxp_legacy_rehearsal` transaction. The new report was generated under
`gxp`, private mode 0600. All postchecks PASS.

- `OBSERVED_ID_EXISTS_AS_DIFFERENT_IMPORTED_SITE`
- `MATCHING_INSPECTION_CODE_CASE_COUNT = 1`
- `OTHER_CASE_WITH_SAME_CODE_COUNT = 0`
- `OTHER_CASE_WITH_OBSERVED_SITE_AND_SAME_CODE_COUNT = 0`
- `OBSERVED_SITE_SAME_COMPANY_AS_SOURCE = true`
- `OBSERVED_ID_PHYSICALLY_VERIFIED_IN_DB_CSO = false`
- `SOURCE_CASE_PHYSICALLY_REVERIFIED_IN_DB_KTRA = false`

Thus the observed folder's alternate numeric Site token matches one
*other imported Site* owned by the same imported Company. It is not a
second canonical Case with the inspection code and not evidence that
the Case was attached to the wrong original Site. The original physical
workbook cells are the first missing independent source evidence.

The targeted witness owner
`tools.audit_ddk_inspection_physical_source_readonly`
reads exactly three physical source identities from the accepted
`Danh sách Kiểm tra GPs.xlsb` using isolated Windows Excel COM:
both `db.cso.ID` Site rows with `ID Cty`, and the one original
`db.ktra.ID` row with `ID CƠ SỞ` and `LOẠI KT`.
All identity cells must be literal (not formulas), header columns
unique, and the workbook SHA-256 must equal the approved source hash
before and after reading. Macros disabled, links not updated, Excel
opened ReadOnly. The request is generated separately from protected VM
report evidence + a guarded read-only Case/Company row; it contains
private source identity and row coordinates and must never be committed
or pasted into chat. The generated public result gives only equality
flags, no Case/Site ID, path, name or company identifier.

This method can establish whether the **accepted physical source
version** gives the same owning Site as the imported Case. It cannot
alone establish why a Synology folder was named for another Site,
whether it belongs legally to the Case, or whether a newer workbook
version supersedes the accepted one. In all outcomes,
`approval_status=NOT_APPROVED`; no Case mutation, directory fallback,
renaming, DB/NAS writing, canonical link or deployment.

## Accepted physical workbook Case/Site witness — verified 14 Oct 2026

The user supplied the private physical-source-request JSON generated by the
guarded VM (its SHA-256 matches the previously printed request fingerprint),
and the original legacy .xlsb bytes. The workbook SHA-256 exactly matches the
previously accepted source workbook fingerprint. Source cells were read
directly from the physical XLSB BIFF12 records with a bounded read-only
decoder, not inferred from the imported PostgreSQL tables.

One source-bound originating Inspection Case was verified using its
original db.ktra worksheet/row and source Case ID; its literal GxP
classification and physical ID CƠ SỞ exactly match the imported Case.
The generated inspection-code contract agrees. Both expected Site IDs
appear independently as unique literal physical db.cso.ID cells. Both
physical ID Cty references match the same original Company, consistent
with the imported projection. Source and alternate Site names and addresses
are DIFFERENT in the physical workbook. The relevant ID, Company and GxP
cells are numeric or shared-string BIFF12 records, rather than formula-cell
records. No source cells were changed.

**Established cause of the resolver's NOT_FOUND for this observation:** the
Inspection-code-only NAS directory name contains a Site numeric token
for a DIFFERENT source Site of the SAME Company, not the Site recorded
on the physical db.ktra Case row. This is a folder-name-to-source-identity
mismatch. The original Case-to-Site importer relationship is CONFIRMED
correct for this one examined Case; do not rewrite it or introduce
an alternate-Site fallback.

Limits: the XLSB record check is not a Windows Excel COM runtime or
macro/linked-workbook execution. This audit does not prove whether the
physical folder's contents legally belong to that Case, how/when it was
named, or its historical custodianship. Three originating Cases remain
NOT_FOUND under the unchanged exact source identity matcher; other
zero-token observations were not physically matched. DDK-to-GxP Certificate
link approval is a separate source and legal-eligibility question and
remains NOT_APPROVED. No DB/NAS write, migration, deployment, link creation
or Production owner reassignment.

## Mismatched Inspection folder: direct-child SMB metadata witness (14 Oct 2026)

The accepted physical db.ktra workbook source and imported canonical Case
agree on the original Site. A SINGLE direct child of an original source-year
inspection root carries the matching inspection code but a DIFFERENT Site
number; the original and alternate Sites are distinct and share one physical
db.cso Company owner. No site/case/company identifiers or actual NAS paths
are recorded in this GitHub document; those remain in prior mode-0600
private VM evidence.

The separate generic, bounded, metadata-only owner
tools/audit_ddk_inspection_folder_mismatch_metadata_readonly.py
checks the original protected source chain, unique marker evidence,
physical-source request SHA and imported projection crosswalk. It scans
at most 3,000 direct entries in exactly one original source-year root,
re-identifies the UNIQUE code-and-alternate-Site folder, then checks
up to 1,000 of its immediate entries only.

Real filenames, root leaf and extensions stay ONLY in mode-0600 private
report. Public logs show file/directory and token-presence counts.
No binary content read, subdirectory descent, other root/year,
database query or NAS/database write is allowed.

This witnesses metadata structure ONLY; it does not verify legal Case
ownership of any document. A filename containing the inspection code
does not authorize changing the source Site or binding that folder.
No Case remap, identity fallback, canonical Certificate or DDK link,
migration or runtime deployment is approved. Three source-bound Cases
remain unresolved by the exact resolver.

## Verified direct-child metadata in one mismatched Inspection folder (14 Oct 2026)

VM operator executed the exact-head, CI-passed guarded read-only script
for the previously sourced code-only Inspection folder. All source-chain,
accepted workbook hash, alternate imported Site and permission checks PASS.
The source year root contains 130 metadata entries, with one uniquely
matching inspection-code directory. That directory contains exactly **41
direct children: 40 files and one child directory**. None of these 41
names contains the original Case inspection-code token, original Site
token or alternate Site token. The protected detailed report was created
by gxp, mode 0600. There were no database or NAS writes; binary contents
and the child subdirectory were not entered.

Interpretation: the exact token-based Case resolver still produces
NOT_FOUND because the parent directory's alternate Site token conflicts
with the physical db.ktra Case Site. The presence of 40 immediate files
shows an actual file population at this one location; neither their names
nor the parent directory's alternate token proves that those files are
Case-specific evidence or that they belong to the original Case. The
separate child directory also has unexamined contents. Do not claim
full archival absence or legal Case ownership.

**Next bounded step:** classify only the already-protected 40 direct
file-name suffixes and 1 directory entry in the existing report;
no renewed SMB access or recursion. Use aggregated extension categories
to determine whether source-attested document/chain-of-custody inspection
could be useful. Never auto-approve a Case folder, relax source Site
matching, copy or rename files, update PostgreSQL, or change DDK↔GxP
Certificate links. The legal/business status stays NOT_APPROVED.

## Verified file-type split and bounded independent-content review manifest (14 Oct 2026)

The VM operator checked the existing owner-gxp, mode-0600 direct-child
metadata JSON and its original source-chain SHA-256. The metadata
contains 41 direct entries: **24 PDF, 15 text documents, and 1 other
extension** (40 files plus one directory). No child name contains the
inspection-code token or either Site marker. The source directory,
Site/Case ownership and downstream DDK↔Certificate link decisions
are unchanged. No DB, NAS or binary access was performed in this
file-type classification run.

No further reclassification of these 40 filenames can independently
prove content provenance. The next gate is *document-content evidence*
for the exactly one mismatched folder, not another search for a
different Site, year or root. Before any binary read, use
tools/triage_ddk_inspection_private_document_candidates.py to select
a maximum of three PDF and two Word-format files from the original
**already protected** direct-child metadata report. The selection is
deterministic with generic document-role filename hints; these hints
are solely prioritization, never Case matching or link authorization.
Unknown filename roles may be sampled without any positive identity
claim. No NAS or DB connection occurs in this manifest step.

Store the selected filename list privately with mode 0600. Subsequent
content examination must be separately bounded to exactly the selected
files, refuse changed folder identity, and report only the presence
of independent Case/Site evidence; private document contents must
not enter stdout, GitHub, history comments or public tests.
Unparsed scanned PDFs or legacy binary Word files remain inconclusive,
NOT negative evidence. An accessible file and matching free text
still do not establish authoritative custody or legal Case ownership.
No production resolver fallback, NAS rename, Case remap or canonical
DDK/GxP link may result automatically.

All 3 originating Cases missing an exact matching Inspection folder
remain source-scoped NOT_FOUND. The DDK↔GxP exception review remains
separate and NOT_APPROVED.
