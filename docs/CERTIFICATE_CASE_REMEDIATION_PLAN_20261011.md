# Certificate–Case remediation plan — no execution authorization

**Status: REVIEW PLAN / NOT APPROVED — 11 October 2026.**
This is a proposed operational decision gate, not a migration, SQL patch, runtime
relaxation, or authorization to change business data. The active Search Facilities
HTTP 409 remains **unresolved**.

## Separation of defects and ownership

| Track | Current evidence | Required owner/action | Forbidden shortcut |
| --- | --- | --- | --- |
| A: legacy Certificate 376 | Source points to Case 378 at a different company/Site. Case 380 has the same Site and reverse reference plus same certificate number. | Verify original issuance documentation; approve or reject Case 380 as the originating Case for 376. Only then plan an exact canonical FK correction. | Null Case FK, change to administrative basis, or infer correction from company alone. |
| B: legacy Certificates 1037 and 1180 | Domesco versions cover Sites 46 and 298; linked Case 1023 is anchored to Site 298. Public assessment evidence corroborates two-Site inspection. Regulatory evidence separately supports 314/GCN-QLD REPLACING 200/GCN-QLD. | Approve a multi-Site domain contract; implement explicit reviewed Case and CertificateVersion coverage, version-specific Site scope/address, and matching validation/projection semantics before any backfill. | Reassign both certificates to Site 298, merge Sites, clone certificates, weaken validators, or treat replacement as identical identity. |

The owner-verified workbook SHA-256 and original source-row evidence are in
`CERTIFICATE_CASE_SOURCE_INTEGRITY_AUDIT_20261011.md`. Reuse the captured
read-only workbook evidence, rather than repeating the Excel audit.

## Gate 0 — source adjudication (no database writes)

- Track A: compare exact Certificate 376 issuance paper trail and Case 380's
  assessment with the legacy row references; record sign-off and source hashes.
  A strong reverse reference remains a **candidate** until approved.
- Track B: review Case 1023's inspection record and both published certificates
  Site-by-Site, retaining the two address strings **66 Quốc lộ 30** (2022)
  and **346 Nguyễn Huệ** (2023) without guessing physical relocation,
  renumbering or canonical Site identity.
- Specify the meaning of legacy `Case.site_id`, `Certificate.site_id`,
  `Certificate.case_id` as anchors vs multi-Site coverage; specify exactly
  which Site scopes belong to which CertificateVersion and the source
  evidence that authorizes that mapping.
- Write a signed decision record for each exact canonical target, including
  *rejected* candidates. No bulk inference from company name or line code.

### Track A — evidence closure checkpoint for Certificate 376 (read-only)

**Provisional assessment: Case 380 is strongly corroborated as the originating inspection; not formally adjudicated.**

| Evidence dimension | Currently stored link, Case 378 | Review candidate, Case 380 |
| --- | --- | --- |
| Source Case Site | 72, Hasan-Dermapharm, unrelated Company | 73, USA-NIC, matches Certificate 376 Site |
| Inspection period | 04–05/03/2008 | 07–08/12/2017 |
| Source Case GxP | GMP | GMP |
| Case's reverse `ID CC GPs` | No corresponding 376 back-reference found | Exact reference to Certificate 376 |
| Case certificate number | Not corroborated to 119/GCN-QLD | Exact `119/GCN-QLD` |
| Entire scope string vs Certificate 376 | Not identical | **Exactly identical** after stripping only outer whitespace |
| Inspection-to-issuance chronology | 2008 → 12/03/2018, inconsistent with apparent renewal context | 12/2017 → 12/03/2018, plausible |

The government-published 2019 WHO-GMP register independently attributes `119/GCN-QLD` (12/03/2018–12/03/2021) to USA-NIC at the Site 73 address. That registry **does not prove the internal Case-to-issuance linkage**. Its public URL, corroborating source row IDs and visual-verification limitation are documented in `CERTIFICATE_CASE_SOURCE_INTEGRITY_AUDIT_20261011.md`.

**Outstanding approval evidence:** obtain the original signed issuance decision/Certificate and referenced inspection dossier or internal approval trail, bind document identifier and immutable checksum to the decision, verify Case 380 and Certificate 376 are uniquely identified in the *target* rehearsal DB, and have an accountable data owner explicitly approve or reject reassignment. The existing legacy source row must remain untouched; this document is not a source correction instruction.

**Decision state:** `PENDING_PRIMARY_DOCUMENT_AND_OWNER_SIGNOFF`. Reassignment target `Case 380` is **review candidate only**. Do not create an auto-remediation rule based on matching text, company, date, certificate number, or this table.

## Gate 1 — immutable target and reversible write plan (after approval)

