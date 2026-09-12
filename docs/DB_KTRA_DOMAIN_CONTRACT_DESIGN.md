# db.ktra Canonical Domain Contract (Design v1)

**Status:** design-only. This document implements no database, API, importer, or runtime behavior.

## Audit conclusion

The existing model already provides the correct aggregate roots for most facts: `CaseAssessment`, `InspectionPlan`, `InspectionOutcome`, `InspectionTeam`, `InspectionTeamMember`, `CapaCycle`, and `Certificate`. The new design extends those owners instead of introducing duplicate case state. `CapaCycle` remains CAPA-specific; approval submissions are a separate repeated event stream.

Current importer paths are semantically contaminated: `db.ktra.Kết quả` is written to both assessment and outcome, `Q. định` is copied into application/outcome compatibility fields, and `B. bản` is held as an untyped reference. Those rows require future read-only reconciliation; this design authorizes no repair.

The discovery inventory records `B. bản` as 1,391 non-empty valid-row values: 1 single-date morphology, 6 multi-date/period values, and 1,152 text values, with 152 empty and 232 dash sentinels. It proves neither a timezone nor a safe universal timestamp parser. The typed contract therefore retains a date and optional local time separately and preserves raw text whenever precision or parsing is incomplete. `role_label` is currently free text (`lead`, `member`, `chair`, and Vietnamese display labels occur in source/tests), so it is not a safe normalized role owner.

## Canonical Owners

| Fact | Owner | Decision |
| --- | --- | --- |
| Dossier assessment result | `CaseAssessment.assessment_result` | Reuse; its source must be a proven dossier-assessment source, never `db.ktra.Kết quả`. |
| Actual inspection result | `InspectionOutcome.outcome_result` | Reuse; the sole target of `db.ktra.Kết quả`. |
| Final post-CAPA conclusion | `InspectionOutcome.final_evaluation` | Add field; distinct from the initial result. |
| Decision number/date | `InspectionPlan.decision_reference`, `InspectionPlan.decision_date` | Add split fields; preserve raw composite source. |
| Minutes/report record date/time | `InspectionOutcome.minutes_recorded_on`, `minutes_recorded_time` | Add source-faithful date plus optional local time. Date-only source stays date-only; no timezone is fabricated; raw input is preserved where parsing is unsafe. |
| Inspection team | `InspectionTeam` / `InspectionTeamMember` | Reuse; strengthen ordering and role contract. |
| PCT/CT rounds | `InspectionApprovalSubmission` | Add entity; do not overload `CapaCycle`. |
| Compliance deadline | `InspectionOutcome.compliance_due_on` | Add informational-only date field. |
| Resulting certificate | `Certificate.case_id` + `Certificate.legacy_certificate_id` | Reuse relation; source row cardinality is 0..1. |

## Schema Change Plan

