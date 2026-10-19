# Proposed multi-Site inspection and certificate coverage model

**Status:** PROPOSED / NOT APPROVED, 2026-10-11. No schema migration, runtime change, source rewrite or data correction is authorized.

## Why a new domain contract is needed

The workbook, 2022 published GxP inspection list, 2022 GMP register and 2023 certificate establish a real multi-Site Domesco case:
- 2022 inspection dated 15–16/01/2022 evaluated **two manufacturing Sites**. Internally `db.ktra` Case 1023 preserves both separately labeled scope sections but stores only one Site FK (298) and leaves `ID CƠ SỞ 2` blank.
- Certificate 200/GCN-QLD dated 20/04/2022 covers both Sites. Its `db.cc` representation (legacy ID 1037) is anchored to Site 46 while Case 1023 is anchored to Site 298.
- Certificate 314/GCN-QLD dated 15/05/2023 again covers both Sites, explicitly replacing 200/GCN-QLD per the regulator. Its `db.cc` legacy ID is 1180.
- Source Site 1 address changes from 66 Quốc lộ 30 (2022) to 346 Nguyễn Huệ (2023). Site 2 is at Cần Lố. The physical identity/relocation/renumbering explanation is **not proven**.
- A separate unrelated source mismatch, Certificate 376 → Case 378, has reverse evidence for Case 380 and must be remediated independently.

Sources:
- https://dav.gov.vn/upload_images/files/Danh%20s%C3%A1ch%20c%C3%A1c%20%C4%91%E1%BB%A3t%20%C4%91%C3%A1nh%20gi%C3%A1%20GxP%20%2820_10_2022%29.pdf
- https://gmp.com.vn/images/upload_file/danh-sach-cac-cong-ty-trong-nuoc-dat-tieu-chuan-gmp-20_10_2022_1667265374.pdf
- https://www.domesco.com/pdf/GCN%20GMP%20-%20WHO%20%28dia%20chi%20moi%20346%20Nguyen%20Hue%29.1f1117ede5f0b54c599a0699cc7fb7f8.pdf
- https://dav.gov.vn/upload_images/files/Danh%20s%C3%A1ch%20c%C3%A1c%20c%C3%B4ng%20ty%20trong%20n%C6%B0%E1%BB%9Bc%20%C4%91%E1%BA%A1t%20ti%C3%AAu%20chu%E1%BA%A9n%20GMP%20%2820_01_2025%29.pdf

## Public GMP register cross-check — 19 October 2026 (source-only addendum)

Two independently dated **published GMP register snapshots** have been inspected
at their original PDF page positions; their table text and visible layout were
checked, rather than relying only on an indexed search excerpt:

