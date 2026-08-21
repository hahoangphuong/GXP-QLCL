# Phase 11 Document Workflow Integration

## Goal
Expose the Phase 5 document-generation contract as authenticated backend APIs before any frontend implementation.

## Delivered
- document workflow service: [backend/app/services/document_api.py](/D:/GXP-QLCL/backend/app/services/document_api.py)
- document router: [backend/app/api/routers/document.py](/D:/GXP-QLCL/backend/app/api/routers/document.py)
- updated app entrypoint: [backend/app/main.py](/D:/GXP-QLCL/backend/app/main.py)
- updated read models: [backend/app/read_models.py](/D:/GXP-QLCL/backend/app/read_models.py)
- updated service exports: [backend/app/services/__init__.py](/D:/GXP-QLCL/backend/app/services/__init__.py)
- ADR: [docs/ADR/0039-phase11-document-workflow-api-stays-run-first-and-fail-closed.md](/D:/GXP-QLCL/docs/ADR/0039-phase11-document-workflow-api-stays-run-first-and-fail-closed.md)

## Current API surface
- `POST /documents/prepare`
- `POST /documents/render-template-docx`
- `GET /document-generation-runs/{generation_run_id}`
- `GET /documents/{document_id}`

## Current rules
- `prepare` and `render-template-docx` allow:
  - `inspector`
  - `manager`
  - `admin`
- document read/status routes allow:
  - `reader`
  - `inspector`
  - `manager`
  - `admin`
- `prepare` persists a `document_generation_run` first and returns:
  - selected template
  - payload-field usage
  - source dependency requirements
  - template readiness
  - blocked reasons
- `render-template-docx` stays fail-closed when:
  - source dependencies are not direct-stream ready
  - template locator is missing
  - source application is not on the current Word template-aware path
  - runtime contract falls back to `payload_passthrough`
- successful render finalizes:
  - `document_version`
  - checksum
  - current-version flag
  - `document_generation_run.status = succeeded`
- blocked render attempts mark the run `failed` with an explicit error summary.

## Proven baseline
- unresolved families can now be prepared and inspected without pretending they are render-safe
- `CERTIFICATE_DECISION` is blocked cleanly through the API when it remains on unresolved runtime-contract semantics
- `DDKD_CERTIFICATE` can render end-to-end through the authenticated API path when:
  - template metadata is seeded
  - template binary locator is present
  - DDKD folder resolution succeeds
  - payload stays within the concrete variant-exact contract

## Scope boundary
- no generic document-family render promise
- no UI yet
- no direct frontend file writes
- no raw path/UNC exposure to business or API callers
- no expansion of unresolved copy-forward-heavy families by inference