| Classification | Table/entity | Proposed change | Constraints and compatibility |
| --- | --- | --- |
| `REUSE_EXISTING` | `case_assessment` | Keep `assessment_result TEXT NULL`. | Only its proper source may write it. |
| `REUSE_EXISTING` | `inspection_outcome` | Keep `outcome_result TEXT NULL`. | `db.ktra.Kết quả` maps here only. |
| `ADD_FIELD` | `inspection_outcome` | `final_evaluation TEXT NULL`. | Explicit finalization mutation only; never aliases `outcome_result`. |
| `ADD_FIELD` | `inspection_plan` | `decision_reference VARCHAR(255) NULL`, `decision_date DATE NULL`, `decision_legacy_raw TEXT NULL`. | Index `(case_id)` already unique through plan ownership; raw field importer-only. |
| `ADD_FIELD` | `inspection_outcome` | `minutes_recorded_on DATE NULL`, `minutes_recorded_time TIME NULL`, `minutes_legacy_raw TEXT NULL`. | `CHECK(minutes_recorded_time IS NULL OR minutes_recorded_on IS NOT NULL)`. Runtime writes typed date plus optional local time; raw evidence is importer-only. No timezone, UTC conversion, midnight, or time is fabricated from date-only source. |
| `ADD_FIELD` | `inspection_outcome` | `compliance_due_on DATE NULL`. | No scheduled job, reminder, task, transition, overdue state, or automatic inspection creation. |
| `ADD_FIELD` | `inspection_team_member` | `role_code VARCHAR(16) NOT NULL`; retain `role_label VARCHAR(128) NULL` as display-only compatibility. | `CHECK(role_code IN ('LEADER','SECRETARY','MEMBER'))`, `UNIQUE(team_id, sort_order)`, `CHECK(sort_order >= 1)`, and `CHECK((inspector_profile_id IS NOT NULL) <> (person_id IS NOT NULL))`. `role_code` is canonical; runtime validates LEADER/1, SECRETARY/2, MEMBER/3+. |
| `ADD_ENTITY` | `inspection_approval_submission` | `id UUID PK`, `case_id UUID NOT NULL FK case.id`, `stage VARCHAR(3) NOT NULL`, `round_no INTEGER NOT NULL`, `reference VARCHAR(255) NULL`, `submitted_on DATE NULL`, `submitted_time TIME NULL`, `completed_on DATE NULL`, `completed_time TIME NULL`, `pct_submission_id UUID NULL FK inspection_approval_submission.id`, `legacy_raw_source TEXT NULL`, timestamps and `row_version INTEGER NOT NULL`. | `UNIQUE(case_id, stage, round_no)`, indexes `(case_id, stage, round_no)` and `(pct_submission_id)`, `CHECK(round_no >= 1)`, `CHECK(stage IN ('PCT','CT'))`, `CHECK(submitted_time IS NULL OR submitted_on IS NOT NULL)`, `CHECK(completed_time IS NULL OR completed_on IS NOT NULL)`, `CHECK((stage = 'PCT' AND pct_submission_id IS NULL) OR (stage = 'CT' AND pct_submission_id IS NOT NULL))`. There is no status column. Service verifies a CT parent is same-case PCT with `completed_on IS NOT NULL`. |
| `REUSE_EXISTING` | `certificate` | Keep `certificate.case_id` and unique `legacy_certificate_id`. | No junction. A legacy row can resolve to zero or one certificate; lifecycle versions/latest state are separate concepts. |
| `DEPRECATE_COMPATIBILITY` | `inspection_outcome.bbkt_reference`, `inspection_outcome.decision_reference`, `case_application.dossier_reference`, `inspection_plan.decision_document_hint` | Retain read-only historical display. | No new `db.ktra` importer or runtime write uses these fields as semantic targets. |

`InspectionApprovalSubmission` is intentionally independent of `CapaCycle`: CAPA rounds and approval rounds have different ownership and cardinality. There is no speculative approval status machine. `completed_on` is the sole canonical completion fact; `completed_time` adds only source-proven local precision. A CT record has a required parent PCT submission; service validation proves same case, PCT stage, and non-null parent `completed_on`. PCT itself has no parent, and a completed PCT never requires CT. Completion requires `expected_version`, is auditable, and cannot later be cleared; a PCT with CT children cannot have its completion fact altered.

## API and Mutation Contract

All proposed mutations are additive extensions of `CaseWorkflowService`, authorization, audit events, and optimistic `expected_version` behavior already used by workflow routes. A readiness/read projection is advisory; mutation handlers enforce the same rules.

| Slice | Read model | Write contract | Failure contract |
| --- | --- | --- | --- |
| C | Outcome projection exposes `outcome_result` and `final_evaluation` separately; assessment remains separate. | Existing `PUT /cases/{case_id}/outcome` writes only actual result. Proposed `POST /cases/{case_id}/outcome/finalize` writes final evaluation. | `409` stale version; `422` finalization before applicable CAPA terminal evidence; `403` authorization. |
| D | Plan exposes split decision fields plus a provenance indicator, never treats raw composite as canonical. | Extend `PUT /cases/{case_id}/plan` with `decision_reference`, `decision_date`. | `409` stale version; `422` invalid typed value. Runtime clients cannot write `decision_legacy_raw`. |
| E | Outcome exposes `minutes_recorded_on` and optional `minutes_recorded_time`; team projection returns `role_code`, optional display `role_label`, ordered members, and read-only `display_text`. | Extend outcome PUT for typed date plus optional local time; team PUT accepts exactly one resolved identity, `role_code`, and `sort_order`. | `422` time without date, duplicate/gapped/invalid order, role-order mismatch, or dual/missing identity; unresolved legacy identity has no runtime mutation shortcut. |
| F | Outcome exposes informational `compliance_due_on`; approval list returns all stages, rounds, and explicit completion facts. | Extend outcome PUT for deadline. Proposed approval create and explicit complete routes use expected row versions. | `422` CT without a completed same-case PCT, invalid parent/stage/round, or time without its date; no automation is triggered by deadline storage. |
| G | Case/certificate read models show exact linked certificate provenance separately from latest version. | Existing certificate owner remains sole writer. | `409` certificate concurrency/duplicate rules; `422` non-exact or incompatible linkage. |