| Publication | Exact location | Certificate and date | Site 1 as printed | Site 2 as printed |
| --- | --- | --- | --- | --- |
| [Domestic GMP list, updated 20/10/2022](https://gmp.com.vn/images/upload_file/danh-sach-cac-cong-ty-trong-nuoc-dat-tieu-chuan-gmp-20_10_2022_1667265374.pdf) | printed p. 13/62, PDF page index 12, row **49**, code VN-046 | `200/GCN-QLD`, issued 20/04/2022 | `Số 66, quốc lộ 30`, phường Mỹ Phú, Cao Lãnh, Đồng Tháp | Cụm công nghiệp Cần Lố, ấp An Định, xã An Bình, Cao Lãnh, Đồng Tháp |
| [Domestic GMP list, updated 04/07/2023](https://gmp.com.vn/images/upload_file/danh-sach-cac-cong-ty-trong-nuoc-dat-tieu-chuan-gmp-04_07_2023_1689564629.pdf) | printed p. 7/31, PDF page index 6, row **48**, code VN-046 | `314/GCN-QLD`, issued 15/05/2023 | `Số 346 đường Nguyễn Huệ`, phường Mỹ Phú, Cao Lãnh, Đồng Tháp | Cụm công nghiệp Cần Lố, ấp An Định, xã An Bình, Cao Lãnh, Đồng Tháp |

In **each** cited table row, the grant activities are separated by the
headings `Cơ sở 1` and `Cơ sở 2`. The first site's scope is principally
nonsterile medicinal products with release, packaging and QC activities.
The second site's scope is predominantly herbal/traditional medicines and
herbal-origin materials with its own release and packaging activities.
These are **distinct site-local scope descriptions**, not a single scope
which may safely be copied to both sites. Any detailed scope comparison
must preserve the exact year, row, section and wording, including qualifiers.

**Evidence classification (strict):** These are third-party-hosted public
register PDF pages, inspected through a PDF reader. Their PDF bytes were
**not retrieved into protected evidence custody and not hashed** in this
audit; the published lists are not authenticated original signed issuance
certificates. Search-indexed text for a separate Domesco-hosted five-page
`314/GCN-QLD` certificate exists, but that signed document's full binary
and annexes could not be directly fetched/verified here. Do **not** invent
or backfill a `source_document_sha256`, Site-local scope digest,
`CertificateVersionSiteCoverage` row or signed-document approval from
the above URL, page position or public register wording.

**No source-safe inference:** The two snapshots establish that different
historic addresses were *printed* for Site 1; **those two register
rows alone** cannot determine why the address changed, whether the
physical GMP premises stayed the same, or whether Site 46 has a persistent
canonical identity. The distinct 04/04/2023 company disclosure below
specifically attributes the *registered headquarters* address change to
street renaming and house-number reassignment, but does not automatically
prove GMP manufacturing-site or Case coverage identity. Site 2's
repeated label does not by itself authorize canonical identity binding.
Neither register provides the internal application's Case 1023 UUID, its
exact signed inspection decision or the scope applied by that Case.
The public notice that 314 replaces 200 is separate regulatory
corroboration; recording an actual `REPLACED_BY` link still requires a
specific owner-approved plan. Source decision, site-identity and
signed-document provenance gates are **still open**. This addendum authorizes
no schema, migration, FK/relationship write, validator relaxation,
storage operation, VM deployment or prospective multi-Site issuance.

## Corporate address-renaming disclosure — 04/04/2023 (new corroboration)

**New evidence distinct from GMP registers:** Domesco itself published
[disclosure No. 15/HĐQT-DMC dated 04/04/2023, with the 35th amended
enterprise-registration certificate attached](https://www.domesco.com/pdf/20230404---dmc---giay-chung-nhan-dkdn-thay-doi-lan-thu-35--thay-doi-dia-chi-tru-so-cty--signed_vi_1680579756.pdf).
The disclosure identifies the registered company headquarters at
`Số 66 - Quốc lộ 30 - P. Mỹ Phú - TP. Cao Lãnh - Đồng Tháp` and
states it was changed to
`Số 346 - đường Nguyễn Huệ - P. Mỹ Phú - TP. Cao Lãnh - Đồng Tháp`
**because Đồng Tháp provincial authorities renamed the street and reassigned
house numbers**. The described enterprise registration amendment is dated
01/04/2023, received 03/04/2023. In the publicly readable **four-page PDF**,
the disclosure is on PDF pages 0–1 and the attached amended enterprise
registration identifies the new headquarters address on PDF page 2.

**Source verification ceiling:** Full text of the remotely indexed PDF was
retrieved and reviewed, including the attached business-registration
certificate; **page image retrieval timed out**, and the binary has not
been retrieved into protected evidence custody, SHA256-verified or
cryptographically validated for signature authenticity. This is
*company-authored public documentary corroboration*, not an
original authenticated GMP certificate, manufacturing-premises decision
or inspection report.

**Narrow conclusion:** The specific **change of the registered
headquarters address and its stated administrative cause are
documented**, so the earlier question "why were the address strings
different?" now has a plausible official explanation grounded in
a dated company disclosure. This reduces, but does **not close**, the
separate GMP *physical manufacturing Site identity* gate. The two GMP
lists independently print the two addresses at Site 1 in different years;
neither that correspondence nor the headquarters' enterprise registration
is proof that a particular production line, inspection Case 1023, GMP
site authorization or historical `site.id` persisted unchanged.
An authorized owner must inspect the signed GMP/inspection primary
evidence, compare facility identity and address chronology, and record
an explicit reviewed Site 46 disposition before any DB Site mapping.

**No automatic mutation or approval:** Do not update either printed
CertificateVersion address, merge canonical Sites, use this disclosure
to synthesize a CaseSiteCoverage row, alter `Certificate.case_id`,
infer `REPLACED_BY`, change read/write validation, or enable
new multi-Site GMP issuance. No real database, storage or VM
operation was performed in this review.

## Proposed additive relational owners (not implemented)

1. **CaseSiteCoverage**: `case_id`, `site_id`, coverage provenance (source sheet/row or published assessment reference), explicit review disposition, optional Site-local evaluation scope reference. A Case can have more than one evaluated Site. No implication from company ID or a shared line code.
2. **CertificateVersionSiteCoverage**: `certificate_version_id`, `site_id`, source Site label and source address **at issuance**, reviewed association with that version's immutable `CertificateScope` or a separately retained scope fragment. A CertificateVersion can certify different operations at different Sites. Do not overwrite historical addresses with the current `Site.site_address`.
3. **CertificateRelationship**: existing `REPLACED_BY` relationship for two independently reviewed regulatory identities. Evidence for 314 replacing 200 exists, but no automatic writer or `latest_flag` promotion follows from that fact.
4. Retain existing `Case.site_id`, `Certificate.site_id`, `Certificate.case_id`, version and ProductionLine UUID FKs until compatibility and canonical ownership semantics have been explicitly decided. Do not silently change their meaning or fill coverage associations by heuristic.

## Proposed integrity boundary for future review

- Single-Site legacy records remain subject to the existing same-Site/same-GxP certificate-to-originating-Case invariant.
- A multi-Site exception cannot be based merely on `company_id`, a certificate scope's text heading, address resemblance or line code.
- A future multi-Site case must have **explicit, reviewed CaseSiteCoverage** and **explicit, reviewed CertificateVersionSiteCoverage** with a consistent GxP context. The full business rule relating evaluated Sites, certificate issuance owner and certified Sites must be approved before any relaxation of the existing validation code.
- An unresolved/bare cross-Site link continues to fail closed. Search and Workspace must not silently omit or relink it to achieve HTTP 200.
- Canonical ProductionLine remains UUID-owned per Site, and no Site merge or physical identity synthesis is permitted.
- Historical source rows, site-address evidence, certificates' version scope and Case association remain inspectable after any migration.

## Proposed phased implementation (requires separate approval)

**P1 — Review:** corroborate the public assessment with Case 1023's source and confirm the Site 46 address transition; retain immutable evidence and review decisions, including the exact Certificate 376 correction separately.

**P2 — Expand:** add the two coverage tables in a reversible Alembic migration, with uniqueness and FK constraints; add domain validators and tests on a disposable PostgreSQL database. No auto-backfill or permissive fallback.

**P3 — Evidence-based backfill:** build a read-only plan and independently approve exact Case/Site and CertificateVersion/Site associations, based on source and regulatory evidence. Apply only with a sealed plan, target DB guard, backup, optimistic stale-state check, row assertions, transaction and audit trail. Do not touch `gxp_qlcl` or `gmpnn_ai`.

**P4 — Runtime convergence:** upgrade the link validator, effective certificate queries and Facility/Case/Certificate workspace projections together, preserving all Site-local scopes. Add adversarial test coverage for the Domesco pattern and unrelated Site mismatches, plus API/Search and Chromium tests. A runtime 409 is not considered fixed until verified against the test rehearsal database.

**P5 — Review/deploy:** CI evidence, owner decision, separate deployment authorization and post-deploy smoke checks. No implicit merge into main or database cutover.

## Code-owner compatibility review (11 October 2026; proposal only)

Current model and service owners examined at the audit branch HEAD:

- `backend/app/db/models/phase1.py`: `Case.site_id` and `Certificate.site_id` are non-null single-Site anchor FKs; `Certificate.case_id` is nullable; `CertificateVersion` is the version identity; `CertificateScope` is linked to a version but has **no Site FK**. `ProductionLine.site_id` owns canonical line identity within one Site. `CertificateRelationship` already constrains `REPLACED_BY` / `SUPERSEDED_BY`.
- `backend/app/services/workflow.py`: `_validate_certificate_linked_case`, `_certificate_valid_linked_case_sql`, and `_certificate_effective_line_sql` all encode same-Site/same-GxP Case ownership. Changing only the Python validator would leave inconsistent SQL semantics.
- `backend/app/services/catalog.py`: `_search_facilities_by_production_line` first validates **all** linked certificates; its projection then reads only `latest_flag=True` certificates and associates them with the single `Certificate.site_id`. An approved multi-Site model must explicitly update both search eligibility and Site-local certificate projection, including preservation of separately queryable historical versions. Skipping the global validator would not solve the missing Site coverage.

### Proposed minimum relational and evidence constraints

| Owner | Proposed key / integrity | Evidence and identity rule |
| --- | --- | --- |
| `CaseSiteCoverage` | FK to Case and Site; unique `(case_id, site_id)` for a reviewed coverage assertion | Inspecting a Site is proven by a reviewable source reference, not membership in the same Company. A review status alone is insufficient without provenance. |
| `CertificateVersionSiteCoverage` | FK to CertificateVersion and Site; unique `(certificate_version_id, site_id)` for each reviewed Site | Retain raw source Site label/address **as printed in that version**, separately from the current Site master address. |
| Scope-to-Site assignment | Explicit version-and-Site-bound association with `CertificateScope` or reviewed immutable Site-local scope fragments | Current `CertificateScope` contains version-wide text; do not parse headings at read time or duplicate undifferentiated scope as if applicable to every Site. |
| Replacement lineage | Existing CertificateRelationship with approved `REPLACED_BY` direction, reference and effective date | Keep regulatory certificate identities distinct; replacement does not imply a Site merge or a change in `latest_flag` by itself. |

Where a document-level `CertificateScope` includes multiple Site parts, the mapping should preserve the original text and cite the exact reviewed source passage/page. Whether to use a coverage-to-scope association table or immutable Site-local fragments is an **unresolved design choice**, not an implementation authorization. No automatic mapping from text headings is permitted.

### Proposed runtime compatibility rules (subject to approval)

1. Legacy single-Site records: keep the present same-Site/same-GxP linked-Case invariant.
2. Reviewed multi-Site records: require a reviewed Site membership on the originating Case **and** the relevant CertificateVersion, consistent GxP, explicit issuance-owner semantics, and an exact source evidence trail. A mere case anchor mismatch is not enough to qualify for an exception.
3. Unresolved cross-Site, missing Case, GxP mismatch, incomplete Site coverage, stale/unreviewed evidence: fail closed. Implement the same predicate in write validation, read validation and query builders rather than separate disagreeing rules.
4. Certificate projections: return the Site's own scope, version and source-address evidence, and distinguish `anchor_site_id` from `covered_site_ids`. Current vs historical versions must be explicit in API contracts.
5. ProductionLine: only link canonical UUIDs for the Site where that production line belongs. A multi-Site certificate cannot confer cross-Site UUID identity or authorize line-code synthesis.
6. Backfill: no guessing from `company_id`, document headings, Site names or historic addresses. Produce an immutable, source-referenced, reviewable plan before any migrations or business-data mutation.

The proposed migration must test both the Python linked-Case validator and SQL predicates with identical adversarial examples, including unrelated cross-company mismatch, legitimate two-Site scope, missing coverage rows and version-specific Site scopes. No coverage table or runtime change has been created by this review.

## Decision log required before code changes

The owner must approve (i) interpretation of current single-Site anchor FKs for multi-Site certificates, (ii) completeness rules connecting an originating Case to covered Sites, (iii) version-specific scope ownership, and (iv) acceptable evidence for historical Site identity/address changes. Until then this document is a proposal, not a new contract.
