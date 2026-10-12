# Certificate–Case Source Integrity: Evidence and Migration Gate

**Status:** source anomaly confirmed, runtime remediation **not approved**, new strict import preflight opt-in only.

## Source provenance

- Workbook: `Danh sách Kiểm tra GPs.xlsb`
- Owner-side read-only audit: 2026-10-11 15:19 Asia/Bangkok
- Workbook SHA-256: `c12537ea5a5c9f470e42fb5bdbe214f36983e310fceac7c560ad38885209fe3d`
- The evidence export was produced in Excel read-only mode. Raw workbook contents and private local paths are **not** committed here.
- GitHub Phase 3C snapshot: `artifacts/phase3c/legacy_snapshot.json`, derived from earlier export; exact line-level values independently corroborated by this owner-side workbook audit.

## Population reconciliation

| Classification | Raw db.cc snapshot | Effective import after previously approved confirmed-blanked exclusions |
| --- | ---: | ---: |
| All source rows | 1,628 | 1,601 |
| Case reference absent (administrative) | 169 | 143 |
| Site + GxP matching linked Case | 1,455 | 1,455 |
| Cross-Site link, GxP matching | 3 | 3 |
| Incomplete Site context | 1 | 0 |
| Confirmed-blanked exclusions | — | 27 |

The one incomplete context in the raw snapshot is a previously excluded legacy placeholder row, not a fourth imported cross-Site link. Exclusions are taken **only** from the already reviewed `artifacts/phase3q/confirmed_blanked_rows.json` contract; the source auditor does not infer exclusions from mismatches.

## Exact cross-source findings

| Certificate db.cc | Certificate Site | Referenced Case db.ktra | Case Site | Reverse evidence | Decision |
| --- | --- | --- | --- | --- | --- |
| 376 | 73 (USA-NIC) | 378 | 72 (Hasan-Dermapharm) | Case 380 belongs to Site 73 and explicitly references Certificate 376 with the same certificate number `119/GCN-QLD` | Strong alternate-originating-Case candidate, **review only** |
| 1037 | 46 (Domesco) | 1023 | 298 (Domesco production center) | Case 1023 explicitly references Certificate 1037 and number `200/GCN-QLD` | Cross-Site context remains unresolved |
| 1180 | 46 (Domesco) | 1023 | 298 | No single reverse `ID CC GPs` reference to 1180; scope mentions both Cơ sở 1 and Cơ sở 2 | Cross-Site context remains unresolved |

### Additional literal source corroboration for Certificate 376

Read-only comparison of Phase-3C `db.cc`/ `db.ktra` source rows on 11 October 2026:

- Certificate 376, issued **12/03/2018**, has `ID ĐỢT KTRA=378`. Linked Case 378 is for **Hasan-Dermapharm, Site 72**, with inspection period **04–05/03/2008**; its inspected scope differs from Certificate 376.
- Case 380, for **USA-NIC, Site 73**, has inspection period **07–08/12/2017** and the reverse reference `ID CC GPs=376`, with the same certificate number `119/GCN-QLD`.
- Crucially, after removing outer whitespace only (no rewriting or language normalization), the **entire** Certificate 376 `PHẠM VI CHỨNG NHẬN` text is exactly equal to Case 380 `PHẠM VI KIỂM TRA` text. It is **not** exactly equal to the inspection scope of Case 378.
- This combines explicit reverse reference, Site/GxP correspondence, matching certificate number, scope-text identity, and plausible inspection-to-issuance chronology. **It is strong evidence but not sufficient authorization** to change `Certificate.case_id`; primary issuance documentation and formal sign-off remain the gate.

**Independent public-register corroboration:** The Drug Administration of Vietnam's 17 January 2019 WHO-GMP register lists USA-NIC at the same Tân Tạo Site, certificate **119/GCN-QLD**, issue **12/03/2018**, expiry **12/03/2021**, with the matching drug-form scope. The government-published 30 November 2019 and 5 June 2020 domestic GMP registers reproduce the same Site and certificate number. These are **certificate attribution** evidence; they **do not identify the internal originating Case** and cannot independently adjudicate 380 vs 378. At this review checkpoint, those PDF statements were cross-checked through their indexed text listings; the PDF full-page visual review was not completed due source-fetch timeout, so the primary paper issuance document remains required.

- Official 17 January 2019: https://dav.gov.vn/upload_images/files/DS_cty_trong_nuoc_dat_GMP-WHO%20%2817_01_2019%29.pdf
- Official 30 November 2019: https://dav.gov.vn/upload_images/files/Danh%20s%C3%A1ch%20c%C3%A1c%20c%C3%B4ng%20ty%20trong%20n%C6%B0%E1%BB%9Bc%20%C4%91%E1%BA%A1t%20ti%C3%AAu%20chu%E1%BA%A9n%20GMP%20%2830_11_2019%29.pdf
- Official 5 June 2020: https://dav.gov.vn/upload_images/files/Danh%20s%C3%A1ch%20c%C3%A1c%20c%C3%B4ng%20ty%20trong%20n%C6%B0%E1%BB%9Bc%20%C4%91%E1%BA%A1t%20ti%C3%AAu%20chu%E1%BA%A9n%20GMP%20%2805_06_2020%29.pdf

