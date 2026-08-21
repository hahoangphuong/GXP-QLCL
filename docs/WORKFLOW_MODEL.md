# Workflow Model

## Evidence base
- `db.ktra` headers and named ranges show a single row spanning intake, review, inspection, decision, and certificate linkage.
- `MainForm.frm`, `RecordForm.frm`, `SelectCC.frm`, `SelectDDK.frm`, and `FilterForm.frm` provide the active workflow behaviors.
- `db.Tdoi` and `db.Tdoi2` add a separate but linked change-management track.

## Actual legacy workflow
### 1. Master data / site context
- Company and site are selected from `db.cty` and `db.cso`.
- Site carries province, address, professional lead, and certificate context.

### 2. Inspection case intake
- A `db.ktra` row is created or updated with:
  - GxP type
  - site
  - scope / `MÃ DC`
  - applicable standard
  - inspection type
  - application/registration dossier metadata

### 3. Assessment / preparation
- The same `db.ktra` row accumulates review metadata such as submit date, dossier code, assessor, and assessment result.
- Team selection happens through `TTVForm` and planning sheets.

### 4. Planning
- `KH` and `KHKT` sheets plus add-in procedures `Ke_Hoach`, `List_KH`, `TaoQDKT_KHKT`, `Mo_QDKT`, `In_KHKT` build and publish planning views and inspection decisions.

### 5. Inspection execution
- `db.ktra` stores inspection date, decision reference, BBKT reference, and execution result.
- Folder/file context is resolved from site/case/year and used to browse or create artifacts.

### 6. Document generation
- `RecordForm` / `ExtRecordForm` generate or update decision documents, BBKT, certificates, CAPA and supporting outputs directly in Word templates.

### 7. Certificate issuance
- GPs certificate succession is active workflow logic:
  - `Replace_CC` validates issue/expiry dates on the replacing certificate.
  - It rejects replacement when the proposed new issue date is earlier than the currently active certificate.
  - On confirmation it marks the prior current row obsolete and promotes the selected row to current.
  - It also refreshes derived linkage/index fields for site and case views.
- Certificate origin is explicit business data:
  - `UpdateCCGPsItem_Row` resolves origin from either `db.ktra` or `db.Tdoi`.
  - If neither origin resolves, the UI marks the source as unknown instead of inferring one.
- Operator-facing status text is derived from business state, not just formatting:
  - not yet issued
  - issued but not yet effective
  - current and still valid
  - expired by date
  - invalidated / superseded
  - invalidated with explicit `HHL` reason text
- `db.cc` records are often linked to `db.ktra`, but not universally.
- Some certificates are reissued or administratively issued without a real inspection row, so blank `db.cc.ID ĐỢT KTRA` can be legitimate.
- UI allows selection, issue, view, and update of certificates.
- `latest` flags and linked IDs track certificate succession.

### 8. DDKD / business eligibility
- `db.dkkd` manages separate but related issuance flow.
- It can reference one or more related `db.cc` rows and has its own document handling and publication flow.
- `SelectDDK.frm` is not just lookup UI. In edit mode it delegates double-click mutations back into `MainForm.GetSetDataDDKDs`, so operators can edit scope text, professional personnel fields, issue metadata, and linked predecessor/successor records directly on the selected DDKD row.
- Replacement lineage is explicit:
  - `MainForm.ChonDDK_Thaythe(..., TT_Type = 0)` links the current DDKD row to the predecessor row, auto-copies missing scalar fields from that predecessor, increments `Lần cấp` when empty, and appends human-readable issuance history text.
  - `MainForm.ChonDDK_Thaythe(..., TT_Type = 1)` links the current row to its replacement and marks the current certificate row as no longer current by writing `"-"` into the status column.
- Status is derived from a combination of:
  - certificate number presence
  - current/obsolete marker
  - expiry-or-invalidity text (`HHL`)
  - replacement linkage
  - these values also gate whether the UI exposes `Update` versus `Export`.
- DDKD scope is multi-track inside one row:
  - four independent DDKD scope columns are used for `GMP`, `GLP`, `GSP`, `GDP`
  - each scope can be edited separately through `EditDaychuyen`
  - each scope can link back to one or more source GPs certificate IDs
- Document generation for DDKD has a preparatory operator step:
  - `LanCapDDK.frm` captures issue-count/history text
  - `PTr_DC_DKKD.frm` captures checklist flags used to suppress or retain adjustment bullets in the presentation document
- Legacy file handling for DDKD is bucketed by numeric prefixes `1..5` within a site folder and a `Lần n` subfolder; `RecordForm.btnFilez` generates a missing output into the matching slot or opens the existing file in Explorer.

### 9. Change management
- `db.Tdoi` tracks request, handling, approval, and effective date.
- `db.Tdoi2` stores detailed before/after changes such as rename/address updates.
- Change-management has its own creation workflow in VBA:
  - `InsertNewTdoiDB` allocates a fresh `db.Tdoi.ID`
  - pre-fills the site ID
  - seeds `Mô tả` and `Hiệu lực` with `???`
  - auto-links the currently effective GPs certificate IDs and DDKD IDs for that site when present
