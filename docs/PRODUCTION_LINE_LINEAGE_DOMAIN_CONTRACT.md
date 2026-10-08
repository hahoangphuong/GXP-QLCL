# Production Line Lineage Domain Contract

## Status And Boundary

`B6D_PRODUCTION_LINE_LINEAGE_DOMAIN_CONTRACT` is the semantic source of truth
for the first-class production-line slice. B6G migration `20260929_0017`
implemented the approved expand-only ORM/schema foundation; its tables and
nullable ownership FKs remain empty. B6G introduced no API endpoint, runtime
writer, data migration, or compatibility-field replacement.

Scope allocation for evaluation and certification is expressly outside this
contract:

`SCOPE_MERGE_SPLIT_RULES = DEFERRED_TO_SEPARATE_BUSINESS_CONTRACT`

## Evidence And Current Representation

### Canonical fields

`ProductionLine`, `ProductionLineTransformation`, and
`ProductionLineTransformationMember` now exist as empty B6G schema owners.
The two current text fields carrying line-like compatibility context are:

| Owner | Field | Current source mapping | Current meaning and limitation |
| --- | --- | --- | --- |
| `Case` | `scope_code: String(32)` | `db.ktra.MÃ DC` via `phase2_import.py` | Compatibility/provenance text. The current system presents it as a production-line context, but it has no immutable identity, lifecycle, or lineage. |
| `Certificate` | `line_code: String(32)` | `db.cc.MÃ DC` via `phase2_import.py` | Compatibility/provenance text. It can differ from its linked Case and currently takes precedence in certificate read contexts. |

The importer preserves source text without declaring it a first-class line:

- `backend/app/domain/phase2_import.py`: aliases `MÃ DC` as `scope_code`,
  writes `Case.scope_code`, and writes `Certificate.line_code`.
- `backend/app/db/models/phase1.py`: the fields remain nullable strings. B6G
  adds nullable `production_line_id` FKs, but no populated identity, runtime
  writer, lifecycle, or lineage is inferred from the text.
- `tools/profile_legacy_semantics.py`: classifies `MÃ DC -> Case.scope_code`
  as `OWNER_COMPATIBILITY_ONLY`.

Source-only Snapshot V2 evidence is insufficient to bootstrap canonical lines
without an approved migration plan:

| Sheet / field | Source rows | Substantive values | Distinct normalized text values | Proven fact |
| --- | ---: | ---: | ---: | --- |
| `db.ktra.MÃ DC` | 1,549 | 1,360 | 6 | Single-letter-shaped tokens occur, but no name, lifecycle, ancestry, or uniqueness contract is supplied. |
| `db.cc.MÃ DC` | 1,632 | 1,381 | 6 | Same lexical shape only; this does not prove that a certificate token identifies the same business object as a Case token. |
| `db.cso.MA CS GMP/GLP/GMPbb` | 380 each | 303 / 54 / 22 | numeric site codes | Site identifiers, not production-line identifiers. |
| `db.cty.MA CTY GMP/GLP/GMPbb` | 333 each | 257 / 53 / 22 | numeric company codes | Company identifiers, not production-line identifiers. |

`db.ktra.MÃ DC 2` is also present in the source inventory, but the current
importer does not map it to a canonical field. It must not be treated as an
implicit second member of a production line.

### Current consumers