The generic read-only source auditor now records `same_nonblank_scope_text` and raw inspection-period evidence for **all** reverse-source Case references associated with anomalous Certificates. This is exact lexical comparison, **not** a Case-selection algorithm: ambiguous or multiple matching reverse references remain review-only, with `remediation_authorized=false`.

Both Domesco Sites have Company legacy ID 37 but are **distinct facilities with distinct addresses**. Shared company ownership and textual scope headings are not sufficient to reassign Site or Case. Reverse evidence is diagnostic only and never authorizes a write.

## Owner/causality

- **Source level:** workbook `db.cc.ID ĐỢT KTRA` contains all three cross-Site relationships; not introduced by a snapshot parser or a runtime read.
- **Importer defect:** `backend/app/domain/phase2_import.py` resolves Case and Site separately and did not enforce their shared Site/GxP invariant before persisting.
- **Read failure:** `CatalogReadService._search_facilities_by_production_line` globally validates all linked Cases; known invalid imported historical rows produce HTTP 409 for search.
- **Domain decision:** ADR 0004 permits missing Case for administrative certificates. B6F Certificate identity contract treats `Certificate.case_id` as the immutable originating Case when present. Neither rule authorizes changing `case_id` because it is inconvenient for search.

## Implemented diagnostic and strict import preflight

- `backend/app/domain/legacy_certificate_case_source_audit.py`: pure, read-only classification, keeping both raw and effective populations and explicit reverse evidence; never chooses a replacement.
- `tools/audit_legacy_certificate_case_sources.py`: CLI that reads snapshot plus the approved blanked-row contract. `--strict` returns status code 2 while effective anomalies remain.
- `ImportExecutionOptions(strict_certificate_case_source_links=True)`: **opt-in** strict gate at `import_snapshot()` before schema creation, reset or database mutation. Fails closed with a structured `CertificateCaseSourceIntegrityError` report for all effective unresolved links. The workbook entrypoint can accept the same option.
- Source-audit parity safeguard: standalone `--strict` also returns exit code 2 for duplicate source row identities **in any sheet** (`source_identity_anomalies`), even if no Certificate references that source row or a duplicate is in the confirmed-blanked exclusion contract. The `db.cc` classification remains `DUPLICATE_CERTIFICATE_SOURCE_ROW_KEY`; other sheets use `DUPLICATE_SOURCE_ROW_KEY` with explicit `source_sheet`, row key and occurrences. This matches the importer's pre-schema, all-sheet `_validate_snapshot_source_keys` invariant without altering Certificate link classifications, approved exclusions, or legacy import behavior. Source-only regression coverage includes duplicate `db.cty`, `db.cso`, `db.ktra` and `db.Tdoi` keys, plus importer pre-schema rejection.
- Source-parent importability safeguard (full snapshot only): additionally model the importer's source-only Company → Site → Case parent materialization. A matching `db.cc`/ `db.ktra` Site ID is not importable if its `db.cso` parent is missing or points to a missing `db.cty` Company. The audit now returns `source_parent_check_available`, `source_parent_anomalies` and `effective_parent_anomalies`. These are **separate** from regulatory link classifications; `--strict` and the opt-in importer preflight reject *effective* missing parents before schema creation. For a partial diagnostic snapshot without all four parent sheets, `source_parent_check_available=false` explicitly means this check was not performed, not that the parent chain is sound; the non-strict CLI can still produce an exploratory report, but `--strict` returns exit code 2 rather than certifying incomplete input. This does not change the default importer behavior or apply any remediation overrides.
- Independently reconciled full snapshot: **27 raw source-parent anomalies** (26 Certificates with non-materializable Site source parents and one Certificate linked to a Case with non-materializable Site parent); **all 27 belong to the existing confirmed-blanked excluded source population**, yielding **zero effective parent anomalies**. In particular the 1,455 source-exact Case links have no additionally detected parent-importability break; the three unresolved cross-Site source links remain unchanged.
- Existing import default remains compatible with historical source until there is an **approved** disposition for the three conflicts. This is **not** a remediation, release, or authorization to cut over.
- Strict-preflight errors now report **both** unresolved Certificate–Case link anomalies and unimportable source-parent dependencies; parent-only failures no longer produce a misleading zero-blocker message.
- Runtime fail-closed regression: `tests/test_certificate_case_global_integrity_read_model.py` seeds a **non-current** historical Certificate with an invalid cross-Site linked Case and a separate legitimate administrative Certificate. Global facility search must still return HTTP 409 even when filtered to a different GxP or paginated; the offending Site's workspace and historical certificate detail also reject it. The unaffected Site's workspace remains independently readable. The SQL-valid-linked-Case predicate must exclude the invalid historical row while retaining the administrative one. This adds **tests only**; no search or workflow validation is relaxed.
- No changes were made to runtime Certificate–Case validation or to canonical ProductionLine UUID identity.

