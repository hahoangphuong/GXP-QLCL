# GXP-QLCL UI redesign specification — VBA/Excel driven

Status: implementation specification for Codex and later audit.

## 1. Purpose

Redesign the web frontend so it behaves like a dense desktop-grade business application, preserving the successful operator workflow of the existing VBA/Excel application instead of the current large-card operator shell.

The web UI must keep backend/business logic server-side. This redesign is primarily frontend/UX. Do not weaken authentication, RBAC, fail-closed document behavior, database contracts, or workflow rules.

Core UX principle:

> Dashboard tells the operator what needs attention. Search finds the business object. Workspace lets the operator complete the work without losing context.

The central feature is **Tra cứu** (Search). Most daily workflows begin there.

## 2. Reference UX extracted from the legacy VBA form

The legacy VBA search form is organized as a highly effective three-level master/history/detail workflow:

1. **Facility master list**
   - GxP category selectors: GMP / GLP / GMPbd
   - one quick filter/search box
   - dense facility list with facility code, facility/company name, scope summary, province
   - quick lookup/actions for GPs certificate, ĐĐK and CCHN
   - contextual create/actions such as Công ty mới, Cơ sở mới, Dây chuyền mới, Tái đánh giá, Thay đổi

2. **History for the selected facility**
   - inspection/change events
   - event type
   - standard
   - date

3. **Detail for the selected event**
   - Hồ sơ đăng ký
   - Kiểm tra thực tế
   - Báo cáo khắc phục
   - Xử lý tiếp
   - Cấp chứng nhận GPs
   - Chứng nhận khác
   - inspection decision and related documents
   - inspection scope
   - certificate scope
   - processing/supporting folders

This **master -> history -> detail** model is authoritative for the redesign. Preserve it even if the visual styling changes.

## 3. Design goals

### 3.1 Dense professional application UI

Prefer information density and fast scanning over decorative cards and large empty areas.

The visual target is a modern line-of-business/data-workspace application, not a marketing website.

Use:
- compact headers
- tables/data grids
- sticky column/table headers
- consistent row heights
- compact controls
- restrained spacing
- clear selected-row state
- status badges only where they add meaning
- clear hierarchy without oversized typography

Avoid:
- giant cards for each record
- excessive whitespace
- decorative gradients as the primary hierarchy mechanism
- technical platform/status information on normal operator screens
- forcing users through many pages for data that belongs to one facility/workspace

### 3.2 Preserve operator familiarity

Preserve from VBA where practical:
- terminology
- grouping of fields
- order of business concepts
- relationship company -> facility -> inspection/change -> certificate/documents
- contextual action placement
- high information density

Do not copy VBA pixel-for-pixel. Improve using web capabilities while keeping the mental model familiar.

### 3.3 Context must remain visible

When the operator selects a facility and then an inspection/change event, the current context must remain obvious while navigating tabs/actions.

Use a persistent summary strip showing at least:
- facility code
- facility name
- company name when useful
- GxP type
- current/selected standard
- province/country if useful
- current certificate state/expiry when available

## 4. Main navigation

Use a compact primary navigation:

- **Tổng quan**
- **Tra cứu** — visually emphasized; this is the core daily entry point
- **Nghiệp vụ**
  - Hồ sơ kiểm tra
  - Giấy chứng nhận
  - ĐĐKKDD
  - Theo dõi thay đổi
- **Tài liệu**
- **Báo cáo**
- **Quản trị** — role-gated

Technical items such as deployment platform, auth provider, Phase 5/6/7 state, projection conflicts, etc. must not occupy the operator dashboard. If still needed, move them under **Quản trị -> Trạng thái hệ thống**.

## 5. Dashboard specification

The default authenticated landing page is a business dashboard.

### 5.1 Dashboard metrics

Choose metrics only when supported by existing API/data. Prefer these when available:
- Tổng số cơ sở
- Hồ sơ đang xử lý
- Hồ sơ đến hạn / quá hạn
- Chứng nhận còn hiệu lực
- Chứng nhận sắp hết hạn (30/60/90 days)
- Chờ bổ sung/khắc phục
- Chờ kiểm tra
- Chờ cấp/gia hạn chứng nhận
- Thay đổi cơ sở chưa hoàn tất

If a metric is not currently supported, do not fabricate values. Either omit it or implement the smallest correct backend read model/API after auditing the source owner.

