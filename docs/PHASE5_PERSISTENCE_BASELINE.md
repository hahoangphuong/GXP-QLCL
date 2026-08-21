# Phase 5 Persistence Baseline

## Scope
This phase turns document generation planning into a persistable workflow, still without rendering.

## Delivered
- logical document ensure/create
- document variant ensure/create
- pending generation-run persistence
- source dependency persistence
- idempotent run reuse by `idempotency_key`
- compatible with seeded `template_definition` / `template_binding` lookup

## Python module
- `backend/app/document/persistence.py`

## Deferred
- output `document_version` persistence after successful render/write
- repository abstraction layer
- DB repository abstraction for production services
