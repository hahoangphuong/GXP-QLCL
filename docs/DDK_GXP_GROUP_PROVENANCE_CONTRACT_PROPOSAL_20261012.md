# ĐĐK source GxP group provenance — proposed domain contract

**Status: REVIEW PROPOSAL / NOT APPROVED — 12 October 2026.**
This is a design and a read-only evidence contract, **not** an approved
database migration, canonical link assignment, production import rule,
legacy workbook rewrite, UI action, or rollout authorization.

## Verified physical workbook boundary

The original `Danh sách Kiểm tra GPs.xlsb` has SHA-256
`c12537ea5a5c9f470e42fb5bdbe214f36983e310fceac7c560ad38885209fe3d`.
`db.dkkd` has 830 original rows, of which exactly 50 are already reviewed
confirmed-blanked deletions in the 14 August 2026 contract; the effective
business-source population is therefore 780 DDK rows. The former flattened V1
snapshot cannot recover the four physical `ID CC` columns and is prohibited
as a source of new GxP–ĐĐK link assertions.

| Explicit row-3 group heading | ID CC | Scope | Standard | Business activity |
|---|---|---|---|---|
| GMP | O | P | Q | R |
| GLP | S | T | U | V |
| GSP | W | X | Y | Z |
| GDP | AA | AB | AC | AD |

Row 4 contains four identically named four-field groups. Their source data
must be keyed by **physical column** and **group heading**, not by the
repeated header name or assumed ordinal/frequency. There are 748 nonempty
ID-CC cells but 861 semicolon-delimited GxP ID tokens (851 GMP, 9 GLP, 1
GSP, 0 GDP). All 861 source tokens resolve to exactly one matching-type raw
`db.cc` identity. A token in a source group is evidence, not a canonical
link permission.

**Source conservation:** 830 × 4 groups × 4 fields = 13,280 original source
cell positions. At least 25 groups have companion fields but no ID CC (GMP
15, GLP 2, GSP 2, GDP 6). GDP's six activity fields have no GDP certificate
identifier. They must remain independently queryable as source observations.

## Current canonical model is insufficient for a lossless mapping

Current `backend/app/db/models/phase1.py` models:

- `BusinessEligibilityCertificate`: one `legacy_dkkd_id` with one
  `site_id` and `company_id` anchor and legacy replacement pointers.
  The pointers alone do not establish actual `BusinessEligibilityVersion`
  history or permit reparenting of another DDK issuance.
- `BusinessEligibilityVersion`: one shared `business_activity_text`;
  currently the importer creates `version_no=1` for each DDK row.
  It has no group-specific scope, standard, business activity or source
  physical column provenance.
- `BusinessEligibilityCertificateLink`: FK from one DDK version to one
  `Certificate` UUID, with `link_role`, but no source GxP group, raw token,
  physical origin, independent approval evidence or linked
  `CertificateVersion`. A global `certificate_id` link must not be
  silently interpreted as one specific historical certificate version.
- Existing `CertificateVersionSiteCoverage` and `CaseSiteCoverage` remain
  **proposals**, not authorized owner relations. Repeated GxP IDs across DDK
  rows are observations and not by themselves an anomaly or proof of
  version replacement.

The current importer path that iterates over
`normalize_row(...).linked_certificate_ids` is the **wrong owner for four
group source reconstruction**. Its legacy/default behavior remains unchanged
pending approval and a reviewed migration plan; do not hide source-group
data loss with a post-import rescue.

## Proposed additive owners (not implemented)

### 1. BusinessEligibilityGxpSourceGroup

An **immutable import provenance snapshot**, conceptually keyed by
`(source_workbook_sha256, db.dkkd physical_row_number, source_group)`,
with independent canonical owner association only after reviewed DDK
identity/Version mapping. Stores:

- `source_workbook_sha256`, `sheet_name=db.dkkd`,
  `source_row_number`, `legacy_dkkd_id_raw`;
- `source_group`: explicit original row-3 `GMP|GLP|GSP|GDP` label
  and the source label/column provenance;
- all four **raw** fields and their physical column ordinals:
  `id_cc`, `certificate_scope`, `applicable_standard`,
  `business_activity`;
- immutable field SHA-256 fingerprints, preservation status, and approved
  exclusion provenance where applicable (no source-row erasure).

A missing `id_cc` leaves other three source fields intact.
Duplicate historical DDK source rows are never conflated by
certificate number, physical site, first/last header, or scope text.

### 2. BusinessEligibilityGxpReferenceEvidence

Zero-to-many **source FK candidate observations** belonging to a group,
conceptually unique on source workbook + Excel row + ID CC column +
**token index** (not certificate number). Retains original whole cell,
token index, raw token, optional parsed legacy `db.cc.ID`, type match,
Site/Company evidence, reverse FK observation, and review disposition.
It is not a canonical relationship and may remain unresolved or rejected.
The approved canonical `BusinessEligibilityCertificateLink` would need
an explicit source-evidence owner and independent version/coverage
adjudication before any future backfill. Duplicate target IDs in different
DDK rows must not be collapsed.

