# Document Source Resolver

## Purpose
This document defines the baseline contract for resolving prior source documents used in copy-forward flows such as CAPA and PT.CT.

## Baseline module
- `backend/app/document/source_resolver_contract.py`
- `backend/app/document/source_resolver_db.py`

## Inputs
`SourceDocumentLookupRequest` carries:
- source `family_code`
- required bookmarks
- dependency type
- parent linkage (`case_id`, `certificate_id`, `business_eligibility_certificate_id`, `change_request_id`)
- current-version preference

## Candidate rules
`SourceDocumentCandidate` is intentionally storage-agnostic. It only expresses:
- logical family
- version identity
- available bookmarks
- whether it is current
- optional storage binding reference

## Resolution rule
- fail closed on zero match
- fail closed on multiple matches
- require bookmark coverage for the requested dependency

## DB-backed baseline
- source candidates are queried from:
  - `document`
  - active `document_variant`
  - `document_version`
- family matching uses `document.family_code`
- parent matching uses the same owning link carried in the generation request
- available bookmark coverage is derived from the active seeded `template_definition.bookmark_contract`
- missing or ambiguous active template metadata for the source family is an error

## Why this boundary exists
- Legacy VBA opened prior Word files directly from folders.
- The target system must preserve that behavior without leaking filesystem logic into business code.
- `StorageService` resolves and reads binaries, but `DocumentService` owns why a prior document is needed.
