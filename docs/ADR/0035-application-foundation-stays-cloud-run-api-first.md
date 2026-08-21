# ADR 0035: Application foundation stays Cloud Run API-first

## Status
Approved

## Date
2026-08-16

## Context
The migration and cutover phases now have closed or near-closed baselines, but the application layer is still only a compact read-only prototype in a single FastAPI module.

The user confirmed the intended deployment target is Google Cloud.
Existing project decisions already state:
- Cloud Run for application services
- Cloud SQL PostgreSQL for business state
- Synology for file binaries only

The next implementation phase must therefore avoid:
- frontend-first implementation detached from backend/service contracts
- local-only conventions that would need redesign before Cloud Run deployment
- coupling application structure to desktop/private-share mechanics

## Decision
- Treat the next application phase as an API-first Cloud Run foundation phase.
- Keep the backend organized around deployable service boundaries first:
  - health
  - application status
  - read-only catalog/query routes
  - storage lookup routes
- Move route registration out of a monolithic `main.py` into modular router files.
- Add an application status endpoint that exposes migration/cutover artifact state for operator visibility.
- Keep frontend framework selection deferred until UI scope is promoted beyond the current backend/API foundation.

## Consequences
Positive:
- aligns implementation with the actual Google Cloud target early
- creates a cleaner base for domain services and future authenticated APIs
- gives the eventual frontend a stable API/status surface

Negative:
- frontend implementation remains intentionally deferred in this phase
- some deployment-specific details remain documented rather than fully provisioned in code
