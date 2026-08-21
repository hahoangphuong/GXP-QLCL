# ADR 0022: Template Binary Locator And Template-aware Readiness

## Status
Approved

## Context
The Phase 5 synthetic DOCX renderer validates the document-generation pipeline, but it does not consume the real legacy Word template binaries.

To move toward template-faithful rendering, the system needs:
- an exact locator for template binaries
- a storage root dedicated to template assets
- a readiness contract that proves template access before any template-aware render starts

## Decision
- Store exact template binary locator fields on `template_definition`.
- Introduce a dedicated `template` storage root in `StorageService`.
- Keep template assets separate from:
  - business document folders (`inspection`, `dkkd`)
  - source document version locators
  - output document version locators
- Add a template-aware readiness contract that requires:
  - a selected `template_definition`
  - an exact template binary locator
  - a Word-backed family
  - all source dependencies already render-ready

## Consequences
- Template ingestion becomes a first-class metadata step instead of hidden filesystem convention.
- Template-aware render adapters can now depend on a stable contract without inventing paths.
- The absence of real template binaries remains explicit and fail-closed.

## Deferred
- bulk import of real legacy `.dotx/.docx/.xltx` files
- template checksum verification policy
- actual bookmark mutation against ingested template binaries
