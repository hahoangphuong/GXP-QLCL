# Legacy System Map

## Scope and evidence
- Primary evidence: `artifacts/legacy_audit/workbook_inventory.json`, `artifacts/legacy_audit/addin_inventory.json`, `artifacts/legacy_audit/anomalies.json`, and extracted VBA sources under `artifacts/legacy_audit/vba_sources/`.
- Workbook and add-in are both active code containers.
- `Danh sách Kiểm tra GPs.xlsb` is not just a data workbook. It loads `GPs.xlam`, exposes user entry points, and delegates most heavy business flows through `Application.Run`.

## Runtime shape
- Excel workbook = UI shell + reporting sheets + hidden data tables + lightweight helper VBA.
- `GPs.xlam` = primary business logic, UserForms, file access, document generation, Word/PowerPoint automation, lookup/filter/planning logic.
- Synology share = operational file store and template/document location.
- Microsoft Word desktop automation is part of core behavior, not a side utility.

## Workbook inventory
Visible or user-facing worksheets:
- `GMP`, `GLP`, `GMPbb`, `DsCB GMP`, `DsCBKT`, `DsCBDDK`, `DsCs`, `DsCty`, `Loc`, `KH`, `Lịch sử TTV`, `TTviên`, `Địa danh`, `Thống kê`, `SXVX`.

Very hidden / hidden control and storage worksheets:
- `GSP`, `GMPnn`, `KHKT`, `Liên hệ`, `Ngừng CN`, `db.cc`, `db.ktra`, `db.Tdoi`, `db.Tdoi2`, `db.DC`, `db.cso`, `db.cty`, `db.dkkd`, `Dịch-Viết tắt`, `DsCB`, `Nhóm 1c`, `Phạm vi CN`.

Core tables in workbook:
- `db.cty`: companies, 333 data rows.
- `db.cso`: sites, 380 data rows.
- `db.ktra`: inspections / cases / workflow row, 1549 data rows.
- `db.cc`: certificates, 1632 data rows.
- `db.dkkd`: business eligibility / DDKD certificates, 835 data rows.
- `db.Tdoi`: changes, 225 data rows.
- `db.Tdoi2`: rename/address change detail, 186 data rows.

## Named-range model
- Workbook contains 1571 names.
- Names are used as a logic layer, not only formatting helpers.
- Important families:
  - `db_*`: logical slices over hidden tables, for example `db_ktra`, `db_cc_GPs`, `db_ID_Cs`, `db_QDKT_ktra`.
  - `List_*`: precomputed filter, planning, and report datasets.
  - `Print_Area`, `Source_Link`, `UpDay`, `Tday`: report export and refresh metadata.
  - `Folder_Hoso`: legacy storage root alias currently pointing at Synology UNC path.

## Cross-workbook call boundary
Workbook entry points discovered in `Danh sách Kiểm tra GPs.xlsb!Module1`:
- Search / main form: `Main`, `Main_LapKH`.
- Planning: `AddTTV_KHKT`, `TaoQDKT_KHKT`, `Mo_QDKT`, `In_KHKT`, `Ke_Hoach`.
- Reporting and listing: `Filterx`, `Ds_cong_bo_GPs`, `Ds_cong_bo_GPs2`, `Ds_lich_su_GPs`, `Ds_cong_bo_KT`, `Ds_cong_bo_DDK`, `Ds_Co_so_Cty_GPs`, `Xuat_XLSx2`.
- Initialization: `LoadInitArray`, `ReFilter`.

This means the real boundary is:
- Workbook owns shortcut macros, sheet-local formulas, print/update metadata.
- Add-in owns most business interactions and side effects.

## Add-in component map
High-value components:
- `MainForm.frm`: central operator UI, 544 procedures. Owns search, case/site navigation, update commands, certificate/DDKD linkage, file-list orchestration.
- `RecordForm.frm`: record/file/document form, 132 procedures. Owns folder loading, document creation, Word bookmark population, CAPA/document copy logic.
- `FilterForm.frm`: filter and listing orchestration.
- `ExtRecordForm.frm`: external templates and supplemental document generation.
- `SelectCC.frm`, `SelectDDK.frm`, `ChonMauCC.frm`, `SelectFile.frm`: certificate/document selection and folder/file browsing.
- `WinAPI.bas`: shell, path, folder, and Win32 wrappers.
- `Module1.bas`: shared business and report helper logic, planning, list generation, export.

Additional implications from re-audit:
- `SelectCC.frm` and `SelectDDK.frm` are not passive pickers. In edit mode they delegate direct row mutation back into `MainForm`.
- `FilterForm.frm` is a persisted operational query layer because it saves filter state into workbook names and reuses those saved semantics later.
- `ExtRecordForm.frm` is not a cosmetic annex; it generates real support artifacts through Word and Excel templates and can print immediately when the operator holds `Shift`.
- `DCForm.frm` is the scope-structure engine, not just a UI tree: it parses legacy serialized scope text, maps nodes against GxP-specific dictionaries, recompiles normalized output, and supports old-form/new-form conversion.
- `TTVForm.frm` is the inspector/team compiler, not just a chooser: downstream flows depend on the exact compiled string variants it emits for names, titles, initials, authorization text, and grouped member sets.
- `TextForm.frm`, `TextFormVA.frm`, `NhapHanHL.frm`, `LanCapDDK.frm`, and `Password_Form.frm` together form a reusable mutation shell layer that encodes how different business fields may be edited.

