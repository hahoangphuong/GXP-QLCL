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