1. Confirm instance identity, project and database before any write:
   `gxp-web-prod` / `gxp-qlcl-vm` / **only**
   `gxp_legacy_rehearsal`. Explicitly reject `gxp_qlcl`, `gmpnn_ai`
   and all unexpected endpoints. Do not switch runtime database.
2. Capture current release SHA, Alembic revision, table counts and a read-only
   Certificate/Case/Site/CertificateVersion/ProductionLine reconciliation.
   Assert exactly the approved legacy IDs and current UUID/FK values; abort
   if stale, missing, duplicated or already diverged.
3. Take a **fresh, independently verified** PostgreSQL backup immediately
   before the permitted transaction. A previous backup from 10 October is
   a historical checkpoint, not the fresh rollback artifact.
4. Seal a versioned remediation manifest containing evidence identifiers,
   reviewed identities, expected-before/expected-after values, expected row
   counts, operator, and exact rollback inverse. Review the dry-run diff.
5. Use one DB transaction with an exact current-state predicate (optimistic
   stale-state guard), exact affected-row-count assertion and an immutable
   remediation audit entry. Roll back immediately on any mismatch. Do not
   change unrelated certificates, Cases, Sites, ProductionLine UUIDs or
   documents.
6. Verify post-write with independent queries, not only the write result.
   Compare **all** related historic certificate versions and Site-local
   scopes, provenance, and source counts. Preserve the before-image and
   test the inverse rollback on a disposable copy before production-like use.
7. Treat deploying changed validators/projections and writing reviewed coverage
   as a separately approved, ordered release. A schema proposal by itself
   is not permission to backfill.

### Track A exact-row assertions (illustrative, not executable SQL)

- One Certificate row with `legacy_certificate_id=376`, anchored to
  USA-NIC Site 73, currently linked to Case legacy 378.
- One approved target Case row with legacy 380, Site 73, GMP; verify the
  originating-inspection documents and issue number `119/GCN-QLD`.
- Reconfirm `issuance_basis=inspection_case`; do not fabricate a nullable
  administrative link. Guard the *UUID* before-image of `case_id` rather
  than relying on integer legacy IDs in the UPDATE predicate alone.
- Expected business FK rows changed if approved: **exactly one**. Other
  fields/rows changed: **zero** except separately approved audit records.
- Stop if the above assertions are not all true or there is no formal approval.

### Track B prerequisites (no current row update permitted)

- Approved `CaseSiteCoverage` for each physically assessed Site of the
  originating Case, with source lineage.
- Approved `CertificateVersionSiteCoverage` for each certified Site on
  each version, and a separately reviewed ownership of each Site's certified
  activities. The master `CertificateScope` is presently version-bound,
  **not** Site-bound.
- Resolve historic Site 1 address identity without changing source addresses,
  merging Site 46 and 298, or generating Site UUIDs by heuristic.
- Review `REPLACED_BY` direction and effective date for the two independent
  regulatory identities, with separate approval. Do not infer `latest_flag`.
- Integrate matching invariants in `CaseWorkflowService` Python and SQL
  linked-Case predicates **and** Catalog search/Facility/Case/Certificate
  projections; a change to only one read path is insufficient.
- The approved release must define treatment of unresolved links as fail
  closed; Search may not hide historical invalid records.

## Gate 2 — regression and controlled runtime acceptance

Test on disposable PostgreSQL first, then an explicitly authorized rehearsal
copy: valid single-Site link; unrelated cross-Site link; reviewed multi-Site
coverage; missing Case; GxP mismatch; administrative null Case; historical
non-current certificates; `REPLACED_BY` lineage; version-specific Site address
and scope; provenance and exact row counts; canonical ProductionLine UUID;
Facility/Search/Case/Certificate APIs; Google OIDC and authorization.

A green PR CI with PostgreSQL integration **SKIPPED** is not database or
runtime acceptance. Separately record:

- migration/schema status and rollback verification;
- PostgreSQL integration run and affected-row audit;
- VM release SHA and runtime readiness;
- HTTP `/api/search/facilities` with GMP, GLP and GMPbb contexts;
- historical certificate visibility without Site merge;
- 409 remaining on deliberately unresolved cross-Site evidence.

**No automated remediation is currently authorized by this document.**

## Gate-0 rehearsal anchor witness after db.cso authority decision (16 October 2026)

The separate **read-only** tool
tools/audit_certificate_case_site_owners_rehearsal_readonly.py compares
existing, source-classified Certificate→Case SITE_MISMATCH rows against
their **actual** canonical rehearsal Certificate/Case/Site/Company
identities. Its source anchor is the checked-in versioned legacy snapshot,
with an explicit snapshot SHA256 in the PRIVATE report; this hash is not
falsely described as the SHA256 of the physical original XLSB. The
physical workbook has been independently reconciled in the DDK audit;
it remains the primary Site/Company ownership authority.

