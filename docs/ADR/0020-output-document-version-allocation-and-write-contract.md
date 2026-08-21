# ADR 0020: Output Document Version Allocation And Write Contract

## Status
Approved

## Context
Phase 5 can already:
- prepare document-generation requests
- resolve source dependencies
- persist generation attempts
- open exact source binaries when locators are known

The next missing step before introducing a render adapter is:
- reserving an exact output binary location for the new document version
- attaching that output version to the generation run
- defining how a rendered binary is written and finalized through `StorageService`

## Decision
- Add an output-allocation step that:
  - resolves the target storage folder through `StorageService`
  - creates a new `document_version` with the next `version_no`
  - persists exact output locator fields before rendering starts
  - links that `document_version` to `document_generation_run.output_document_version_id`
- Add a write-finalization step that:
  - writes the rendered binary through `StorageService.write_stream`
  - computes checksum through `StorageService.checksum`
  - marks the allocated version current
  - marks prior versions for the same variant non-current
  - marks the generation run succeeded

## Consequences
- The render adapter will receive a preallocated output target instead of inventing file paths.
- `DocumentService` remains the owner of document-version lineage and success semantics.
- `StorageService` remains the owner of file IO only.

## Deferred
- naming policy automation beyond caller-supplied exact filename
- non-inspection output scopes such as `support_document`
- rollback/cleanup policy for allocated-but-never-written versions
