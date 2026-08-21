# ADR 0024: Table-region Row-repeat DOCX Baseline

## Status
Approved

## Context
Scalar bookmark replacement covers only a small subset of the legacy Word behavior. Many GxP flows require repeated table rows populated from row-shaped data.

The current payload registry is still intentionally flat and bookmark-driven. We do not yet have enough reverse-engineered evidence to standardize full table semantics across all families.

## Decision
- Add a narrow table-region baseline for template-aware DOCX rendering.
- The baseline uses:
  - a row-level region bookmark that identifies the template row to repeat
  - row dictionaries supplied as render-side input
  - scalar bookmark replacement inside each cloned row
- Keep this contract render-local for now rather than merging it into the payload-builder registry.
- Fail closed when:
  - the region bookmark row is missing
  - a required row bookmark is missing in the cloned template row
  - copy-forward is required

## Consequences
- The project now proves a second major class of DOCX mutation beyond scalar bookmarks.
- Business payload registry remains stable while table semantics are still being reverse-engineered.
- A later phase can promote proven table-region contracts into first-class family metadata.

## Deferred
- nested/merged table structures
- row deletion based on conditions
- multi-row regions
- source-document table copy-forward