### 3. Review and migration ownership

Decisions should be recorded independently with reviewer, timestamp,
decision reason, primary document references, expected-before/after FK
identities, explicit source SHA and target database revision. A
`SOURCE_OBSERVED_NOT_APPROVED` record is not a signed approval. Source
link evidence, physical Site certification coverage, regulatory certificate
identity, DDK issuance history and canonical ProductionLine UUID are
different relations and must not be inferred from each other.

## Implemented owner-only read-only review manifest

`tools/ddk_group_evidence_review.py` consumes the completed V3 audit JSON,
optionally the *already approved* confirmed-blanked contract, and creates an
independently checkable manifest. It validates source-workbook identity,
exact row/column/group field ownership, 4×4 physical field conservation,
unaltered semicolon token order, candidate/reference count, and
source exclusion correspondence. It reports:

- `SOURCE_OBSERVED_NOT_APPROVED`;
- `EMPTY_SOURCE_GROUP`;
- `SOURCE_REVIEW_REQUIRED` (including companion-only group, cross-Site,
  source type, Company ownership, or conflicting reverse-FK evidence);
- `CONFIRMED_BLANKED_SOURCE_ROW` when bound to the existing owner-approved
  exclusion contract.

All records retain `approval_status=NOT_APPROVED`. The read-only
manifest preserves **all four original Excel Value2 string values, including\nleading/trailing whitespace and line breaks, without applying shared\n`safe_text()` trimming**
alongside original physical column ordinals, field labels and individual
SHA-256 checksums; a single whole-group checksum also binds their order.
This avoids forcing reviewers to reconstruct critical GMP/GLP/GSP/GDP
scope, standard and business-activity text from a separate intermediate
artifact. The correction is made at the **original db.dkkd COM extraction
owner**, overriding the previously trimmed grouped values in the source
snapshot; the shared normalizer and importer are unchanged. For numeric
Excel Value2 cells, the existing integer-text conversion is retained, so
this is *Value2 representation preservation*, **not** proof of original
Excel display formatting or original formula text. Token parsing may trim
each candidate ID while retaining the unchanged whole ID CC source cell.
Whitespace-only ID CC cells are preserved and explicitly review-flagged,
never promoted into invented Certificate IDs. A missing ID CC is never interpreted as permission to drop a
nonblank companion. Even a `SAME_SITE` observation stays
`SOURCE_REVIEW_REQUIRED` if Certificate type comparison or Company owner
evidence is not verified. No source observation becomes an approved
canonical link.

The CLI fingerprints the **exact bytes** of the V3 audit JSON and, when
provided, the owner-approved confirmed-blanked exclusions JSON in
`input_artifact_sha256`. These are separate from the **original binary
workbook SHA-256**, which is retained in `source_workbook_sha256`. The JSON
fingerprints permit repeatable artifact-to-artifact comparisons but do not
assert that the upstream workbook extraction or formula results have been
independently revalidated.

The CLI **will not overwrite** the original V3 audit JSON, the approved
confirmed-blanked contract, or an existing prior review manifest. A new
output path is required for each sealed review attempt. Manifest files
can contain confidential original legacy records and are written only
to the operator's local output path, **not committed to GitHub**.

A source SHA-256 inside an input report cannot independently prove that
an edited JSON is still identical to the binary workbook; the original
read-only Excel extraction and Windows COM/HasFormula verification remain
necessary provenance gates.

The manifest emits no approved links, no version/UUID resolution, and no SQL.
A mismatched/missing source field, token or approval contract fails closed.
A V1 flattened snapshot and partial source-header evidence cannot be used.

Owner command after a full **read-only Windows Excel V3 audit**:

```powershell
py -3 -m tools.ddk_group_evidence_review `
  --audit-json "D:\GXP-DDK-IDCC-REVIEW\ddk_idcc_physical_source_review.json" `
  --approved-exclusions-json "D:\GXP-QLCL\artifacts\phase3q\confirmed_blanked_rows.json" `
  --output "D:\GXP-DDK-IDCC-REVIEW\ddk_group_review_manifest.json"
