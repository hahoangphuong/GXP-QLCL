# Phase 10 Workflow Mutation Baseline

## Goal
Introduce the first safe business mutation endpoint using audited case-state transitions.

## Delivered
- workflow service: [backend/app/services/workflow.py](/D:/GXP-QLCL/backend/app/services/workflow.py)
- workflow router: [backend/app/api/routers/workflow.py](/D:/GXP-QLCL/backend/app/api/routers/workflow.py)
- updated app entrypoint: [backend/app/main.py](/D:/GXP-QLCL/backend/app/main.py)
- updated service exports: [backend/app/services/__init__.py](/D:/GXP-QLCL/backend/app/services/__init__.py)
- updated read models for transition request/response: [backend/app/read_models.py](/D:/GXP-QLCL/backend/app/read_models.py)
- ADR: [docs/ADR/0037-phase10-case-mutations-start-with-audited-state-transitions.md](/D:/GXP-QLCL/docs/ADR/0037-phase10-case-mutations-start-with-audited-state-transitions.md)
- certificate/DDKD mutation baseline ADR: [docs/ADR/0038-phase10-certificate-and-dkkd-mutations-keep-issue-separate-from-current-promotion.md](/D:/GXP-QLCL/docs/ADR/0038-phase10-certificate-and-dkkd-mutations-keep-issue-separate-from-current-promotion.md)

## Current mutation API surface
- `POST /cases/{case_id}/transition`
- `PUT /cases/{case_id}/application`
- `PUT /cases/{case_id}/assessment`
- `PUT /cases/{case_id}/plan`
- `PUT /cases/{case_id}/outcome`
- `PUT /cases/{case_id}/team`
- `POST /sites/{site_id}/certificates`
- `PUT /certificates/{certificate_id}/latest-version`
- `POST /certificates/{certificate_id}/promote-current`
- `POST /sites/{site_id}/business-eligibility-certificates`
- `PUT /business-eligibility-certificates/{business_eligibility_certificate_id}/latest-version`
- `POST /business-eligibility-certificates/{business_eligibility_certificate_id}/promote-current`

## Current rules
- allowed roles:
  - `manager`
  - `admin`
- transition must follow the explicit state graph
- same-state transition is rejected
- unsupported target state is rejected
- successful transition writes an `audit_event`
- successful transition also writes an `inspection_event` when the target state has a mapped workflow event
- stage record upserts are also role-gated and audit-first
- stage record upserts write `inspection_event` only when a matching workflow event is semantically available
- inspection team upsert is explicit and replaces the member list atomically within the team record boundary
- certificate and DDKD issuance/create is explicit and starts as not-current by default
- certificate and DDKD latest-version updates replace the latest persisted payload explicitly rather than mutating a free-form row
- case-backed certificate issuance remains allowed, but issuance itself does not imply current/effective status
- current/effective promotion is a separate mutation gate for both GPs certificates and DDKD
- certificate promotion rejects candidates missing required issue metadata
- certificate promotion rejects candidates older than the currently active certificate of the same `site_id + certificate_type`
- DDKD promotion rejects candidates missing required issue metadata
- DDKD promotion rejects candidates older than the currently active DDKD row for the same site

## Scope boundary
- no free-form case field mutation yet
- no document mutation yet
- no storage write mutation yet
- no change-request mutation yet
- no document/storage side effects are triggered from mutation routes yet