### 5.2 Dashboard interactions

Dashboard metric tiles are shortcuts into **Tra cứu** with filters pre-applied.

Example:
- `Chứng nhận sắp hết hạn 90 ngày: 12`
- click -> Tra cứu opens with the corresponding expiry filter

### 5.3 Work queue

Include a compact `Việc cần xử lý` table/list when data supports it:
- object/facility
- business state
- due/important date
- owner/assignee when available
- direct action/open link

Do not show technical health information here.

## 6. Tra cứu — core screen

### 6.1 Overall layout

Desktop-first layout, designed for 1366px+ screens but still usable at narrower widths.

Recommended structure:

```
+---------------------------------------------------------------+
| TRA CỨU | GMP | GLP | GMPbd | [Search....................]   |
+---------------------------------------------------------------+
| Advanced filters: province | status | standard | year | ...  |
+-------------------------------+-------------------------------+
| FACILITY RESULTS              | FACILITY SUMMARY              |
| dense data grid               | selected facility context     |
+-------------------------------+-------------------------------+
| INSPECTION / CHANGE HISTORY                                   |
| compact table                                                |
+---------------------------------------------------------------+
| Hồ sơ | Kiểm tra | Khắc phục | Xử lý | Chứng nhận | ...      |
+---------------------------------------------------------------+
| selected event detail / document actions / scopes             |
+---------------------------------------------------------------+
```

Do not rigidly reproduce these exact percentages. Preserve the master/history/detail behavior.

### 6.2 GxP mode selector

At minimum preserve current concepts:
- GMP
- GLP
- GMPbd

Use the authoritative codes already present in data/API; do not create translation logic that changes stored values.

Selection filters the master results while preserving the current search string when sensible.

### 6.3 Unified search

One primary search field should match existing searchable data across as many of these as the current API safely supports:
- facility code/legacy ID
- facility name
- company name
- address
- province
- inspection code/file code
- certificate number
- scope/standard

Search should be case-insensitive and Vietnamese-operator friendly where backend support exists.

Do not implement client-only fake search over only the currently loaded 20 rows if that gives misleading results. Prefer server-side search through existing query APIs; extend API only after owner audit if necessary.

### 6.4 Advanced filters

Provide a collapsible compact filter row/panel. Candidate filters:
- province/city
- GxP type
- standard
- facility/current status
- inspection status
- inspection year/date range
- inspection type
- certificate state
- certificate expiry range
- change request state

Only expose filters supported by real data/API.

Provide `Xóa lọc`.

Saved filters are desirable but not required in first implementation unless a persistence owner already exists.

### 6.5 Facility results data grid

Replace large record cards with a dense grid.

Recommended columns, based on available data:
- Mã cơ sở
- Tên cơ sở
- Công ty
- GxP
- Phạm vi / tiêu chuẩn chính
- Tỉnh/thành
- Kiểm tra gần nhất
- Trạng thái
- Chứng nhận hiện hành
- Hết hạn

The exact first iteration may use fewer columns if the current read models do not expose all of them.

Required grid UX:
- visible selected row
- sortable columns where correct
- horizontal scrolling instead of destroying density
- sticky header
- reasonable min/max widths
- text ellipsis with tooltip/title for long fields
- keyboard focus behavior should remain usable
- double-click or explicit `Chi tiết` action

Do not add a heavy grid dependency unless it provides clear value and fits current frontend architecture. A well-built semantic table is acceptable.

### 6.6 Facility summary panel

When a facility is selected show a concise summary, not another giant card.

Include existing fields as available:
- facility code
- facility name
- company
- address
- province
- GxP type
- current state
- current standard/scope summary
- current certificate status/expiry when supported

Contextual actions should appear near this summary.

## 7. Contextual actions

Preserve the legacy action model and progressively enable actions based on selected context/RBAC.

Desired action bar:
- `+ Công ty`
- `+ Cơ sở`
- `+ Dây chuyền`
- `+ Hồ sơ kiểm tra`
- `Tái đánh giá`
- `Thay đổi`

Rules:
- do not invent backend write flows that do not exist
- actions without a valid implemented workflow may be rendered disabled with a clear reason, or omitted in the first slice
- do not fake success locally
- use permissions/RBAC from the server

Legacy quick lookups such as GPs certificate / ĐĐK / CCHN should become tabs/actions in the selected business workspace rather than isolated decorative buttons.

