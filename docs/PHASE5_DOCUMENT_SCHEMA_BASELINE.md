# Phase 5 Document Schema Baseline

## Scope
This phase projects the curated template registry into the target relational model. It still does not implement rendering, Word automation replacement, or user-facing document workflows.

## Implementation source
- `backend/app/db/enums.py`
- `backend/app/db/models/phase1.py`
- `backend/app/document/registry.py`
- `tools/build_phase5_template_registry.py`

## New schema concepts
### `document.family_code`
- Stable document family identifier from the curated registry.
- Avoids coupling domain identity to broken raw template literals or display names.

### `template_definition`
Extended to store:
- `family_code`
- `source_application`
- `storage_scope`
- `legacy_host_procedure`
- `legacy_case_number`
- `template_pattern`
- active flag and notes
- variant type can represent both Word-backed and Excel-backed editable outputs in the baseline.

### `template_binding`
Maps a family to a concrete template definition under branch conditions such as:
- `gxp_type`
- `legacy_mode`
- `storage_scope`

### `document_generation_run`
Stores an auditable execution attempt:
- selected binding/definition
- generation status
- source application
- idempotency key
- redacted input payload
- linked output version
- failure summary

### `document_source_dependency`
Stores copy-forward provenance for cases where a generated document reuses prior document content.

## Why this matters
- CAPA and PT.CT are not pure template-fill documents.
- DDKD and inspection flows share the same `DocumentService` domain but not the same selection rules.
- Retry, auditing, and reconciliation need a real execution entity, not just the final file row.

## Still intentionally deferred
- exact bookmark payload schema
- exact section suppression DSL
- actual rendering adapter
- template binary ingestion
- Alembic migration scripts
