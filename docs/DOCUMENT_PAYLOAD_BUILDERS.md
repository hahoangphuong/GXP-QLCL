# Document Payload Builders

## Purpose
This document defines the baseline payload-builder registry for `DocumentService`.

## Source artifacts
- `artifacts/phase5/payload_builder_registry.json`
- `artifacts/phase5/payload_builder_registry.md`

## Baseline design
- Each `family_code` maps to one payload-builder spec.
- Builder provenance is traced to one or more legacy population procedures.
- Builder fields are currently bookmark-driven.
- Sensitive support-document fields are explicitly flagged when they look like:
  - identity card values
  - bank account values

## Why bookmark-driven first
- The template binaries are not yet available.
- Bookmark writes are the strongest direct evidence available from VBA.
- This keeps the payload registry deterministic and auditable.

## Known limitations
- Required vs optional fields are not fully resolved yet.
- Grouped/table/section semantics are not modeled yet.
- Support-document families hosted by `ExtRecordForm.CreateFile` still share one broad builder footprint and should later be narrowed per case when binaries are available.

## After real-template audit
- Real templates are now available and audited under `legacy/Templates`.
- The payload registry remains the business-facing field vocabulary, but it is no longer assumed to equal the physical bookmark set of each template.
- See `docs/PHASE5_TEMPLATE_CONTRACT_RECONCILIATION.md` and `artifacts/phase5/template_contract_reconciled.json` for the current evidence-based mapping between payload fields and real template bookmarks.