## 8. Inspection/change history

For the selected facility show a compact table by default.

Recommended columns:
- Loại sự kiện
- Tiêu chuẩn
- Ngày
- Trạng thái
- Số hồ sơ / mã kiểm tra
- Chứng nhận liên quan when available

A timeline visualization may be offered later, but the table is primary because it supports fast scanning.

Selecting a history row updates the event detail area below without losing the selected facility.

## 9. Event detail tabs

Preserve the VBA workflow concepts. Use compact tabs:

- **Hồ sơ**
- **Kiểm tra**
- **Khắc phục**
- **Xử lý**
- **Chứng nhận GPs**
- **Chứng nhận khác**

Tab labels may include a subtle completeness/state marker only when backed by real data:
- complete
- warning/incomplete
- pending

Do not infer completion from missing frontend fields.

## 10. Inspection detail content

The selected inspection/event detail should support fields analogous to the VBA form when the backend already exposes them, such as:
- inspection decision number/date
- inspector/team members
- inspection date
- applicable standard
- report date
- evaluation/result
- notes

Use aligned label/value grids instead of large standalone cards.

Do not duplicate business logic in React. Editing/actions must use existing server workflow APIs.

## 11. Document actions

Replace the right-side VBA document buttons with a compact `Tài liệu đợt kiểm tra` panel/list.

Examples:
- Quyết định kiểm tra
- Kế hoạch kiểm tra
- Biên bản đánh giá
- Báo cáo đánh giá

Each item may expose only supported actions:
- Mở
- Tạo
- Xem lịch sử
- Mở thư mục

Document flow must remain fail-closed. Frontend must never receive NAS credentials. Existing Synology/Tailscale/storage contracts remain authoritative.

## 12. Scopes

Preserve prominent side-by-side or tabbed display of:
- **Phạm vi đánh giá**
- **Phạm vi chứng nhận GPs**

These are important high-density text fields. Use readable, scrollable text areas/panels that preserve line breaks.

Future enhancement: a compare/diff mode. Do not implement semantic diff unless supported/tested correctly.

## 13. Document explorer / folders

The legacy `Hồ sơ xử lý` and `Hồ sơ phụ trợ` concepts must remain easy to reach.

Web may provide a document list/tree when existing APIs support it, but retain an operator-friendly path to the existing Explorer/Word workflow where supported by the existing storage design.

Do not mirror NAS files to another storage provider for this redesign.

## 14. Business alerts

Where data is authoritative, use compact warnings for things such as:
- certificate nearing expiry
- overdue processing
- missing required workflow document
- unresolved change request
- missing evaluation result

Warnings must be business-relevant and must not be guessed client-side.

## 15. Frontend architecture requirements

Current frontend has a large `frontend/src/App.tsx`. The redesign should reduce monolithic growth rather than adding another large conditional block.

Codex should refactor incrementally into components/modules with clear responsibility, e.g. conceptually:

```
frontend/src/
  App.tsx
  components/
    AppShell.tsx
    TopBar.tsx
    PrimaryNav.tsx
    DataTable.tsx
    StatusBadge.tsx
    EmptyState.tsx
    ErrorState.tsx
  pages/
    DashboardPage.tsx
    SearchPage.tsx
  features/search/
    SearchToolbar.tsx
    SearchFilters.tsx
    FacilityTable.tsx
    FacilitySummary.tsx
    HistoryTable.tsx
    EventWorkspace.tsx
    DocumentActions.tsx
    ScopePanels.tsx
```

Names may differ. The requirement is separation of concerns, testability, and avoiding a single mega-component.

Reuse the existing auth/API client/error handling contracts instead of duplicating fetch/token logic inside components.

## 16. Styling requirements

Create a coherent compact design system using CSS variables/tokens for at least:
- page background
- panel background
- border
- text primary/secondary
- accent
- danger/warning/success
- selected row
- compact control height
- spacing scale
- border radius

Visual direction:
- neutral light workspace
- strong but restrained teal/blue accent is acceptable
- tables and form fields should dominate, not decorative backgrounds
- clear focus styles
- readable Vietnamese text
- no tiny fonts; density should come from layout, not illegibility

Use semantic HTML and accessibility basics:
- labels
- buttons instead of clickable divs
- keyboard focus
- ARIA only where needed
- sufficient contrast

## 17. Responsive behavior

Primary target is desktop office use.

