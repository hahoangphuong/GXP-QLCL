# ADR 0025: Header/Footer Bookmark DOCX Baseline

## Status
Approved

## Context
Some GxP administrative Word templates place scalar fields in headers or footers rather than only in the main document body.

The current template-aware baseline already supports:
- scalar bookmark replacement in `word/document.xml`
- repeated-row table rendering in `word/document.xml`

It does not yet address header/footer parts.

## Decision
- Extend the scalar bookmark renderer to process:
  - `word/document.xml`
  - `word/header*.xml`
  - `word/footer*.xml`
- Keep the scope narrow:
  - scalar bookmark replacement only
  - no table-region logic in header/footer parts
  - no copy-forward in header/footer parts

## Consequences
- Template-aware rendering now covers more real template placements without changing core service boundaries.
- Multi-part scalar bookmark coverage is explicit and testable.
- Table and advanced mutation logic remain constrained to the document body for now.

## Deferred
- header/footer table regions
- section-dependent different first/even headers
- shapes/text boxes not represented as straightforward bookmark paragraphs
