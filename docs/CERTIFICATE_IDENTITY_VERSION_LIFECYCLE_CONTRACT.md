# Certificate Identity And Version Lifecycle Contract

## Status And Boundary

`B6F_CERTIFICATE_IDENTITY_VERSION_LIFECYCLE_CONTRACT` remains the semantic
source of truth. B6G migration `20260929_0017` added the approved expand-only
`CertificateRelationship` schema and nullable Certificate production-line FK,
but no database access, importer, writer, API, frontend behavior, certificate
runtime change, B6C linkage change, or populated relationship.

It resolves the ownership boundary required by B6D/B6E: a `Certificate` is a
regulatory certificate identity; a `CertificateVersion` is a revision of that
one identity; and certified scope belongs immutably to the exact version that
carries it. It does not make ProductionLine a scope owner.

## Current Schema And Runtime Inventory

| Current owner/field | Verified behavior | B6F conclusion |
| --- | --- | --- |
| `Certificate` | Has unique optional `legacy_certificate_id`, optional `case_id`, required `site_id` and `certificate_type`, compatibility `line_code`, `issuance_basis`, `latest_flag`, and scalar `latest_legacy_certificate_id`. | Present certificate identity container, but no explicit relationship/freeze semantics. |
| `Certificate.case_id` | Phase 2 derives it from `db.cc.ID ĐỢT KTRA`; case-backed runtime issuance receives a Case and writes it when creating the Certificate. No current version-level originating-Case field exists. | Sufficient for the approved contract: all versions retain this immutable originating Case. |
| `CertificateVersion` | Unique `(certificate_id, version_no)` with dates/number/standard/authority and `is_latest_version`. | Technical revision container; neither version state nor grant/freeze state is persisted. |
| `CertificateScope` | Ordered rows owned by `certificate_version_id`. | Correct certified-scope ownership boundary. |
| `latest_flag` / `is_latest_version` | Runtime promotion flips `Certificate.latest_flag` among rows selected by Site and certificate type. `_load_latest_certificate_version` prefers `is_latest_version` then max version number. | Technical/read compatibility flags, not a proven regulatory effective-certificate selector. |
| `latest_legacy_certificate_id` | Scalar integer field, no FK or relation. Phase 2 uses `parse_int` against `db.cc.ID MỚI NHẤT`. | No canonical replacement relation; source values do not currently parse to legacy integer IDs. |
| `issuance_basis` | Runtime accepts `inspection_case` with required Case/type match, or `administrative_no_inspection` without a Case. | Proven issuance context, not certificate identity/replacement semantics. |

### Current workflow

`issue_certificate` creates a new `Certificate` identity and one
`CertificateVersion(version_no=1)`, then writes CertificateScope rows.
`upsert_certificate_latest_version` mutates that latest version and uses
`_replace_certificate_scopes`, deleting and recreating its scopes. Promotion
sets the Certificate-level `latest_flag`, emits an inspection event for a
linked Case, and does not create a version or freeze scope content.

No current workflow creates version 2, clones a Certificate, records a
Certificate-to-Certificate replacement edge, or changes a Certificate's
`case_id`. These are current-runtime gaps; the approved target identity rule
for reassessment and renewal is defined below.

Catalog's current selection and status are compatibility behavior: it filters
by Site/type and ranks rows by `latest_flag`, issue date, expiry date, and
update timestamp; status derives from expiry and `latest_flag`. It does not
model grant, revocation, withdrawal, replacement lineage, or a ProductionLine
identity. It cannot be promoted to canonical effective-certificate semantics.

## Legacy Source Evidence

The authoritative Snapshot V2 `db.cc` morphology is read-only evidence:

| Evidence | Observed result | What it proves / does not prove |
| --- | ---: | --- |
| Source data rows | 1,632 | Legacy certificate rows, not automatically canonical identities or versions. |
| Valid distinct legacy `ID` values | 1,621 / 1,621 | No duplicate legacy ID in this source extraction. |
| Substantive Case link / Site / type / line / certificate number | 1,459 / 1,602 / 1,603 / 1,381 / 1,539 | Row-level source context exists, with gaps. |
| GxP types | GMP 1,493; GLP 87; GMPbb 20; GSP 3 | Regulatory type context, not identity lineage. |
| `MỚI NHẤT` marker | 468 `o`; 1,164 blank/sentinel | A display/current marker exists, but no regulatory definition is proven. |
| Nonblank `ID MỚI NHẤT` | 468 text values; zero parse as legacy integer IDs | Not a usable source key for a canonical replacement edge under current parser. |
| Repeated substantive certificate numbers | 354 number groups / 915 rows; maximum repetition 6 | Repetition alone cannot prove same identity, a revision, renewal, or duplicate. |
| Date morphology | Issue: 1,538 numeric Excel serials, 42 sentinels, 51 null, 1 other. Expiry: 1,525 numeric serials, 4 partial numeric pairs, 13 other, 90 null. | Date fields provide timing evidence only; they do not establish identity/replacement lineage. |

