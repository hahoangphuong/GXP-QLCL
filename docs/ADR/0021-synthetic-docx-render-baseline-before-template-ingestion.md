# ADR 0021: Synthetic DOCX Render Baseline Before Template Ingestion

## Status
Approved

## Context
As of August 14, 2026, the repository still does not contain the real legacy Word template binaries needed for template-faithful rendering.

Phase 5 already has:
- registry-based template selection
- payload contracts
- source dependency resolution
- source-binary access
- output allocation and write finalization

What remains missing is an end-to-end render adapter that can exercise the pipeline without pretending to have proven legacy layout fidelity.

## Decision
- Add a synthetic DOCX render baseline that produces a valid `.docx` package directly from the document-generation contract.
- Restrict this baseline to Word-backed families with no copy-forward dependencies.
- Fail closed for families that require copy-forward semantics or template-structure-aware mutation.
- The synthetic output includes:
  - logical family metadata
  - generation-run metadata
  - payload field values
  - registry missing-field summary

## Consequences
- The project now has one fully executable end-to-end Word generation path:
  - prepare
  - allocate
  - render bytes
  - write
  - finalize metadata
- This validates the service boundaries without overstating legacy compatibility.
- Template-faithful bookmark/section/table mutation remains a later phase that depends on real template ingestion.

## Deferred
- real template binary ingestion
- bookmark-level mutation against actual `.docx/.dotx`
- copy-forward content insertion into rendered outputs
