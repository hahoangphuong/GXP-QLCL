# Phase 5 Template Ingestion Baseline

## Scope
This step introduces first-class template binary locators and a template-aware readiness contract, without yet performing template-faithful rendering.

## Delivered
- exact template binary locator fields on `template_definition`
- `template` storage root support in `StorageService`
- template locator assignment and direct stream access
- template-aware preparation wrapper for DOCX generation
- smoke flow proving template binary access and template-aware readiness

## Python modules
- `backend/app/document/template_binary.py`

## Main rules
- template binaries are not stored on `document_version`
- template binaries do not reuse `storage_binding`
- template binaries must use `storage_root = template`
- template-aware rendering remains fail-closed when the template locator is missing

## Tooling
- `tools/smoke_phase5_template_ingestion.py`
