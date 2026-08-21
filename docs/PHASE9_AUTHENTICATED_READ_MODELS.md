# Phase 9 Authenticated Read Models

## Goal
Introduce a provisional but explicit auth boundary and expand the backend read model surface before mutation APIs begin.

## Delivered
- auth boundary: [backend/app/auth.py](/D:/GXP-QLCL/backend/app/auth.py)
- read service:
  - [backend/app/services/__init__.py](/D:/GXP-QLCL/backend/app/services/__init__.py)
  - [backend/app/services/catalog.py](/D:/GXP-QLCL/backend/app/services/catalog.py)
- expanded read models: [backend/app/read_models.py](/D:/GXP-QLCL/backend/app/read_models.py)
- updated routes:
  - [backend/app/api/routers/catalog.py](/D:/GXP-QLCL/backend/app/api/routers/catalog.py)
  - [backend/app/api/routers/status.py](/D:/GXP-QLCL/backend/app/api/routers/status.py)
  - [backend/app/config.py](/D:/GXP-QLCL/backend/app/config.py)
- ADR: [docs/ADR/0036-phase9-authenticated-read-models-before-mutations.md](/D:/GXP-QLCL/docs/ADR/0036-phase9-authenticated-read-models-before-mutations.md)

## Current auth baseline
- auth mode: `header_stub`
- request headers:
  - `X-Auth-User`
  - `X-Auth-Role`
- current read roles:
  - `reader`
  - `inspector`
  - `manager`
  - `admin`

## Current API surface added in this phase
- `GET /companies/{company_id}`
- `GET /sites/{site_id}`
- `GET /cases/{case_id}`

## Scope boundary
- this phase does not add mutation endpoints
- this phase does not claim final Google Cloud identity integration is done
- this phase only creates the auth boundary and detail read surface needed before business write flows

## Follow-up
- the provisional `header_stub` baseline introduced here is productionized later in Phase 13 through Google Cloud IAP JWT verification.
