# Phase 5 Header/Footer Render Baseline

## Scope
This step extends template-aware scalar bookmark replacement from the main document body to header and footer XML parts.

## Delivered
- scalar bookmark replacement in `word/header*.xml`
- scalar bookmark replacement in `word/footer*.xml`
- smoke flow proving body, header, and footer values are all rendered in one DOCX

## Python modules
- `backend/app/document/docx_template_render.py`

## Supported now
- body scalar bookmarks
- header scalar bookmarks
- footer scalar bookmarks

## Not supported yet
- header/footer table regions
- header/footer copy-forward
- shapes or non-paragraph bookmark containers

## Tooling
- `tools/smoke_phase5_header_footer_render.py`
