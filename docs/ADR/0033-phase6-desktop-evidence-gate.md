# ADR 0033: Phase 6 closes only on evidence, not assumptions

## Status
Approved

## Date
2026-08-14

## Context
Phase 6 is the first migration phase whose core outcome depends on behavior outside the pure application codebase:
- private-share availability
- Windows Explorer navigation
- Microsoft Word desktop open/edit/save behavior
- SMB/file-lock behavior under real network conditions
- disconnect/reconnect recovery

Those behaviors cannot be inferred safely from local filesystem tests or from prior architecture decisions alone.

## Decision
- Treat Phase 6 as evidence-gated.
- Required desktop scenarios remain `blocked` or `pending` until they are executed against an active private-share path.
- Local Word COM harness results may prove desktop capability on the current machine, but they do not substitute for private-share evidence.
- A disconnected SMB mapping is an explicit blocker, not a soft warning.

## Consequences
Positive:
- prevents false claims that desktop/NAS workflow is validated when it is not
- preserves a clean audit trail between local-desktop proof and real private-share proof
- keeps later cutover decisions grounded in observed operator behavior

Negative:
- Phase 6 may remain operationally blocked even when the code/tooling baseline is ready
- manual execution evidence is required before this phase can be marked closed
