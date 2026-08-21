# ADR 0036: Phase 9 introduces authenticated read models before mutation APIs

## Status
Approved

## Date
2026-08-16

## Context
After Phase 8, the backend is a modular API-first Cloud Run foundation, but all read routes are still effectively anonymous.

Before implementing workflow mutations, the system needs:
- a clear auth boundary
- role-aware read access
- entity detail endpoints that map to real operator workflows

At the same time, production identity integration is not ready yet, so the project still needs a low-risk local/dev baseline that can later be replaced by Google Cloud identity integration.

## Decision
- Introduce Phase 9 as an authenticated read-model phase.
- Add a minimal header-based auth stub boundary for now:
  - `X-Auth-User`
  - `X-Auth-Role`
- Restrict current read routes to approved read roles.
- Add detail endpoints for `company`, `site`, and `case` before any mutation endpoints are introduced.
- Treat this auth layer as a replaceable boundary, not as the final production identity solution.

## Consequences
Positive:
- creates a clean path toward real RBAC and mutation APIs
- prevents the application layer from remaining anonymously readable by default
- supports Google Cloud deployment evolution without blocking current implementation progress

Negative:
- the auth mechanism is intentionally provisional
- frontend and production identity work still remain for later phases
