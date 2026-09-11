# Inspection Case Lifecycle — Canonical Business Owner Matrix

## Purpose

This document records the product-owner-confirmed business lifecycle for an inspection case and reconciles it against the current PostgreSQL domain model.

It is a **business semantic contract**, not a claim that every field is already present in the current schema or that every legacy VBA/database column has already been migrated correctly.

The confirmed workflow is user-authored transactional data entered over the lifetime of one inspection case. These values must not be treated as derived display prose merely because the legacy VBA later renders them into bookmarks/documents.

## Confirmed lifecycle

The user creates one case and progressively enters:

1. Application intake
   - dossier code;
   - submission date.
2. Initial dossier assessment
   - assessment date;
   - assessment result;
   - assessor.
3. Inspection authorization/planning
   - inspection decision reference/number (QĐKT);
   - inspection decision date.
4. Inspection execution
   - inspection date;
   - inspection report-written date;
   - inspectors/team members;
   - applicable standard;
   - inspection-result assessment.
5. Corrective-action/CAPA follow-up, round 1 and round 2
   - incoming correspondence/reference number;
   - submission date;
   - assessment date;
   - assessor.
6. Final case disposition
   - final inspection evaluation;
   - compliance/re-inspection deadline.
7. Approval routing
   - vice-chair (PCT) submission/reference number + date;
   - chair (CT) submission/reference number + date.
8. Certification
   - certificate number;
   - certificate issue date;
   - certificate expiry/valid-until date.

## Canonical owner matrix

| Lifecycle field | Current model | Classification | Canonical direction |
|---|---|---|---|
| Dossier code | `CaseApplication.dossier_code` | `OWNER_PROVEN_EXISTING` | Use directly as canonical business owner. |
| Application submission date | `CaseApplication.submitted_on` | `OWNER_PROVEN_EXISTING` | Use directly; UI/API should write structured datetime/date according to final API contract. |
| Initial assessment date | `CaseAssessment.assessed_on` | `OWNER_PROVEN_EXISTING` | Use directly. |
| Initial assessment result | `CaseAssessment.assessment_result` | `OWNER_PROVEN_EXISTING` | Use directly. |
| Initial assessor | `CaseAssessment.assessor_name` | `OWNER_PROVEN_EXISTING` | Existing string owner is sufficient for compatibility; future user/profile linkage may be additive. |
| QĐKT reference | `InspectionPlan.decision_document_hint` only; legacy compatibility also writes to `InspectionOutcome.decision_reference` | `OWNER_NEEDS_MODEL_EXTENSION` | Planning/authorization owner must hold structured `decision_reference`; do not use outcome compatibility projection as source of truth. |
| QĐKT date | none on planning owner | `OWNER_NEEDS_MODEL_EXTENSION` | Add structured `decision_date` on planning/authorization owner. |
| Raw legacy QĐKT composite text | no canonical owner | `OWNER_NEEDS_MODEL_EXTENSION` | Optional audit/compatibility field only; never semantic truth once structured ref/date exist. |
| Inspection date | `InspectionOutcome.inspected_on` | `OWNER_PROVEN_EXISTING` | Current field is semantically usable for actual inspection start/date. |
| Inspection report-written date | none identified | `OWNER_NEEDS_MODEL_EXTENSION` | Add explicit `report_written_on` to inspection-result/outcome owner. |
| Inspectors/team | `InspectionTeam`, `InspectionTeamMember` | `OWNER_PROVEN_EXISTING` | Ordered members via `sort_order`; `role_label` owns role text. Legacy `display_text` is presentation compatibility only. |
| Applicable standard | `Case.applicable_standard` | `OWNER_PROVEN_EXISTING` | Use directly. |
| Inspection-result assessment | `InspectionOutcome.outcome_result` | `OWNER_PROVEN_EXISTING_WITH_NAMING_REVIEW` | Semantics match post-inspection assessment; keep distinct from initial `CaseAssessment`. Consider clearer API naming, not duplicate storage. |
| CAPA round number | `CapaCycle.round_no` | `OWNER_PROVEN_EXISTING` | Use `1`, `2`, ...; do not create separate tables for round 1/2. |
| CAPA incoming correspondence/reference number | none identified on `CapaCycle` | `OWNER_NEEDS_MODEL_EXTENSION` | Add structured `incoming_reference` (name may be finalized during migration review). |
| CAPA submission date | `CapaCycle.submitted_on` | `OWNER_PROVEN_EXISTING` | Use directly. |
| CAPA assessment date | `CapaCycle.assessed_on` | `OWNER_PROVEN_EXISTING` | Use directly. |
| CAPA assessor | `CapaCycle.assessor_name` / `assessor_user_id` | `OWNER_PROVEN_EXISTING` | Prefer user FK when available, retain name snapshot for historical rendering. |
| CAPA result | `CapaCycle.result` | `OWNER_PROVEN_EXISTING` | Use when the round itself has an assessment result. |
| Final inspection evaluation | no distinct canonical field identified | `OWNER_NEEDS_MODEL_EXTENSION` | Keep distinct from ordinary inspection-result assessment; add explicit final-disposition field on case/outcome finalization owner. |
| Compliance/re-inspection deadline | no distinct canonical field identified | `OWNER_NEEDS_MODEL_EXTENSION` | Add structured date such as `compliance_due_on`; do not store only in notes/prose. |
| PCT submission/reference number + date | no dedicated structured owner | `OWNER_NEEDS_NEW_ENTITY` | Model as an approval-routing record, not two case columns. |
| CT submission/reference number + date | no dedicated structured owner | `OWNER_NEEDS_NEW_ENTITY` | Same approval-routing entity with a stage/type discriminator. |
| Certificate number | `CertificateVersion.certificate_number` | `OWNER_PROVEN_EXISTING` | Use directly. |
| Certificate issue date | `CertificateVersion.issue_date` | `OWNER_PROVEN_EXISTING` | Use directly. |
| Certificate expiry/valid-until | `CertificateVersion.expiry_date` | `OWNER_PROVEN_EXISTING` | Use directly. |

