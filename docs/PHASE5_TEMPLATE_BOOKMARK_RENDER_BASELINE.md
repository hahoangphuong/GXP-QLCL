# Phase 5 Template Bookmark Render Baseline

## Scope
This step adds the first template-aware DOCX renderer that mutates real DOCX XML instead of generating a synthetic package from scratch.

## Delivered
- template-aware scalar bookmark replacement in `word/document.xml`
- fail-closed behavior when required bookmarks are missing
- service wrapper for template-aware DOCX rendering
- smoke flow proving bookmark replacement from a managed template binary

## Python modules
- `backend/app/document/docx_template_render.py`

## Supported now
- Word-backed families
- scalar bookmark replacement
- templates with bookmarks present in the main document body XML

## Not supported yet
- headers/footers
- tables and region expansion
- conditional section deletion
- source-document copy-forward insertion

## Tooling
- `tools/smoke_phase5_template_bookmark_render.py`
