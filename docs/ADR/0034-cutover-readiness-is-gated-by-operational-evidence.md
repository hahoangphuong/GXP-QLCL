# ADR 0034: Cutover readiness is gated by operational evidence

## Status
Approved

## Date
2026-08-14

## Context
By the end of Phase 5, the migration has:
- a closed structured-data baseline;
- a closed storage contract baseline;
- a closed document/runtime baseline.

However, Phase 6 remains blocked on real desktop/private-share evidence, and current-projection conflicts remain unresolved outside the structured-import baseline.

## Decision
- Treat Phase 7 as an explicit cutover-readiness gate, not as an assumption that prior technical baselines are sufficient.
- Cutover cannot be considered `ready` while:
  - Phase 6 desktop/private-share evidence is blocked;
  - current-projection conflicts remain unresolved;
  - legacy write-freeze and rollback window approvals remain pending.
- Keep the readiness report and execution checklist as separate artifacts:
  - readiness = objective preconditions from prior phases
  - checklist = operational execution items for the cutover window

## Consequences
Positive:
- prevents accidental promotion of the web system to authoritative status before operator workflow is proven
- separates technical baseline completeness from operational approval/execution
- creates a deterministic cutover audit surface

Negative:
- Phase 7 may remain blocked even when application/domain baselines are mature
- operational stakeholders must complete explicit evidence and approvals before cutover