```

The `--approved-exclusions-json` file is optional to build a
non-adjudicated manifest, but omitting it must be clearly reported as
`NOT_CHECKED`; never claim that the source population has been reviewed
without the signed exclusions.

## Necessary approval gates before schema or importer changes

1. Resolve the semantic meaning of one physical DDK row versus a
   `BusinessEligibilityVersion` (current importer creates one version per
   source DDK identity; this is **not** automatically a complete issuance
   history), including legacy latest/replaced-by pointers.
2. Decide whether grouped fields are DDK-version historical facts versus
   present-day facility metadata. Preserve the original unchanged values
   regardless of projections.
3. Review the 5 cross-Site source candidate occurrences and DDK 626 Company
   inconsistency separately; never treat shared company or scope as coverage
   approval. Honor the existing separate multi-Site Case/CertificateVersion
   proposal before relaxing Search HTTP 409 behavior.
4. Approve an exact version + GxP group + source-token-to-canonical-certificate
   ownership mapping, including separate treatment of missing GDP ID and
   companion-only scopes. Never create a GDP Certificate from six activities.
5. Only after signed approval, prepare an additive reversible schema migration,
   dry-run on disposable PostgreSQL, explicit rehearsal authorization,
   backup/rollback and API integration tests. Keep PR #3 Codex UI independent.

**No writes/merges/deploys on this proposal.** Green CI alone does not
validate Excel COM formulas, skipped PostgreSQL integration or the active
Search Facilities HTTP 409.


## Replay gate: independent XLSB exports against original read-only Excel COM V3

Added on 12 October 2026: `tools/reconcile_ddk_source_artifacts.py`.
This tool reconciles the already-created `GXP_DDK_GROUPED_SOURCE_EVIDENCE_V1`
and `GXP_DDK_XLSB_INDEPENDENT_SOURCE_ANALYSIS_V1` exports against the **actual
binary workbook SHA-256**, and **optionally** against freshly extracted
`GXP_DDK_IDCC_PHYSICAL_REVIEW_V3`. The prior exports were produced by the
same underlying XLSB-reading library and are **not** independent proof of
different extraction engines or Excel formula status. All comparisons are
read-only. A mismatch raises `MissingPhysicalEvidence`, exits nonzero and
does not create a purported PASS report.

A real Excel COM replay must record, not merely assume, the following
source checks in V3 header evidence:

- `source_reader=MICROSOFT_EXCEL_COM_VALUE2_READONLY`;
- `source_read_only=true`;
- exactly four original physical ID CC column formula checks,
  each `has_formula=false` using `Excel.Range.HasFormula`.

An old V3 snapshot lacking these checks is **not** a COM validation PASS.
The group field strings may contain source whitespace that the earlier XLSB
export trimmed. The cross-reader comparison tolerates only that
known leading/trailing normalization; mismatches in actual group contents,
DDK row identity, GxP headings, 16 group field coordinates or token
multiset remain **hard failures**. A complete review manifest is created
separately only *after* this source check.

For an owner-side Windows replay, use a separate evidence output directory
for each run. From the latest backend PR #7 worktree:

```powershell
py -3 -m tools.audit_ddk_idcc_physical `
  --workbook "D:\GXP-QLCL\legacy\Danh sách Kiểm tra GPs.xlsb" `
  --expected-workbook-sha256 "c12537ea5a5c9f470e42fb5bdbe214f36983e310fceac7c560ad38885209fe3d" `
  --out-dir "D:\GXP-DDK-IDCC-REPLAY-20261012"

py -3 -m tools.reconcile_ddk_source_artifacts `
  --workbook "D:\GXP-QLCL\legacy\Danh sách Kiểm tra GPs.xlsb" `
  --groups-json "D:\GXP-DDK-IDCC-EVIDENCE\gxp_ddk_grouped_source_projection_20261012.json" `
  --references-json "D:\GXP-DDK-IDCC-EVIDENCE\gxp_ddk_idcc_workbook_source_analysis.json" `
  --audit-v3-json "D:\GXP-DDK-IDCC-REPLAY-20261012\ddk_idcc_physical_source_review.json" `
  --output "D:\GXP-DDK-IDCC-REPLAY-20261012\ddk_source_reconciliation.json"

py -3 -m tools.ddk_group_evidence_review `
  --audit-json "D:\GXP-DDK-IDCC-REPLAY-20261012\ddk_idcc_physical_source_review.json" `
  --approved-exclusions-json "artifacts\phase3q\confirmed_blanked_rows.json" `
  --output "D:\GXP-DDK-IDCC-REPLAY-20261012\ddk_group_review_manifest.json"
```

Paths to the two earlier independent-export JSONs are examples; their bytes
must come from the original owner-supplied evidence, not from a recomputed
flattened V1 snapshot. The `--expected-workbook-sha256` pin is tied only
to the exact verified original workbook; new legitimate source workbooks
require separate independent identity evidence. Each output is created
**exclusively** and cannot overwrite the original source or previous report.

Expected result labels (not asserted until executed):
`PARTIAL_INDEPENDENT_EXPORTS_ONLY` without V3,
`COM_V3_AND_INDEPENDENT_EXPORTS_CONSISTENT` only after strict V3
comparison. Passing a source comparison does **not** approve business
linkage, history, multi-Site coverage, import, SQL migration or production
cutover. The current environment lacks Microsoft Excel COM; the original
Windows-specific `HasFormula` replay cannot be represented as completed
by this repository-level proposal or by GitHub CI.
