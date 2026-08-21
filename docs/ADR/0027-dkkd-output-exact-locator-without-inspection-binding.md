# ADR 0027: DDKD Output Uses Exact Locator Without Inspection-Style Binding

## Context
Phase 5 output allocation originally supported only `inspection_folder` and assumed every generated output could attach to an inspection-style `storage_binding`.

That assumption does not hold for DDKD:
- active DDKD folder resolution currently depends on `site_legacy_id`, not the inspection triplet;
- the existing `storage_binding` table is keyed for inspection folders only;
- forcing DDKD outputs into that key model would invent a false identity contract.

## Decision
- Support `dkkd_folder` output allocation in `DocumentService`.
- Resolve the target DDKD folder live through `StorageService.resolve_dkkd_folder(...)`.
- Persist the exact output locator on `document_version` with:
  - `storage_root = "dkkd"`
  - exact `storage_relative_path`
  - `storage_binding_id = NULL`

## Consequences
Positive:
- DDKD document generation can now run end-to-end without inventing inspection-style binding rows.
- Exact file identity remains first-class on `document_version`.

Negative:
- DDKD outputs do not yet benefit from binding-first lookup caching.
- A future DDKD-specific binding model may still be needed if folder identity is later proven stable enough.