- Detail rows are explicit child records:
  - `InsertNewTdoi2DB` allocates a fresh `db.Tdoi2.ID`
  - links back through `ID Gốc`
  - seeds the change-category field with `???`
- “Cấp điều chỉnh” in change flow is not just a status flip:
  - `btnCapCCTD_Click` copies a new GPs certificate row from the selected source certificate and appends the new ID back onto the change row
  - `btnCapDDKTD_Click` does the same for DDKD via a revision-copy flow
  - the change row therefore becomes a linkage hub to newly issued adjusted documents, not merely a note about change intent
  - those newly created successor rows are not automatically current/effective
  - later promotion happens through separate update actions (`Replace_CC`, `CapNhat_DDK`) after issue metadata exists and date-order checks pass

### 10. Shared mutation gateway
- `GetSetData` is the central field-mutation router used by case, certificate, DDKD, and change flows.
- It chooses editor behavior by field-type contract:
  - plain text editor
  - bilingual text editor
  - date text editor
  - expiry/effective-date picker with month-offset shortcuts
  - professional-license/person selector
  - DDKD issue-count/history editor
- Successful writes force recalculation and refresh workbook-level derived state, so the helper is part of business mutation semantics, not only UI plumbing.

### 11. Saved filtering / operational views
- `FilterForm` is a persisted query-definition layer, not a temporary dialog only.
- It stores operator selections back into workbook names under `Loc!Dk_Loc*`, so filtering intent survives across sessions.
- The filter engine applies business semantics across `db.ktra` and `db.cc`, including:
  - certificate present vs absent
  - valid vs expired certificates
  - initial registration vs renewal
  - not yet inspected vs decision-issued-but-not-yet-inspected vs inspected
  - in-progress vs completed processing
  - “new site” / “new production line” detection by scanning earlier inspections for the same site or same site+scope after a cut-off date
  - product-class / dosage-form flags
  - validity filters derived from linked current certificate rows

### 12. Scope and inspector helper semantics
- `DCForm` is the actual scope-structure engine:
  - it parses legacy scope strings into old-form vs new-form representations
  - loads GxP-specific node dictionaries from workbook names like `PVCN_GMP`, `PVCN_GLP`, `PVCN_GSP`, `PVCN_GDP`
  - recompiles edited nodes back into serialized legacy strings
  - can force “new-form” editing and can switch limitation text into translated EN display mode
- `TTVForm` is the actual inspector/team compiler:
  - it builds compact names, decorated names, initials, authorization text, and grouped lists across core inspectors, VKN, and SYT
  - downstream document generation depends on these compiled string variants, not only on raw person IDs or names

## Proposed target workflow model
Split the wide legacy row into explicit business stages:
1. `Case`
2. `CaseApplication`
3. `Assessment`
4. `InspectionPlan`
5. `InspectionExecution`
6. `InspectionOutcome`
7. `CertificateIssuance`
8. `BusinessEligibilityIssuance`
9. `ChangeRequest`
10. `ChangeApproval`
11. `DocumentLifecycle`

## State model proposal
### Inspection case
- `draft`
- `application_received`
- `under_assessment`
- `planned`
- `decision_issued`
- `inspection_in_progress`
- `inspection_completed`
- `awaiting_certificate_decision`
- `certified`
- `closed`
- `cancelled`

### CAPA subworkflow
- CAPA is modeled as a child workflow on top of `inspection_completed`, not as a separate primary case-state ladder.
- A case may move from `inspection_completed` to `awaiting_certificate_decision` only when:
  - no CAPA cycle is required, or
  - the latest CAPA cycle for that case is `accepted`
- A new CAPA cycle may be requested only while the case is still in `inspection_completed`.
- Once the case has advanced to `awaiting_certificate_decision`, CAPA must not be reopened implicitly; operators must first resolve workflow state explicitly instead of creating contradictory "awaiting but CAPA requested" data.
- All case-backed certificate paths share one eligibility rule:
  - `inspection_case` issuance requires case state `awaiting_certificate_decision` or `certified`
  - promotion to current for a case-backed certificate requires the same eligibility
  - `awaiting_certificate_decision -> certified` also re-checks the same CAPA gate
- Current implemented CAPA cycle statuses are:
  - `requested`
  - `submitted`
  - `accepted`
  - `rejected`
- New CAPA rounds are allocated by incrementing `round_no`.
- A new round is currently allowed only after the latest round was rejected.
- Accepted CAPA cycles are immutable.
- CAPA assessment identity is bound to the authenticated application user; client-supplied assessor text is treated only as legacy/non-authoritative input.
- CAPA document families such as `INSPECTION_CAPA_LAN_1` and `INSPECTION_CAPA_LAN_2` link to the exact `capa_cycle` row, not only to the parent case.

### Change request
- `received`
- `under_review`
- `accepted`
- `rejected`
- `effective`
- `superseded`

### Document lifecycle
- `template_selected`
- `draft_generated`
- `edited`
- `issued`
- `signed`
- `archived`

## Migration note
- Do not map the workflow back into one target table like `db.ktra`.
- Migrate history as events or stage records linked to a stable case identifier.
- Certificate migration must support both case-backed and non-case-backed issuance flows.
- DDKD migration must preserve predecessor/successor lineage and issuance-history text as first-class data, not just as derived document text.
