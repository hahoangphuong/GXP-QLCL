# ADR 0037: Phase 10 case mutations start with audited state transitions

## Status
Approved

## Date
2026-08-16

## Context
The backend now has:
- a modular Cloud Run aligned API foundation
- provisional authenticated read models

The next mutation phase must not begin with broad write surfaces across certificates, documents, and storage flows all at once.

Legacy reverse engineering also showed that `db.ktra` is a workflow aggregate, so the safest first mutation surface is controlled case-state transition rather than arbitrary field editing.

## Decision
- Start Phase 10 with one narrow mutation surface:
  - `POST /cases/{case_id}/transition`
- Enforce role-aware access for mutations (`manager`, `admin`).
- Record every successful transition in:
  - `audit_event`
  - `inspection_event` when a target state maps to a known workflow event
- Reject unsupported or out-of-order transitions with explicit errors.

## Consequences
Positive:
- creates an audit-first mutation baseline
- opens business write flow without jumping straight into high-risk document or certificate mutation
- aligns with the target workflow/event model

Negative:
- mutation coverage remains intentionally narrow in this phase
- legacy free-form field editing is still deferred