| Surface / exact owner | Existing behavior | B6D consequence |
| --- | --- | --- |
| `backend/app/services/workflow.py:CaseWorkflowService` | Normalizes `line_code`, finds open Cases by `Case.scope_code`, and creates reassessment Cases with the selected text copied to `scope_code`. | Future create/reassessment operations must select an active `ProductionLine` and store its UUID; text matching is transitional only. |
| `backend/app/services/catalog.py:CatalogReadService` | Groups facility contexts by normalized `Case.scope_code`; `_certificate_line_code` returns `Certificate.line_code` before falling back to linked Case `scope_code`. | The precedence fallback is a legacy display rule, not lineage. It must be retired only after an explicit compatibility projection is available. |
| `backend/app/api/routers/catalog.py` and `backend/app/read_models.py` | Facility workspace and certificate endpoints accept/return `line_code`; a non-null text value is labelled `production_line`; context keys include it. | Existing public read contracts remain compatibility contracts until a versioned ProductionLine projection is introduced. |
| `backend/app/api/routers/workflow.py` | The reassessment payload exposes a string `line_code` to the workflow owner. | A future request must submit a production-line UUID and row-version token, not an inferred text code. |
| `frontend/src/pages/SearchPage.tsx`, `frontend/src/features/search/*`, `frontend/src/types.ts`, and `frontend/src/lib/api.ts` | Send `line_code` query parameters, show `Dây chuyền`, and retain the text in client context keys. | The frontend must not derive merge/split ancestry or active status from strings. A future projection must provide UUID, code, lifecycle, and action readiness. |
| `CaseEvaluationScope` tables and `CaseWorkflowService.upsert_evaluation_scope` | Scope is owned by `case_id`, with blocks and selections owned below it. | No scope is currently line-owned. A merge/split must not union or redistribute these rows under this contract. |
| `CertificateScope` table and certificate read models | Scope is owned by `certificate_version_id`. | No scope is currently line-owned. A merge/split must not union or split these rows under this contract. |
| `backend/app/domain/legacy_certificate_linkage.py` and B6C planner | Matches legacy inspection/certificate evidence by legacy IDs, site, GxP type, and existing Case relationship. | It remains one legacy certificate to one historical source context. B6D adds no many-to-many certificate linkage and does not relink B6C records. |

The existing Phase 2, Phase 9, and Phase 10 test suites deliberately exercise both line-scoped (`A`, `B`,
`C`) and facility-wide (`None`) contexts. It also demonstrates that a
certificate's direct line text can disagree with its linked Case text. That is
evidence that matching text is not a safe identity or lineage mechanism.

### GxP dimension is not yet an identity key

The current workflow and catalog context is explicitly the tuple `Site + GxP
type + normalized line text`: reassessment availability/open-case lookup filters
`Case.site_id`, `Case.gxp_type`, and `Case.scope_code`; certificate context
lookup similarly filters Site, certificate type, and `line_code`. This is a
compatibility and regulatory-context lookup, not evidence that GxP is either
part of, or independent from, physical production-line identity.

Read-only Snapshot V2 morphology provides the following bounded observation:

| Source | Eligible substantive rows | Distinct `(legacy Site ID, GxP, MÃ DC)` tuples | Distinct `(legacy Site ID, MÃ DC)` tuples | Observed same Site/code with multiple GxP values |
| --- | ---: | ---: | ---: | ---: |
| `db.ktra` | 1,360 | 386 | 386 | 0 |
| `db.cc` joined through `ID ĐỢT KTRA -> db.ktra.ID` | 1,355 | 361 | 361 | 0 |

The six observed substantive codes are `A` through `F`. Twenty-five `db.cc`
rows with substantive line text could not be joined to a usable `db.ktra`
parent and are not treated as contrary or supporting identity evidence. Zero
observed multi-GxP Site/code combinations does **not** prove that text equality
denotes one physical line. Neither source exposes a separate physical-line
identifier, roster, or lifecycle key. Therefore:

```text
PRODUCTION_LINE_GXP_DIMENSION = NOT_PROVEN
```

The initial schema must not freeze either `(site_id, normalized_code)` or
`(site_id, gxp_type, normalized_code)` as the identity uniqueness key until an
approved physical-line roster resolves this question. In particular, B6D does
not add `gxp_type` merely because current compatibility queries use it.

## Regulatory Scope Is Event-Owned, Not Line-Owned

`ProductionLine` identity and regulatory scope are distinct concepts. A line
can remain the same identity while its scope changes through a requested
application, assessment, inspection/conclusion, and certification. Those
facts can differ and can coexist. Consequently the B6D target schema
intentionally has **no** mutable `ProductionLine.scope` field, and no future
read model may derive a historical certificate's scope from a line's current
state.

### Existing scope-owner inventory

