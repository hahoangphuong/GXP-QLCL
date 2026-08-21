# ADR 0040: Phase 12 Frontend Uses a Vite + React Router Client Shell

## Status
Approved

## Context
The repository had no existing frontend scaffold.
Phases 8 through 11 established:
- modular backend APIs
- authenticated read endpoints
- workflow mutation endpoints
- document workflow endpoints

Phase 12 needs an operator shell that consumes those APIs without:
- re-embedding backend business rules in the browser
- introducing a server-rendered framework requirement before there is a clear need
- coupling the shell to private-share or Word desktop mechanics

## Decision
- Use `Vite` for the frontend build/runtime baseline.
- Use `React` + `TypeScript` for the client application.
- Use `React Router` for route-level shell navigation.
- Keep the Phase 12 frontend as a client-side operator shell, not a server-rendered framework application.
- Consume backend APIs directly through a typed fetch layer.
- Keep authentication at the current stub-header boundary for this phase.
- Keep document actions orchestration-first:
  - prepare run
  - inspect blocked reasons
  - render only through backend document APIs

## Consequences
### Positive
- Fastest path from empty `frontend/` directory to a usable operator shell.
- Keeps Phase 12 aligned with the current API-first architecture.
- Avoids inventing frontend business logic that should remain in backend services.
- Leaves room to revisit a larger framework choice later if deployment, SSR, or app-shell constraints materially change.

### Negative
- This phase does not yet provide SSR or framework-level data loading abstractions.
- Frontend auth remains tied to the current non-production stub boundary.
- A later productionization pass may still reorganize how frontend assets are hosted with Cloud Run.

## Follow-up
- Build the first operator shell around:
  - dashboard/status
  - case workspace
  - document workbench
- Revisit frontend hosting and production auth integration in a later phase, not before current operator workflows are validated.
