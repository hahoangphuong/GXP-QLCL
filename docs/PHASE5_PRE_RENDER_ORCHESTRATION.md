# Phase 5 Pre-render Orchestration

## Scope
This step adds a single orchestration path for document generation up to, but not including, render/write.

## Delivered
- `DocumentService` pre-render orchestration
- source-binary requirement planning
- explicit `render_ready` decision
- smoke script covering orchestration from payload input through persistence

## Python modules
- `backend/app/document/service.py`
- `backend/app/document/source_binary_contract.py`

## Main flow
1. Build payload from registry-known fields.
2. Select template family from curated registry.
3. Build source lookup requests for copy-forward dependencies.
4. Resolve source logical documents from DB.
5. Build source-binary requirements.
6. Persist `document_generation_run` and `document_source_dependency`.
7. Report whether render can safely start.

## Current result
- families without copy-forward can already become `render_ready`
- families with copy-forward remain fail-closed until exact source file location is modeled, even when the source folder is already known

## Tooling
- `tools/smoke_phase5_pre_render_orchestration.py`