Local source-only verification command:

```bash
python -m tools.audit_legacy_certificate_case_sources \
  --snapshot artifacts/phase3c/legacy_snapshot.json \
  --output /tmp/gxp-certificate-case-audit.json --strict
```

Expected on current unremediated legacy source: exit code **2**, **three** effective anomalies, no database access. Avoid writing a report onto an existing approved evidence file.

## Independent published GMP documentation (11 October evidence expansion)

The cross-Site Domesco context is **not merely an ambiguous Excel label**:

- Published 20 October 2022 domestic GMP list, document page 13, row 49: one **200/GCN-QLD** certificate issued 20/04/2022 covering **two manufacturing Site addresses**, each with its own GMP scope:
  https://gmp.com.vn/images/upload_file/danh-sach-cac-cong-ty-trong-nuoc-dat-tieu-chuan-gmp-20_10_2022_1667265374.pdf
- Certificate **314/GCN-QLD** (15/05/2023), published by Domesco, names Site 1 and Site 2 in Part 1:
  https://www.domesco.com/pdf/GCN%20GMP%20-%20WHO%20%28dia%20chi%20moi%20346%20Nguyen%20Hue%29.1f1117ede5f0b54c599a0699cc7fb7f8.pdf
- Drug Administration of Vietnam's 20 January 2025 GMP list explicitly records **314/GCN-QLD replacing 200/GCN-QLD**, which provides independent regulatory evidence for a historical certificate relationship:
  https://dav.gov.vn/upload_images/files/Danh%20s%C3%A1ch%20c%C3%A1c%20c%C3%B4ng%20ty%20trong%20n%C6%B0%E1%BB%9Bc%20%C4%91%E1%BA%A1t%20ti%C3%AAu%20chu%E1%BA%A9n%20GMP%20%2820_01_2025%29.pdf
- The preserved `db.cc` source agrees with the address history: Certificate 1037's Site 1 is **66 Quốc lộ 30**, while Certificate 1180's Site 1 is **346 Nguyễn Huệ**. Both retain Site 2 at **Cần Lố**. The evidence does not establish whether Site 1 premises were moved, renumbered or otherwise redescribed.

**Proven:** the two certificates each encompass **two named manufacturing Site locations**, with explicit replacement lineage. **Not proven:** that inspection Case 1023 assessed both Sites, the exact canonical issuance-owner rules, or how each version's Site-specific certified scope must be stored. Certificate Site coverage and inspection Case Site coverage must remain distinct.

A separately reviewed future model can distinguish `Certificate` (regulatory issuance identity), immutable `CertificateVersion` and `CertificateVersionSiteCoverage` (version-specific certified physical Sites, source address and scope), from any independently evidenced `CaseSiteCoverage` (inspection coverage). The existing `CertificateRelationship` model provides a possible `REPLACED_BY` edge after explicit approval. None of this is authorization for a database write or alteration of the current Site equality check.

## Published inspection evidence for the originating Case

The Drug Administration of Vietnam's published 20 October 2022 **GxP assessment list** independently records Domesco on **15–16 January 2022**, covering **Site 1 at 66 Quốc lộ 30** and **Site 2 at Cần Lố**, with separately defined GMP inspection scope:
https://dav.gov.vn/upload_images/files/Danh%20s%C3%A1ch%20c%C3%A1c%20%C4%91%E1%BB%A3t%20%C4%91%C3%A1nh%20gi%C3%A1%20GxP%20%2820_10_2022%29.pdf

`db.ktra` Case 1023 independently records that same assessment date and two-site `PHẠM VI KIỂM TRA`, yet its structured `site_id` is only Site 298 and `ID CƠ SỞ 2` is blank. This is strong **cross-source corroboration of multisite inspection** and confirms a one-Site representation gap, though the publicly released document does not expose the application's internal Case ID 1023.

The newly corroborated domain distinction is:
- the **Case coverage** can contain multiple physical sites;
- a **CertificateVersion's certified coverage** can contain multiple sites, with differing per-Site activities;
- each regulatory **Certificate identity** remains independent; the 2023 document explicitly replaces the 2022 document;
- the stored single `site_id` for a Case/Certificate is legacy anchoring data, **not** proof that its regulatory scope excludes every other site.

The draft relational design is in `docs/CERTIFICATE_CASE_MULTISITE_MODEL_PROPOSAL_20261011.md`; no schema or runtime mutation is implied.

