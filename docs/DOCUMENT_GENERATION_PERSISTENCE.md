# Document Generation Persistence

## Purpose
This document defines the persistence/orchestration baseline for `DocumentService` before any render adapter is invoked.

## Baseline module
- `backend/app/document/persistence.py`

## Workflow
1. Ensure or create logical `document`.
2. Ensure or create matching `document_variant`.
3. Look up `template_definition` and `template_binding` if seeded rows exist.
4. Create `document_generation_run` with status `pending`.
5. Persist `document_source_dependency` for resolved copy-forward sources.

## Idempotency
- `idempotency_key` is checked before creating a new generation run.
- If an existing run is found, the baseline reuses it and does not duplicate dependency rows.

## Fail-closed expectations
- at least one parent link must be present on generation request
- ambiguous template rows are errors
- ambiguous binding rows are errors
- source dependency resolution must be completed before persistence of those dependencies

## Current limitation
- This baseline does not yet persist `document_version` output because render/write has not happened.
- Template references remain null only if seed rows have not yet been loaded into the database.