At narrower widths:
- allow horizontal table scrolling
- stack summary panel below results if needed
- keep primary search/navigation usable
- do not transform dense tables into giant cards unless absolutely necessary

Mobile optimization is secondary to correct desktop business workflow.

## 18. API/backend rules

Before adding an API, audit existing backend read/write contracts.

Hard rules:
- do not reimplement workflow logic in browser
- do not bypass RBAC
- do not put NAS credentials in frontend
- do not make fake dashboard statistics
- do not silently map missing data to invented values
- preserve fail-closed behavior
- keep canonical DB/cutover state unrelated to this UI redesign

If a desired field is unavailable, Codex must document the gap and either:
1. leave that UI element out/disabled in the first implementation, or
2. add the smallest correct backend read model/API in the source owner with tests.

## 19. Implementation strategy to minimize rework

Implement in slices, but keep a coherent visual system from the first slice.

### Slice A — foundation + dashboard + Tra cứu shell

Required:
- refactored app shell/navigation
- business dashboard replacing technical landing content
- Tra cứu page
- GxP selector
- unified search
- dense facility/case results using existing APIs
- selection state
- summary strip/panel
- history area using existing case data
- no regression to Google OIDC/RBAC

### Slice B — selected facility/event workspace

Required:
- selected facility context
- event/history selection
- business tabs
- case detail rendering
- scope panels where supported
- document action area using existing API contracts

### Slice C — richer business actions and analytics

Only after A/B are stable:
- create/reassessment/change actions
- richer certificate views
- ĐĐKKDD/CCHN views
- saved filters
- dashboard drilldowns
- business alerts
- document explorer improvements

Do not attempt to implement every legacy VBA button with fake/incomplete flows in Slice A.

## 20. Acceptance criteria for Slice A

A Slice A implementation is acceptable only if all are true:

1. Authenticated user lands on a business dashboard, not a deployment/phase-status screen.
2. `Tra cứu` is a first-class primary navigation item.
3. Search screen preserves the master/history/detail mental model.
4. Results are shown as a dense table/grid, not large per-record cards.
5. Existing case/facility data is read from real authenticated APIs.
6. Selecting a result gives persistent context and does not require navigating through unrelated pages.
7. No technical Phase 5/6/7/deployment/auth-provider cards are shown to normal operators.
8. Existing Google OIDC and database-backed RBAC behavior remains intact.
9. Existing error responses are rendered clearly; frontend does not convert an API error into fake empty data.
10. No NAS credentials or business rules move into frontend.
11. `pnpm` frontend tests/build/lint (as currently defined by the repository) pass.
12. Add/adjust tests for navigation, search loading, selected-row/detail state, authenticated API errors, and dashboard rendering.
13. UI works at typical 1366x768 and 1920x1080 desktop sizes without unusable overflow.
14. App.tsx is not allowed to become a larger monolith; meaningful decomposition is required.

## 21. Codex implementation report required

At the end of each slice, report only:
- files changed
- major UX decisions
- existing APIs reused
- API/backend gaps discovered
- tests/build/lint results
- screenshots or concise visual description if screenshot generation is available
- full commit SHA
- exact VM deploy command

Do not repeat this full specification in the report.

## 22. Audit rule

This document is the acceptance source for UI redesign audit. If implementation deviates, Codex should explicitly state why and obtain approval rather than silently replacing the workflow with a generic web dashboard pattern.

## 23. UAT refinement — compact search, production-line rows, and facility tabs

This section records the post-Slice-A.1 UAT decision and is authoritative over earlier illustrative column/layout recommendations where they conflict.

### 23.1 Search and results become one compact workspace

On desktop, do not waste vertical space on separate large `Tra cứu` and `Kết quả` cards.

Preferred structure:

```
+--------------------------------------------------------------------------+
| TRA CỨU  [GMP] [GLP] [GMPbd] [quick search................] [Bộ lọc ▾] |
|          active-filter chips when advanced filters are applied           |
+-------------------------------------------+------------------------------+
| KẾT QUẢ / DÂY CHUYỀN                     | LỊCH SỬ                     |
| internal scroll                           | internal scroll              |
+-------------------------------------------+------------------------------+
| FACILITY WORKSPACE TABS                                                  |
| Thông tin chung | Các đợt kiểm tra & thay đổi | GCN GxP | ĐĐKKDD        |
+--------------------------------------------------------------------------+
```

