# GXP-QLCL UI redesign — additional VBA workspace references

Status: companion implementation specification to `docs/UI_REDESIGN_VBA_REFERENCE.md`.

This document captures additional operator workflows visible in the supplied legacy VBA forms. Codex must read both documents together. Where this document adds more specific behavior for certificates, registration eligibility, or document workspaces, this document supplements the main specification; it does not override backend/domain contracts.

## 1. What the additional VBA forms reveal

The additional forms confirm that the legacy application is not merely a search form. It is a **context-preserving business workspace** centered on one selected facility.

The top master list remains visible while the lower workspace changes tabs. The operator can inspect:
- facility general information
- inspection/change history
- GPs certificates
- ĐĐK certificates
- supporting professional-license/personnel information
- document sets for a selected inspection round

The web redesign should preserve this concept: **selection of a facility is durable context; tabs switch the business projection, not the business object.**

## 2. Facility workspace top-level tabs

The VBA examples show the following major facility-level tabs:

- `Thông tin chung`
- `Các đợt kiểm tra & Thay đổi`
- `Giấy chứng nhận GPs`
- `Giấy chứng nhận ĐĐK`

These should map naturally to facility workspace sections/tabs on web.

Recommended web naming:
- **Thông tin chung**
- **Kiểm tra & thay đổi**
- **Chứng nhận GPs**
- **ĐĐKKDD / ĐĐK**

Keep terminology aligned with the authoritative backend/domain terminology already used in the repository. Do not silently rename stored business concepts.

## 3. Chứng nhận GPs workspace

The legacy GPs certificate form has a two-pane structure:

### 3.1 Left pane — certificate history for selected facility

Compact list of certificates with information equivalent to:
- GxP type (e.g. GMP)
- certificate class/category when present
- certificate number
- issue date

The web version should show a compact selectable history table, not large cards.

Recommended columns when data exists:
- Loại GxP
- Số GCN
- Ngày cấp
- Hết hạn
- Tiêu chuẩn
- Tình trạng

Selecting a row updates the certificate detail panel without leaving the selected facility workspace.

### 3.2 Right pane — selected certificate detail

The VBA form shows fields equivalent to:
- `Số GCN`
- `Ngày cấp`
- `Hết hạn`
- `Tiêu chuẩn`
- `Tên cơ sở`
- `Địa chỉ cơ sở`
- `Tên công ty`
- `Trụ sở`
- `Phạm vi chứng nhận`
- `Giới hạn`
- `Cơ quan cấp`
- `Tình trạng`
- `Nguồn gốc`

Web implementation should use a dense label/value form layout. Long values such as certificate scope and limitations should use large readable text panels with preserved line breaks.

`Tình trạng` should be visually clear but not decorative. Use a compact status badge or status strip.

`Nguồn gốc` is important provenance/context and should not be dropped merely because it looks legacy-specific. If the current backend has an authoritative equivalent, surface it.

### 3.3 Certificate chain/history

The certificate list is clearly historical, while one certificate can be current/valid. The web UI should distinguish:
- historical certificates
- current certificate
- expired/replaced certificate

Do not infer replacement rules client-side; use backend state/relationships where available.

## 4. ĐĐK / ĐĐKKDD workspace

The second VBA form reveals that ĐĐK is a richer business object than a simple certificate number.

### 4.1 Left pane — ĐĐK certificate history

The list shows multiple historical ĐĐK records, with fields such as:
- certificate/decision number
- date
- issuance sequence (`Lần`)

The web version should preserve this as a compact history table.

Recommended columns when supported:
- Số GCN / Số ĐĐK
- Ngày cấp
- Lần cấp
- Tình trạng
- Thay thế / bị thay thế bởi

### 4.2 Primary actions

The VBA form exposes actions equivalent to:
- `Tạo mới`
- `Điều chỉnh`
- `Hồ sơ`

On web these should be contextual actions in the ĐĐK workspace, enabled only when existing backend write/workflow APIs and RBAC permit.

Do not implement local-only fake forms.

### 4.3 ĐĐK detail fields

