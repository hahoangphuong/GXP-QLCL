# VBA Function Map

## Scope
- Exhaustive module/procedure inventory is stored in `artifacts/legacy_audit/*inventory.json`.
- This document maps the proven high-value procedures and component responsibilities to business purpose and target web ownership.

## Workbook shell (`Danh sách Kiểm tra GPs.xlsb`)
| VBA entry point | Evidence | Business purpose | Reads/Writes | File ops | Target service |
|---|---|---|---|---|---|
| `Load_Lib` | workbook `Module1.bas` | Load `GPs.xlam` from local add-in folder or Synology fallback | workbook path | open workbook | client bootstrap only |
| `Tracuu`, `Tracuu2` | workbook `Module1.bas` | Launch main search/processing UI | names/init arrays | no direct file write | web shell -> `CaseService` search UI |
| `Tracuu_LapKH`, `Tracuu_ThemKH` | workbook `Module1.bas` | Launch planning mode | names / KH sheets | no direct file write | `InspectionService` planning |
| `ThemTTV_KHKT` | workbook `Module1.bas` | Add inspectors to planning/QDKT | `KHKT` context | document side effects downstream | `InspectionService` |
| `Tao_QDKT`, `Mo_QDKTx`, `In_KHKTx` | workbook `Module1.bas` | Planning document generation/open/print | `KHKT`, names | create/open files | `DocumentService` + `StorageService` |
| `KeHoach`, `Filter` | workbook `Module1.bas` | Recompute planning and filter outputs | names and list sheets | export side effects downstream | `InspectionService` / query layer |
| `Ds_cong_bo`, `Ds_cong_bo2`, `Ds_lich_su_GPs`, `Ds_cong_boKT`, `Ds_cong_boDDK`, `Ds_Co_so_GPs`, `Ds_Cong_ty_GPs` | workbook `Module1.bas` | Produce report/list sheets | table names + print areas | export only | read model / reporting |
| `Xuat_XLS` | workbook `Module1.bas` | Export active print area to separate workbook | print areas | save workbook | reporting/export adapter |

## Add-in components and target owners
| Component | Proven role | Target owner |
|---|---|---|
| `MainForm.frm` | main operator workflow, site/case search, updates, list refresh, certificate/DDKD linkage | `CaseService`, `InspectionService`, `CertificationService`, `ChangeManagementService` |
| `RecordForm.frm` | record preparation, folder/file browsing, document creation, bookmark filling, CAPA copy-forward | `DocumentService` + `StorageService` |
| `ExtRecordForm.frm` | external/supplementary templates, travel/payment/support documents | `DocumentService` |
| `FilterForm.frm` | list filtering and reporting criteria | read/query layer |
| `SelectCC.frm` | certificate lookup/select/show/edit | `CertificationService` |
| `SelectDDK.frm` | DDKD lookup/select/show/edit shell; delegates row mutation back into `MainForm` | `CertificationService` or dedicated `BusinessEligibilityService` |
| `LanCapDDK.frm` | collect issue-count (`Lần cấp`) and issuance-history text for DDKD | `BusinessEligibilityService` |
| `PTr_DC_DKKD.frm` | collect explicit checklist flags for adjusted DDKD presentation generation | `DocumentService` |
| `ChonMauCC.frm` | resolve prior BBKT/template files and choose certificate template | `DocumentService` + `StorageService` |
| `WinAPI.bas` | folder exists/create/find, shell open, rename wrappers | `StorageService` adapter only |
| `TTVForm.frm`, `AddTTVForm.frm` | inspector/team selection and rendering | `InspectionService` |