Remove redundant `Danh sách cơ sở` headings when the context is already obvious.

### 23.2 Advanced filters collapsed by default

Keep the quick search and GxP selector always visible.

The following are advanced filters and should be hidden/collapsed by default, expanding only when the operator requests them:
- Tỉnh/thành
- Trạng thái hồ sơ
- Chứng nhận
- Sắp hết hạn
- other secondary filters added later

When collapsed, active filters must still be visible through compact chips/summary text so a dashboard drilldown or multi-state predicate is not hidden from the operator.

`Xóa lọc` remains accessible without forcing expansion.

### 23.3 Header should be even more compact

The application chrome should minimize vertical usage further. Brand, primary nav, user identity, and sign-out should fit into a compact single-row or near-single-row application header where practical.

Avoid subtitle text that consumes a second line unless it materially helps the operator.

### 23.4 Search result grain is production-line level, not only facility level

The visible result table must support **production-line granularity** when the authoritative data has production lines.

Example:
- facility `1.1`
- lines `A`, `B`, `C`

must be representable as separate rows/codes:
- `1.1A`
- `1.1B`
- `1.1C`

Do not fabricate line suffixes. Derive the composite display code from authoritative facility + production-line identity.

A facility with no line-level records may still appear at facility grain if that is the authoritative domain state. The backend/API should expose the grain explicitly enough that the frontend does not infer or duplicate line ownership rules.

Search, sorting, selection, and later workspace actions must preserve both facility identity and selected production-line identity.

### 23.5 Revised default result columns

For the compact default result table, remove these columns unless a user chooses an expanded view later:
- Công ty
- Phạm vi/tiêu chuẩn (old summary column)
- GCN hiện hành
- Hết hạn

Default columns should prioritize:
- Mã cơ sở/dây chuyền (e.g. `1.1A`)
- Tên cơ sở
- GxP
- **Phạm vi chứng nhận**
- Tỉnh/thành
- Kiểm tra gần nhất
- Trạng thái hồ sơ gần nhất

`Phạm vi chứng nhận` must mean actual authoritative certificate scope / line-specific certified scope as modeled by the backend. Do not substitute `applicable_standard`, generic scope code, or latest-case summary merely because those values are already available.

If the current backend cannot expose authoritative line-level certificate scope, record the gap and add the smallest correct read model/API rather than faking the field in React.

### 23.6 Typography density

Use a smaller desktop data-grid type scale than the current A.1 implementation where readability permits.

For compact controls and tables, prefer a legible sans-serif font stack. Serif typography may remain for occasional high-level headings if desired, but dense tables, labels, filters, tabs, and data values should use sans-serif.

Density must come from compact row height, spacing, and font sizing without making Vietnamese text unreadable.

### 23.7 History panel moves beside results

The compact `Lịch sử` panel should sit beside the result table, replacing the current top-right facility-summary card.

History default columns should be reduced to:
- Loại sự kiện
- Tiêu chuẩn
- Ngày
- Trạng thái

Remove by default:
- Mã hồ sơ
- GxP

History remains bounded with internal scrolling.

### 23.8 Facility context moves below into top-level tabs

The current standalone `Ngữ cảnh cơ sở` card should no longer consume the top-right pane.

Facility context belongs below the result/history split inside a top-level facility workspace with these tabs:
- **Thông tin chung**
- **Các đợt kiểm tra & thay đổi**
- **Giấy chứng nhận GxP**
- **Giấy chứng nhận đủ điều kiện**

The selected facility and selected production line must remain stable when switching these tabs.

The existing event-level tabs (`Hồ sơ`, `Kiểm tra`, `Khắc phục`, `Xử lý`, etc.) belong inside the **Các đợt kiểm tra & thay đổi** facility tab, not as a competing top-level workspace model.

### 23.9 Acceptance additions for the next implementation round

The next UI round is accepted only if:
1. Advanced filters are collapsed by default and active predicates remain visible when collapsed.
2. Search + results no longer waste space as two large stacked cards.
3. Header chrome is smaller than A.1.
4. Result rows support authoritative production-line grain and composite codes such as `1.1A` where real line data exists.
5. Default result table removes Company, old scope/standard summary, GCN current, and expiry columns.
6. Default result table adds authoritative `Phạm vi chứng nhận`.
7. Dense tables/controls use a smaller readable sans-serif type scale.
8. History sits beside results and omits default `Mã hồ sơ` and `GxP` columns.
9. Facility context is moved below into the four top-level facility tabs listed above.
10. No line code, certificate scope, filter meaning, or workflow state is fabricated client-side.