| Regulatory fact | Current owner and evidence | Phase / preservation conclusion |
| --- | --- | --- |
| Requested application scope | `CaseApplication` records submission metadata only; it has no structured scope field. | Missing owner. Requested scope is not represented as a distinct fact. |
| Assessed scope | `CaseAssessment` records assessment metadata/result/notes only; it has no structured scope field. | Missing owner. Assessment scope is not represented as a distinct fact. |
| Inspection/concluded scope | One `CaseEvaluationScope` is unique by `case_id`, with taxonomy, rendered prose, raw legacy value, blocks, selections, and unkeyed entries. Phase 2 imports `db.ktra.PHẠM VI KIỂM TRA` into it. | A structured Case-owned aggregate exists, but its business phase is `NOT_PROVEN`: the source/import contract does not distinguish requested, assessed, inspected, or concluded scope. It is insufficient as a multi-phase lifecycle owner. |
| Certified scope | `CertificateScope` belongs to `CertificateVersion`, and Phase 2 creates/collision-checks source scopes under that version. | Version-specific structural owner exists. Historical snapshot immutability is nevertheless required: current `upsert_certificate_latest_version` uses `_replace_certificate_scopes` to delete and recreate scopes on the latest version. |

`CaseWorkflowService.upsert_evaluation_scope` updates the one
`CaseEvaluationScope` in place: it replaces child blocks/selections and
increments the Case scope row version. This is appropriate only for a
single-owner compatibility aggregate. It cannot preserve separate requested,
assessed, inspected, and concluded facts within one Case.

Reassessment currently copies the prior `CaseEvaluationScope` into a new Case
when site, GxP type, and normalized compatibility line text agree. That is a
seed for a new Case, not proof that the copied value is the new request,
assessment, inspection, or certificate scope. An unchanged line can therefore
have historical certified scope `S1` and a later reassessment scope `S2`; both
must remain event-specific records and must not overwrite each other.

### Certificate snapshot rule

`CertificateScope` is already attached to a particular `CertificateVersion`,
which is the correct owner boundary for certified scope. The future contract
must make a granted/historical version immutable: correction or renewal creates
a later `CertificateVersion` and its own scopes, rather than replacing the
scopes of the historical version. A draft/ungranted version may have an
explicitly authorized editing lifecycle, but that lifecycle must not permit a
historical certificate to dynamically read a current `ProductionLine` scope.

### Recommended future scope-version model

No B6D schema is created. The recommended follow-up is a separately approved
event-owned version model:

1. Retain certificate scope as a `CertificateVersion` snapshot and harden its
   granted/historical immutability contract.
2. Introduce an append-only Case-owned regulatory-scope snapshot/fact for
   each proven Case phase, at minimum `REQUESTED`, `ASSESSED`,
   `INSPECTED`, and `CONCLUDED`, with phase ordinal/version, establishment
   date, source/taxonomy provenance, and structured scope content.
3. Each Case fact references the relevant `ProductionLine` identity but does
   not make the line the owner of the scope. Cross-owner polymorphic foreign
   keys are not approved by this design; any common abstraction requires its
   own schema decision.
4. Read models may derive explicit views such as current certified scope or
   pending assessed scope only from persisted event facts, their lifecycle,
   and their stated as-of time. They must label the fact phase and owner.

This recommendation deliberately does not define automatic scope allocation
for a merge or split. A transformation changes line identity/lifecycle only;
it cannot union, copy, split, or infer event-owned regulatory scope.

## Target Relational Contract

### ProductionLine

`ProductionLine` is a Site-scoped immutable identity. Its UUID, not its code,
is the technical identity.

| Field | Contract |
| --- | --- |
| `id` | UUID primary key. |
| `site_id` | Required FK to `Site`; a line cannot cross sites. |
| `code` | Required business code, validated/normalized by the domain owner but never parsed to infer ancestry. |
| `display_name` | Optional current human-readable name. |
| `effective_from` | Required `Date`, inclusive. |
| `effective_to` | Nullable `Date`, exclusive. A predecessor closed by a transformation effective on `D` has `effective_to = D`; an output has `effective_from = D`. |
| `created_at`, `updated_at`, `row_version` | Standard timestamp and optimistic-concurrency contract. |

No code uniqueness constraint is proposed in B6D. The `Site + code` and
`Site + GxP + code` alternatives are both deferred behind the unresolved
physical-identity evidence gate above. A future roster-backed contract must
also decide whether and how a retired code may be reused.

The active-at-date predicate is deterministic:

```text
effective_from <= as_of
AND (effective_to IS NULL OR as_of < effective_to)
```

