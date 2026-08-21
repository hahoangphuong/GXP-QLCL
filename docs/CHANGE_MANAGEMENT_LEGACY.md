# Legacy Change Management Model

## Purpose
- This document captures the actual legacy behavior of `db.Tdoi` / `db.Tdoi2` and the related VBA flows that create adjusted GPs certificates and adjusted DDKD outputs.
- Evidence comes from real VBA procedures in [`MainForm.frm`](/D:/GXP-QLCL/artifacts/legacy_audit/vba_sources/GPs/MainForm.frm:142), [`MainForm.frm`](/D:/GXP-QLCL/artifacts/legacy_audit/vba_sources/GPs/MainForm.frm:3891), and [`RecordForm.frm`](/D:/GXP-QLCL/artifacts/legacy_audit/vba_sources/GPs/RecordForm.frm:406).
- `db.Tdoi` is not only a note or correspondence tracker. In live behavior it is the orchestration hub for change requests, approval handling, and issuance of adjusted certificate artifacts.

## Core records
### `db.Tdoi`
- Header row for one change request / change outcome.
- Holds site identity through `ID Co so`.
- Holds operator-entered dossier, submitter, handling, result, and effective-date data.
- Also stores linked certificate/DDKD IDs in two distinct pairs:
  - `IDCC_TD`: current GPs certificates being affected by the change.
  - `IDCC_TD + 1`: newly issued adjusted GPs certificates created from the change flow.
  - `IDDDK_TD`: current DDKD rows being affected by the change.
  - `IDDDK_TD + 1`: newly issued adjusted DDKD rows created from the change flow.

### `db.Tdoi2`
- Child detail rows for structured change items.
- Links back through `ID Goc`.
- Stores classification and before/after payload:
  - change type
  - acceptance status
  - old information
  - new information
  - notes

## Actual creation flow
### Header creation
- [`InsertNewTdoiDB`](/D:/GXP-QLCL/artifacts/legacy_audit/vba_sources/GPs/MainForm.frm:3284) allocates a new `db.Tdoi.ID`.
- It pre-fills:
  - `ID Co so`
  - `Mo ta = "???"`
  - `Hieu luc = "???"`
- It also auto-links currently effective rows for the same site:
  - current GPs certificate IDs into `IDCC_TD`
  - current DDKD IDs into `IDDDK_TD`
- That means a freshly created change row already knows which current regulated artifacts are being changed.

### Detail creation
- [`InsertNewTdoi2DB`](/D:/GXP-QLCL/artifacts/legacy_audit/vba_sources/GPs/MainForm.frm:3308) allocates a new child row in `db.Tdoi2`.
- It pre-fills:
  - `ID Goc`
  - `PL_TD2 = "???"`
- The detail row is therefore not derived later from free text; it is an explicit subordinate record in the operator workflow.

## Editing and operator workflow
### Header editing
- [`GetSetDataTD`](/D:/GXP-QLCL/artifacts/legacy_audit/vba_sources/GPs/MainForm.frm:1663) edits `db.Tdoi` through the shared mutation gateway.
- Field `id = 4` routes through `TTVForm` with `Dtype = 2`, so part of change handling depends on the same structured person/inspector selector used elsewhere, not plain free text only.

### Detail editing
- [`GetSetDataTD2`](/D:/GXP-QLCL/artifacts/legacy_audit/vba_sources/GPs/MainForm.frm:1674) edits `db.Tdoi2` through the same mutation infrastructure.
- The change detail list is refreshed after every accepted edit.

### Live UI semantics
- [`UpdateThaydoiItem`](/D:/GXP-QLCL/artifacts/legacy_audit/vba_sources/GPs/MainForm.frm:2100) treats four ID collections separately:
  - current linked GPs certificates
  - newly issued adjusted GPs certificates
  - current linked DDKD rows
  - newly issued adjusted DDKD rows
- The form shows separate lists for each collection via:
  - [`Load_ListCCLQTD`](/D:/GXP-QLCL/artifacts/legacy_audit/vba_sources/GPs/MainForm.frm:4673)
  - [`Load_ListDDKLQTD`](/D:/GXP-QLCL/artifacts/legacy_audit/vba_sources/GPs/MainForm.frm:4717)
- So the UI itself confirms that the legacy model distinguishes documents being changed from documents newly issued because of that change.

