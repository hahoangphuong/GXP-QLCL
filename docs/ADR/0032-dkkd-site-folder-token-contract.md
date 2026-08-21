# ADR 0032: Formalize DDKD site-folder identity on `(<site_id>)`

## Status
Approved

## Date
2026-08-14

## Context
Legacy VBA proves that DDKD storage is separate from the inspection tree and that folder creation uses a descriptive prefix plus the site ID token in parentheses.

Evidence from reverse engineering:
- DDKD folder lookup searches for `* (<site_id>)*`
- if no folder exists, VBA creates `TenCtyx - DiaChi (<site_id>)`
- later file enumeration and generation happen beneath that site folder and a `Lần n` child folder

This means the full folder display name is not a durable business identifier.

## Decision
- Standardize DDKD site-folder resolution on the durable token `(<site_id>)`.
- Treat the descriptive folder prefix as mutable presentation text only.
- Keep the `Lần n` issuance-cycle child folder out of the folder identity key.
- Keep DDKD binding persistence deferred until a dedicated DDKD binding-key model is approved.

## Consequences
Positive:
- aligns the storage resolver with proven legacy behavior
- avoids using mutable folder labels as business identity
- keeps future folder renames from breaking site-folder resolution

Negative:
- DDKD lookup remains live-resolution only in the current Phase 4 baseline
- issuance-cycle placement still needs higher-level DDKD document logic