## Remaining business decisions and implementation gates

1. **Certificate 376:** verify original issuance provenance/case reference (candidate Case 380). An authorized remediation would need a sealed source+canonical-state plan, verified target rehearsal DB, backup, exact row assertions, transactional update, audit and rollback. Do not directly overwrite the historical `db.cc` source.
2. **Domesco 1037/1180:** both the certifications' multi-Site scope and the 2022 inspection's multi-Site scope are now corroborated. Confirm the internal Case-to-public-inspection mapping and Site 1 address lineage before applying reviewed CaseSiteCoverage / CertificateVersionSiteCoverage rows. Review the 66 Quốc lộ 30 versus 346 Nguyễn Huệ historical address relationship without synthesizing a Site-identity merge. The regulator-published replacement is a review candidate for the existing CertificateRelationship model, not an inferred automated write.
3. **Only after adjudication:** enforce the corrected import invariant by default for the future cutover, backfill or remediate the existing three canonical rows with approved plans, then execute integration tests and search/workspace smoke tests. Confirm canonical ProductionLine UUID preservation.
4. Do not deploy or mutate `gxp_legacy_rehearsal`, `gxp_qlcl`, or `gmpnn_ai` as part of this audit. Existing site filtering must not be weakened to turn HTTP 409 into an apparently successful search.

The current documented state remains **Search Facilities FAIL HTTP 409** until a separate, reviewed remediation release is proven in runtime.


## Strict preflight: excluded Certificate source-row drift (11 October follow-up)

A confirmed-blanked source-row key marks a business-deleted row that must not
silently become importable simply because its FK values are later populated.
The original import FK resolver checks materializable parents before recording
a confirmed-blanked missing-parent anomaly. Therefore a source row whose
Case (or administrative-null Case) and Site parents both resolve can otherwise
materialize despite remaining in the approved exclusion contract.

The read-only source auditor now reports `excluded_importable_certificate_rows`
separately from `effective_anomalies` and `effective_parent_anomalies`.
Standalone `--strict` and opt-in importer strict preflight reject such drift
before DB schema creation or write. Ordinary diagnostic CLI mode is unchanged,
and the legacy importer default is **not** modified by this opt-in safeguard.
This is not an authorization to resurrect blanked rows: any restoration must
follow the owner-approved resurrection/remediation process.

Independent review of the captured full Phase-3C snapshot and its 27 approved
`db.cc` confirmed-blanked keys found **0 importable excluded Certificates**.
The three unresolved effective cross-Site source links remain unchanged.


## Import-owner protection for default replay and all confirmed-blanked sheets (11 October)

A second audit identified that the default Phase-2 importer previously treated
`confirmed_blanked_rows.json` primarily as a missing-parent anomaly
classification. If a previously deleted row acquired resolvable FKs, its
FK resolver could return before classifying it as excluded; this was true
outside strict Certificate–Case audit mode and across source sheets, not only
`db.cc`.

`import_snapshot` now performs a **pre-schema, pre-reset source-materialization
check** across `db.cty`, `db.cso`, `db.ktra`, `db.cc`, `db.dkkd`,
`db.Tdoi` and `db.Tdoi2`. It follows the importer's existing required-FK
graph and explicit remediation overrides, without inferring missing parent
identities. A confirmed-blanked row with importable parents and **without
an exact, explicitly approved resurrection override** raises
`ConfirmedBlankedResurrectionError` before database mutation, even in
ordinary import mode. The existing approved-resurrection contract retains
ownership; it is validated before any schema creation or data reset.

A read-only comparison of the captured Phase-3C source with all 151
confirmed-blanked contract entries yielded **0 currently importable
excluded source rows**. No source content, owner approval, Certificate–Case
business association or database row was altered. The strict source audit's
three effective cross-Site Certificate links remain unresolved.


## Strict importer and owner-approved Certificate resurrection population

A further compatibility check found that strict import previously passed **all**
confirmed-blanked `db.cc` keys as effective exclusions to the standalone source
auditor even when the importer had an independently owner-approved, exact
resurrection override. The auditor then classified a legitimate importable
restored Certificate as `excluded_importable_certificate_rows`, making strict
import reject a source row that default import would lawfully materialize.

The importer now validates the existing owner-approved resurrection contract
**before** calculating strict effective exclusions. A Certificate with a
matching explicit approved override is included in the strict effective
source population, so its literal Case/Site/GxP relationship is checked
exactly like any other Certificate; a wrong Site or GxP still fails before
schema creation. Without an exact signed approval, the source remains
excluded and a newly importable deleted row is still rejected. The standalone
`--strict` CLI has no remediation authority and remains unchanged.

This is not source-FK repair by inference. Where a reviewed override itself
would change a missing Case/Site source FK, the literal source auditor may
still reject incomplete raw context, as a fail-closed limitation pending an
explicit, provenance-preserving applied-override audit contract. No approval
file, workbook, business row, schema or runtime Certificate link was edited.


