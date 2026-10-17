# Regulatory Scope Lifecycle Contract

## Status And Boundary

`B6E_REGULATORY_SCOPE_LIFECYCLE_CONTRACT` remains the lifecycle source of
truth. B6G migration `20260929_0017` added the approved empty
`CaseScopePhase`/`CaseScopeRevision` expand-only schema, but no query,
importer, writer, API, frontend behavior, or legacy scope population. It is
still a separately approved future workflow slice.

ProductionLine identity is not a scope owner. B6E preserves the accepted B6D
contract: line identity/lineage and regulatory scope are separate, historical
owners are not rewritten, and merge/split scope allocation remains deferred.

## Authoritative Lifecycle Semantics

For one Case lifecycle, these are independent regulatory facts:

```text
REQUESTED -> scope requested by the company in its application
ASSESSED  -> scope accepted, narrowed, clarified, or otherwise defined by dossier assessment
INSPECTED -> scope actually inspected onsite
CONCLUDED -> scope finalized/recommended after inspection
```

`CERTIFIED` is not a Case phase. It is a separately owned snapshot on the
exact `CertificateVersion` that carries the certified scope. Whether a later
certification event belongs to a later version of the same `Certificate`
identity or version 1 of a new `Certificate` identity is deliberately outside
this lifecycle contract.

Adjacent phases must not be presumed equal. A valid lifecycle can be
`REQUESTED=S1`, `ASSESSED=S2`, `INSPECTED=S3`, `CONCLUDED=S4`, and
`CERTIFIED=S5`. A later reassessment of the same ProductionLine may establish
`REQUESTED=S6`, even when S6 is broader, narrower, or different from S5.

## Current Owner Inventory

| Current owner | Actual stored behavior | B6E lifecycle conclusion |
| --- | --- | --- |
| `CaseApplication` | Unique by `case_id`; contains submission date, dossier code/reference, and applicant name. It stores no structured or free-text regulatory scope. | No current requested-scope owner. |
| `CaseAssessment` | Unique by `case_id`; contains assessment date, assessor, result, and notes. It stores no regulatory scope. | No current assessed-scope owner. |
| `CaseEvaluationScope` | Unique by `case_id`; stores taxonomy version, source classification, raw legacy value, rendered prose, limitation, structured blocks, selections, and unkeyed entries. | One mutable Case aggregate, not a phase lifecycle. |
| `CaseEvaluationScopeBlock` | Ordered child of the single Case scope; stores block name/note/raw block text. | Existing structured-content shape worth reusing, not a phase owner. |
| `CaseEvaluationScopeSelection` | Ordered child of a block; stores taxonomy-node FK plus node and description snapshots. | Existing keyed-content shape worth reusing. |
| `CaseEvaluationScopeUnkeyedEntry` | Ordered child of a block; preserves unresolved/free-text legacy content. | Must remain preservable; it prevents treating all scope content as freely editable taxonomy data. |
| `InspectionOutcome` and `InspectionPlan` | One outcome/plan per Case, with timing, result/final evaluation, decision, minutes, and compliance fields. No scope aggregate or report-scope relation exists. | No current inspected or concluded scope owner. |
| `Certificate` | Certificate identity with optional Case link, Site, type, compatibility line text, issuance basis, and current flag. | Not the certified scope owner. |
| `CertificateVersion` | Versioned certificate data, unique by `(certificate_id, version_no)`, with `is_latest_version`. | Correct parent boundary for certified scope. |
| `CertificateScope` | Ordered text/key rows owned by `certificate_version_id`. | Existing certificate-version scope representation. |

No canonical inspection report/result model adds a second scope owner. Existing
inspection `final_evaluation` is an outcome/result field, not a regulatory
scope fact.

## Verified Current Behavior And Gaps

### Legacy import

Phase 2 aliases `db.ktra.PHẠM VI KIỂM TRA` to `evaluation_scope_raw`, parses
it with the evaluation-scope parser, and imports it as the unique
`CaseEvaluationScope` for the Case. The import contract does not assign a
requested, assessed, inspected, or concluded phase. Existing imports protect
the same Case against incompatible replacement, but this does not create a
multi-phase history.

