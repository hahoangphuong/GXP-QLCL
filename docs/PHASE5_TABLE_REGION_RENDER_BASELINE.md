# Phase 5 Table-region Render Baseline

## Scope
This step adds repeated-row DOCX rendering against template tables using a narrow region-bookmark contract.

## Delivered
- row-repeat rendering for table regions in `word/document.xml`
- row data passed as render-side region input
- fail-closed behavior for missing region bookmarks or row bookmarks
- smoke flow proving two repeated rows are rendered from one template row

## Python modules
- `backend/app/document/docx_template_render.py`
- `backend/app/document/service.py`

## Baseline contract
- one template row is identified by a region bookmark
- each row payload is a flat dictionary of bookmark-to-value replacements
- the template row is removed and replaced by zero or more cloned rows

## Not supported yet
- nested regions
- header/footer table regions
- source table copy-forward
- promotion of table semantics into the payload-builder registry

## Tooling
- `tools/smoke_phase5_table_region_render.py`