## 24. UAT refinement — result/history micro-density and selection behavior

This section records the next post-deploy UAT decision and is authoritative where it conflicts with earlier presentational wording.

### 24.1 Result panel title and compact code column

The result panel title should be exactly **`Cơ sở/dây chuyền`**. Do not render a redundant second heading with the same meaning below an eyebrow/title pair.

The first result-table column header should be **`#`** and should be intentionally narrow, sized for compact values such as `1.1A`, `10.1A`, etc. Preserve the full code in a tooltip/title when useful.

### 24.2 Compact facility-name presentation

For display in the result grid only, a presentation-layer abbreviation may be applied to facility names to improve scan density:
- `Công ty` -> `Cty`
- `cổ phần` -> `CP`

This is display-only. Never mutate authoritative facility names, search semantics, API values, exports, or persistence. Preserve the full authoritative name in the cell tooltip/title.

### 24.3 `Kiểm tra gần nhất` must mean an actual latest inspection signal

The result column **`Kiểm tra gần nhất`** must not simply display `legacy_inspection_code` if that field is commonly blank and therefore produces misleading `Chưa có` rows.

Audit the authoritative inspection/event owner and define the smallest correct read-model projection for latest inspection information. Prefer a useful business signal such as the latest actual inspection date (or another explicitly approved latest-inspection reference) derived server-side from authoritative inspection/case/event data.

Do not fabricate a value in React and do not relabel an unrelated field as inspection information.

### 24.4 Result count must not be an arbitrary client cap

The current hard-coded `limit: 80` is not an acceptable representation of the complete result set when more matching rows exist.

Search results must expose the full logical result set through a scalable contract. Preferred options are proper server-side pagination/infinite loading/virtualized paging with total count metadata. Do not simply raise an arbitrary limit to another magic number.

The UI must make clear how many matching rows exist and which subset/page is currently loaded when pagination is used.

### 24.5 Selecting a result must not refetch the result list

Clicking a result row should update only the selected context/history/workspace that depends on the selection. It must not trigger a fresh search request or temporarily replace the result area with an `Đang tra cứu` card.

Selection state must be decoupled from search-query dependencies. Preserve the current result list while loading the selected workspace/history, using subtle local loading only in the dependent pane if needed.

### 24.6 History panel title and compact columns

The history panel title should be exactly **`Lịch sử kiểm tra & thay đổi`**, without a redundant second line such as `Kiểm tra và thay đổi`.

For event presentation, display `Thay đổi cơ sở` as **`Thay đổi`** in the compact history grid. This is a presentation label only; do not mutate stored event type values.

Make the event-type column narrow and size all remaining columns to their information content so the history panel can use less horizontal width than the result panel.

### 24.7 Result/history split priority

The result panel is the primary master list and should receive more horizontal space than history. The history pane should be only as wide as needed for the compact four-column table.

### 24.8 Facility tabs must look unambiguously like tabs

The lower workspace selectors (`Thông tin chung`, `Các đợt kiểm tra & thay đổi`, `Giấy chứng nhận GxP`, `Giấy chứng nhận đủ điều kiện`) must read visually as a tab strip, not as a row of generic pill buttons.

Use a conventional selected-tab affordance such as a connected strip, active underline/top border, stronger selected background, or equivalent desktop application tab treatment. The active tab must be obvious at a glance while remaining compact.

### 24.9 Acceptance additions

The next refinement is accepted only if:
1. Result panel uses one compact title `Cơ sở/dây chuyền` and `#` as the narrow code-column header.
2. Facility-name abbreviations are display-only and preserve full names for tooltip/search/data ownership.
3. `Kiểm tra gần nhất` is backed by an authoritative latest-inspection projection rather than blank legacy codes.
4. Search no longer truncates matching rows to an unexplained fixed 80-row client limit; a scalable result-count/paging contract is used.
5. Result-row selection does not refetch the result list or flash a global `Đang tra cứu` state.
6. History title is `Lịch sử kiểm tra & thay đổi`, with compact columns and `Thay đổi cơ sở` displayed as `Thay đổi` only in presentation.
7. Result pane receives more width than history.
8. Lower facility-level navigation is visually implemented as a real tab strip.