## Read-only effective-FK projection for strictly reviewed restorations

A signed `confirmed_blanked_resurrections.json` override may restore a
previously blanked mandatory Site or Case FK. Strict import must inspect the
**effective** relationships Phase 2 would actually import, not reject the raw
missing FK merely because the owner supplied a validated restoration.

The existing pre-schema materialization walker now also constructs a copied,
normalized audit view and a field-level provenance trace for *actually used*
approved resurrection overrides. It follows parent-first source materialization,
including approved restored parent Case/Site rows, and uses the legacy import
rule: an existing, resolvable raw FK always wins over an override. A generic
override on an unapproved row cannot manufacture an acceptable strict source
relationship. The original snapshot is never modified.

In strict mode, a preview builds the effective audit view; the source auditor
checks its Site/GxP/Case invariants. If any approved FK replacement is used, an
error report retains both the original-source classifications and explicit
per-field `raw_fk_value`, `effective_fk_value`, `source_row_key` and
`approved_override_key`. The unchanged default-mode materialization guard
then enforces excluded-row drift and exact contract authorization before any
schema creation. Standalone read-only `--strict` continues to describe the
literal source and has no approval/override input.

This improvement does not repair Certificate 376 by inference: its original
Case 378 is a resolvable FK and cannot be remapped to candidate Case 380 by
an override. Site-mismatched or GxP-mismatched projected relationships still
fail before import. No historical source or database rows were changed.


## Blank administrative Certificate and signed Case resurrection mismatch

The importer treats a literally empty `db.cc.inspection_case_legacy_id_ref`
as an administrative Certificate: `_resolve_optional_legacy_fk` returns `None`
without consulting remediation overrides. A signed resurrection contract with
`case_legacy_id` for that same blank value could previously pass preflight
without applying the approved link, silently materializing the Certificate with
`case_id=NULL` instead.

The import-owner parent preflight now rejects this contradictory approved
override **before any schema creation or data reset**, in both ordinary and
strict import modes. It does not infer, insert or reassign a Case; formally
changing an administrative issuance basis needs a separately reviewed business
contract. A restoration that approves only the missing Site FK continues to
import an administrative Certificate with a null Case. Four targeted regression
cases cover both import modes, the schema-write boundary, raw-snapshot
immutability, and the permitted administrative Site repair.



## Literal legacy ID parsing: importer and audit parity (12 October)

The default Phase-2 FK resolver previously called `parse_int()` through a
floating-point conversion. A nonintegral source reference such as `100.5`
could consequently resolve to Case `100`, even though the standalone
Certificate–Case auditor correctly classified that same value as an
unparseable reference. Source identity collision checks could similarly
truncate malformed explicit source IDs.

The shared import-owner parser now accepts only non-negative integral
literals, including spreadsheet-rendered `100.0`, and refuses fractional,
scientific or prose values. The read-only auditor uses this same parser
rather than maintaining a separate lexical interpretation. Explicit,
nonblank nonintegral source IDs are rejected at the existing pre-schema
source-key guard across all seven source sheets; standalone audit reports
`INVALID_SOURCE_LEGACY_ID` in its existing source-identity anomaly channel,
which also makes CLI `--strict` fail. Missing IDs still use the established
Excel-row fallback and are not equated with malformed explicit IDs.

Regression coverage distinguishes invalid Case/Site FKs, accepted integral
literals, all seven source-ID sheets, source immutability and the no-schema
failure boundary. This hardening does not infer a replacement Case/Site,
change any signed business correction, or modify the three outstanding
Certificate–Case conflicts.


## Orphan resurrection approvals: independent confirmed-blanked ownership (12 October)

A further owner-contract audit identified a fail-open gap: an entry in
`confirmed_blanked_resurrections.json` could name an identity absent from the
independently reviewed `confirmed_blanked_rows.json`, yet the importer would
silently ignore that stale/mismatched signed entry and proceed. The resurrection
contract itself states that only previously confirmed-blanked rows can appear
in its approval list; the existing code checked matching applied overrides but
not the scope of *all* signed approvals when no override was supplied.

The owner pre-schema authorization guard now rejects any approval whose
`(source_sheet, source_row_key)` is not present in the independent blanked-row
contract, even with no remediation overrides. This raises
`ConfirmedBlankedContractError` without creating/resetting tables. Regression
covers an unrelated row key and an unrelated source sheet, each in normal and
strict importer modes; snapshot immutability and no-schema-write are asserted.
The currently checked-in resurrection contract has no approval rows, so this
change does not authorize or apply any business correction. The outstanding
three cross-Site Certificate links are unaffected.


## Fail-closed value fidelity for signed resurrection payloads (12 October)

