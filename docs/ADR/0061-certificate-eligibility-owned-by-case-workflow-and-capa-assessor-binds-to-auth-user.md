# ADR 0061: Certificate eligibility stays in case workflow and CAPA assessor binds to authenticated user

## Status
Accepted

## Context
- Phase 10 introduced explicit CAPA, certificate issuance, and certificate current-promotion mutations.
- The first implementation guarded CAPA only on `inspection_completed -> awaiting_certificate_decision`.
- That left bypass paths where a case-backed certificate could still be issued or promoted while the latest CAPA cycle was still `requested`, `submitted`, or `rejected`.
- CAPA assessment also trusted client-supplied `assessor_name`, which is not strong enough for operational audit semantics in the web application.

## Decision
- `CaseWorkflowService` owns one shared certificate-eligibility policy for every case-backed certificate path.
- The shared policy checks both:
  - allowed case state for the attempted action
  - latest CAPA cycle status when a CAPA cycle exists
- The policy is applied to:
  - `inspection_completed -> awaiting_certificate_decision`
  - `awaiting_certificate_decision -> certified`
  - `issue_certificate(..., issuance_basis="inspection_case")`
  - `promote_certificate_current(...)` when the certificate is case-backed
- New CAPA cycles may be requested only while the case is still `inspection_completed`.
- CAPA assessment binds to authenticated `app_user` through `capa_cycle.assessor_user_id`.
- `capa_cycle.assessor_name` remains as a nullable legacy-compatible display snapshot / imported text field, but client input is not authoritative for web mutations.

## Consequences
- Certificate/CAPA behavior now has one owner and no route-level or mutation-specific bypass.
- Audit trails can identify the authenticated assessor precisely while still tolerating legacy imported rows with only text names.
- Reopening CAPA after the case already advanced to `awaiting_certificate_decision` now requires an explicit workflow correction instead of creating contradictory state.