Phase 2 aliases `db.cc.PHẠM VI CHỨNG NHẬN` to certificate scope text and
creates/collision-checks `CertificateScope` rows for the exact imported
`CertificateVersion`. The source also has a short certificate-scope column,
but the current canonical scope import uses the full certification-scope text.

Neither `CaseApplication` nor `CaseAssessment` has an imported scope source.
The inspected/concluded distinction has no phase-specific source owner in the
current import. Historical `PHẠM VI KIỂM TRA` is therefore classified as:

```text
LEGACY_SCOPE_PHASE_CLASSIFICATION = UNPHASED
legacy source class = LEGACY_UNPHASED_CASE_SCOPE
```

It must not be relabeled as requested, assessed, inspected, or concluded based
only on its Vietnamese header or adjacent timing columns.

### Current Case scope mutation

`CaseWorkflowService.upsert_evaluation_scope` permits an editable structured
scope only for a non-terminal Case with a `STRUCTURED_VALID` taxonomy-backed
aggregate. It applies optimistic concurrency to the scope row, deletes the
existing block/selection children, and writes replacement children. Imported
unkeyed entries keep the aggregate read-only because their VBA mutation
contract is not proven. This is a single mutable aggregate with an audit event,
not append-only phase history.

`create_inspection_case(..., source_case_id=...)` calls
`_copy_evaluation_scope_for_reassessment` after matching Site, GxP type, and
compatibility line text. It copies the old Case scope and every child into the
new Case. That is an implementation prefill/copy today; it does not establish
a distinct new requested fact and must not be interpreted as such.

### Current certificate mutation

`issue_certificate` creates `CertificateVersion(version_no=1)` and writes its
scope rows. `upsert_certificate_latest_version` then updates that latest
version and calls `_replace_certificate_scopes`, which deletes all existing
scope rows for that version and recreates the supplied payload. Promotion sets
`Certificate.latest_flag`; it does not create a new CertificateVersion or
freeze the candidate version's scope. Consequently the structural owner is
correct, but granted/historical scope immutability is not yet enforced.

### Current read/API/frontend behavior

The Case workspace exposes exactly one `evaluation_scope`; its editor calls
the replace-style Case scope mutation. Certificate details expose scopes for
the selected/latest version and the certificate UI submits an independently
editable list of scope rows. Catalog/search render certificate scope summaries
and line context, but they do not expose concurrent requested, assessed,
inspected, concluded, and certified scope facts. These are compatibility read
models, not lifecycle projections.

## Target Lifecycle Contract

### Event-owned Case facts

The future authoritative owner is a Case-owned regulatory-scope lifecycle
aggregate with append-only phase revisions. `CaseRegulatoryScopeSnapshot` is a
conceptual name only; B6E does not freeze table names or column names.

For every `(case_id, phase)` there is exactly one logical phase aggregate. A
phase aggregate has zero or more revisions, with at most one editable `DRAFT`
revision and zero or one current `ESTABLISHED` revision. Historical established
revisions remain immutable. Each aggregate has exactly one phase from:

```text
REQUESTED | ASSESSED | INSPECTED | CONCLUDED
```

Each revision retains an ordinal, establishment timestamp or date, source or
user action provenance, taxonomy version where applicable, rendered content,
and the structured content required to reproduce that revision. It derives
line context through its Case. B6E does **not** add a duplicate
`production_line_id` to the scope fact: doing so would create two sources of
truth while B6D's future `Case.production_line_id` remains the normalized
owner. Facility-wide Cases therefore remain valid; a scope fact has no line
unless its Case has one.

The preferred content direction is **B**: a phase/revision header plus the
existing block/selection/unkeyed-entry-shaped content beneath it. This reuses
the evaluated taxonomy snapshots, preserves unkeyed legacy content, and avoids
a competing incompatible scope serialization. Whether existing
`CaseEvaluationScope*` tables can be evolved or need a one-way migration is a
separate schema decision after the child-content audit and compatibility plan.