This half-open interval makes an input inactive and an output active at the
start of the same effective date. It is the sole owner of historical activity;
there is no stored `ACTIVE`/`SUPERSEDED` status that can override the interval.
An operational "active now" projection uses this same predicate with the
authoritative current business date and transformation records only.

For example:

```text
A:  effective_from = 2020-01-01, effective_to = 2027-01-01
AC: effective_from = 2027-01-01, effective_to = null

as_of 2026-12-31: A active,   AC inactive
as_of 2027-01-01: A inactive, AC active
```

### ProductionLineTransformation

`ProductionLineTransformation` records a graph event, rather than an edge
stored on a line:

| Field | Contract |
| --- | --- |
| `id` | UUID primary key. |
| `site_id` | Required FK to `Site`; independently checked against every participant. |
| `transformation_type` | `MERGE` or `SPLIT`; extensible to future `N_TO_M` only through an approved enum change. |
| `effective_on` | Required `Date`; drives the half-open lifecycle boundary. Operational service requires the authoritative current business date exactly; a historical migration may use another date only under its separate approved contract. |
| `reason` | Required nonblank business reason. |
| `created_by` | Required FK to the authenticated admin actor. |
| `created_at`, `updated_at`, `row_version` | Audit and optimistic-concurrency fields. |

`ProductionLineTransformationMember` is the participant relation:

| Field | Contract |
| --- | --- |
| `transformation_id` | Required FK. |
| `production_line_id` | Required FK. |
| `role` | `INPUT` or `OUTPUT`. |
| `ordinal` | Positive deterministic order for audit/display only; it has no semantic inference role. |

Required database-level shape constraints in the later schema slice include a
unique `(transformation_id, production_line_id)`, a unique
`(transformation_id, role, ordinal)`, and a positive ordinal. Aggregate
cardinality, same-site validation, new-output identity validation, no cycles,
and temporal overlap require the transactional domain owner because they span
multiple rows/tables.

## Transformation Invariants

The future admin service is the single owner of every rule below; read models,
frontend code, importers, and writers must not reimplement them.

1. Every participant and the transformation have the same `site_id`.
2. `MERGE` has at least two `INPUT` members and exactly one `OUTPUT` member.
3. `SPLIT` has exactly one `INPUT` member and at least two `OUTPUT` members.
4. Outputs are newly created ProductionLine UUIDs, never reactivated inputs.
5. Inputs receive `effective_to = effective_on`; outputs receive
   `effective_from = effective_on`. The interval is lifecycle truth.
6. A line active at the effective date cannot be an `INPUT` in another
   overlapping active transformation.
7. An attempted edge that makes an output reachable from itself is rejected;
   the lineage graph is a directed acyclic graph, not a hierarchy.
8. Existing Case, Certificate, evaluation-scope, certification-scope, CAPA,
   change, report, and document rows retain their original owner. No historical
   owner FK is rewritten during a transformation.
9. Each `Case.production_line_id` and `Certificate.production_line_id` will
   be at most one FK in the target model, subject to a separately approved
   nullable/bootstrap rule. Neither FK is unique: one `ProductionLine` has
   many historical/reassessment Cases and many Certificates over its lifetime.
   A merge output is one line identity; neither association needs a
   many-to-many table.
10. A transformation is all-or-nothing, concurrency-protected, and emits a
    structured audit event containing actor, reason, effective date, input and
    output UUID sets, and transformation UUID.

### Case and certificate ownership cardinality

`Case` and `Certificate` are children of a line identity, not one-to-one
extensions of it. Once the separately approved nullable/bootstrap decision is
made, each individual child has at most one line FK, while a line has many
children across its lifetime. Reassessment is therefore another Case for the
same line identity, not a reason to create a duplicate line:

```text
ProductionLine A
  -> Case 2025
  -> Case 2028 reassessment
  -> Case 2031 reassessment

ProductionLine A
  -> Certificate 2025
  -> Certificate 2028
  -> Certificate 2031
```

After `A + C -> AC`, future Cases and Certificates are associated with new
identity `AC`; the historical children remain associated with `A` or `C`.

## Future Administrative Operations

### Merge: N inputs to one new identity

1. Admin selects at least two lines active on the authoritative current
   business date at one Site.