Source-contract audit found two owner-side truncation paths. The approval loader
previously ignored malformed values when `approved_override` also contained a
valid numeric value. Independently, remediation equality normalized by dropping
malformed supplied fields, so a payload containing an unapproved invalid extra
field could appear to match the signed approval. Both were silently lossy and
were reached before any FK resolver could distinguish provenance.

The signed-approval loader now rejects any invalid numeric value instead of
authorizing a subset. The pre-schema remediation equality guard similarly
rejects the *whole* malformed submitted payload on a confirmed-blanked source
identity, preserving the exact signed scope. Regression uses fractional,
scientific, prose and null values across ordinary/strict modes, checks source
immutability and absence of schema writes, and retains valid literal decimal-zero
IDs. Other generic remediation behavior is unchanged. No Case/Site reassignment
or signed approval was introduced.


## Sheet-bound signed resurrection FK ownership (12 October)

The signed-approval loader previously accepted syntactically valid numeric
`approved_override` keys unrelated to the sheet's parent FK owner. This could
authorize a confirmed-blanked source row with already-resolving parents even
though the signed remediation did not name a relationship that the import
would resolve (for example, `case_legacy_id` on `db.cso`).

`SOURCE_PARENT_FK_REQUIREMENTS` is now the single ordered source of truth for
the Phase-2 parent-materialization graph and allowed signed-remediation keys.
The approval loader validates key ownership against this graph before checking
integer literals, rejecting unsupported keys with `ConfirmedBlankedContractError`
before schema creation. No business case, company, or document-specific
exception is introduced. Regression exercises six source sheets, ordinary and
strict import modes, source immutability and no-schema-write boundaries, and
a valid two-FK Certificate approval. Existing behavior remains: an approved
value identical to an already-resolving source FK confirms the current link,
but never silently replaces that link with a different parent. The checked-in
resurrection contract still contains no approved rows.


## Fail-closed execution of signed resurrection requests (12 October)

Owner audit distinguished **approval presence** from an actual submitted
restoration. The importer could previously accept a signed parent ID absent
from the effective parent population, silently use a different, already
resolving raw FK instead, and import the supposedly resurrected row; an
unmaterializable approved row could also be skipped without failing. Likewise
a requested signed restoration for a source row absent from the snapshot was
not detected at all.

At the existing pre-schema source-materialization owner, every expressly
submitted confirmed-blanked restoration must now match an actual snapshot row
and materialize, and each signed FK value must refer to an importable parent.
Only submitted requests are execution orders; a signed but unused approval
entry does not cause an import by itself. Existing already-resolving source
FK precedence remains unchanged for **importable** alternative approved IDs:
no Certificate/Case/Site relink or source rewrite occurs, and strict-source
classification remains independent. Tests cover normal/strict modes, a raw
resolved/missing FK, orphan requested rows, unused signed approvals, no-schema
writes and snapshot immutability. The production resurrection contract still
has zero approved entries; no business corrections were applied.


## Case ĐĐK attribution / independent rehearsal integrity check (12 October)

Code-level last-correct / first-incorrect boundary: `get_case_workspace`
correctly selects the related ĐĐK using its version-owned GxP basis links,
but then passed the *Case* `Site` and `Company` into the ĐĐK detail
serializer. The legacy importer can create a GxP–ĐĐK link by `ID CC`
without checking the two Site IDs. A cross-Site link therefore produced a
payload whose `site_id` and `company_id` belonged to the ĐĐK while its
displayed company, legal address, facility name and address belonged to
the unrelated Case. This is a read-model misattribution regardless of
whether any such row exists in rehearsal.

Case workspace now looks up each linked ĐĐK's own Site and Company for its
displayed fields, using the same certificate-owned identity already used
by the standalone ĐĐK detail endpoint. No source link is rewritten, filtered
out, relinked or promoted; no HTTP 409 or hidden client fallback is introduced.
Regression covers a deliberately cross-Site, cross-Company legacy-style link
and a same-Site baseline. A separate **read-only** SQL audit
(`scripts/audit_ddk_gxp_site_links_readonly.sql`) is available for
`gxp_legacy_rehearsal`; it was *not* executed against the VM here because
no VM SQL connection is attached to this session. Actual occurrence counts
and business ownership of any anomalies remain unverified. Do not infer
that the cross-site association is authorized merely because display
attribution is now truthful.


## Independent raw-source ĐĐK↔GxP evidence audit (12 October)

