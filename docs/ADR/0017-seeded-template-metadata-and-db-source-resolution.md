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
- reject semantic conflicts on matched rows instead of silently overwriting curated metadata; re-activate an otherwise identical inactive canonical row deterministically
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
- Canonical template metadata is reference/application data, not Alembic schema data. VM deployment runs the canonical bootstrap after schema migration and verifies the canonical subset before RBAC verification or service activation. Family-specific binary locators remain separate runtime extensions.

## Deferred
- render adapter selection
- output `document_version` persistence after successful render/write
- storage binary read/write integration for source document content
