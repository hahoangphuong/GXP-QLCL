# ADR 0007: Persist storage binding only on resolved folder matches

## Status
Approved

## Date
2026-08-13

## Context
Folder resolution against legacy Synology-compatible storage may yield:
- `RESOLVED`
- `NOT_FOUND`
- `AMBIGUOUS`
- `INVALID`

The system needs a durable record of proven folder mappings, but must not persist guesses or ambiguous paths.

## Decision
- Persist or update `storage_binding` only when folder resolution returns `RESOLVED`.
- Use the existing stable triplet:
  - `year`
  - `site_legacy_id`
  - `inspection_legacy_code`
- Store only root-relative path and observed folder label.
- Do not create `storage_binding` rows for `NOT_FOUND`, `AMBIGUOUS`, or `INVALID`.
- Re-resolution of the same triplet updates the existing binding in place.
- The explicit-year persisted binding fast path may reuse a cached folder only when its root-relative path is exactly `<year>/<folder>`, the folder label still matches both literal legacy tokens, and StorageService confirms the path is a directory. An existing but foreign, wrong-year, or file path is not an identity proof: use the ordinary live resolution; update the binding only on an unambiguous RESOLVED result, and otherwise preserve the existing row without exposing it as resolved.

## Consequences
Positive:
- durable mappings come only from proven resolutions
- no silent persistence of ambiguous guesses
- future reads can consult binding first and avoid unnecessary rescans

Negative:
- unresolved folders still require live resolution attempts and operator intervention
- DDKD remains outside binding persistence until its identity rule is proven more clearly
