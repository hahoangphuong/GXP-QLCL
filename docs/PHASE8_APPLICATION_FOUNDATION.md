# Phase 8 Application Foundation

## Goal
Promote the project from a compact read-only prototype into an application foundation that matches the approved Google Cloud deployment direction.

## Scope of this phase
- modularize the FastAPI application surface
- keep the deployment stance explicitly aligned to `google_cloud_run`
- add an application status endpoint for migration/cutover visibility
- preserve existing read-only and storage lookup behavior while creating a better base for later domain APIs

## Delivered
- backend application config: [backend/app/config.py](/D:/GXP-QLCL/backend/app/config.py)
- backend application status reader: [backend/app/status.py](/D:/GXP-QLCL/backend/app/status.py)
- modular API routing:
  - [backend/app/api/__init__.py](/D:/GXP-QLCL/backend/app/api/__init__.py)
  - [backend/app/api/routers/__init__.py](/D:/GXP-QLCL/backend/app/api/routers/__init__.py)
  - [backend/app/api/routers/health.py](/D:/GXP-QLCL/backend/app/api/routers/health.py)
  - [backend/app/api/routers/status.py](/D:/GXP-QLCL/backend/app/api/routers/status.py)
  - [backend/app/api/routers/catalog.py](/D:/GXP-QLCL/backend/app/api/routers/catalog.py)
  - [backend/app/api/routers/storage.py](/D:/GXP-QLCL/backend/app/api/routers/storage.py)
- updated app entrypoint: [backend/app/main.py](/D:/GXP-QLCL/backend/app/main.py)
- ADR: [docs/ADR/0035-application-foundation-stays-cloud-run-api-first.md](/D:/GXP-QLCL/docs/ADR/0035-application-foundation-stays-cloud-run-api-first.md)

## Current API surface
- `GET /healthz`
- `GET /app/status`
- `GET /companies`
- `GET /sites`
- `GET /cases`
- `GET /storage/inspection-folder`
- `GET /storage/dkkd-folder`

## Deployment posture
- application mode is explicit in config
- deployment platform defaults to `google_cloud_run`
- no business layer code depends on UNC paths, Tailscale IPs, or desktop-only behavior

## Not in scope yet
- authenticated business mutation APIs
- frontend framework implementation
- Cloud Run IaC or CI/CD provisioning
- production auth integration
