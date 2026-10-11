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
- Existing import default remains compatible with historical source until there is an **approved** disposition for the three conflicts. This is **not** a remediation, release, or authorization to cut over.
- No changes were made to runtime Certificate–Case validation or to canonical ProductionLine UUID identity.

Local source-only verification command:

```bash
python -m tools.audit_legacy_certificate_case_sources \
  --snapshot artifacts/phase3c/legacy_snapshot.json \
  --output /tmp/gxp-certificate-case-audit.json --strict
```

Expected on current unremediated legacy source: exit code **2**, **three** effective anomalies, no database access. Avoid writing a report onto an existing approved evidence file.

## Remaining business decisions and implementation gates

1. **Certificate 376:** verify original issuance provenance/case reference (candidate Case 380). An authorized remediation would need a sealed source+canonical-state plan, verified target rehearsal DB, backup, exact row assertions, transactional update, audit and rollback. Do not directly overwrite the historical `db.cc` source.
2. **Domesco 1037/1180:** inspect authentic certificate/inspection scope and identify whether one regulatory certificate has *multiple covered Site identities*. If supported, design separate, evidence-backed Certificate/Site coverage and Case/Site coverage concepts rather than treating a shared company ID as a surrogate Site FK. Domain schema/read contracts require separate review.
3. **Only after adjudication:** enforce the corrected import invariant by default for the future cutover, backfill or remediate the existing three canonical rows with approved plans, then execute integration tests and search/workspace smoke tests. Confirm canonical ProductionLine UUID preservation.
4. Do not deploy or mutate `gxp_legacy_rehearsal`, `gxp_qlcl`, or `gmpnn_ai` as part of this audit. Existing site filtering must not be weakened to turn HTTP 409 into an apparently successful search.

The current documented state remains **Search Facilities FAIL HTTP 409** until a separate, reviewed remediation release is proven in runtime.
