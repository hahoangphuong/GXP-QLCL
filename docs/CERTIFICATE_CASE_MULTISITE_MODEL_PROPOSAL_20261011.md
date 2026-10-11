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

## Decision log required before code changes

The owner must approve (i) interpretation of current single-Site anchor FKs for multi-Site certificates, (ii) completeness rules connecting an originating Case to covered Sites, (iii) version-specific scope ownership, and (iv) acceptable evidence for historical Site identity/address changes. Until then this document is a proposal, not a new contract.
