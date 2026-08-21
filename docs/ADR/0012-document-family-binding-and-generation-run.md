# ADR 0012: Document Family, Template Binding, and Generation Run

## Status
Accepted

## Context
Phase 5 reverse engineering established that legacy document generation depends on:
- curated `family_code` groups rather than raw template filename fragments;
- branch-specific template selection by GxP stream, storage scope, and legacy mode;
- copy-forward dependencies from prior generated documents;
- auditable generation attempts that may succeed, fail, or be retried.

The existing Phase 1 schema separated logical document, variant, and version, but it did not yet model:
- template binding between a family and a concrete template;
- an execution record for generation attempts;
- explicit lineage from a generated output back to source documents used during copy-forward.

## Decision
Add these first-class schema concepts:
- `document.family_code`
- `template_binding`
- `document_generation_run`
- `document_source_dependency`

Keep `family_code` as a string code sourced from the curated registry, not a hard-coded database enum.

Use enums only for stable operational states such as `document_generation_status`.

## Consequences
- The curated template registry can drive data and service behavior without a schema migration for every new proven family.
- Generation attempts become auditable and retry-safe.
- Copy-forward flows such as CAPA and PT.CT can preserve provenance explicitly.
- Later `DocumentService` implementation can remain deterministic and idempotent without overloading `document_version` alone.
