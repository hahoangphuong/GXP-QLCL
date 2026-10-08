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
- create `document_generation_run` in `pending` with the exact prepared `document_variant_id`, before an output version exists
- persist resolved source dependencies when available

Template definition/binding references are attached when seeded rows exist; otherwise the baseline allows null references while keeping the rest of the generation run auditable.

Idempotency rule:
- if `idempotency_key` already exists, reuse the prior `document_generation_run` instead of creating a duplicate.
- On PostgreSQL, acquire transaction-scoped advisory locks in the fixed order: nonempty idempotency key first, then logical document identity (family code and all five nullable parent links used by the document lookup, with UUID parent IDs canonicalized to match PostgreSQL UUID equality). Both locks precede idempotency preflight and document/variant creation. The key lock serializes retries of one generation run; the document lock also serializes distinct or absent keys targeting the same logical document so a concurrent preparation reuses the committed document and variant while creating its own run. A mismatched request under the same key still fails closed. Preserve existing database uniqueness constraints; SQLite tests do not emulate PostgreSQL advisory locks.
- The idempotency preflight compares the persisted `document_generation_run.document_variant_id` to the existing variant selected by `(document_id, variant_type, language_code)` before creating any variant or run. Reusing one key across language/variant identity is a 409 conflict, not a new variant linked to the old run. PostgreSQL migration `20261008_0022` backfills historical runs only where the output version proves a matching variant, or the logical document has exactly one variant; missing/ambiguous variant evidence stays NULL and cannot be used for idempotent reuse.

- If legacy rows already contain multiple logical documents for the same family and exact parent links, preparation fails closed with an explicit persistence conflict instead of arbitrarily picking a document or raising an uncaught ORM multiplicity error. No automatic merge or rescue is performed.

## Consequences
- Generation attempts can be audited even before a render adapter is implemented.
- Source provenance is preserved independently of render success.
- Database seeding for template metadata can be staged separately from orchestration rollout.