### Requested and assessed ownership

`REQUESTED` is a Case-owned scope fact established in the application
workflow. `CaseApplication` remains the submission metadata/event context; it
must not become a second independently writable scope owner. A request is not
inferred from a prior certificate or reassessment copy.

`ASSESSED` is a distinct Case-owned scope fact established by the assessment
workflow. `CaseAssessment` remains the assessment metadata/event context. It
must be written explicitly even if it equals the request, because equality is
not a business invariant.

### Inspected and concluded ownership

The authoritative business semantics require `INSPECTED` and `CONCLUDED` to
be independently representable: onsite activity can differ from final
conclusion/recommendation. Current code/source does not prove that they are the
same fact, so B6E does not collapse them. Inspection timing/result rows remain
their event context; neither is allowed to infer a scope from the other.

## Mutability, Revision, And Freeze Rules

The lifecycle uses the smallest required state distinction:

```text
DRAFT -> ESTABLISHED
ESTABLISHED -> SUPERSEDED_BY_CORRECTION (only through a new revision)
```

While a phase aggregate has a `DRAFT` revision, that one revision may be
edited under a scope-aggregate optimistic-concurrency token. Establishing a
phase freezes its current revision. A business correction creates a new
revision of the **same phase**, with reason, actor, timestamp, and explicit
supersession link; it never destructively replaces an established revision. A
later lifecycle phase uses a different phase aggregate and does **not**
supersede the prior phase aggregate.

The exact workflow event that establishes each phase must be approved with the
future write contract. Existing Case application/assessment/inspection services
do not currently own scope establishment transitions, so B6E does not invent a
larger status machine or claim that today's state transition freezes a scope.

For concurrency, the phase aggregate/revision header is the primary fence;
the Case row version is additionally checked only when the operation changes
Case-owned lifecycle context. Two users cannot establish competing revisions
of the same Case phase without an expected-version conflict. Child content is
mutated only while the enclosing draft is editable.

## Certificate Version Scope Contract

`CERTIFIED` is a CertificateVersion-owned snapshot created by a certification
event. The event may offer a reviewed seed from Case `CONCLUDED` scope, but it
creates certificate-owned content. It must preserve the source Case scope
revision/provenance and any issuance-time differences in its audit data; it
must not use a live FK as a dynamic certificate-scope view.

The future boundary is:

1. A draft candidate CertificateVersion may be edited under its version fence.
2. The action that grants/promotes the CertificateVersion establishes and
   freezes its scope snapshot.
3. A later certification event creates a new certified-scope owner. Whether
   that owner is a later `CertificateVersion` of the same certificate identity
   or version 1 of a new certificate identity is deferred to a dedicated
   certificate lifecycle/identity contract.
4. Correction/amendment may use a later CertificateVersion only if that future
   certificate contract proves the identity/version rule.
5. A historical/granted CertificateVersion never invokes replacement of its
   existing `CertificateScope` rows and never regenerates them from a Case or
   ProductionLine current scope.

This closes the current `_replace_certificate_scopes` gap without changing it
in B6E.

## Reassessment Semantics

For the same future ProductionLine identity, all regulatory facts coexist:

```text
Case 2026: REQUESTED -> ASSESSED -> INSPECTED -> CONCLUDED
Certification event 2026: exact CertificateVersion owns CERTIFIED S1

Case 2029: REQUESTED S2 -> ASSESSED -> INSPECTED -> CONCLUDED
Certification event 2029: exact CertificateVersion owns CERTIFIED S3
```

An old scope can be shown as a non-authoritative UI prefill/template, but the
new Case has no persisted `REQUESTED` fact until an authorized user or
workflow establishes it. Prefill provenance must be labelled separately from
the new fact; copying prior Case scope cannot silently establish S2.

## Read-Model Projections

The future read owner derives, but does not persist as a mutable line field:

| Projection | Deterministic owner/query boundary |
| --- | --- |
| Certified scope for a specified CertificateVersion | The exact CertificateVersion snapshot, with version, owner, phase, and establishment date. |
| Established requested scope for a specified Case | Current established `REQUESTED` revision for that exact Case and phase aggregate, with revision provenance. |
| Latest assessed scope for active Case | Latest established `ASSESSED` fact for that exact Case. |
| Latest inspected scope for active Case | Latest established `INSPECTED` fact for that exact Case. |
| Latest concluded scope for active Case | Latest established `CONCLUDED` fact for that exact Case. |

Every projection retains owner ID, phase, revision, lifecycle state, and
as-of/established provenance. A draft may be displayed as draft, but must not
be silently presented as an established phase fact. A global "current certified
scope" across certificate identities/versions for a ProductionLine, Site, or
GxP context is deferred: `latest_flag`, `is_latest_version`, issue date, and
expiry date alone are not a proven selector.

## Legacy And Compatibility Transition

Legacy imported `CaseEvaluationScope` remains preserved as
`LEGACY_UNPHASED_CASE_SCOPE`; it is not backfilled into a new phase. Imported
certificate scope remains a `CertificateVersion`-owned historical snapshot
candidate, but its grant/freeze status must be reconciled under the future
certificate lifecycle contract before mutation rules rely on it.

The staged transition is strictly one-way:

```text
legacy owner writable
        -> approved migration/cutover
new lifecycle owner writable
        -> compatibility READ projection/API adapter
```

There must never be two writable owners, lifecycle-to-legacy-table
synchronization, or legacy-writer-to-lifecycle-writer dual write. The existing
`CaseEvaluationScope` table may remain historical/source evidence, while API
and UI compatibility shapes are served by a read adapter. If a temporary
physical compatibility row is ever required, it is non-authoritative and needs
a separate migration contract; B6E does not authorize one.

## ProductionLine Transformation Boundary

For `A + C -> AC` or `AC -> X + Y`, a line transformation alone creates no
regulatory scope fact. A separately approved allocation workflow may inspect
historical certified facts, active Case facts, and an admin-authored candidate,
but the first AC/X/Y scope must be newly established under its own Case or
CertificateVersion owner. No union, copy, inverse replay, or text inference is
authorized here.

`SCOPE_MERGE_SPLIT_RULES = DEFERRED`

## Unresolved Business Questions

1. Which exact authorized workflow action establishes each Case phase, and is
   `INSPECTED` explicitly recorded separately from `CONCLUDED` in future
   source/process evidence?
2. What permitted draft-edit window applies to each Case phase before it is
   established?
3. Which correction authority/permission and retention rule applies to a
   superseding revision?
4. What certificate identity/version lifecycle selects a global current
   certified snapshot when more than one certificate/version may be
   historically valid for a ProductionLine, Site, or GxP context?
5. Can historical imported certificate versions be proven granted, or must
   they remain immutable compatibility evidence pending a distinct
   reconciliation classification?
6. What approved migration maps any legacy `PHẠM VI KIỂM TRA` record into a
   phase, if source evidence beyond the current unphased field becomes
   available?

## Final Markers

```text
B6E_V2_CONTRACT = PASS
PRODUCTION_LINE_SCOPE_OWNER = NO
CASE_SCOPE_PHASE_AGGREGATE = ONE_PER_CASE_AND_PHASE
CASE_SCOPE_REVISIONS = VERSIONED
ESTABLISHED_SCOPE_DESTRUCTIVE_OVERWRITE = NO
CERTIFIED_SCOPE_OWNER = CERTIFICATE_VERSION
CERTIFICATE_RENEWAL_IDENTITY_RULE = DEFERRED
CERTIFICATE_REASSESSMENT_IDENTITY_RULE = DEFERRED
CURRENT_CERTIFIED_SCOPE_SELECTOR = DEFERRED
COMPATIBILITY_WRITE_DIRECTION = NEW_OWNER_ONLY
LEGACY_SCOPE_PHASE_CLASSIFICATION = UNPHASED
SCOPE_MERGE_SPLIT_RULES = DEFERRED
ALEMBIC_MIGRATION_CREATED = NO
DATABASE_MUTATED = false
stage = false
commit = false
push = false
deploy = false
```