2. The service locks every selected line and checks row versions.
3. It validates Site equality, active status, interval overlap, and DAG safety.
4. Admin supplies a new output code/name and reason. The service derives, or
   validates an explicitly supplied value against, `effective_on = current
   business date`; it rejects past and future dates.
5. The service creates a new output `ProductionLine`, transformation, and
   ordered input/output members.
6. It closes inputs and activates the output at the same date boundary.
7. It writes an audit event and commits one transaction.

`A + C -> AC` therefore creates a new UUID for `AC`. `A` and `C` remain
immutable historical identities and never become live child members of `AC`.

### Split: one input to N new identities

1. Admin selects one line active on the authoritative current business date
   and locks it with its row version.
2. Admin supplies two or more new output identities, codes/names, effective
   date, and reason.
3. The service derives/validates the same current-business-date
   `effective_on`, then repeats the Site, lifecycle, interval, DAG, audit,
   and atomicity checks as merge.
4. It creates the new outputs, closes the input, and commits atomically.

`AC -> X + Y` is a new forward transformation. The service never reads the
code `AC` to reconstruct `A` and `C`, nor does it auto-restore predecessors.

The first operational implementation has no retroactive or scheduled
transformation mode:

```text
OPERATIONAL_TRANSFORMATION_RETROACTIVE = NO
OPERATIONAL_TRANSFORMATION_FUTURE_SCHEDULED = NO
HISTORICAL_MIGRATION_EFFECTIVE_DATES = SEPARATE_CONTRACT
```

This prevents an output becoming operationally active before its event and
prevents current administration from rewriting interval history. A later
legacy/bootstrap migration may establish historical intervals only through its
own approved reconciliation contract; B6D creates neither that migration nor a
scheduler.

## Current State, History, And Scope Boundaries

For a selected `AC` line, current line state is only data explicitly owned by
`AC`: identity, lifecycle, and transformation metadata. Regulatory-scope
views are event-owned and must name their Case or CertificateVersion owner,
phase, and as-of context. The system must never construct a scope view by
unioning prior `A` and `C` scopes.

A future lineage-aware history projection may traverse predecessor and
successor graph events and present original-owner labels, for example:

```text
original_line_id, original_line_code, event_type, occurred_on, payload
```

Traversal is graph traversal with visited UUIDs, a bounded direction, and an
explicit time ordering. It must not turn ancestor events into current state or
allow an ancestor's descendants/siblings to contaminate a selected line.
Operational selectors show active lines only by default; admin history views
may include superseded lines and transformation events.

Evaluation-scope and certification-scope allocation is intentionally deferred:

- a merge may require newly authored event-owned output facts only under a
  separately approved scope contract;
- predecessor scopes stay historical;
- a split requires admin-controlled allocation to each output;
- no automatic union, copy, inverse replay, or textual-code inference is
  authorized by this contract.

## Legacy Transition Strategy

No B6D importer or migration is authorized yet. A future source-only planning
step must classify every proposed legacy association without creating lines:

| Classification | Required evidence / outcome |
| --- | --- |
| `DETERMINISTIC_SINGLE_LINE` | One approved Site-scoped source code maps to exactly one explicitly planned new `ProductionLine`; preserve source field and row provenance. |
| `MISSING_LINE` | Blank, sentinel, or absent legacy text; no inferred line. |
| `AMBIGUOUS_CODE` | One code could identify multiple planned lines, or source cannot select a single Site-scoped identity; block. |
| `CASE_CERTIFICATE_CODE_INCONSISTENT` | Existing Case and Certificate compatibility texts disagree; preserve both values and block automatic ownership assignment. |
| `CODE_REUSED_ACROSS_SITES` | Text repeats at different Sites; never globalize it. Site-scoped mapping may be possible only with approved evidence. |
| `POTENTIALLY_HISTORICAL_OR_OBSOLETE` | A source value is known only from historical records or has no approved current identity; preserve as provenance and do not activate it. |

The plan must retain raw/source-safe provenance and distinguish legacy Case and
Certificate text. It must not parse `AC` into `A` and `C`, infer transformations
from chronology, or change B6C certificate linkage cardinality.

## Authorization, Audit, And Rollout Gates

Merge/split are admin-only future operations. Their endpoint/service contract
will require database-backed authorization, a nonblank reason, actor identity,
input/output row-version fences, and structured before/after audit data. Normal
workflow users may select only active lines and cannot perform transformations.