Phase 2 imports every accepted `db.cc` row as a separate `Certificate` with
`CertificateVersion(1)` and maps the full `PHẠM VI CHỨNG NHẬN` into that
version's scope. It does not infer versions/replacements from duplicate
certificate number, chronology, `MỚI NHẤT`, or `ID MỚI NHẤT`. B6C's
`ID CC GPs` linkage remains evidence that connects inspection references to
these current Certificate identities; B6F does not relink or collapse it.

## Canonical Identity Rule

### Certificate identity

A Certificate identity represents one regulatory issuance identity. It has an
immutable originating Case when case-backed, Site, GxP/type, issuance basis,
and future ProductionLine owner valid at issuance. The identity retains all
historical ownership; it is never rewritten to point at a later reassessment
Case or a post-transformation ProductionLine.

### CertificateVersion

A CertificateVersion is a revision of the same regulatory certificate
identity, not a generic bucket for every later certificate event. A version is
appropriate only when the business rule proves that the regulatory act is a
correction/amendment of the same identity. Every version retains the
Certificate's immutable originating Case and ProductionLine ownership.
Cross-Case and cross-ProductionLine CertificateVersion creation are not
authorized by this contract.

### New identity

A new Certificate identity is required for a distinct issuance, explicit
replacement/reissue, periodic reassessment certification, or renewal following
a new regulatory evaluation. Each reassessment/renewal has its new
application-to-Case lifecycle and successful certification creates the new
Certificate with `CertificateVersion(1)`. A special administrative extension
without a new regulatory issuance is outside this contract and requires its
own event contract. Identity is never inferred from certificate number, dates,
Site, GxP text, or a display flag.

## Draft, Grant, And Freeze Lifecycle

The minimal future version lifecycle is:

```text
DRAFT -> GRANTED -> immutable
```

Draft edits and corrections before grant remain on the same draft version under
the version concurrency fence. Grant establishes the version's regulatory
content and freezes every field relevant to issuance plus its CertificateScope
rows. `_replace_certificate_scopes` must be forbidden for a granted version.

Post-grant correction is
`SAME_CERTIFICATE_NEW_VERSION_WHEN_SAME_IDENTITY_PROVEN`: an authorized
same-identity correction creates a later version, while the prior granted
version remains immutable. A distinct issuance, reassessment, renewal after a
new evaluation, or replacement creates a new Certificate identity. No
destructive overwrite after grant is permitted in either case.

## Replacement And Supersession Lineage

The future target needs an explicit, normalized Certificate identity relation
when a business event proves a relationship:

```text
CertificateRelationship
  source_certificate_id
  target_certificate_id
  relation_type
  effective_on
  reason
  audit/provenance
```

The relation is explicit, directional, auditable, and acyclic. Its initial
taxonomy must distinguish at least `SUPERSEDED_BY` and `REPLACED_BY`, without
over-expanding relation types in this batch. It preserves both identities and
their exact versions/scopes. It must never be inferred from chronology,
matching certificate number, `latest_flag`, `MỚI NHẤT`, or
`latest_legacy_certificate_id`. A new reassessment/renewal Certificate may
supersede a prior identity only where the approved business event explicitly
establishes that edge.

At the time a future relation is written, its domain owner validates whatever
Site, GxP/type, ProductionLine, and issuance-basis compatibility the approved
event type requires. B6F does not presume every replacement has identical
context, because B6D's physical-line/GxP key remains unresolved. The legacy
scalar `latest_legacy_certificate_id` is not sufficient source evidence for a
canonical relation and requires separate reconciliation if ever used.

## Case And ProductionLine Ownership

For the current schema, `Certificate.case_id` is the source inspection Case on
import and the immutable originating Case on case-backed issuance. It must
never be rewritten to a later reassessment Case. Reassessment and renewal
after a new evaluation create a new Certificate identity, which references the
new Case while the prior identity retains the earlier Case. Cross-Case
CertificateVersion creation is not authorized; consequently no
`CertificateVersion.case_id` is required or recommended by this contract.

In B6D's future model, each Certificate identity has one ProductionLine owner
valid at issuance. Historical certificates of A/C stay with A/C after
`A + C -> AC`; later certification creates a new Certificate owned by AC. A
CertificateVersion cannot cross a ProductionLine transformation.

