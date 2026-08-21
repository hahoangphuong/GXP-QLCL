# ADR 0017: Seeded Template Metadata And DB Source Resolution

## Status
Approved

## Context
Phase 5 already established:
- curated registry-first template contracts
- payload builder runtime
- copy-forward dependency planning
- generation-run persistence before render

The remaining gap before any render adapter is practical is that:
- `template_definition` / `template_binding` rows were not yet seeded deterministically
- source-document resolution for copy-forward was still contract-only and not backed by the database

## Decision
- Seed template metadata from `artifacts/phase5/template_seed.curated.json` into `template_definition` and `template_binding`.
- Use deterministic rerun semantics:
  - match `template_definition` by `(family_code, template_name)`
  - match `template_binding` by `(family_code, template_definition_id, gxp_type, legacy_mode, storage_scope)`
  - fail closed on ambiguous existing rows
  - update matched rows to curated values instead of creating duplicates
- Resolve copy-forward source candidates from DB using:
  - `document.family_code`
  - same parent linkage (`case_id`, `certificate_id`, `business_eligibility_certificate_id`, `change_request_id`)
  - active `document_variant`
  - available `document_version` rows
  - bookmark coverage derived from the active seeded `template_definition.bookmark_contract`

## Consequences
- Document generation can now run registry -> payload -> DB source lookup -> persistence before render/write.
- Copy-forward resolution stays storage-agnostic; filesystem access still belongs to `StorageService`.
- Ambiguous active template rows become operational errors rather than silent fallback.

## Deferred
- render adapter selection
- output `document_version` persistence after successful render/write
- storage binary read/write integration for source document content
