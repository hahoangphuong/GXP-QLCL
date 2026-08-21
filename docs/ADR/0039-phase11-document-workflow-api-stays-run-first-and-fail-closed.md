# ADR 0039: Phase 11 Document Workflow API Stays Run-First and Fail-Closed

## Status
Approved

## Context
Phase 5 already established the evidence-based `DocumentService` contract, template registry, generation-run persistence, source-binary readiness checks, and a narrow set of render-safe Word families.

What was still missing was the authenticated application API layer that lets the web replacement:
- prepare a document-generation run
- inspect run readiness and blockers
- trigger render only for families that are actually safe
- inspect document lineage and output versions afterwards

Legacy evidence also makes it unsafe to treat all families as generically renderable:
- some families remain on `payload_passthrough`
- some families still require copy-forward semantics
- some families are selection-safe but not render-safe

## Decision
- Add authenticated document workflow API endpoints for:
  - prepare generation
  - render template-aware DOCX
  - inspect generation-run status
  - inspect logical-document lineage/detail
- Keep the API run-first:
  - `prepare` persists a `document_generation_run` before render
  - blocked runs remain explicit and inspectable
- Keep render fail-closed:
  - no render when source dependencies are not stream-ready
  - no render when template locator is missing
  - no render when runtime contract falls back to `payload_passthrough`
  - no render when source application is not currently supported by the template-aware DOCX path
- Allow document workflow actions to `inspector`, `manager`, and `admin`.
- Keep document detail/read status open to `reader`, `inspector`, `manager`, and `admin`.
- Keep file placement and binary access fully behind `StorageService`.

## Consequences
### Positive
- The backend now exposes document-generation workflow in a web-native shape without bypassing the evidence gathered in reverse engineering.
- Operators and future frontend code can see why a document family is blocked instead of inferring safety from template presence alone.
- Rendered output still lands on Synology-compatible storage through the storage abstraction.

### Negative
- Some prepared runs may remain `pending` or become `failed` because the family is not yet promoted to render-safe status.
- The API still reflects the current narrow render-safe baseline rather than promising broad legacy parity.

## Follow-up
- Phase 12 frontend work should consume these APIs rather than calling file/template code directly.
- Later document-family promotion should continue one family at a time from blocked to render-safe with explicit evidence and ADR updates.