Before any schema implementation, a follow-up must separately approve:

1. the exact `ProductionLine` and transformation migration;
2. legacy bootstrap plan and reconciliation results;
3. API/read-model versioning and frontend migration off `line_code` text;
4. scope allocation rules; and
5. admin authorization/audit tests, concurrency tests, cycle tests, and
   transition rollback tests.

## Unresolved Business Questions

The following require explicit business evidence before a migration or writer:

1. Is every nonblank legacy `MÃ DC` value a production-line identity, or do
   some values denote a broader inspection/certification scope?
2. What approved roster gives each initial Site-scoped line its name, active
   state, effective date, and allowed GxP contexts?
3. Are facility-wide records (`scope_code`/`line_code` null) intentionally
   outside ProductionLine ownership, or must they be assigned through a
   separate administrative decision?
4. How should a Case/Certificate text disagreement be adjudicated for an
   initial bootstrap, if it must be linked at all?
5. Does the business require code reuse after retirement? The proposed initial
   schema key is deferred until this is answered together with the physical
   identity/GxP question.
6. Which admin role/permission name is the database-backed authority for merge
   and split, and what retention policy applies to transformation audit events?
7. Which source/evidence identifies the requested, assessed, inspected, and
   concluded scope phase for historical records that currently collapse into
   one `CaseEvaluationScope`?
8. What grants a certificate version its immutable historical status, and what
   draft-edit lifecycle is permitted before that boundary?

## B6C Compatibility Statement

B6C certificate-linkage evidence remains pre-merge historical evidence. The
current read-only B6C result includes exact links, representation-only GxP
differences, one duplicate-source certificate reference, and source-missing or
unresolved records; none authorizes a relationship rewrite. Its
read-only result does not authorize changing any `Certificate.case_id`, source
link, or scope. B6D will not make B6C linkage many-to-many: one Certificate
will eventually reference at most one `ProductionLine`, while historical
source records retain their original context.

## Explicit Non-Goals

- No `ProductionLine` model, table, migration, importer, endpoint, or writer.
- No database access or mutation.
- No automatic merge/split of evaluation or certification scopes.
- No historical Case/Certificate owner rewrite.
- No frontend-local state or string parsing as lineage authority.

## B6D Scope-Aware Design Conclusion

```text
PRODUCTION_LINE_IDENTITY_SCOPE_SEPARATED = YES
PRODUCTION_LINE_SCOPE_MUTABLE_SINGLE_FIELD = NO
CASE_SCOPE_PHASE_MODEL = INSUFFICIENT
CERTIFICATE_SCOPE_HISTORICAL_SNAPSHOT = REQUIRED
REASSESSMENT_SCOPE_VERSIONING = REQUIRED
SCOPE_MERGE_SPLIT_RULES = DEFERRED
```

## B6D V2 Contract Markers

```text
B6D_V2_CONTRACT = PASS
FIRST_CLASS_PRODUCTION_LINE_REQUIRED = YES
CASE_TO_PRODUCTION_LINE = MANY_TO_ONE
CERTIFICATE_TO_PRODUCTION_LINE = MANY_TO_ONE
CASE_HAS_SINGLE_LINE_OWNER = YES
CERTIFICATE_HAS_SINGLE_LINE_OWNER = YES
HISTORICAL_ACTIVITY_OWNER = EFFECTIVE_INTERVAL
OPERATIONAL_TRANSFORMATION_RETROACTIVE = NO
OPERATIONAL_TRANSFORMATION_FUTURE_SCHEDULED = NO
PRODUCTION_LINE_GXP_DIMENSION = NOT_PROVEN
PRODUCTION_LINE_IDENTITY_SCOPE_SEPARATED = YES
CASE_SCOPE_PHASE_MODEL = INSUFFICIENT
CERTIFICATE_SCOPE_HISTORICAL_SNAPSHOT = REQUIRED
REASSESSMENT_SCOPE_VERSIONING = REQUIRED
SCOPE_MERGE_SPLIT_RULES = DEFERRED
ALEMBIC_MIGRATION_CREATED = NO
DATABASE_MUTATED = false
stage = false
commit = false
push = false
deploy = false
```