## Key add-in procedures
| VBA procedure | Evidence | Business purpose | Reads/Writes | File ops | Target web owner |
|---|---|---|---|---|---|
| `Main` | workbook calls `Application.Run "GPs.xlam!Main"` | main operator search and workbench | hidden db sheets, names | downstream through forms | web UI + `CaseService` |
| `Main_LapKH` | workbook call | planning workbench | `KH`, `KHKT`, lists | QDKT generation downstream | `InspectionService` |
| `Ke_Hoach` | `GPs.xlam!Module1.bas` | build planning dataset by GxP stream and date window | `KH` names and certificate/inspection slices | generated docs later | `InspectionService` |
| `List_KH` | `GPs.xlam!Module1.bas` | compute schedule candidate list | `db.ktra`, `db.cc`, filter names | none | query/read model |
| `TaoQDKT_KHKT` | workbook call + add-in module | create inspection decision document from plan row | `KHKT`, inspector/team info, templates | create folder/save file | `DocumentService` |
| `Mo_QDKT` | add-in module | open generated QDKT doc | planning metadata | shell open file | `StorageService` client open |
| `Ds_Co_so_Cty_GPs` | workbook call | produce company/site listing output | `db.cso`, `db.cty`, names | export/print area | read model |
| `Ds_cong_bo_GPs`, `Ds_cong_bo_GPs2` | workbook call | publication/report list generation | `db.cc`, names | export/print area | reporting |
| `PrepareRecordFormData` | `RecordForm.frm` | load selected inspection/DDKD into document/file form | `db.ktra`, `db.cc`, `db.dkkd`, `db.cso` | indirect folder/file load | `CaseService` + `DocumentService` |
| `PrepareRecordForm` | `RecordForm.frm` | set current context before file/document actions | current UI state | none directly | orchestration layer |
| `Tao_QD_CapCC` | `RecordForm.frm` | populate certificate decision document | active doc + current inspection/certificate context | bookmark writes | `DocumentService` |
| `Input_DC_to_CC2` | present as commented legacy variant in `RecordForm.frm` | legacy scope insertion into certificate from source doc | Word bookmarks/ranges | copy/paste within docs | `DocumentService` |
| `AddCC_Cs` | `MainForm.frm` | attach certificate to site/DDKD flow | current site/certificate selection | no direct file op | `CertificationService` |
| `Select_CC`, `Tracuu_CC`, `Show_CC`, `Edit_CC` | `SelectCC.frm` | choose/show/edit certificate links | `db.cc` slices | optional open file | `CertificationService` |
| `GetSetDataCCGPsDs`, `UpdateCCGPsItem_Row` | `MainForm.frm` | edit GPs certificate rows directly from the selection UI and derive status/origin text | read/write `db.cc`, `db.ktra`, `db.Tdoi` | none | `CertificationService` |
| `Replace_CC`, `btnCapnhatCC_Click`, `btnCapnhatCC_STD_Click` | `MainForm.frm` | promote a newer GPs certificate into current status, demote prior current row, update linkage fields, and validate issue-date ordering | writes `db.cc` current marker/link fields and dependent site indexes | none | `CertificationService` |
| `Select_DDK`, `Tracuu_DDK`, `Show_DDK`, `Edit_DDK` | `SelectDDK.frm` | choose/show/edit DDKD rows with active-only filter and direct detail refresh | `db.dkkd` slices via `MainForm.LoadMapping2FullDDKList` | no direct write | `BusinessEligibilityService` |
| `ChonDDK_Thaythe` | `MainForm.frm` | link replacing/replaced-by DDKD records, auto-copy missing fields from predecessor, and append issuance history text | reads/writes `db.dkkd` replacement, issue-count, history, scalar profile fields | no direct file op | `BusinessEligibilityService` |
| `GetTinhtrangCCDDK`, `UpdateCCDDKItem_Row` | `MainForm.frm` | compute DDKD effective-status text/color and gate update/export actions | `db.dkkd` current row + replacement markers | none | `BusinessEligibilityService` |
| `GetSetDataDDKDs`, `edPvi_DDKDs`, `EditDaychuyen` | `MainForm.frm` | edit DDKD scope text and related scalar fields directly on the selected DDKD row | read/write `db.dkkd` | none | `BusinessEligibilityService` |
| `InsertNewTdoiDB`, `InsertNewTdoi2DB` | `MainForm.frm` | create change-request header/detail rows with fresh IDs and prefill linked current certificate/DDKD IDs for the same site | writes `db.Tdoi`, `db.Tdoi2` | none | `ChangeManagementService` |
| `btnCapCCTD_Click`, `btnCapDDKTD_Click` | `MainForm.frm` | create adjustment/revision certificate rows from change-request context and append the new IDs back onto the change row | reads/writes `db.Tdoi`, `db.cc`, `db.dkkd` | none | `ChangeManagementService` |
| `GetSetDataTD`, `GetSetDataTD2`, `UpdateListThaydoi2`, `lbThaydoi_Change` | `MainForm.frm` | edit change-request header/detail rows and refresh structured before/after change detail lists | reads/writes `db.Tdoi`, `db.Tdoi2` | none | `ChangeManagementService` |
| `GetSetData` | `MainForm.frm` | shared mutation gateway that chooses the correct editor contract by field type: plain text, bilingual text, date, expiry picker, professional-license picker, issuance-history picker | writes active workbook tables and recalculates named formulas | none | orchestration helper |
| `Nhap_Lan_Cap` | `LanCapDDK.frm` | operator-confirmed issue count/history capture before DDKD issuance flow | user-entered issuance metadata | none | `BusinessEligibilityService` |
| `Nhap_han_HL` | `NhapHanHL.frm` | operator chooses expiry/effective date from fixed month offsets or manual date entry | user-entered date output | none | shared workflow helper |
| `SuaSoDDK` | `NhapSoDDK.frm` | normalize DDKD number entry by auto-appending `/ĐKKDD-BYT` when missing | user-entered DDKD number/date | none | `BusinessEligibilityService` |
| `GetCheck` | `PTr_DC_DKKD.frm` | operator checklist driving which adjustment bullets remain in DDKD presentation output | form checkboxes only | none | `DocumentService` |
| `Tao_PT_cap_DDK` | `RecordForm.frm` | build DDKD presentation document, including predecessor comparison and conditional bullet suppression | `db.dkkd`, linked GPs certificates, `PTr_DC_DKKD` flags | Word bookmark writes | `DocumentService` |
| `Tao_Giay_DDK` | `RecordForm.frm` | build DDKD certificate document; new-vs-adjustment logic depends on current row and predecessor/history fields | `db.dkkd` current row and predecessor row | Word bookmark writes | `DocumentService` |
| `Tao_PL_QD_GiayDDK`, `Tao_PL_QD_GiayDDK_Thongtinchung` | `RecordForm.frm` | build DDKD appendix / issuance decision with shared common-field writer and per-GxP scope loop | `db.dkkd`, `db.cc`, scope templates `z3. Phamvi{GP}.docx` | Word open/read/write | `DocumentService` |
| `FilterForm.TT_*`, `DoFilter`, `SaveCheck`, `LoadCheck` | `FilterForm.frm` | persistent business filter engine for case/certificate/workflow status, date ranges, product classes, and novelty detection | reads/writes workbook names under `Loc!Dk_Loc*`, scans `db.ktra` + `db.cc` arrays | none | query/read model |
| `DCForm.Edit_DC`, `Get_DCx`, `Get_DC_Nodes`, `Get_Full_DC`, `Load_DC_Nodes`, `Init_PVCN` | `DCForm.frm` | parse, normalize, edit, and recompile scope strings between legacy text form and node-tree form; also translate limitation text for EN mode | scope strings, named certificate-node dictionaries | none directly | `ScopeService` |
| `TTVForm.Get_TTV`, `Get_TTV2`, `Get_TTV_UQ` | `TTVForm.frm` | select inspector/team sets and compile multiple output formats: compact names, decorated names, initials, authorization text, and grouped VKN/SYT lists | inspector directory names `Ds_TTV*` | none directly | `InspectionService` |
| `TextForm.GetText`, `TextFormVA.GetText`, `Password_Form.Get_Pass` | shared forms | operator editing shells that also encode shortcut insertion, bilingual translation assist, and read-only override mode | UI inputs only | none | shared workflow helper |
| `ExtRecordForm.CreateFile` | `ExtRecordForm.frm` | generate support/travel/payment/checklist artifacts with Word and Excel templates, dynamic inspector row expansion, and optional direct print on `Shift` | current inspection/team context, inspector directory, payment form inputs | create/open Word and Excel documents, print | `DocumentService` |
| `LoadFolder2`, `LoadFiles`, `Get_MauCC`, `Get_BBKT` | `ChonMauCC.frm` | enumerate year/folder structure and pick prior certificate or BBKT templates | filesystem only + file names | read/list files | `StorageService` + `DocumentService` |
| `LoadAllFolders`, `LoadDDKFolder`, `LoadFiles2`, `LoadFilesDDK` | `RecordForm.frm` | resolve inspection and DDKD folders/files | filesystem + current IDs | list/open/create folders | `StorageService` |
| `Creat_Update_Folderz`, `btnFilez` | `RecordForm.frm` | create DDKD site/issuance subfolders on demand and generate/open numbered document slots `1..5` | current DDKD folder context | create folder, save docx, shell open | `StorageService` + `DocumentService` |

## Important dependency observations
- Workbook module is mostly a dispatcher into add-in procedures.
- `MainForm.frm` and `RecordForm.frm` are the operational center of gravity.
- `RecordForm.frm` is where business process, file browsing, and document generation are tightly coupled today.
- `WinAPI.bas` should not survive as a business dependency in the web target; only its storage behaviors should survive behind `StorageService`.

## Dead/specific/legacy code
- Multiple folder-loading implementations remain commented out in `RecordForm.frm` and `ChonMauCC.frm`.
- There are commented legacy procedure bodies for `PrepareRecordForm`, `RefreshHistoryItem`, `UpdateDotKtra`, and old `Input_DC_to_CC2` logic.
- These commented variants are valuable as historical specification but should not be treated as active runtime path without call evidence.
