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
- Source-audit parity safeguard: standalone `--strict` also returns exit code 2 for duplicate `db.cc` source row identities (`source_identity_anomalies`), even when their Case/Site/GxP links are individually valid or the row key is in the exclusion contract. This mirrors the importer's pre-schema `_validate_snapshot_source_keys` failure without altering effective source classifications or legacy import behavior.
- Existing import default remains compatible with historical source until there is an **approved** disposition for the three conflicts. This is **not** a remediation, release, or authorization to cut over.
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
