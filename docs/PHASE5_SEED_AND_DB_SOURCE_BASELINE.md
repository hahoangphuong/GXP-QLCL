# Phase 5 Seed And DB Source Baseline

## Scope
This step closes the gap between the curated document registry and the database-backed generation workflow, still stopping before render/write.

## Delivered
- deterministic template metadata seed runtime
- seed command for `template_definition` and `template_binding`
- DB-backed source candidate lookup for copy-forward flows
- smoke script covering seed -> source lookup -> persistence

## Python modules
- `backend/app/document/seed_runtime.py`
- `backend/app/document/source_resolver_db.py`

## Tools
- `tools/seed_phase5_template_metadata.py`
- `tools/smoke_phase5_document_pipeline.py`

Current seed-runtime note:
- the default artifact SQLite seed database is now recreated from scratch on each plain `tools/seed_phase5_template_metadata.py` run so schema-expanding contract changes remain rerunnable without manual cleanup.

## Fail-closed rules
- ambiguous `template_definition` rows are errors
- ambiguous `template_binding` rows are errors
- missing active template metadata for source families is an error
- copy-forward resolution still requires exactly one bookmark-compatible candidate

## Deferred
- render adapters for DOCX/XLSX generation
- persisted output `document_version`
- binary reads through `StorageService`
