# Document Service Contract

## Purpose
This document defines the service boundary between application workflows and document generation orchestration. It does not define the rendering adapter itself.

## Baseline module
- `backend/app/document/service_contract.py`
- orchestration baseline: `backend/app/document/service.py`

## Main request shape
`DocumentGenerationRequest` contains:
- `family_code`
- parent linkage (`case_id`, `certificate_id`, `business_eligibility_certificate_id`, `change_request_id`)
- optional selection hints:
  - `gxp_type`
  - `legacy_mode`
  - `storage_scope`
- `language_code`
- `idempotency_key`

## Template selection rules
- Selection starts from the curated registry, not raw template filenames.
- `family_code` is mandatory.
- Other selectors only narrow the result.
- `DocumentService` must fail closed on:
  - no match
  - multiple matches

## Payload contract
### `DocumentPayloadField`
Stores:
- `field_name`
- `value`
- `source`
- `is_sensitive`

### `DocumentPayloadEnvelope`
Stores:
- target `family_code`
- flat field list
- source procedures used to build the payload
- optional notes

Current baseline intentionally keeps payload flat because:
- template binaries are not yet available;
- many legacy bookmarks are simple scalar replacements;
- a flatter payload is easier to audit and redact.
- repeated-row table regions are currently passed as render-side sidecar input, not yet as part of the payload-builder registry contract.

## Copy-forward planning
`SourceDependencyPlan` is derived from registry copy-forward dependencies and expresses:
- source document family
- dependency type
- required bookmarks
- triggering condition

This is the service-level bridge between:
- curated legacy evidence
- future document lookup/reuse logic
- persisted `document_source_dependency`

## Runtime orchestration extensions
- Payload building is executed through a registry-driven runtime builder, not by passing arbitrary dicts straight to rendering.
- Template-aware DOCX rendering may route payload fields through a runtime template contract before physical bookmark mutation.
- The current runtime contract gate only promotes families whose scalar reconciliation is fully exact; all others stay on payload passthrough.
- Variant-sensitive families may enforce a stricter concrete-template contract after template bytes are loaded.
- Current DDKD baseline detects the active template variant from the DOCX bookmark set and rejects fields not supported by that concrete variant.
- Current BBTD baseline detects the active template variant from the DOCX bookmark set and expands business-facing payload fields into numbered physical bookmark slots when required by the concrete template.
- Current DDKD appendix/decision baseline splits template selection at registry level and requires explicit `legacy_mode` before any future render-side promotion.
- Source-document lookup requests are derived before rendering and must resolve fail-closed.
- A single pre-render orchestration path now prepares payload, template plan, source resolutions, source-binary requirements, and persistence state.
- Render readiness must be explicit; it is not assumed merely because a logical source document was found.
- Exact source-binary readiness now depends on a persisted locator on `document_version`, not only on folder binding.
- Output document versions are allocated before render starts and linked to the generation run.
- Final rendered bytes are written through `StorageService`, after which `DocumentService` finalizes checksum/current-version/run-status metadata.
- A synthetic DOCX render baseline now exists for Word-backed families without copy-forward dependencies.
- A template-aware DOCX baseline now exists for scalar bookmark replacement in `word/document.xml`.
- A table-region baseline now exists for repeated-row rendering from a bookmarked template row in `word/document.xml`.
- Header/footer scalar bookmark replacement is now supported for template-aware DOCX rendering.

## Persistence expectations
- `document_generation_run` stores the attempt, selected binding, redacted payload, status, and output version.
- `document_source_dependency` stores resolved source-document provenance when copy-forward is used.
- `document_version` stores the actual output lineage.
- The baseline now persists `document_generation_run` before rendering so the attempt is auditable even if rendering has not started or later fails.

## Intentional deferrals
- bookmark grouping DSL
- section suppression DSL
- Word table mutation primitives
- exact render-adapter interface
- template-binary import lifecycle
- output version write-path allocation policy per `document_version`
- template-faithful render adapter semantics for real legacy Word files
- generalized table semantics in the payload-builder registry
- non-paragraph bookmark containers in DOCX parts