## Adjusted GPs certificate issuance
### Creation path
- [`btnCapCCTD_Click`](/D:/GXP-QLCL/artifacts/legacy_audit/vba_sources/GPs/MainForm.frm:142) is the explicit issue-adjusted-certificate-from-change-request action.
- It:
  - selects one current linked GPs certificate
  - calls [`CopyNewCCGPsDB`](/D:/GXP-QLCL/artifacts/legacy_audit/vba_sources/GPs/MainForm.frm:3328)
  - appends the newly created ID into `db.Tdoi.(IDCC_TD + 1)`
  - refreshes the adjusted-certificate list

### Copy semantics
- `CopyNewCCGPsDB` creates a new row by copying the old certificate row, then resets issuance-specific fields.
- Proven reset behavior includes:
  - fresh `ID = Max + 1`
  - clear current marker/status
  - clear invalidity text
  - `Ma CC = "???"`
  - blank issue date / expiry date
- This is not a pure relation row. The legacy system physically creates a new certificate business row before document generation or later promotion.

## Adjusted DDKD issuance
### Creation path
- [`btnCapDDKTD_Click`](/D:/GXP-QLCL/artifacts/legacy_audit/vba_sources/GPs/MainForm.frm:162) is the explicit issue-adjusted-DDKD-from-change-request action.
- It:
  - selects one current linked DDKD row
  - calls [`CopyRevDDKDB`](/D:/GXP-QLCL/artifacts/legacy_audit/vba_sources/GPs/MainForm.frm:183)
  - appends the new DDKD ID into `db.Tdoi.(IDDDK_TD + 1)`
  - refreshes the adjusted-DDKD list

### Copy semantics
- `CopyRevDDKDB` builds the adjusted DDKD row from the current one.
- Proven behavior includes:
  - create a new DDKD row first
  - increment `Lan cap`
  - append human-readable issuance history text
  - set predecessor linkage through `clDB_Thaythe_DDK`
- This means legacy stores both structured lineage and narrative issuance history in the new row.

## Promotion to active/current
### GPs certificate promotion gate
- A copied successor row is not automatically active.
- [`Check_CC_Update`](/D:/GXP-QLCL/artifacts/legacy_audit/vba_sources/GPs/MainForm.frm:3725) only exposes the update action when:
  - the candidate row has certificate number
  - the candidate row has issue date
  - the candidate row has expiry date
  - the candidate row is newer than the currently indexed active row for the same site and scope
- This means a change-created row can exist in the table before it becomes effective in business terms.

### GPs certificate promotion execution
- Promotion can be triggered from:
  - inspection/case context via [`btnCapnhatCC_Click`](/D:/GXP-QLCL/artifacts/legacy_audit/vba_sources/GPs/MainForm.frm:3789)
  - change-successor context via [`btnCapnhatCC_STD_Click`](/D:/GXP-QLCL/artifacts/legacy_audit/vba_sources/GPs/MainForm.frm:3855)
- Both routes call [`Replace_CC`](/D:/GXP-QLCL/artifacts/legacy_audit/vba_sources/GPs/MainForm.frm:3891).
- `Replace_CC`:
  - validates issue date and expiry date on the candidate row
  - finds the currently indexed active row for the same site and scope
  - blocks promotion if the candidate issue date is older than the active row
  - prompts the operator for confirmation
  - marks the prior active row with `"-"` in the status column
  - marks the promoted row with `"o"` in the status column
  - updates the site/scope current-certificate index via `Update_LinkIdxCCGPs`
  - refreshes derived current-state UI via `Update_LastCC_Cso` and `UpdateListCCCs`

### GPs certificate state semantics
- [`UpdateCCGPsItem_Row`](/D:/GXP-QLCL/artifacts/legacy_audit/vba_sources/GPs/MainForm.frm:4411) proves the status model is data-driven:
  - no certificate number or `???` -> not yet issued
  - status column `"-"` -> obsolete / no longer effective
  - blank status column -> issued but not yet effective
  - valid expiry date in the future -> effective
  - expiry date in the past -> expired
  - `HHL` text present -> invalidated with explicit reason
- So legacy distinguishes at least three separate row states after creation:
  - created but incomplete
  - issued but not current
  - current/effective