The form shows business fields such as:
- `Số GCN`
- `Ngày cấp`
- `QĐ cấp`
- `Cấp lần`
- `Tên công ty`
- `Trụ sở`
- `Tên cơ sở`
- `Địa chỉ cơ sở`
- professional/technical responsible persons
- qualification
- CCHN number/date
- business activity/scope by GxP type
- applicable standard
- `Tình trạng`
- `Thay thế`
- `Bị thay thế bởi`

This means the web workspace must support a richer structured detail view rather than reducing ĐĐK to a single document link.

### 4.4 Professional-person / CCHN data

The VBA form includes at least two professional-person rows with concepts such as:
- person name
- qualification (`Dược sỹ đại học` in example)
- CCHN number
- CCHN date

Treat this as structured business data if the backend already models it. Do not flatten it into free text if authoritative structured fields exist.

If the current backend does not yet expose this data, Codex should record the API/domain gap rather than fabricating it in React.

### 4.5 Business scope by GxP type

The form exposes scope/activity grouped by types such as:
- GMP
- GLP
- GSP
- GDP

The web UI should display these as compact sections/tabs/rows associated with the selected ĐĐK record. Preserve long scope text and applicable standard.

Do not assume every record has all four types.

## 5. Inspection document workspace

The third VBA form is especially important. It shows a dedicated **document bundle/workspace for one inspection round**.

This is more than a generic file browser.

### 5.1 Context header

The form keeps the inspection context visible, including:
- year
- selected facility / inspection descriptor
- inspection type/context
- identifiers such as facility and inspection code when available

The web document workspace should therefore open in the context of a selected inspection/change event, not as an unscoped global file list.

### 5.2 Canonical document checklist

The VBA workspace shows named business-document slots such as:
- Biên bản thẩm định
- Quyết định kiểm tra
- Kế hoạch kiểm tra
- Biên bản đánh giá
- Báo cáo đánh giá
- Đánh giá CAPA 1
- Đánh giá CAPA 2
- Phiếu trình PCT
- Phiếu trình CT
- Quyết định cấp CC
- Chứng chỉ GPs
- Đánh giá rủi ro
- Xác nhận tình trạng
- Đổi tên, địa chỉ
- Đánh giá thay đổi
- CV đồng ý thay đổi

These names are valuable legacy workflow signals. The web redesign should not collapse them into an undifferentiated list of files.

Instead provide a **document checklist/table** where each business document type is a row with columns/actions such as:
- Document type
- Current file name
- Status/presence
- Modified/version info where available
- `Mở`
- `Tạo từ mẫu` / `Tạo file nháp` when an authoritative template workflow exists
- `Xem lịch sử`
- optional `Mở thư mục`

The exact labels must use authoritative repository terminology and template contracts.

### 5.3 Presence/completeness indicators

The legacy form visually makes it obvious which slots have files and which are blank.

The web UI should preserve this operational clarity:
- present/current
- missing/not yet created
- multiple/history available
- possibly stale/replaced when backend supports that state

Do not infer requiredness or completion purely client-side. Requiredness should come from workflow/domain/template contracts.

### 5.4 Template-based creation

The VBA interface contains actions equivalent to creating a draft/template-derived document next to individual document rows.

Where the existing backend/template pipeline supports this, web should expose `Tạo từ mẫu` contextually from the correct document row.

Do not reproduce VBA automation logic in React. Web calls server-side document-generation workflow.

### 5.5 Direct Office/Explorer workflow remains important

The user workflow still relies on opening/editing Word documents against Synology. The redesign must preserve an efficient path to that workflow.

Do not force a download-edit-upload loop if an existing Explorer/desktop integration path is available.

The web UI can be the control plane while Word/Explorer remains the document editing surface.

## 6. Stronger workspace architecture derived from all supplied forms

The combined legacy UI suggests this web structure:

```
FacilityWorkspace
  PersistentContextHeader
  FacilityTabs
    GeneralInfo
    InspectionAndChange
    GpsCertificates
    DdkCertificates

InspectionAndChange
  EventHistoryTable
  SelectedEventSummary
  EventTabs
    Registration
    Inspection
    Capa
    FollowUp
    GpsCertification
    OtherCertification
    Documents

GpsCertificates
  CertificateHistoryTable
  CertificateDetail

DdkCertificates
  DdkHistoryTable
  DdkDetail
  ProfessionalPersons
  BusinessScopes
  DdkDocuments

Documents
  InspectionDocumentChecklist
  SupportingDocuments
  FolderActions
```

