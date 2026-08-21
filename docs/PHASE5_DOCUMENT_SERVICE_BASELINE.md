# Phase 5 Document Service Baseline

## Scope
This phase converts the curated registry and schema baseline into an application-facing service contract. Rendering remains deferred.

## Delivered baseline
- request contract
- payload contract
- template selection contract
- copy-forward planning contract
- default registry loader for local orchestration

## Python source
- `backend/app/document/service_contract.py`

## Service flow
1. Caller submits `DocumentGenerationRequest`.
2. `DocumentService` selects exactly one registry/template candidate.
3. Caller-provided or domain-built payload is wrapped in `DocumentPayloadEnvelope`.
4. Copy-forward requirements are projected into `SourceDependencyPlan`.
5. A `document_generation_run` can then be persisted before render execution.

## Current design choices
- Fail closed on template ambiguity.
- Keep `family_code` registry-driven.
- Keep payload flat and traceable.
- Keep sensitive values redactable before persistence.
- Keep copy-forward planning explicit and separate from storage access.

## What is still missing
- seeded `template_definition` / `template_binding` rows from curated registry
- API endpoint contract
- payload builders for each family
- source-document lookup resolver
- rendering adapter
