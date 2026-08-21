# ADR 0062: Production Cloud Run image serves frontend and deploys via migration job

## Status
Accepted

## Context
- The repository now contains both `backend/` and `frontend/`.
- The user-facing production deployment must deliver the complete application, not only the backend API.
- The current frontend is a Vite client shell whose default API base URL is same-origin.
- Production rollout must stop if Alembic migration fails; deploying a new application revision first would violate that safety rule.

## Decision
- Build the Vite frontend into the same production container image as the FastAPI backend.
- Serve built frontend static assets from the FastAPI application in the Cloud Run service.
- Use one Cloud Run service as the current production baseline for the operator web app and API.
- Build an immutable image traceable to the Git commit.
- Run `alembic upgrade head` through a dedicated Cloud Run job before deploying the new service revision.
- If the migration job fails, do not deploy the new Cloud Run service revision.

## Consequences
- Production deployment stays single-service for the web application while still preserving backend/business separation internally.
- Browser requests use same-origin API calls by default, which avoids introducing a second public runtime or cross-origin configuration prematurely.
- Alembic remains the production schema owner and rollout ordering becomes explicit and auditable.
