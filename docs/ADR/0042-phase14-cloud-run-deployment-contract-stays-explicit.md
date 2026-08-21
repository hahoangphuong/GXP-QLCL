# ADR 0042: Phase 14 Cloud Run deployment contract stays explicit

## Status
Approved

## Context
By Phase 13, the codebase has a Cloud Run-aligned application shape and a production-oriented IAP auth boundary, but the repository still lacks the runtime artifacts needed to deploy the backend in a controlled way:
- no backend runtime dependency manifest
- no container entrypoint
- no explicit Cloud Run env contract
- no pre-deploy validation for Cloud SQL, IAP, and Synology-backed storage inputs

This project has several architectural invariants that make deployment details materially important:
- Cloud Run hosts the app
- Cloud SQL PostgreSQL stores business data
- Synology remains the file binary system of record
- auth must fail closed
- storage access must remain adapter-owned

If deployment assumptions remain implicit, later phases risk baking in local-only behavior or hidden production gaps.

## Decision
- Add a backend runtime dependency manifest dedicated to Linux/Cloud Run execution.
- Add a backend container entrypoint that serves `backend.app.main:app` via Uvicorn.
- Expose a default ASGI `app` object from the backend entrypoint.
- Support Cloud SQL PostgreSQL URL composition from component env vars when `DATABASE_URL` is not explicitly supplied.
- Add a Cloud Run env-contract example and a validation tool that checks:
  - deployment platform
  - auth mode prerequisites
  - database connectivity inputs
  - storage roots
  - risky fallback flags
- Keep this phase focused on deployability contract and validation, not full IaC or CI/CD automation.

## Consequences
- The repository now has a concrete backend runtime baseline for Cloud Run instead of only documentation-level intent.
- Database connection setup becomes easier to inject from Secret Manager-backed env vars without hardcoding a full URL in git.
- Deployment remains fail-closed because invalid auth/database/storage configuration is surfaced before production rollout.
- Full infrastructure provisioning is still deferred to a later phase.