Names can differ, but the context hierarchy must remain recognizable.

## 7. Interaction rules

### 7.1 Selecting a facility

Selecting a facility must update all relevant lower workspaces while retaining the selected row visibly.

Do not require repeated search after switching tabs.

### 7.2 Selecting a history record

Selecting an inspection/certificate/ĐĐK history record updates only the corresponding detail pane.

Do not navigate away unless the user explicitly asks for a full-page/editor view.

### 7.3 Create/change actions

Actions such as:
- Công ty mới
- Cơ sở mới
- Dây chuyền mới
- Tái đánh giá
- Thay đổi
- ĐĐK Tạo mới
- ĐĐK Điều chỉnh

must be context-aware and RBAC-aware.

If backend support is not ready, disabled state is preferable to fake behavior.

## 8. Density and dimensions

The screenshots confirm operators are comfortable with very dense desktop forms. Therefore the web UI should intentionally target high density:
- default table row height roughly compact desktop scale, not touch-first oversized scale
- compact tabs and toolbar buttons
- use full available viewport width
- minimize redundant titles
- allow long business text areas to consume vertical space where necessary
- use split panes and resizable regions when practical

At 1920x1080, the operator should be able to see:
- facility search/results
- selected context
- at least one history table
- meaningful detail content
without excessive scrolling.

At 1366x768, horizontal/vertical scrolling inside panes is acceptable, but the master context and primary navigation must remain usable.

## 9. Color semantics from VBA — preserve meaning, not exact colors

The legacy forms use strong color to distinguish selected rows, editable/detail fields, certificate/history areas, and status.

Do not copy the exact Windows/VBA palette. Preserve semantic contrast instead:
- selected row: strong accent
- read-only data regions: neutral/light surface
- success/current-valid state: subtle green semantics
- warnings: amber
- errors/blocked: red
- editable or actionable controls: visually distinct but restrained

Avoid turning every panel into a colored card.

## 10. Additional acceptance criteria

In addition to `docs/UI_REDESIGN_VBA_REFERENCE.md`, audit the implementation against these criteria:

1. Facility selection persists while switching among General / Inspection & Change / GPs / ĐĐK sections.
2. GPs certificate history is a compact selectable list/table with detail shown in context.
3. GPs detail preserves scope, limitation, issuer, validity/status, and provenance/source when authoritative data exists.
4. ĐĐK history/detail is treated as a first-class business workspace, not only a downloadable certificate.
5. Professional-person/CCHN information is structurally represented when backend data supports it.
6. Inspection documents are shown as a typed business-document checklist, not only a generic filesystem listing.
7. Template/draft actions are server-backed and contextual to a document type.
8. Missing backend fields are documented as gaps; the frontend does not invent data.
9. High-density desktop layout remains the design target.
10. The UI does not force the user to lose facility/event context to inspect certificate or document history.

## 11. Slice impact

### Slice A

The new references reinforce, but do not materially expand, Slice A:
- dashboard
- Tra cứu
- facility selection
- persistent context
- dense results

### Slice B

Slice B should now explicitly include:
- facility-level tabs
- inspection/change history
- GPs certificate history/detail where APIs already exist
- ĐĐK history/detail where APIs already exist
- selected-event detail
- document checklist shell using existing document APIs/contracts

### Slice C

Later richer actions:
- create/edit ĐĐK workflows
- professional-person/CCHN editing
- template-based document generation for all legacy slots
- certificate replacement chains
- advanced saved filters/alerts
- richer Explorer/document integration

Do not pull Slice C into Slice A merely because the legacy screenshots display these functions.

## 12. Codex reporting requirement for UI work

When implementing UI slices, Codex must explicitly state which of these legacy-workspace concepts were:
- implemented with existing API support
- displayed as disabled/not yet available
- omitted because backend data is unavailable
- supported by newly added minimal backend read APIs

This makes later audit deterministic and prevents silent feature loss during redesign.
