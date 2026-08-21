# Legacy Current Lookup Registry

## Purpose
- This document captures how legacy VBA resolves the current inspection, current GPs certificate, and current DDKD row for a site or site+scope.
- The main goal is to separate business truth from lookup acceleration structures before target-schema design proceeds further.

## High-level finding
- Legacy does not always discover the current row by scanning base tables at the point of use.
- Instead, many workflows first resolve a derived lookup entry, then dereference the returned row index in the base table.
- This makes the legacy system partly dependent on workbook-maintained current-row indexes and sheet-level lookup grids.

## Key lookup families
### `db_LastID_CCGPs`
- Read path evidence:
  - [`Check_CC_Update`](/D:/GXP-QLCL/artifacts/legacy_audit/vba_sources/GPs/MainForm.frm:3725)
  - [`Replace_CC`](/D:/GXP-QLCL/artifacts/legacy_audit/vba_sources/GPs/MainForm.frm:3891)
  - [`Update_LastCC_Cso`](/D:/GXP-QLCL/artifacts/legacy_audit/vba_sources/GPs/MainForm.frm:5301)
- Workbook inventory evidence:
  - [`workbook_inventory.json`](/D:/GXP-QLCL/artifacts/legacy_audit/workbook_inventory.json:1685)
- Access pattern:
  - lookup key is `GP type + "-" + site_id + ma_dc`
  - `GetDbIdx_MaC(..., "db_LastID_CCGPs")` returns a row index in `db_CC_Gps`
- Operational meaning:
  - legacy treats this as the current/effective certificate row for a site+scope combination
  - UI gating and status refresh rely on it

### `db_LastIDCs_DDK`
- Read path evidence:
  - [`Check_DDK_Update`](/D:/GXP-QLCL/artifacts/legacy_audit/vba_sources/GPs/MainForm.frm:3755)
  - [`CapNhat_DDK`](/D:/GXP-QLCL/artifacts/legacy_audit/vba_sources/GPs/MainForm.frm:3985)
  - [`Update_LastCC_Cso`](/D:/GXP-QLCL/artifacts/legacy_audit/vba_sources/GPs/MainForm.frm:5301)
- Workbook inventory evidence:
  - [`workbook_inventory.json`](/D:/GXP-QLCL/artifacts/legacy_audit/workbook_inventory.json:1693)
- Access pattern:
  - lookup key is `site_id`
  - `GetDbIdx_MaC(..., "db_LastIDCs_DDK")` returns a row index in `db_ddk`
- Operational meaning:
  - legacy treats this as the current/effective DDKD row for a site

### `db_LastID_ktra`
- Read path evidence:
  - `MainForm.frm` around `InsertNewTaiDK`
- Workbook inventory evidence:
  - [`workbook_inventory.json`](/D:/GXP-QLCL/artifacts/legacy_audit/workbook_inventory.json:1689)
- Access pattern:
  - lookup key is `GP type + "-" + site_id + ma_dc`
- Operational meaning:
  - tracks the current/latest inspection row used by some renewal/additional-registration flows

### `Ds_IDCs_DC`
- Write path evidence:
  - [`Update_LinkIdxKtra`](/D:/GXP-QLCL/artifacts/legacy_audit/vba_sources/GPs/MainForm.frm:7691)
  - [`Update_LinkIdxCCGPs`](/D:/GXP-QLCL/artifacts/legacy_audit/vba_sources/GPs/MainForm.frm:7719)
- Access pattern:
  - lookup key is `site_id + ma_dc`
  - column 2 is written with inspection row index
  - column 3 is written with GPs certificate row index
- Workbook inventory evidence:
  - `GLP!Ds_IDCs_DC = GLP!$AO$8:$AO$60`
  - `GMP!Ds_IDCs_DC = GMP!$AP$8:$AP$385`
  - `GMPbb!Ds_IDCs_DC = GMPbb!$AO$8:$AO$30`
- Binary workbook evidence:
  - sampled rows show the named-range anchor column contains the site/scope key
  - adjacent columns contain the current inspection row index and current certificate row index
  - for example on `GMP`, the anchor column contains values like `2B`, `3A`, `258A`, while the next two columns contain row indexes such as `1544` and `1485`
- Important conclusion from evidence:
  - `Ds_IDCs_DC` is a mutable worksheet lookup grid keyed by site/scope
  - the named range anchors only the first column, but VBA intentionally writes relative columns 2 and 3 beside that anchor
  - `db_LastID_CCGPs` and `db_LastID_ktra` are compatible with this same conceptual registry, though they materialize as base-table mirror columns rather than the sheet grid itself

## Workbook formula layer
### Base-table mirror columns
- Workbook inventory shows:
  - `db_Last_CCGPs = db.cc!$B$5:$B$1632`
  - `db_LastID_CCGPs = db.cc!$C$5:$C$1632`
  - `db_Last_DDK = db.dkkd!$B$5:$B$836`
  - `db_LastIDCs_DDK = db.dkkd!$C$5:$C$836`
  - `db_Last_ktra = db.ktra!$AI$5:$AI$1549`
  - `db_LastID_ktra = db.ktra!$AJ$5:$AJ$1549`
- In the workbook snapshot, direct binary reads show these as stored cell values, not as formulas surfaced by `pyxlsb`.
- Practical interpretation:
  - from VBA's perspective these named ranges behave like mirror/index columns embedded in the base tables
  - whether they are populated by formulas earlier in workbook recalc or by prior manual/VBA operations must still be treated as a separate question