The source `artifacts/phase3c/legacy_snapshot.json` contains **830** ĐĐK
rows with **zero nonblank `db.dkkd.ID CC` values**, the forward field
currently consumed by Phase-2 for creating version-specific
`BusinessEligibilityCertificateLink`. Conversely, among **1,628**
`db.cc` Certificate rows, **806** have a nonempty `ID DDK`, of which
**639** are literal valid numeric IDs and **167** are placeholder `-`.
All 639 literal IDs point to an existing raw ĐĐK row, but **nine**
point to entries in the independently confirmed-blanked contract, leaving
**630 source-reference candidates** (495 distinct target ĐĐK IDs).
Among those candidates, **628 share the same Site** and **two cross
Sites**: Certificate **790** → ĐĐK **160**, and Certificate **1500**
→ ĐĐK **464**. One of these also differs by Company. These are
source-side *competing claims*, not validated canonical links and not
automatic justification to repair or import them.

New independent `backend/app/domain/legacy_ddk_gxp_source_audit.py`
classifies both reference directions without mutating input or introducing
a downstream rescue. CLI: `python -m scripts.audit_legacy_ddk_gxp_source_links`.
The module reports only literal row IDs and numeric lineage; no name,
address or personnel fields are emitted. Regression covers synthetic
missing/blanked/cross-Site references plus the checked-in real corpus.
This audit does not modify Phase-2 import, Certificate/Site/Case owners,
version history, or existing canonical link counts. Current PostgreSQL
link-population counts still require the separate read-only rehearsal
SQL check. Any decision to translate reverse `ID DDK` into canonical
`BusinessEligibilityCertificateLink` rows requires source-authority
review, including the two cross-Site rows, and cannot be implemented
as an unreviewed fallback. The former SQL audit is still necessary
to distinguish current DB state from raw Excel evidence.

The source audit reports nonliteral reference counts and placeholder counts only;
unknown free-text values are intentionally not echoed into logs or JSON output.


## V1 duplicate-header source-loss audit (12 October 2026)

The original Core Sheet V1 Excel reader used a dictionary comprehension
keyed only by visible header text. If the four `db.dkkd` columns for GMP,
GLP, GSP and GDP share the heading `ID CC`, each successive physical column
**overwrites the previous one**, even if its value is blank. The checked-in
V1 JSON has 830 ĐĐK rows and only one blank `ID CC` field; that is evidence
of the **flattened artifact**, not proof that the original workbook had no
forward GxP references. The original distinct column values cannot be
recovered from that V1 JSON. The user's source information establishes four
separate columns; their exact source column ordinals and corresponding header
groups still require verification against the authoritative `.xlsb` or its
coordinate-preserving Snapshot V2.

At the source-extraction owner, `legacy_snapshot._core_header_plan` and
`_core_source_row` now preserve *every* duplicate-heading cell in keys
containing the physical Excel column number, e.g.
`ID CC [excel_column=14]`, and attach `__excel_duplicate_headers`
metadata for the whole group. Unique headers retain their legacy names.
No positional assignment to GMP/GLP/GSP/GDP is inferred and no reverse
`db.cc.ID DDK` value is used to fill a missing forward link.

The Phase-2 pre-schema owner refuses a snapshot carrying this unresolved
duplicate-header metadata in either normal or strict mode. This makes
re-extraction non-lossy and import fail closed until physical-column roles
are reviewed. The already-flattened V1 snapshot has no such metadata;
therefore it must **not** be used to claim complete historical ĐĐK–GxP
basis linkage or to authorize new link generation. The pre-existing
version-specific canonical link contract is unchanged; no live import,
database data, or source workbook was changed.


## Physical db.dkkd ID CC source recapture (12 October 2026)

Read-only Windows audit owner: tools/audit_ddk_idcc_physical.py
(requires installed Excel, Python 3 with pywin32). Run from D:\GXP-QLCL:

    py -3 -m tools.audit_ddk_idcc_physical --workbook "D:\GXP-QLCL\legacy\Danh sách Kiểm tra GPs.xlsb" --out-dir "D:\GXP-DDK-IDCC-REVIEW"

The tool opens the authoritative .xlsb in an isolated Excel COM process
(DispatchEx), ReadOnly, with macros forcibly disabled and external-link
updates disabled; the workbook is never saved. Captured evidence includes
the true physical Excel column ordinals and the header band, instead
of guessed GMP/GLP/GSP/GDP roles. The extraction reuses the existing
position-preserving source parser, and independently audits each populated
ĐĐK -> GxP FK, source Site/Company identities, target certificate types,
and reverse db.cc.ID DDK corroboration/conflicts.

Local output is D:\GXP-DDK-IDCC-REVIEW\ddk_idcc_physical_source_review.json.
It contains source SHA-256, original row count, physical column totals,
certificate-type distributions and one reference-evidence record for each
nonblank source cell. **All source roles remain UNVERIFIED** until independent
review of header groups. No canonical link is generated, no source value or
PostgreSQL row modified, and no raw workbook is committed.