## DDKD promotion to active/current
### DDKD promotion gate
- A copied successor DDKD row is also not automatically active.
- [`Check_DDK_Update`](/D:/GXP-QLCL/artifacts/legacy_audit/vba_sources/GPs/MainForm.frm:3755) only exposes the update action when:
  - the candidate row has DDKD number
  - the candidate row has issue date
  - the candidate row is newer than the currently indexed active DDKD row for that site

### DDKD promotion execution
- Promotion is executed by [`CapNhat_DDK`](/D:/GXP-QLCL/artifacts/legacy_audit/vba_sources/GPs/MainForm.frm:3985), reached from:
  - main DDKD list via [`btnCapnhatDDK_Click`](/D:/GXP-QLCL/artifacts/legacy_audit/vba_sources/GPs/MainForm.frm:4039)
  - detail/update button path via `btnUpdate_DDK`
- `CapNhat_DDK`:
  - resolves the currently indexed active DDKD row for the site
  - blocks promotion if the candidate already has a successor linked in `clDB_Thaythe_DDK + 1`
  - validates candidate date and current-row date
  - blocks promotion if the candidate date is older than the active row
  - prompts the operator for confirmation
  - marks the prior active row with `"-"` in the status column
  - writes the promoted row ID into the prior row's successor field `clDB_Thaythe_DDK + 1`
  - marks the promoted row with `"o"` in the status column
  - refreshes history and DDKD list views

### DDKD lineage pre-linking
- [`ChonDDK_Thaythe`](/D:/GXP-QLCL/artifacts/legacy_audit/vba_sources/GPs/MainForm.frm:923) supports two distinct linkage directions:
  - predecessor selection for a new candidate row
  - successor selection for an already current row
- If used in successor-selection mode (`TT_Type = 1`), it can already mark the current row obsolete by writing `"-"` to the status column even before `CapNhat_DDK` is used elsewhere.
- In predecessor-selection mode it also:
  - copies missing scalar fields from predecessor to candidate
  - increments `Lan cap` when empty
  - appends narrative issuance history text
- Therefore DDKD lineage may be partially staged before formal promotion.

### DDKD state semantics
- [`UpdateCCDDKItem_Row`](/D:/GXP-QLCL/artifacts/legacy_audit/vba_sources/GPs/MainForm.frm:4537) and [`GetTinhtrangCCDDK`](/D:/GXP-QLCL/artifacts/legacy_audit/vba_sources/GPs/MainForm.frm:4609) prove the status model is data-driven:
  - no certificate number or `???` -> not yet issued
  - status column `"-"` -> obsolete / no longer effective
  - blank status column -> issued but not yet effective
  - otherwise -> effective
  - `HHL` text present -> invalidated with explicit reason
- The same routine also gates operator actions:
  - update is allowed only when row is not current, has no successor, and has a real number
  - export is allowed only when row is current, has no successor, and has a real number

## Link to record/file workflow
### Record identity
- [`Get_sIDTD`](/D:/GXP-QLCL/artifacts/legacy_audit/vba_sources/GPs/RecordForm.frm:406) formats change rows as `TD-<ID>`.
- [`GetTT_Tdoi`](/D:/GXP-QLCL/artifacts/legacy_audit/vba_sources/GPs/RecordForm.frm:409) resolves the selected change row into RecordForm context.

### Shared folder loading
- [`LoadAllFolders_KT_TD_DDK`](/D:/GXP-QLCL/artifacts/legacy_audit/vba_sources/GPs/RecordForm.frm:499) is shared by:
  - inspection records
  - change records
  - DDKD records
- This is important for migration design:
  - change rows are not isolated metadata rows
  - they participate in real folder/file browsing and document preparation paths

## Business interpretation
- Actual legacy meaning of one change request:
  - identify a site
  - capture requested/accepted changes
  - preserve structured before/after details
  - link the currently effective certificates/DDKD being impacted
  - create successor rows for adjusted certificates when needed
  - later promote those successor rows into active/current state through explicit update actions
  - expose both current links and successor links back in the same change record UI

## Migration implications
- Target model should treat change management as a first-class bounded workflow, not as free-form notes under site or certificate.
- The target model should separate:
  - affected-current artifact links
  - issued-successor artifact links
  - structured change details
  - promotion-to-current events
  - document generation events
- The target model should preserve lineage:
  - `current artifact` -> `change request` -> `issued successor artifact` -> `promotion to current`
- Record/file access for change requests must still flow through `StorageService`, because legacy RecordForm places change rows on the same document/file axis as inspection and DDKD records.
