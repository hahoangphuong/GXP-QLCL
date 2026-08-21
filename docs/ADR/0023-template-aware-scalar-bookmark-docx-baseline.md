# ADR 0023: Template-aware Scalar Bookmark DOCX Baseline

## Status
Approved

## Context
After template binary locators were introduced, the next practical step is to prove template-aware rendering against a real DOCX package structure.

However, as of August 14, 2026:
- real legacy templates are still not present in this repository
- section deletion, table mutation, and copy-forward insertion are not yet modeled safely

## Decision
- Add a template-aware DOCX renderer that supports only scalar bookmark replacement in `word/document.xml`.
- Require:
  - Word-backed family
  - exact template binary locator
  - no copy-forward dependencies
- Fail closed when:
  - a requested payload field bookmark is missing from the template
  - source dependencies are present
  - template locator is not ready

## Consequences
- The system now proves end-to-end rendering against actual DOCX XML structure, not only synthetic output assembly.
- This remains an incremental baseline, not a full replacement for legacy Word automation.
- Future phases can layer:
  - header/footer bookmark support
  - table-region mutation
  - conditional section suppression
  - copy-forward insertion

## Deferred
- bookmark replacement outside `word/document.xml`
- table and row operations
- bookmark content insertion from source documents
- legacy-template fidelity validation against real binaries