Audit hardening (12 October): the physical dkkd header must be uniquely
identifiable by its ID and **exactly four** ID CC headings in the first ten
rows; preserved cell metadata must contain four distinct physical ordinals
and unique row coordinates. Neither repeated DDK legacy IDs nor repeated GxP
references collapse independently sourced rows. Each nonblank candidate
records its original raw FK for local review, while cross-row duplicates are
reported separately from duplicates within a physical ĐĐK row. An ID CC
column containing Excel formulas (or an indeterminate HasFormula result)
is rejected rather than treating cached Value2 results as literal IDs.
These guards do **not** approve any column's GMP/GLP/GSP/GDP role.
The recapture reads only the four audit owners (db.cty, db.cso, db.cc and
db.dkkd). Each requires a uniquely identified source ID header rather than
choosing the densest worksheet row. Source Site and Company IDs are resolved
with explicit UNIQUE/MISSING/AMBIGUOUS/UNRESOLVED states: a numeric equality
of certificate and ĐĐK Site IDs is **not** called SAME_SITE when the site
identity is absent or duplicated. Company-vs-Site ownership has its own
MATCH/MISMATCH/UNRESOLVED evidence, not an inferred business approval.

The optional --snapshot-json input must be a new lossless coordinate-preserving
snapshot. The old V1 artifacts/phase3c/legacy_snapshot.json is rejected because
the four original column values were destroyed during flattening. Database
rehearsal state requires the separate read-only SQL audit. Any transition from
these candidate source references into actual BusinessEligibilityCertificateLink
records requires reviewed business authority, never a reverse-FK fallback.


## Uploaded authoritative .xlsb cross-check — 12 October 2026

The complete owner-supplied binary workbook was examined independently and
**read-only**. Its SHA-256 is
`c12537ea5a5c9f470e42fb5bdbe214f36983e310fceac7c560ad38885209fe3d`,
exactly matching the original owner-side read-only workbook fingerprint already
recorded in this audit. No raw workbook or customer/staff data were committed.

`db.dkkd` has **830 source records** (Excel header row 4). Its row 3 contains
**explicit physical category headings**, not inferred group order:

| Source heading | Physical Excel ID CC | 1-based ordinal | Nonblank cells | Actual literal ID tokens |
|---|---|---:|---:|---:|
| GMP | O | 15 | 738 | 851 |
| GLP | S | 19 | 9 | 9 |
| GSP | W | 23 | 1 | 1 |
| GDP | AA | 27 | 0 | 0 |
| **Total** | | | **748** | **861** |

The 738 GMP cells include 636 single-ID cells, 91 two-ID cells and 11
three-ID cells. All 861 separately tokenized literal references resolve to a
unique `db.cc` Certificate and match the observed source category heading:
851 GMP, 9 GLP and 1 GSP; no GDP source references were populated. In
contrast, the previous single-integer `parse_int(raw_fk)` silently classed
**102 whole multi-ID cells** (215 valid source IDs) as `NONLITERAL_FK`.
This was a **source audit interpretation bug**; it was not authority to create
new canonical business links. Owner-level tokenization now keeps the original
cell, token ordinal and raw token, including malformed/empty tokens, separately.

Independent source analysis reports five GMP **cross-Site candidate
occurrences**, referring to four Certificate IDs (1064 appears in two separate
ĐĐK rows; 1180, 1308 and 1385 appear once each). There is one
ĐĐK/owning-Site **Company mismatch** (ĐĐK legacy ID 626). An independent exact-ID reconciliation against the previously owner-approved
`artifacts/phase3q/confirmed_blanked_rows.json` (14 August 2026) confirms
**all 50** source `db.dkkd` rows with missing Site and Company are exactly
the 50 approved `db.dkkd` exclusions, with zero omissions/extras and zero
populated ID CC cells among them. Hence the effective owner-approved
`db.dkkd` source population is **780 / 830 rows**; the 861 token references
remain unchanged. This is a *read-only population reconciliation*, not a
new exclusion inference or restoration approval. Repeated GxP IDs across ĐĐK
rows and non-equal reverse `db.cc.ID DDK` references are **not** by themselves
proof of invalid history or business ownership; no version/history link is
inferred or persisted.

The DDK source also repeats `PHẠM VI CHỨNG NHẬN`,
`TIÊU CHUẨN ÁP DỤNG`, and `HOẠT ĐỘNG KINH DOANH` four times under
the same four GxP group headings. A future owner-approved mapper must
explicitly preserve each group's companion fields as well as `ID CC`;
a mere first/last duplicate-header selection would lose source information.

**Verification boundaries:** These are independent read-only binary values
from the uploaded workbook. This environment has not executed Microsoft Excel
COM/HasFormula checks; cached values cannot alone prove the absence of
formulas. The isolated Windows COM audit remains the independent literal-source
formula confirmation gate. The `GMP/GLP/GSP/GDP` roles are **observed labels
in source row 3**, not authorization to create
`BusinessEligibilityCertificateLink` records. No import/schema/DB alteration,
rehearsal reconciliation, merge, deployment, or business adjudication occurred.
