# Phase 14 Cloud Run Deployment Baseline

## Goal
Turn the Cloud Run target from an architectural assumption into an explicit runtime contract that can be validated before deployment.

## Delivered
- runtime dependency manifest: [requirements.runtime.txt](/D:/GXP-QLCL/backend/requirements.runtime.txt)
- backend container entrypoint: [Dockerfile](/D:/GXP-QLCL/backend/Dockerfile)
- container context hygiene: [.dockerignore](/D:/GXP-QLCL/backend/.dockerignore)
- Cloud Run env example: [.env.cloudrun.example](/D:/GXP-QLCL/backend/.env.cloudrun.example)
- Cloud SQL URL composition and ASGI app exposure:
  - [config.py](/D:/GXP-QLCL/backend/app/config.py)
  - [main.py](/D:/GXP-QLCL/backend/app/main.py)
- deployment validator: [validate_phase14_cloud_run_contract.py](/D:/GXP-QLCL/tools/validate_phase14_cloud_run_contract.py)
- tests: [test_phase14_cloud_run_contract.py](/D:/GXP-QLCL/tests/test_phase14_cloud_run_contract.py)
- ADR: [0042-phase14-cloud-run-deployment-contract-stays-explicit.md](/D:/GXP-QLCL/docs/ADR/0042-phase14-cloud-run-deployment-contract-stays-explicit.md)

## What changed
- The backend now exposes a default ASGI `app` for container startup.
- If `DATABASE_URL` is absent, backend config can now build a PostgreSQL SQLAlchemy URL from:
  - `DB_NAME`
  - `DB_USER`
  - `DB_PASSWORD`
  - `CLOUD_SQL_CONNECTION_NAME` or `DB_HOST`
- The repo now carries a Cloud Run-oriented runtime dependency set including:
  - FastAPI
  - SQLAlchemy
  - Uvicorn
  - `psycopg`
  - `google-auth`
- A validation tool now checks whether a deployment env contract is internally coherent before rollout.

## Intended operating model
- Cloud Run runs the backend container.
- Cloud SQL PostgreSQL is reached through a composed SQLAlchemy URL.
- Secret values should be injected by Cloud Run from Secret Manager-backed env vars, not committed in git.
- Synology paths remain external storage roots consumed only through `StorageService`.

## Validation tool
Example:

```powershell
python tools/validate_phase14_cloud_run_contract.py backend/.env.cloudrun.example
```

The tool reports:
- `errors`
- `warnings`
- resolved `database_url`

It exits non-zero when the contract is not deployable.

## Scope boundary
- This phase does not create Terraform, Cloud Build, or GitHub Actions yet.
- This phase does not provision Cloud Run, Cloud SQL, IAP, or Secret Manager resources.
- This phase does not change workflow, storage ownership, or document-generation logic.

## Google Cloud references
Reviewed on August 19, 2026:
- [Connect Cloud Run to Cloud SQL for PostgreSQL](https://docs.cloud.google.com/sql/docs/postgres/connect-run)
- [Configure secrets for Cloud Run](https://docs.cloud.google.com/run/docs/configuring/services/secrets)
- [IAP identity and signed headers](https://docs.cloud.google.com/iap/docs/identity-howto)
- [IAP signed headers / JWT verification](https://docs.cloud.google.com/iap/docs/signed-headers-howto)
