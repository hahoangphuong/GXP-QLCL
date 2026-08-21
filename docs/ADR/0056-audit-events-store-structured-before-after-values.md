# ADR 0056: Audit events store structured before and after values

## Status
Accepted

## Context
`audit_event` already had columns for `changed_fields_json`, `old_values_json`, and `new_values_json`, but workflow mutations were still writing mostly flat payload snapshots. That left the audit contract weaker than the schema implied.

## Decision
- Workflow mutations must persist:
  - structured `old_values_json`
  - structured `new_values_json`
  - field-level `changed_fields_json`
- Audit helpers derive diffs from structured before/after snapshots when explicit changes are not separately supplied.
- `payload_redacted` remains a non-secret operational payload snapshot baseline.
- Secrets, tokens, auth headers/cookies, signing keys, and file binary content markers must never be written to `payload_redacted`.
- Redaction is enforced centrally by audit payload helpers rather than relying on each caller to remember specific secret field names.

## Consequences
- Operators and future reconciliation tooling can inspect precise field-level mutations.
- Rollback and concurrency failures do not produce misleading success audits.
- A future redaction-policy refinement can build on a structured baseline instead of free-form blobs.