## Required model changes — consolidated candidate

The business contract now supports designing the schema delta in one coherent migration rather than adding fields one at a time.

### 1. Extend `InspectionPlan`

Preferred conceptual additions:

```text
inspection_plan.decision_reference
inspection_plan.decision_date
inspection_plan.decision_raw_legacy_text   # optional audit/compatibility only
```

`decision_document_hint` may remain for compatibility until migration cleanup, but it should not be the long-term semantic owner if it contains only a hint/raw display value.

The importer currently copying the legacy `Q. định` raw value to `InspectionOutcome.decision_reference` and `CaseApplication.dossier_reference` must be treated as compatibility behavior. A future migration/importer change should parse/fail-close into the planning owner rather than preserving that duplication as canonical truth.

### 2. Extend `InspectionOutcome` (or create a tightly scoped finalization companion only if ownership becomes too broad)

Preferred conceptual additions:

```text
inspection_outcome.report_written_on
inspection_outcome.final_evaluation
inspection_outcome.compliance_due_on
```

`outcome_result` remains the ordinary post-inspection result/assessment. `final_evaluation` is intentionally separate because the product owner confirmed a later final evaluation after CAPA processing.

Do not overload `notes`, `InspectionEvent.payload`, or another prose field to avoid a migration.

### 3. Extend `CapaCycle`

Preferred conceptual addition:

```text
capa_cycle.incoming_reference
```

Existing fields already cover repeated rounds:

```text
round_no
submitted_on
assessed_on
assessor_user_id
assessor_name
result
status
```

This means CAPA round 1 and round 2 should remain rows of the same entity rather than separate round-specific columns/tables.

### 4. Add a generic approval-routing entity

Do **not** add four fixed columns such as `pct_reference`, `pct_date`, `ct_reference`, `ct_date` to the case.

Preferred conceptual model:

```text
InspectionApprovalSubmission
- id
- case_id
- stage                 # VICE_CHAIR / CHAIR; extensible enum or controlled code
- reference_number
- submitted_on
- sort_order            # optional if workflow order must be explicit
- notes                 # optional non-semantic supplementary note only
```

Suggested uniqueness:

```text
UNIQUE(case_id, stage)
```

unless later business rules prove multiple submissions per stage are valid. If resubmission history is possible, use a sequence/version instead of forcing uniqueness by stage.

## Legacy/importer implications

The existing legacy importer must not be used as proof of semantic ownership merely because it currently fills a similarly named modern field.

Known example:

- legacy `Q. định` is presently copied into `InspectionOutcome.decision_reference`;
- the same legacy value is also copied into `CaseApplication.dossier_reference`;
- the business owner confirmed that the legacy UI value is a user-authored QĐKT composite input containing decision reference + decision date.

Therefore future importer work should:

1. preserve the raw legacy value for audit;
2. parse the reference/date only under a proven grammar;
3. fail closed when the composite cannot be parsed unambiguously;
4. populate the planning decision owner;
5. stop treating compatibility copies as canonical semantic truth after migration/cutover.

## API/UI implications

New UI should not reproduce the VBA combined-text pattern where structured values are known.

Use separate inputs for at least:

- QĐKT reference;
- QĐKT date;
- CAPA incoming reference;
- CAPA submitted/assessed dates;
- final evaluation;
- compliance deadline;
- approval-routing reference/date per stage;
- certificate number/issue/expiry dates.

The backend payload should be typed around lifecycle owners, not around Word bookmark names.

## Read-only legacy morphology overlay

The real workbook profile is recorded in
`artifacts/legacy_audit/inspection_case_lifecycle_legacy_profile.json` and is
diagnostic evidence only. Its exact source header for `bbkt_reference` is
`db.ktra.B. bản`; its profile is timestamp-dominant, so the canonical runtime
name must not be treated as proof that this is a BBKT reference. `decision_reference` has 1,289 deterministic
reference-plus-trailing-date shapes, 26 without a trailing date, 16 `-`
sentinels, 7 multi-reference forms, and 4 invalid date-like forms. This is a
composite requiring split, not a backfill authorization.

The migration-safety values below are a human-reviewed static audit
conclusion, not an automatic classifier derived from the aggregate counts.
The profile records this provenance explicitly as
`migration_safety_basis = human_reviewed_static_audit_conclusion`; morphology
counts and normalized-domain counts are supporting evidence only.

| Field | Safe aggregate finding | Migration safety |
|---|---|---|
| `decision_reference` | composite reference/date; exceptional and multi-reference forms | `COMPOSITE_REQUIRES_SPLIT` |
| `bbkt_reference` | timestamp-dominant despite canonical name | `OWNER_MISMATCH` |
| `inspected_at` | 936 date ranges, 477 ISO timestamps, 11 multi-date values, 59 empty values, 58 sentinels, and 1 invalid/other value | `AMBIGUOUS` |
| `submitted_at` | 875 empty, including 489 `-`; multi-date forms exist | `INSUFFICIENT_SOURCE` |
| `dossier_code` | 400 `-`; multi-code morphology exists | `AMBIGUOUS` |
| `applicable_standard` | normalized domain is finite but has multi-value exceptions | `SAFE_WITH_DETERMINISTIC_NORMALIZATION` |
| `inspection_type` | normalized domain is finite but has composite exceptions | `SAFE_WITH_DETERMINISTIC_NORMALIZATION` |
| `certificate_number` | 62 `???` and heterogeneous identifier forms | `AMBIGUOUS` |
| `certificate_issue_date` | 42 `???`, one malformed non-date form | `SAFE_WITH_DETERMINISTIC_NORMALIZATION` |
| `certificate_expiry_date` | partial dates such as `9-9` and mixed annotations | `AMBIGUOUS` |

No raw business values are persisted in the profile and no backfill is
allowed by this overlay.

## Readiness decision for `INSPECTION_QD_KT`

This lifecycle matrix materially closes the business-owner question for QĐKT and the surrounding case workflow, but it does **not** by itself authorize document-generation readiness.

Before changing `BUSINESS_INPUT_CONTRACT_MISSING`, the QĐKT document payload still needs:

1. exact template logical-field reconciliation;
2. rendering contract for team ordering/conditional deletion;
3. facility/location display projection contracts (`Tencoso`, `Diadiem`, `Diadiemx`, `Diachicoso`);
4. explicit schema/importer implementation for QĐKT reference/date if the typed document path depends on the new structured owner.

## Migration discipline

When implementation starts, prefer one reviewed schema migration containing the coherent lifecycle delta rather than serial migrations that add one discovered field at a time.

Before migration:

- freeze this owner matrix;
- inspect real legacy value morphologies and null rates;
- define parse/fail-closed rules for composite legacy QĐKT and any other combined legacy cells;
- define backfill diagnostics and conflict handling;
- preserve immutable raw legacy evidence until acceptance.

Do not mutate production data merely to make document generation pass.