## Word and document generation map
Evidence:
- `RecordForm.frm` and `ExtRecordForm.frm` create or attach to `Word.Application`.
- Templates are populated through named bookmarks such as `TenCoSo`, `Diachicoso`, `QDKT`, `TT1`, `DsTT`, `CAPAx`, `Pvi...`.
- `RecordForm.frm` contains direct logic to delete rows, paste bookmark content from source documents, and save `.docx`.
- `ExtRecordForm.frm` also automates PowerPoint for at least one document path.
- DDKD generation is a distinct subflow inside `RecordForm.CreateFilez`:
  - case `1` -> `Tao_PT_cap_DDK`
  - case `2` -> `Tao_Giay_DDK`
  - case `3` and `4` -> `Tao_PL_QD_GiayDDK`
- The DDKD presentation writer is not a pure scalar fill:
  - it compares current and predecessor DDKD rows
  - deletes whole bookmark groups when rename / personnel change conditions are absent
  - suppresses adjustment bullets from `PTr_DC_DKKD` checkbox state
- The DDKD appendix/issuance-decision writer is also not one generic template:
  - `Get_Tplz` selects `z3. Phụ lục GCN ĐĐKKDD.dotx` for appendix and `z4. QĐ cấp ĐĐKKDD.dotx` for issuance decision
  - both selected templates then pass through the same shared writer
  - that shared writer iterates across four DDKD scope groups (`GMP`, `GLP`, `GSP`, `GDP`) and opens secondary scope templates `z3. Phamvi{GP}.docx`

Implication:
- Legacy documents are template-driven desktop Office artifacts, not simple text exports.
- A single business document may have multiple technical renditions: source template, generated `.docx`, derived `.pdf`, scanned/signed outputs.

## File and Synology interaction map
Observed behaviors:
- Workbook loads add-in from local `Addins\` or Synology UNC fallback.
- Folder discovery uses year directories and nested inspection folders.
- File browsing uses `FindFirstFileW`, `FindFirstDir`, `Shell`, and `explorer.exe`.
- Folder creation is active behavior in some flows, for example planning/QDKT output and DDKD folder creation.
- File naming is prefix-driven: examples found in VBA and docs include `4.*.doc*`, `9.*.ppt*`, and generated names beginning with numeric registry prefixes.
- DDKD has its own folder-loading behavior under a separate root:
  - first-level folder match is `* (<site_id>)*`
  - if no site folder matches, VBA creates one using `TenCtyx - DiaChi (<site_id>)`
  - second-level folder match is `Lần *` or a single concrete `Lần n`
  - if no `Lần n` folder exists for the current issuance, VBA creates it on demand
- DDKD file enumeration is number-bucket based:
  - `LoadFileDDKLists` scans `*.*.*`
  - the numeric token before the first dot routes the file into slot `1..5`
  - `btnFilez(i)` either opens the selected file in Explorer or generates the missing file for slot `i`
- Inspection-support artifacts generated by `ExtRecordForm` are application-mixed:
  - Word `.dotx` families for travel letters, checklists, payment authorization, and attendance lists
  - Excel `.xltx` families for advance-payment and reimbursement forms
  - optional immediate print path when `Shift` is held

## Actual operating model
1. User works inside Excel workbook.
2. Workbook loads `GPs.xlam`.
3. User opens `MainForm` or planning/report commands.
4. Add-in reads hidden workbook tables and names.
5. Add-in resolves site/case context and corresponding Synology folders/files.
6. Add-in opens Word templates, fills bookmarks, copies content from prior records when needed, and saves back into legacy folder structure.
7. Workbook sheets are refreshed/exported for lists, plans, and public/internal outputs.
8. For DDKD specifically, operators can also maintain predecessor/replacement lineage, issue-count history, linked GPs certificates, and per-GxP scope payload directly from the add-in forms before generating files.
9. For change-management specifically, operators can create a new change row that is immediately pre-linked to current certificate/DDKD records for the selected site, then issue adjusted certificate/DDKD rows from that change context.
10. For “current” inspection/certificate/DDKD context, the add-in often resolves a derived lookup row first and only then dereferences the base table row. In practice, legacy relies on workbook-maintained current-row indexes as an operational read model.
11. That operational read model is layered: hidden base-table mirror columns, site/scope key grids like `Ds_IDCs_DC`, and sheet-level `MATCH(...)` formulas all participate in resolving the active row.

## Reverse-engineering caveats
- Full procedure inventory is captured in generated audit artifacts; this document is the system map, not the exhaustive dump.
- VBA project trust is disabled in Excel, so source extraction uses `oletools` rather than COM `VBProject` access.
- Some procedure names remain commented-out or duplicated legacy variants; they should not be treated as active behavior without call evidence.
