# GMP multi-site certificate coverage — source-bound decision contract

Status: **design/evidence gate only**, 01/11/2026. Owner: Issue #6. This document does not authorize migrations, historical Case relinking, or weakening the currently fail-closed HTTP 409 guard.

## Verified problem boundary

`Certificate.site_id` is the primary administrative Site, not a proven exhaustive list of manufacturing Sites covered by each certificate. A cross-site `Certificate.case_id` cannot be deemed valid merely because the company or GMP type matches. Current `_validate_certificate_linked_case` and `_certificate_valid_linked_case_sql` require identical primary Site; facility search evaluates all linked certificate records before filtering. This intentionally blocks unverified legacy relationships but means one invalid historical link can block a general read.

The original snapshot evidence in Issue #6 distinguishes: legacy certificate 376 (primary Site 73) references Case 378 (Site 72) while inspection Case 380 (Site 73) contains the reverse certificate number/reference; certificates 1037 and 1180 (primary Site 46) reference Case 1023 (Site 298), while certificate address text lists two Domesco manufacturing sites. These are **review candidates**, not authorized data corrections.

## Target domain model (proposed, NOT implemented)

Keep immutable canonical identities: `Certificate`, `CertificateVersion`, `Site`, `Case`, `ProductionLine`, and certificate relationships. Introduce a source-grounded, **version-scoped** association `CertificateCoveredSite` keyed by `certificate_version_id` + `site_id` with:

- `coverage_role`: primary / additional manufacturing Site, supported by source; do not infer from same company.
- `evidence_reference`: immutable reference to source document, page/section/address or a reviewed evidence record.
- `evidence_digest` and `decision_status`: proposed / verified / rejected / unresolved, with reviewer identity, decision time and rationale as auditable, immutable provenance.
- Explicit line scope association only if independently evidenced; production-line UUID must never be inferred from free-text line code.
- No backfill of additional covered Sites solely from matching company, name, address fragment, or legacy numeric ID.

A certificate with multiple versions may change coverage. A Site covered by an earlier version is not automatically covered by a later version. Historical records without review remain **unresolved**, never implicitly valid.

## Planned validation boundary

1. Same-Site Case link: existing strict GMP type and canonical line validation still apply.
2. Cross-Site Case link: allowed **only** with reviewed, positive, version-appropriate coverage evidence explicitly referencing the linked Case's Site and matching GxP type; do not treat proposed/unresolved coverage as true.
3. Wrong company / unrelated Site / unreviewed historical link: reject. Multi-site address text alone is not proof that the linked Case belongs to the certificate version.
4. Current-certificate promotion and `latest_flag` retain context isolation and Site locking; a covered Site is not a second owner of the primary certificate current flag.
5. Facility search must not silently omit invalid historical certificates. Any future change in read-query failure behavior requires a separately reviewed data-quality exposure contract (error details/quarantine), not a generic `try/except` rescue.

## Required acceptance fixtures before schema or importer change

| Fixture | Expected | Evidence |
|---|---|---|
| Same Site / GMP / valid line | Valid | Canonical Case and line identities |
| Cross Site, explicitly covered by reviewed version | Valid conditional on approved model | Signed/adjudicated source |
| Same company, no coverage evidence | Fail closed | No inference |
| Wrong company or wrong GxP type | Fail closed | Canonical mismatch |
| Cross Site covered only on obsolete version | Fail closed for latest version | Version-scoped coverage |
| Historical certificate 376 → 378 | Unresolved/rejected pending adjudication | Conflicting snapshot cross-references |
| Historical 1037/1180 → 1023 | Unresolved pending coverage+successor review | Two-site certificate address text |
| Multiple ProductionLines, same line code | Distinct contexts | Canonical UUID |
| Global facility search with unresolved historical link | Reproduces existing HTTP409; no silent skip | Disposable DB; current baseline |

## Controlled reconciliation sequence

1. Pin original legacy snapshot checksum, exported source certificate pages, full Case/inspection references and their Site identifiers.
2. Human adjudicates evidence and records version-specific covered Sites and legal/issuance relationship (including successor/amendment).
3. Implement additive schema and importer only after model approval; no mutation to original snapshot. Add forward/backward Alembic and reproducible test fixtures.
4. Update service and SQL predicates **together** to avoid inconsistent write/read semantics. Preserve new prospective `1 Case = 1 Site = 1 GMP Certificate` while modeling historical multi-site coverage as explicit scope, not multiple certificate owners.
5. Execute disposable PostgreSQL integration, wrong-site negative tests, migration dry-run and deterministic read/write/audit regression.
6. Rehearsal remediation requires separate authorized backup, reversible transaction, operator approval and logged source-to-row decision. Never mutate rehearsal or production during this engineering PR.