### Sheet-level MATCH formulas
- Workbook inventory also proves a formula layer above the mirror columns:
  - `GMP!ID_CsDC = IF(GMP!$D10<>"","GMP-"&GMP!$D10&GMP!$L10,"?")`
  - `GMP!Idx_LastCC = IFERROR(IF(GMP!ID_CsDC="?","?",MATCH(GMP!ID_CsDC,db_LastID_CCGPs,0)),"\")`
  - `GMP!Idx_LastKT = IF(GMP!ID_CsDC="?","?",MATCH(GMP!ID_CsDC,db_LastID_ktra,0))`
  - equivalent formulas exist for `GLP` and `GMPbb`
- This proves a two-step resolution pattern:
  - build a site/scope key on the working sheet
  - match that key into the base-table mirror column
  - use the resulting row index to dereference the actual base row

## Source-of-truth versus cache behavior
### GPs certificates
- Base truth still lives in `db.cc` / `db_CC_Gps` rows:
  - status marker column (`"o"`, `"-"`, blank)
  - issue date
  - expiry date
  - invalidity text (`HHL`)
- But active-row resolution is accelerated by `db_LastID_CCGPs` and `Ds_IDCs_DC`.
- Promotion flow shows mixed responsibility:
  - [`Replace_CC`](/D:/GXP-QLCL/artifacts/legacy_audit/vba_sources/GPs/MainForm.frm:3891) changes the base rows
  - then `Update_LinkIdxCCGPs` updates the sheet-level current-row lookup
- Conclusion:
  - the base row state is business truth
  - the sheet lookup and mirror columns are derived current-row indexes used like a read model / cache

### DDKD
- Base truth still lives in `db.dkkd` rows:
  - status marker column
  - predecessor/successor fields
  - issue number/date
  - invalidity text
- Legacy reads the current row through `db_LastIDCs_DDK`.
- No imperative writer equivalent to `Update_LinkIdxCCGPs` was found in the audited VBA for DDKD current lookup.
- Conclusion:
  - `db_LastIDCs_DDK` is still being trusted as the current-row lookup
  - but in the audited VBA snapshot it appears more workbook-maintained than VBA-maintained
  - that last point is evidence-backed as a negative finding: read paths exist, but no direct VBA write path was found in the audited sources

### Inspections
- `Update_LinkIdxKtra` writes the inspection row index into `Ds_IDCs_DC` column 2.
- This indicates the legacy workbook also keeps a mutable current/latest inspection lookup per site+scope.

## Where these lookups affect behavior
### UI gating
- `Check_CC_Update` uses `db_LastID_CCGPs` to decide whether the Update button should appear.
- `Check_DDK_Update` uses `db_LastIDCs_DDK` similarly for DDKD.

### Summary panel / operator context
- `Update_LastCC_Cso` loads:
  - current DDKD row index into `Idx_DDKhh`
  - current certificate row index into `Idx_ccGPshh`
- It then populates the “current status” panel from those rows.

### Document generation context
- [`Make_RecordKT`](/D:/GXP-QLCL/artifacts/legacy_audit/vba_sources/GPs/RecordForm.frm:365) passes `Idx_ccGPshh` and `Idx_DDKhh` into `RecordForm`.
- RecordForm later uses those indexes to populate “current certificate / current DDKD” bookmarks in generated documents:
  - [`RecordForm.frm`](/D:/GXP-QLCL/artifacts/legacy_audit/vba_sources/GPs/RecordForm.frm:2791)
  - [`RecordForm.frm`](/D:/GXP-QLCL/artifacts/legacy_audit/vba_sources/GPs/RecordForm.frm:2825)
  - [`RecordForm.frm`](/D:/GXP-QLCL/artifacts/legacy_audit/vba_sources/GPs/RecordForm.frm:2841)

## Migration implications
- Target design must not treat workbook current-row lookup names as the primary business truth.
- Target design should separate:
  - artifact/version rows
  - status events or current-state transitions
  - read-optimized current lookup projections
- The legacy projection stack is layered:
  - base-table state columns
  - base-table mirror/index columns
  - sheet-level key grid (`Ds_IDCs_DC`)
  - sheet-level `MATCH(...)` formulas resolving the active row index
- A suitable target pattern is:
  - base transactional tables hold truth
  - an explicit projection or materialized current pointer supports fast UI/document reads
- For migration verification:
  - reconcile base-row truth against workbook current-row lookup outputs
  - detect cases where row markers and derived current lookup disagree
- The audited workbook snapshot already proves this reconciliation is necessary:
  - base-table mirror columns are internally consistent for current rows
  - but sheet-level grid pointers frequently resolve to non-current or blank-key base rows
  - see [CURRENT_LOOKUP_RECONCILIATION.md](/D:/GXP-QLCL/docs/CURRENT_LOOKUP_RECONCILIATION.md)

## Open question for later audit
- We have proven the `MATCH(...)` formula layer and the mutable `Ds_IDCs_DC` grid.
- We have not yet exhaustively traced how the base-table mirror columns themselves are refreshed over time in every workbook path.
- In particular, `db_LastIDCs_DDK` still needs a dedicated formula-path audit because no direct VBA writer was found in the audited sources.