## Effective Certificate And Certified Scope Projections

Two selectors are distinct:

| Projection | B6F contract |
| --- | --- |
| Latest version of a specified Certificate | Technical identity-local selection; a current implementation may use `is_latest_version`/version number, but it is not a global effective certificate rule. |
| Certified scope for a specified CertificateVersion | Deterministic: use that exact version's immutable CertificateScope snapshot. |
| Current effective Certificate for a ProductionLine/Site/GxP context | Partially designed: requires a granted version, relevant Site/GxP/ProductionLine context, no explicit effective successor, and applicable effective/expiry timing. Revocation, withdrawal, and suspension semantics remain unresolved. |
| Current certified scope for a ProductionLine/Site/GxP context | Partially designed: scope of the exact immutable CertificateVersion selected by the effective-certificate lifecycle. It remains incomplete until revocation, withdrawal, and suspension semantics are approved. |

No projection persists a mutable `ProductionLine.scope`. `latest_flag`,
`is_latest_version`, issue date, expiry date, and not-expired status cannot
individually select current regulatory truth.

## Reassessment, Renewal, And Correction Decisions

| Event class | B6F result | Required future discriminator |
| --- | --- | --- |
| Draft edit/correction before grant | Same draft CertificateVersion. | Draft state and version fence. |
| Administrative correction after grant | Same Certificate, new version only when same identity is proven. | Explicit same-identity proof; otherwise a new issuance identity. |
| Explicit reissue/replacement | New Certificate identity with explicit relation. | Authorized replacement event and relation evidence. |
| Renewal after a new regulatory evaluation | New Certificate with Version 1. | New regulatory evaluation/issuance event. |
| Periodic reassessment | New Certificate with Version 1. | New application and Case lifecycle. |
| Scope expansion/reduction after reassessment | New Certificate with Version 1. | New reassessment certification; never a mutable granted scope edit. |

## Migration, Audit, And Compatibility Implications

Historical imported Certificate and CertificateScope records remain
read-only compatibility evidence. Version ownership is structurally known, but
whether each imported version was formally granted/frozen is not proven and
must not be altered merely to fit the future lifecycle.

Any future migration must preserve original Case, certificate identity, version,
scope, raw/source provenance, actor/action evidence where available, and any
explicit replacement relation. It must classify ambiguous legacy identity
signals as unresolved rather than collapse rows. B6F authorizes no mutation,
backfill, scope rewrite, or B6C reinterpretation.

Future issuance/grant/replacement writes require actor, timestamp, reason,
originating Case, version concurrency fence, scope provenance, before/after
audit data, and explicit relationship evidence. A granted version cannot be
destructively updated.

## Unresolved Business Questions

1. What regulatory evidence proves that a post-grant correction remains the
   same Certificate identity rather than a new issuance?
2. Which legal event defines an explicit replacement/reissue relation, and
   which context differences are permitted across that edge?
3. Which lifecycle states/evidence define grant, withdrawal, revocation,
   suspension, and expiration for effective-certificate selection?
4. Can `db.cc.ID MỚI NHẤT` be reconciled to an authoritative source key, or is
   it only legacy display text?

## Final Markers

```text
B6F_V2_CONTRACT = PASS
CERTIFICATE_VERSION_SCOPE_OWNER = YES
GRANTED_VERSION_MUTABLE = NO
REASSESSMENT_CERTIFICATE_RULE = NEW_CERTIFICATE
RENEWAL_CERTIFICATE_RULE = NEW_CERTIFICATE
POST_GRANT_CORRECTION_RULE = SAME_CERTIFICATE_NEW_VERSION_WHEN_SAME_IDENTITY_PROVEN
CERTIFICATE_CASE_OWNER_MODEL = SUFFICIENT_FOR_CURRENT_CONTRACT
CROSS_CASE_CERTIFICATE_VERSIONING = NOT_AUTHORIZED
CROSS_PRODUCTION_LINE_CERTIFICATE_VERSIONING = NOT_AUTHORIZED
CERTIFICATE_REPLACEMENT_RELATION = REQUIRED
CURRENT_EFFECTIVE_CERTIFICATE_SELECTOR = PARTIALLY_DESIGNED
CURRENT_CERTIFIED_SCOPE_SELECTOR = PARTIALLY_DESIGNED
PRODUCTION_LINE_SCOPE_OWNER = NO
ALEMBIC_MIGRATION_CREATED = NO
DATABASE_MUTATED = false
stage = false
commit = false
push = false
deploy = false
```
