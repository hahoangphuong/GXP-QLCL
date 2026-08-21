# ADR 0060: CAPA remains a case subworkflow guard

## Status
Accepted

## Context
Legacy evidence proves explicit CAPA round 1 and round 2 document families and operator flow, but it does not justify expanding the primary case-state machine with multiple CAPA-specific top-level states. The modern target still needs to block certificate decision when CAPA is active or unresolved.

## Decision
- Keep `case.state` coarse.
- Model CAPA as child rows in `capa_cycle` with optimistic concurrency and audit coverage.
- Guard `inspection_completed -> awaiting_certificate_decision` using the latest CAPA cycle:
  - if no CAPA cycle exists, transition may proceed
  - if the latest CAPA cycle is `accepted`, transition may proceed
  - if the latest CAPA cycle is `requested` or `submitted`, transition is blocked
- CAPA rounds are open-ended via `round_no`; do not hardcode a maximum of 2 without stronger legacy evidence.
- CAPA document families must link to the exact `capa_cycle` row.

## Consequences
- Case-state semantics stay understandable without losing CAPA enforcement.
- CAPA history, round lineage, and document linkage become explicit business data.
- Later evidence can extend round counts without reshaping the primary case-state enum.