The rehearsal comparison is fail-closed on:
- Unexpected effective Certificate source population (current accepted
  mismatch set 376/1037/1180), unapproved source parents, duplicate
  source legacy IDs and missing original source Site→Company evidence.
- DB target, role, revision or read-only transaction changing from the
  strict gxp_legacy_rehearsal target.
- Certificate's current Site ID, source Case ID, Case's Site/GxP,
  Site→Company ownership, issuance basis and certificate type drifting
  from the original legacy source.
- Reverse-reference Case missing or no longer belonging to the
  original source Site and Company.

Per actual CertificateVersion the private witness keeps version identity,
dates, lifecycle state and **only cryptographic hashes** of its ordered
stored CertificateScope rows. These rows have no Site FK in the
present canonical model. Even a version with nonempty stored scopes is
classified **SITE_COVERAGE_NOT_APPROVED**; neither current legal scope
nor any DDK grant is inferred. Original legacy Case is never rewritten;
a reverse-reference Case remains a candidate only.

The tool uses one explicit database READ ONLY transaction and
creates only an owner-private output file mode 0600. No SQL writes,
migrations, changes to Case/Site/Company/Certificate, DDK links,
NAS reads, StorageBinding, or runtime deployment are authorized.
Its result is a **prerequisite for evidence review**, not an approval
of Gate 1 remediation. For Track A, an issuance document linking the
actual Certificate to its originating inspection and the data owner's
signed decision are still missing. For Track B, original per-version
signed Certificate/annex evidence and the approved multi-Site
coverage model remain outstanding.

## Gate-0 reverse-reference binding and source snapshot pin (16 October 2026)

After the successful original Site/Company/Case/version SELECT-only witness,
the **same owner** now binds its two independent source audit projections of
reverse-referencing Cases **one-to-one**:

- The db.cso-derived original Case Site/Company record.
- The literal db.ktra reverse Case record, original GxP, certificate-number
  match and full scope-text lexical match.

The two sets must have identical unique legacy Case IDs. Every reverse
candidate's canonical Case Site and GxP must match the literal source
evidence, and the source's Site/GxP correspondence flag must agree with the
current canonical Certificate Site/type. Missing/altered/duplicated Case
evidence now **blocks** the witness; it does not silently reduce its
candidate list. The three independent source correspondence flags remain
separate and **never grant** a Case rebinding or a multi-Site certification.

GMP 376 / Case 380 is the strongly corroborated source-only review candidate:
original Site/GxP, original certificate number and entire source scope text
match, but an original signed issuance trail and owner sign-off are still
required. For GMP 1037/1180, same-company Site anchoring and surviving
reverse signals are not substitutes for reviewed CaseSiteCoverage or
CertificateVersionSiteCoverage.

The original witness CLI now pins the **exact legacy_snapshot.json export
bytes** to SHA256
\`b3bde05963e4e4d14d5b244e7c62b0f810f1cbbe206750574def6a366bdf7296\`
(verified by the operator on 16 October 2026). This is explicitly
**not** the authoritative original physical XLSB hash; the accepted original
physical workbook retains its different checksum recorded earlier. Swapping
in a new export with identical row totals cannot satisfy this sealed
historical witness without an independently reviewed new source checkpoint.

All source Case candidates remain \`remediation_authorized=false\`,
\`primary_signed_issuance_case_link_verified=false\`,
and \`case_rebinding_authorized=false\`. This change adds no database write,
NAS access, migration, legal-grant assertion, or runtime fallback.

## Original CertificateVersion import-value fidelity gate (16 October 2026)

The sealed read-only rehearsal witness now checks the **original**
`db.cc` data for each of the three Certificate–Case mismatch rows against
the actual stored imported `CertificateVersion` and `CertificateScope`:
original certificate number, parsed source issue date, one imported version,
and the exact (importer-trimmed) certificate scope content, represented in
reports as SHA256 only. Original source text itself is not duplicated into
diagnostic output.

This is **import-value fidelity**, not issued-original legal document
verification. It does **not** establish that a stored CertificateScope has
a particular Site, or prove that a Case was the inspection leading to
issuance. New versions or changed scope text block reuse of the historical
witness until reviewed and independently re-pinned; the owner does not
silently reinterpret new versions as old imported records.

Regression tests reject source or canonical drift in certificate number,
issue date and scope. The first-correct owner remains the `db.cc` source
mapping and `CertificateVersion` import, and regulatory evidence
remains a separate gate. Neither the DDK certificate grant nor
a Case-rebinding is approved by this code.
