# Phase 5 DOCX Render Baseline

## Scope
This step adds the first executable DOCX render adapter for the Phase 5 pipeline, while intentionally stopping short of legacy-faithful template rendering.

## Delivered
- synthetic valid `.docx` output generation
- service wrapper that prepares, allocates, renders, writes, and finalizes
- fail-closed restriction for copy-forward families
- smoke test covering end-to-end DOCX generation

## Python modules
- `backend/app/document/docx_render.py`

## Baseline behavior
- supports Word-backed document families only
- supports families with no source-document dependencies only
- renders payload and lineage metadata into a valid DOCX package
- writes output through the existing output-allocation/write-finalization flow

## Explicit non-goals
- template-faithful `.dotx` consumption
- bookmark deletion or table mutation
- source bookmark/table copy-forward into the rendered output

## Tooling
- `tools/smoke_phase5_docx_render_baseline.py`
