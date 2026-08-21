# ADR 0019: Document Version Exact Binary Locator

## Status
Approved

## Context
Phase 5 pre-render orchestration proved that a resolved source folder is not enough for safe copy-forward execution.

The missing capability was:
- identifying the exact source binary for a `document_version`
- opening that binary through `StorageService` without wildcard guessing

## Decision
- Store exact binary locator on `document_version`.
- The locator consists of:
  - `storage_root`
  - `storage_relative_path`
  - optional `original_filename`
- Keep `storage_binding` as folder-level identity only.
- Validate that inspection-scoped document-version locators stay within the bound inspection folder when `storage_binding_id` exists.
- `DocumentService` may only treat a source dependency as stream-ready when:
  - the source `document_version` exists
  - the family storage scope maps to a supported storage root
  - the exact locator is present
  - the exact locator is consistent with the bound folder

## Consequences
- Copy-forward can move from logical source resolution to exact binary access without leaking NAS rules into business code.
- `StorageService` still owns the actual file open/read operation.
- Folder prefix hints remain supporting evidence only; they are not a substitute for persisted file identity.

## Deferred
- output version write path allocation
- render adapter execution
- imported legacy backfill for exact source locators
