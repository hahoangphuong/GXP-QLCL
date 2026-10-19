# Case / CertificateVersion multi-Site coverage — source-readiness gate

**Status:** DRAFT evidence-shape contract only; no schema, runtime, migration or data remediation authorization. Issue #6.

## Effective owner decision — future GMP is strictly one Case / one Site / one Certificate

**Approved by the business owner (18 October 2026):** for **new GMP issuance**, each originating Case is tied to exactly one Site and may issue **zero or one GMP Certificate**. The Certificate must carry that same Site. A second GMP Certificate may not be created from the same Case. A replacement for the same `MÃ DC` is a new Certificate identity, requiring its **own originating Case and single Site**, while retaining both historic certificates; a previous CertificateVersion is not overwritten to represent a replacement.

**This proposed multi-site evidence audit is HISTORICAL EXCEPTIONS ONLY.** It exists to preserve/reconcile imported 376, 1037 and 1180 (and other proven legacy anomalies). The multi-Site review structures **must never become an allowed prospective GMP issuance workflow**. The historical exception is evidence-bound; do not issue new multi-site certificates through those tables, and do not skip global integrity checks. The source-only readiness report does not grant any historical remediation or deployment authorization.

A Case may remain without any GMP Certificate if no certificate is issued. New-issuance guard is owned by the service issuance workflow; a legacy import must not retroactively be declared valid/invalid merely by its creation timestamp. Backdating an issue date cannot enable multi-Site or duplicate new issuance.

## Verified boundaries

- `Case.site_id` and `Certificate.site_id` remain source/import-era anchor FKs. They cannot substitute for complete physical-site inspection and certification coverage.
- `CaseSiteCoverage` is **proposed** inspection/evaluation membership, distinct from `CertificateVersionSiteCoverage` (**proposed** grant membership for one immutable version). Case membership does not itself grant a GMP certificate at that Site.
- `CertificateScope` today belongs to a CertificateVersion without per-Site binding; whole-document scope cannot simply be copied to every Site.
- A distinct later GMP certificate with the same reviewed `MÃ DC` is a **new Certificate identity**, not a rewrite of the earlier version. `CertificateRelationship.REPLACED_BY` exists; no approved or automatic population is made in this slice.
- Legacy workbook `db.ktra.ID CC GPs` is GMP-specific reverse issuance evidence. User established Case 380 issued GMP 376 and Case 378 did not. GMP 1037 and 1180 each certify both Site 46 and Site 298. These owner business statements do not authenticate Site-local source fragments or physical address identity.

## Pure source-readiness API

`backend/app/domain/certificate_site_coverage_readiness.py` exposes `audit_site_coverage_proposal`, accepting explicit owner-supplied Context, proposed CaseSite rows and proposed CertificateVersionSite rows. The structural checks insist upon:

- Exact Case, Certificate and Version identity consistency, including origin Case and GxP match.
- Explicit Site IDs and unique membership per owner: Case rows cannot be inferred from Company or `MÃ DC`; version rows cannot be inferred from Case/site anchors.
- SHA-256-shaped immutable source-document references and specific source locators for each assessed Site and each certified Site.
- Distinct reviewed **site-local evaluation scope digest** and **site-local certified scope fragment digest + locator**, rather than assigning an entire multi-site scope paragraph to every Site.
- Explicit original Site address **as shown on that CertificateVersion at issuance**, not the current address on the Site master. Differences between historical versions are retained, never normalized.
- Both original anchor Sites must be present in their corresponding proposed membership; uncertified, unproven or duplicate Sites produce explicit gaps.
- Where a proposed certified Site is absent from the proposed originating Case coverage, report a **review gap** rather than universally concluding that such a regulatory issuance must be invalid.

The report intentionally contains only error codes and aggregate Site counts. It does not echo original address strings, scope text, document bytes or credentials. It also does not verify that the alleged SHA-256 belongs to the actual document: all proof is **shape only**.

Even when the shape is `COMPLETE_FOR_DOMAIN_OWNER_REVIEW`, the returned `source_document_authenticity_verified`, `physical_site_identity_verified`, `site_scope_allocation_approved`, `case_rebinding_authorized` and `runtime_validator_change_authorized` remain **false**. Do not equate syntactic evidence with adjudication.

## Outstanding decisions before historical-only schema/runtime implementation

1. **Historical originating Case evidence only:** define how an imported historical Case with one anchor Site was proved to have evaluated several Sites; what original documents support each historical coverage assertion; and how unproven Site memberships fail closed. **No future multi-Site issuance is permitted.**
2. **Site historical identity:** independently reconcile Site 46's source address labels across 2022/2023. Do not collapse two Sites or infer relocation/renumbering from the same Company.
3. **Scope ownership:** approve normalized `CertificateVersionSiteCoverage` plus explicit `CertificateScope` fragment binding versus immutable reviewed Site-local scope fragments. Each solution must permit independent historical version and Site queries.
4. **GMP 376 remediation:** approve the exact row Case 380, preserving the conflicting original `db.cc.ID ĐỢT KTRA=378` literal and full audit/rollback provenance.
5. **Replacement:** approve exact `MÃ DC` group identities and ordering for 1037→1180; lineage may be represented by existing `CertificateRelationship`, but source chronological ordering alone is review evidence.

Only after a domain decision: design additive, reversible Alembic coverage tables, source evidence FKs, unique constraints, lifecycle protection, Python/SQL identical predicates, Facility/Search and Case/Certificate version-aware projections, adversarial PostgreSQL integration tests and approved exact-row reconciliation. A bare cross-Site association must continue HTTP 409. The authenticated read-only QA currently fails `facility-search` HTTP 409 against the **older deployed runtime**, which this source-only slice does not touch.

No VM deployment, actual DB/NAS/GCS write, import/rebind, backup/restore or nightly backup timer activation is authorized by this document or these tests.