Compatibility fields are never writable through new typed contracts. Legacy raw evidence is importer-only metadata and must not become a free-form runtime editing channel.

## Legacy Migration and Reconciliation

All future migration work begins with a read-only planner. It classifies each fact independently and preserves raw source when a lossless typed conversion is not proven.

| Source fact | Classification rule | Prohibited shortcut |
| --- | --- | --- |
| `Kết quả` | `SAFE_DIRECT` to `InspectionOutcome.outcome_result` only with deterministic case identity; prior `CaseAssessment` value is `BLOCKED_EXISTING_CANONICAL_CONFLICT`. | Treating it as dossier assessment. |
| `Q. định` | `SAFE_SPLIT` only for one proven reference and one proven date; otherwise `BLOCKED_PARSE`. | Copying composite string to application/outcome fields. |
| `B. bản` | `SAFE_DIRECT`/`SAFE_SPLIT` only to minutes-recorded metadata; otherwise `BLOCKED_PARSE`. | Using it for actual inspection dates. |
| Team | `SAFE_ORDERED_EXPANSION` if all names resolve once; `SAFE_DISPLAY_ONLY` if names are unresolved; `BLOCKED_IDENTITY` if ambiguous. | Creating people/profiles from text. |
| PCT/CT | `SAFE_ORDERED_EXPANSION` only if stage sequence and CT-to-completed-PCT relation are proven; otherwise `BLOCKED_PARSE` or `MANUAL_REVIEW`. | Synthesizing rounds or CT parentage. |
| Final evaluation/deadline | `SAFE_DIRECT` only with deterministic typed source date/text; otherwise `BLOCKED_PARSE`. | Inventing workflow completion or deadline automation. |
| Certificate ID | `SAFE_LINK` only on one exact certificate identity plus case/site/type invariants; otherwise `BLOCKED_IDENTITY`. | Creating a 0..n relation from one source cell. |

## Compatibility and Deprecation

Historical compatibility fields remain readable only for provenance and legacy display. They cannot be treated as current semantic truth, used as fallbacks, or updated by new runtime APIs. Reconciliation must report rather than overwrite contaminated existing values. No source row is deleted or silently normalized.

## Implementation Batches

1. **Semantic foundation:** models, Alembic, Pydantic/read projections, workflow validation, and owner tests for split fields, team constraints, and approval submissions. Gate: no compatibility field receives new typed writes.
2. **Runtime/API convergence:** additive routes and frontend consumption through backend readiness/projections; mutation/audit/concurrency/permission tests. Gate: all typed mutations reject invalid transitions and stale versions.
3. **Read-only legacy planners:** source parsers, raw-evidence preservation, contamination reports, exact identity/sequence plans. Gate: every proposed write has a deterministic classification; no DB writes.
4. **Rehearsal apply:** separately approved transactional migration against rehearsal only, reconciliation and rollback evidence. Gate: independent audit before any production decision.

Likely affected implementation areas are `backend/app/db/models/phase1.py`, Alembic revisions, `backend/app/read_models.py`, `backend/app/services/workflow.py`, `backend/app/api/routers/workflow.py`, `backend/app/services/catalog.py`, `backend/app/domain/phase2_import.py`, migration planners, frontend workspace contracts, and focused model/workflow/importer/read-model tests.

## New Business Questions

None. The nine business facts in the approved clarification resolve this design. Source-specific parser grammars and historical reconciliation eligibility are technical evidence questions for the planner, not new business-policy questions.
