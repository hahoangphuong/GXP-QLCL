# Primary issuance evidence request — GMP 376, 1037 and 1180

**Status:** EVIDENCE MISSING / NOT APPROVED — 16 October 2026. This is a
source-retrieval and business-adjudication request only, not a migration or
storage-probe authorization. Owner: GXP-QLCL Certificate–Case source integrity,
PR #7.

## Technical checkpoint and exact scope

- V5 verified 3/3 source-to-rehearsal Certificate/Case/Site/Company anchors
  and 3/3 imported CertificateVersion number/date/scope values. The frozen
  legacy snapshot SHA256 is
  `b3bde05963e4e4d14d5b244e7c62b0f810f1cbbe206750574def6a366bdf7296`.
- V6 independently revalidated the same sources in a SELECT-only rehearsal
  transaction. It found **zero Document, zero DocumentVariant and zero
  DocumentVersion rows** attached to three target Certificates, their
  three original Case targets and two reverse-Case review targets (eight
  attachment-target roles; three distinct Case UUIDs).
- V6 private report SHA256:
  `e54cc0856959faba38d957494c1629d3cca8a415168937abd74cb424c20698ff`.
  Full private report remains on the VM.
- V6 absence means **no attached database metadata**, not a proven absence
  of paper originals, digitally signed PDFs, NAS folders or archives.
- Historical inspection storage *year anchors*, if present, are only discovery
  context: not a file locator, proof of a specific original, or binding
  permission. No filename heuristics or recursive NAS scanning is authorized
  by this document.

## Requested primary documents and decisions

| Source certificate / issued number | Original linked source Case | Independent review Case | Exact evidence needed | Decision gate |
| --- | --- | --- | --- | --- |
| 376 / 119/GCN-QLD (12/03/2018) | Case 378 — Site 72 / Company 57 | Case 380 — Site 73 / Company 58 | Original issued signed certificate and issuance decision; official inspection record and approval chain identifying the particular originating inspection; complete scope/annex | Data owner explicitly ACCEPTS or REJECTS Case 380 as issuance origin after checking paper trail; do not infer approval from three source-text matches |
| 1037 / 200/GCN-QLD (20/04/2022) | Case 1023 — Site 298 / Company 37 | Source Case 1023's reverse reference, **not a new Case** | Original signed certificate/annex specifying each Site/address and Site-local manufacturing activities; original inspection team report and decision for both Site 46 and Site 298 | Reviewed per-version Site coverage plus Case-to-Site inspection coverage; no substitution of Site anchors |
| 1180 / 314/GCN-QLD (15/05/2023) | Case 1023 — Site 298 / Company 37 | No separately proven source reverse Case for 1180 | Original signed 314 certificate with both Site address/scope attachments; decision on replacement relation to 200 and its effective date; assessment/inspection provenance | Explicit coverage mapping for 314 and separately approved 200→314 relationship; do not conflate distinct certificate identities |

The dates and numbers above are the **existing source-audit context**, not newly
verified signed-original PDF content. Address variations in the archived
Domesco records (e.g., 66 Quốc lộ 30 and 346 Nguyễn Huệ) must be preserved
verbatim and adjudicated, not normalized to a Site by inference.

## Per-document provenance to capture outside public GitHub

For each actual file or paper original found, the authorized records owner
must record: issuing authority, full issued number, issue/effective/expiry dates,
all referenced Site names/addresses, the corresponding version/annex, certified
activities per Site, related inspection decision/report reference, original
custodian/source system, evidence retrieval date, immutable binary SHA256,
and a reviewer's dated ACCEPT / REJECT / INCONCLUSIVE decision **with reasons**.

- A filename, shared company, Site heading, existing storage locator, signed
  document *type label*, or checksum *field* does not prove authenticity.
- Keep sealed document binaries and confidential storage locators in protected
  evidence custody. Do not commit scans, UNC paths, bearer tokens, private
  UUIDs or archive credentials to the repository.
- Distinguish **original issuance evidence**, **source correspondence**,
  **Site-specific grant**, **Case origin**, and **registry corroboration**.
  Public published registers can corroborate the issued certificate and Site
  attribution but do not independently prove an internal Case FK.
- A scanned original must be examined (including relevant annex pages), with
  legal-signature/provenance verification by authorized reviewers. If there is
  no original or its authenticity/version cannot be proved: mark
  `EVIDENCE_MISSING` or `INCONCLUSIVE`, never auto-approve.

## Locked disposition until adjudicated

`Certificate.case_id` remains unchanged for GMP 376, 1037 and 1180.
`Case.site_id`, `Certificate.site_id`, `Site.company_id`, source workbook
and source snapshot remain untouched. No `CaseSiteCoverage` or
`CertificateVersionSiteCoverage` is inferred or backfilled. No DDK–GxP link
approval, file/folder mapping, `Document` creation, StorageBinding, DB/NAS
write, validator bypass, merge or deployment is authorized.

**Next controlled gate:** review captured, genuinely issued primary evidence
and owner sign-off against the already proven source/canonical V5 witness.
Only after adjudication should a *separate* exact-row, reversible rehearsal
change plan be proposed; missing evidence must retain the present blockers.

## V7 procedural metadata triage — no archive or signature verification

The additive **read-only** tool
\`tools/audit_certificate_case_procedural_metadata_readonly.py\`
checks the V5 source/canonical anchors and V6 document metadata in the
**same REPEATABLE READ / READ ONLY** rehearsal DB transaction. For each
distinct original/reverse Case (378, 380, 1023), it only inventories the
existence and limited metadata of existing CaseApplication, InspectionPlan,
InspectionDecision, InspectionOutcome, InspectionApprovalSubmission,
LegacyInspectionStorageAnchor and StorageBinding rows, plus any recorded
CertificateRelationship references for the three affected GMP identities.

All inspection decision references are hashed in the private report; archive
years are clearly labeled **not file locators**. StorageBinding is counted
as **metadata only**. The tool never follows a path, asks the storage
service to resolve a folder, probes NAS, accesses any document binary,
creates a binding, changes relationships, or asserts a regulatory grant.
Missing rows or references remain evidence gaps. A matching year or plan
decision does not prove that a particular GMP Certificate was issued from
that Case.

A full V7 run is **not claimed** until operator terminal output confirms
the pinned commit, required exact-head CI and the private rehearsal report.
Prior V5/V6 reports remain immutable historical checkpoints.

