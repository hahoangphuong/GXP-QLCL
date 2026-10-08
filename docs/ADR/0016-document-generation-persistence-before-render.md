# ADR 0016: Persist Document Generation State Before Render

## Status
Accepted

## Context
Phase 5 already has:
- template selection
- payload building
- source lookup contracts
- schema tables for generation runs and source dependencies

The remaining orchestration question is when `document_generation_run` and `document_source_dependency` should be created relative to actual rendering.

## Decision
Create persistence/orchestration baseline that prepares generation state before render execution:
- ensure or create logical `document`
- ensure or create matching `document_variant`
- create `document_generation_run` in `pending`
- persist resolved source dependencies when available

Template definition/binding references are attached when seeded rows exist; otherwise the baseline allows null references while keeping the rest of the generation run auditable.

Idempotency rule:
- if `idempotency_key` already exists, reuse the prior `document_generation_run` instead of creating a duplicate.
- On PostgreSQL, acquire transaction-scoped advisory locks in the fixed order: nonempty idempotency key first, then logical document identity (family code and all five nullable parent links used by the document lookup). Both locks precede idempotency preflight and document/variant creation. The key lock serializes retries of one generation run; the document lock also serializes distinct or absent keys targeting the same logical document so a concurrent preparation reuses the committed document and variant while creating its own run. A mismatched request under the same key still fails closed. Preserve existing database uniqueness constraints; SQLite tests do not emulate PostgreSQL advisory locks.

## Consequences
- Generation attempts can be audited even before a render adapter is implemented.
- Source provenance is preserved independently of render success.
- Database seeding for template metadata can be staged separately from orchestration rollout.
