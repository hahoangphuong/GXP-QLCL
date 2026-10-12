# LEGACY_UI_PARITY_MATRIX — Issue #1

Direction: the user decision dated 2026-10-10 supersedes earlier aesthetic
recommendations in UI_REDESIGN_VBA_REFERENCE and PHASE12. Preserve legacy UI where
evidenced. Baseline: `50576b0b383161e26e27b6cdc4a1a469aff1ae17`; work branch:
`codex/legacy-ui-parity-20261010`. This delivery is partial; it does not close #1.

General Information runtime evidence received 2026-10-11: left certificate scope,
standard, limits, certificate dates/status and facility status; right facility
name/address, company/headquarters, leader, professional/QA persons, contacts,
specialist and foreign-investment snapshot. FacilitySummary now uses this order
and two-pane composition. General Information spans the lower workspace; history
presentation is hidden only for this tab, without changing selection ownership.
Master search appearance and the removal of the extra filter/context surfaces
remain in force. Long right-hand content scrolls independently on desktop.

Concrete data gap C7: FacilityWorkspaceSummary has certificate_scope_summary but
no separate certificate limitation or current certificate ID. The Giới hạn row
therefore shows an explicit unavailable-data message. No text parsing, inference,
certificate-detail fetch by guessed identity or API/schema change is introduced.
Other canonical fields are retained, including province/context indicators that
are additional to the pictured lower form. StatusBadge uses the authoritative
certificate status; expiry dates do not trigger new client-side business rules.
Legacy file/link buttons are not invented without an established action contract.

Fixture captures: legacy-general-1366/1920/390.png outside git. No horizontal
page overflow, vertical GxP rail preserved, and returning to history retains its
selected event. Supplied screenshot/business values are excluded from git.
RecordForm/pickers and the remaining inspection/CAPA/final groups still need work.

General Information validation: typecheck, lint, all 309 tests / 23 files and
build PASS. The two complete related test files also pass (143 tests). An initial
full run hit two unchanged 5000ms test timeouts; a name-filtered diagnostic run
failed two App async queries. Complete-file and full-suite reruns above pass
without changing test timeouts or business code. This does not establish the
cause of those transient diagnostic failures. Browser evidence is fixture API
only; real-backend integration and screen-reader verification remain pending.
Older EVIDENCE_MISSING references to General Information below are superseded by
the runtime screenshot and validation recorded in this section.

Latest user correction (2026-10-10): remove the entire Lọc / Lọc dữ liệu row;
retain only the existing master name/scope inputs. Remove the facility context
summary below history and extend history to the bottom of the workspace. Restore
the original three visible history columns (Loại / Tiêu chuẩn / Ngày). State is
retained in each row's accessible label and hover title, with unchanged canonical
identity and keyboard behavior. These instructions supersede the earlier filter
disclosure and context-summary presentation decisions documented below. Existing
deep-link filter values remain supported by the router/API; they are not cleared
merely because the additional filter controls are no longer rendered.

Fixture browser: history bottom equals workspace bottom at 1366x768 and
1920x1080; no horizontal history scrollbar. At 390x844, no page overflow and Arrow
navigation changes focus without selection. Captures outside git:
expanded-history-1366/1920/390.png. Full legacy parity remains partial.
Latest correction validation: typecheck, lint, 309 tests / 23 files and build PASS.
The obsolete context-summary assertion was updated; no timeout was increased.

User exception (2026-10-10, latest two screenshots): preserve the existing web
master search table, vertical GMP/GLP/GMPbb rail, right-hand action panel and
history table appearance. These surfaces are excluded from legacy palette,
radius, control and selected-row overrides. The filter disclosure is a separate
row below the master. Existing history columns, canonical state, selection and
keyboard behavior remain unchanged. This exception supersedes earlier parity
styling statements for these surfaces; detail/certificate parity is retained.
Validation of this exception: typecheck, lint, all 309 tests / 23 files and build
PASS. Browser fixture at 1366x768, 1920x1080 and 390x844 confirms original vertical
rail, 12px panel radii, selected-row palette, right-hand actions, focus-only
history Arrow navigation and no horizontal page overflow. Captures are stored
outside git as preserved-master-history-1366/1920/390.png.

## Evidence inspected

- Local source workbook `legacy/Danh sách Kiểm tra GPs.xlsb`, add-in
  `legacy/GPs.xlam`, exported `legacy/GXP-VBA code.zip` and existing workbook/add-in
  inventories. Originals were not opened with enabled macros or modified.
- ZIP contains complete `.frm` headers and `.frx` compound control streams for
  MainForm, RecordForm, FilterForm, SelectCC, SelectDDK and related forms. Existing
  `artifacts/legacy_audit/vba_sources/GPs/*.frm` files contain VBA code, not the
  designer control properties; they cannot establish positions on their own.
- MainForm export: ClientWidth 21480 / ClientHeight 9930.001 (designer twips).
  Runtime VBA changes Width to 864 + FBorderWidth outside planning mode. Therefore
  designer dimensions are not proof of runtime pixel dimensions.
- Static FRX SitePosition coordinates below were read from the compound `f`
  streams using oletools' site parser with SitePosition retained and string
  padding aligned relative to the site block. They establish ordering, not
  screen pixels. Some nested caption parsing fails; those results are excluded.
- Tab captions were checked directly against UTF-16 strings in FRX, with companion
  workspace documentation and VBA initialization as corroboration.
- Initial source audit found no runtime screenshots of the named forms in local legacy assets,
  repository image files. Template DDK1/DDK2 PNGs
  are document assets, not screenshots of these UI forms. A native Excel designer
  inspection was stopped by the user; no source macros were run.
- The user subsequently supplied nine runtime captures: images 1–6 and 8 show
  the six inspection workspace tabs; image 7 shows the GPs certificate page;
  image 9 shows the business eligibility page. Image 8 repeats image 5.
  These establish grey frames, blue facility tabs, green case/scope tabs,
  inset value boxes and cyan certificate values. Original captures remain local.

| Container | Control | Static SitePosition (x, y) | Grounded conclusion |
| --- | --- | --- | --- |
| MainForm root | tbGMP / tbGLP / tbGMPbb | (212,106) / (1940,106) / (3669,106) | Horizontal GxP selector above list |
| MainForm root | edSearch | (6421,212) | Quick filter in top row |
| MainForm root | lbDsCoso | (141,988) | Master list above workspace |
| MainForm root | MultiPage6 | (106,5574) | Facility workspace below master |
| MainForm/i221/i194 | lbHist | (71,459) | History at left of event workspace |
| MainForm/i221/i194 | MpgHoatdong | (8008,0) | Event detail/tab group to right of history |
| MainForm application page | edDKNop / edDKMaHS | (3104,247) / (3104,1023) | Submission date before dossier code, vertically aligned |
| RecordForm root | MultiPage1 | (106,71) | Tabbed document form, not a free-standing global file feed |
| FilterForm root | Frame1 / Frame3 / Frame4 | (706,1482) / (7620,1553) / (7620,5786) | Grouped conditions, not one unstructured toolbar |

## Surface mapping and remaining gaps

| Legacy surface / evidence | React owner | Baseline divergence | Implemented / remaining | Confidence / verification |
| --- | --- | --- | --- | --- |
| MainForm master over workspace, coordinates above | SearchPage / CSS | History beside master in top row | Master now full-width above history-left/detail-right; one mounted workspace and one selection owner | High for relative arrangement; browser geometry at 1366/1920 |
| tbGMP, tbGLP, tbGMPbb top row | FacilityTable / CSS | Vertical rotated buttons | Horizontal selector; canonical GMPbb retained | High for placement; browser checks transform and selection |
| edSearch, Label29 “Lọc:” | LegacySearchFilters / SearchPage | No visible quick search input | Controlled quick filter uses existing q search contract | High for control/intent, not exact dimensions |
| MainForm facility page captions | FacilityWorkspaceTabs / facilityTabs | GxP / expanded eligibility label | Displays “Các đợt kiểm tra & Thay đổi”, “Giấy chứng nhận GPs”, “Giấy chứng nhận ĐĐK”; existing URL keys unchanged | High; caption/key regression and existing tab keyboard tests |
| Nested case tabs: Hồ sơ đăng ký, Kiểm tra thực tế, Báo cáo khắc phục, Xử lý tiếp, Cấp chứng nhận GPs | EventWorkspace | Shortened labels and numbered stepper | Verified captions restored; numbered connector presentation removed in search | High for all six case captions, including image 6 for ĐĐK |
| Label/value rows, frames, dense tab controls | Scoped search CSS | Rounded cards and larger controls | Reduced corner radius/spacing; runtime grey frames, blue/green tabs and white inset values applied; cyan certificate values | Partial; no exact appearance claim |
| Application page date then dossier code | CaseApplicationWorkspace | Same order, currently two-column grid | Order retained; runtime images establish vertical date/code and assessment grouping; implementation remains partial | Runtime evidence available |
| FilterForm named condition groups | LegacySearchFilters | Supported filters only accessible by URL | Quick filter and grouped supported controls added; complete legacy condition set remains unsupported | Partial; controlled-state tests and browser request/URL evidence |
| RecordForm MultiPage1, document bundle | ContextualDocumentSection / EventWorkspace | Web list/detail with canonical versions | Existing owner preserved, inherited compact frame styling; no invented tabs or filename-based keys | Partial; full interaction/race tests retained; precise placement pending capture |
| GPs / ĐĐK historical lists and details | Certificate workspaces | Existing two-pane model; different chrome | Legacy facility tab captions and scoped density applied; fields/provenance retained | Partial; existing certificate/draft/modal tests, runtime references now available; exact field grouping remains partial |
| SelectCC, SelectDDK, ChonMauCC, SelectFile, ExtRecordForm, DCForm, TTVForm | Existing selectors/editors | Full runtime appearance unknown | Audited as related forms; no guessed replacement screens | EVIDENCE_MISSING for runtime states and visual comparison |
| GMP/GLP/GMPbb workbook worksheets, list/planning outputs | Search/results/report screens | UserForm and worksheet roles differ | Workbook inventory reviewed; worksheet rendering not cloned without evidence | EVIDENCE_MISSING for rendered workbook baseline |

## CONFLICT_REGISTER

| ID | LEGACY_EXPECTED | CURRENT_CONTRACT / WHY_CONFLICT | Minimal resolution and affected checks |
| --- | --- | --- | --- |
| C1 | Full FilterForm flags: registration, inspection, compliance, product classification, dosage form and date ranges; persisted workbook names | Existing search API supports q, facility/scope/province, canonical states, certificate state/expiry; no equivalent for all legacy flags or saved workbook names | User resolved: keep unsupported legacy conditions visibly disabled in their evidenced groups. Supported controls alone update server filters. No client-only filtering of a paginated subset; filter and URL tests apply. |
| C2 | Native Explorer/Word, opening raw folders and prefix-selected files | Backend owns storage binding/access, logical document/rendition/version identity; frontend cannot resolve NAS paths | Preserve available backend open/create/history commands and IDs. Do not implement raw-path fallback or fake file actions. Document races/storage contract checks apply. |
| C3 | Legacy row editing may be directly available | RBAC, readiness and optimistic concurrency own permission/mutation availability | Preserve disabled/omitted commands and real 403/409 behavior. Caption/placement changes do not enable commands. Certificate/modal/draft tests apply. |
| C4 | Runtime legacy pixel layout and all form states | FRX supplies structure, but runtime resizing, visibility, font/OS rendering and macro-driven states are not fully established; captures now available for case and certificate pages only | Keep verified arrangement/captions; do not invent colors, additional tabs or forms. Obtain redacted runtime captures before exact geometry/style work and screenshot comparison. Exact font metrics, main-list, RecordForm and FilterForm runtime states remain unverified. |
| C5 | Fixed desktop windows | 390px viewport cannot fit the desktop panes | Stack the same panes and keep independent table scrolling. No cards or identity changes. Browser mobile functionality checks apply. |
| C6 | MSForms top-level window and workbook shell | Web retains existing route navigation, OIDC/login/logout, legal routes and canonical UUID deep links | Preserve web shell outside scoped search styling; no fabricated Office chrome. Existing auth/legal/navigation tests apply. |

Existing province/state/expiry filters are supported web projections, not claimed
as exact copies of FilterForm's legacy condition semantics. API states are never
translated into legacy flags in the browser. Multiple URL-owned case_state values
remain intact unless the operator explicitly chooses a single state.

## Validation and visual limits

Commands: `pnpm typecheck`, `pnpm lint`, `pnpm test --maxWorkers=1`, `pnpm build`.
Focused tests cover legacy captions with stable activation/deep-link keys and
controlled filters without a second draft or requests on disclosure toggle.
Existing identity, stale request, 409, draft, modal and keyboard tests remain.

Browser uses the actual App and local fixture API with sanitized App-test data;
it is not real-backend integration or production UAT. Checked 1366×768,
1920×1080 and 390×844, independent pane/table scrolling, tab switching, retained
facility/UUID/history context and server query from the province filter. The
first certificate fixture returned the wrong shape and was corrected; no product
contract was altered to accommodate it.

Before evidence: previous baseline web captures `slice5-1366.png` and
`slice5-1920.png` in the local visualization directory. After evidence:
`legacy-parity-1366.png`, `legacy-parity-1920.png`, `legacy-parity-390.png`,
`legacy-filter-390.png` in that same directory. These establish before/after web
layout changes, not a screenshot comparison against runtime Excel.

Next required evidence: redacted runtime captures of MainForm's full master list
and general information page, RecordForm, FilterForm and related pickers; include Windows
scaling and active GxP/tab. Read-only originals remain local. With those captures,
continue field geometry, actual colors/fonts and per-form side-by-side review.

## Runtime-reference follow-up

Images 1–6 establish two mutually exclusive scope tabs below the case form.
EvaluationScopeWorkspace now owns this presentation state; both projections and
one editor instance remain mounted. Arrow/Home/End navigation moves focus without
activation; Enter/Space activates through the native button. Navigation never
saves or creates a new request. Existing aggregate version/draft/conflict ownership
is unchanged. Both panes scroll independently and remain within the desktop viewport.

The green completion strip is not reproduced: no equivalent per-stage backend
completion projection has been established. Its ticks cannot be inferred from
file availability. The screenshot's blank right-hand scope box is not filled
with a guessed data source. Existing extra canonical fields and web navigation
remain available. Facility tabs now span both history and detail panes. Context is below the
history pane; certificate tabs use their own list/detail pair across the lower
workspace. No owner was moved or duplicated to obtain this layout. This is a partial delivery and does not close Issue #1.

Updated local fixture captures: legacy-runtime-1366.png, legacy-runtime-1920.png,
legacy-runtime-390.png. Original user screenshots and business payloads are not
included in the repository. Real-backend integration and production UAT were not
performed.
Validated foundation: typecheck, lint, full Vitest run (305 tests / 22 files),
and production build passed. Scope Tab/Enter navigation was exercised in the
fixture browser with unchanged request counters. An existing pagination test was
made deterministic by waiting for committed settled rows before scrolling; no
timeout was increased. Existing React act warnings remain non-failing.

## User resolution of C1 — disabled legacy conditions

The user chose to retain unsupported legacy conditions visibly disabled.
LegacyUnavailableFilters preserves three relative columns from FilterForm FRX:
certificate/compliance at left, registration/inspection/processing in the middle,
product/dosage/validity at right. Checkbox captions were recovered with the
MorphData caption string aligned after Value relative to the control block;
this fixes the initial parser's three-byte caption offset. No original asset or
installed oletools source was modified. This evidence includes Non-beta/Peni/Cepha
and separate dosage rows; procedure names were not used as caption evidence.

Every unsupported input is inside a disabled fieldset and has no callback,
request or local selection state. Existing supported query controls remain
separate. The filter surface overlays the workspace and scrolls independently;
opening it leaves the master pane at the same height. Escape closes it and
restores summary focus. Runtime FilterForm screenshots are still missing, so
exact dimensions/fonts and the complete native window appearance remain unverified.
The web disclosure substitutes for a separate VBA window; this is a documented
remaining interaction difference, not a claim of complete FilterForm parity.

Fixture evidence: legacy-filter-disabled-1366.png and
legacy-filter-disabled-390.png. Both have no horizontal page overflow, all
unsupported inputs disabled, and unchanged master height across open/close.

## Full-width tab and certificate group follow-up

Search layout wrappers use display:contents so the existing facility tab owner
can span the history and detail columns. The existing summary context is below
history. Certificate tabs hide that history/context presentation and show their
own existing lists and details across the workspace. Hidden/inert retained
workspaces remain hidden during canonical refresh. No fetch effect or selection
owner was copied. Fixture tab round-trips preserve the history ID and line UUID.

GPs detail groups number/date/expiry/standard first, then full-width content rows.
DDK groups number/date/decision/sequence first, followed by canonical content.
The existing DDK expiry field remains available lower down even though image 9
has no equivalent header field. At 1366px the summary uses two rows so values
remain readable; at 1920px it uses one row; narrow viewports stack the fields.
All mutations, permissions, version tokens and modal owners are unchanged.

Fixture captures: legacy-mainform-1366/1920/390.png, legacy-gps-1366/1920.png,
legacy-ddk-1366/1920/390.png. Populated GPs/DDK fixtures use synthetic business
names and IDs, and existing API response shapes. Detailed certificate UI was
visually checked; no user business payload was used in fixtures.

Remaining parity gaps: detailed case field placement, document actions relative
to those fields, the certificate activity sub-tabs and source navigation commands,
full master/General Information/RecordForm/picker runtime appearance. The green
completion ticks still have no established backend readiness projection. This
work does not assert pixel-perfect or complete legacy parity and keeps #1 open.

Latest workspace group: targeted filter/certificate tests 38 passed, full suite
308 tests / 23 files passed, typecheck/lint/build passed. Unsupported conditions
mount only while the disclosure is open, keeping the closed search DOM compact;
opening/closing still has no query or mutation effect. Native disclosure, desktop
pane geometry and certificate tab round-trips were checked in the fixture browser.

## Case GPs issuance visual/interaction slice — 2026-10-12

Baseline: 26bc7065b60b5dcc48e68f9e246ff902b410f120. Evidence distinction:
runtime image 7 is the Facility Giấy chứng nhận GPs page (four horizontal header
fields and full certificate body). Images 5/8 show Case Cấp chứng nhận GPs:
Mã số Chứng chỉ, Ngày cấp and Ngày hết hạn vertically aligned in cyan boxes,
with document access at right. MainForm DataCC(0..2) maps edCCMa/edCCCap/edCCHH;
DataCC2 maps the separate Facility controls. FRX names/captions corroborate both
contexts; no designer-to-runtime pixel conversion is asserted.
GetSetDataCCGPs is called by the common edit dispatcher for IDs 300..305, reads
selected history, resolves Get_List_RngCCGPs, writes through GetSetData/DataCCCl
and refreshes facility/history controls. That legacy editing path is not copied
into the web; certificate workflow/version mutation owners remain authoritative.

Root cause: Case used a nested certificate list/detail split and a vertical
document stack, applying Facility's horizontal header to the Case form.
After: preserve all directly linked certificates in a compact UUID-keyed list;
the selected certificate's three primary fields align vertically with Case
captions and cyan values. Canonical standard and full body remain available.
One unchanged contextual document workspace occupies the independently scrolling
right column. Narrow layout stacks before scopes. The shared detail renderer
gets an optional Case caption presentation; Facility defaults, fields, owners
and horizontal layout are unchanged. Scope/status/source data are not inferred.

Case rows reuse the existing certificate keyboard helper: Arrow/Home/End change
focus only, Enter/Space activate the exact UUID. No extra detail request or second
selection owner. The issue modal now reuses the existing focus containment hook:
initial input focus, inert background, 0-enabled-control fallback while pending,
Tab/Shift+Tab containment and focus restoration; mutation handlers are unchanged.
Readiness, error handling, draft/scope initialization, duplicate-submit guard,
Escape/pending semantics and payload construction remain as before.

Contract differences: the list and full canonical certificate body are retained
instead of reducing Case to one legacy certificate. No edit/renewal/relink/source
navigation action or completion strip is added. Backend maps certificate decision
documents to Xử lý; it is not moved to Case GPs merely to match the pictured button.
Document family/parent/UUID/context filtering remains unchanged. The list's
latest_flag label remains a display projection, not a version/readiness selector.
Catalog serializes scopes using each certificate's selected version row; frontend
uses that certificate's supplied snapshot without joining scopes across records
or copying evaluation scope into issuance. New issue scopes still start empty.

EVIDENCE_MISSING: immutable CertificateVersion IDs/history/scopes per historical
version in the current GxpCertificateDetail contract; it exposes row_version and
the selected version's fields/scopes, not a certificate-version collection.
row_version is a concurrency token, not a CertificateVersion ID. No history or
replacement relation is inferred from latest_flag. CertificateIssueRequest is a
create contract without expected_version; do not fabricate a token. Existing
edit/promote expected_version contracts are untouched, and issue conflicts remain
backend-owned. Runtime issue-dialog/editor/error states and shared Ghi chú
provenance are missing; retain canonical UI/behavior rather than invent them.

Regression: the Case layout assertion and initial/pending focus regression fail
on baseline, then pass. Tests cover equal certificate numbers with distinct UUIDs
and scope snapshots, focus-only navigation, no relink/promotion, backend readiness,
empty issue scopes, explicit scope ordering, 403/409/422 and network draft retention,
pending duplicate submit/Escape, and late success after dialog context unmount.
The new mock's request type was corrected after typecheck caught its zero-argument
tuple; production request types/handlers were not changed. Async rejection in the
focus test is settled with act before checking idle Escape; no timeout is raised.

Actual App + synthetic fixture API: 1920x1080, 1366x768 and 390x844; certificate
Arrow/Enter selection, scope identity, document Enter/F6 with exact rendition and
document-version IDs, workflow/facility round-trips and canonical history/line URL.
At pending, all controls disable and Tab/Shift+Tab stay on the dialog; pending
Escape does not close. One explicit issue gets 409 and keeps number/scope draft
without retry. Another explicit issue is held across external URL navigation to
a different Case; its late response cannot restore a dialog/error there, and
that Case's unavailable issue readiness stays disabled. No binary success claimed.

Desktop page width equals viewport; narrow content fits before scope, with only
the unchanged header overflow (clientWidth 375 / scrollWidth 384 at width 390).
Counters include three deliberate page initializations (initial, external URL,
final visual recapture), explicit Case re-selection, one document-detail read,
and two explicit rejected issue POSTs. Focus/tab navigation adds no duplicate read
or unintended mutation; no real certificate is created. Evidence outside git:
case-gps-parity-1920/1366/390.png, case-gps-pending-390.png,
case-gps-conflict-390.png, case-gps-unavailable-390.png,
case-gps-request-counts.json and fixture harness. Original business screenshots
remain local. Real-backend integration, binary storage, historical certificate
version selection, screen-reader acceptance and production UAT are unverified.
No backend PR #7 change, merge/cherry-pick, backend/API/DB/storage/RBAC change,
deployment or work on Case ĐĐK is performed.

Validation: typecheck, lint, all 339 frontend tests / 26 files and production
build PASS. Targeted issue/Facility certificate/document/focus files pass 45 tests
in each of two repeated runs. New Case presentation/UUID tests also pass in their
targeted run and the full App suite. The unchanged A3 frontend-owner guard passes
in isolated function execution (not a full backend run). No timeout increase,
disabled test or backend guard modification. Existing non-failing act warnings
remain. Diff is seven frontend/QA files; no business mutation handler changes.

## Follow-up processing visual/interaction slice — 2026-10-12

Baseline: 538e33ee4c6f256adf18f5c71e355230cc90791f. Runtime image 4 and MainForm
FRX establish Xử lý tiếp: left-hand final evaluation, compliance deadline and
PCT/CT reference/date rows; right-hand risk/PCT/CT document access. MainForm
DataKT(16/17/26/27) maps edDanhgiaCuoi, edLichKTTT, edPT_PCT and edPT_CT; their
control names and captions are present in the FRX stream. The grey frame and
white values are evidenced; the yellow deadline box is not a canonical business
state or permission signal. Designer coordinates do not prove runtime pixels.

Root cause of the presentation gap: EventWorkspace used one vertical stack for
the timeline and documents, placing document access after the entire timeline.
CaseWorkspace.processing combines a CaseAssessment projection and a filtered
InspectionEvent list. Its timeline view is deliberately read-only; it cannot be
reinterpreted as the legacy final-evaluation/approval form.

After: the unchanged server milestone order, dates, payloads and labels remain
in a left-hand timeline, with a neutral grey frame and white content cells. The
single existing ContextualDocumentSection moves into an independently scrolling
right column. The timeline scroll region is keyboard-focusable; PageDown scrolls
without selecting events or issuing requests. Narrow layout stacks timeline,
documents and scopes without overlap. All styles are scoped to processing;
assessment rendering/editing and other tabs are unchanged.

Contract differences retained: final evaluation/compliance deadline belong to
InspectionOutcome, PCT/CT rounds to InspectionApprovalSubmission. Their existing
inspection-workspace controls are not moved, cloned or aliased into processing.
CaseAssessment stays in registration. No new final/date/approval field, action,
completion tick, yellow status, shared Ghi chú or legacy file shortcut is created.
The canonical timeline and document list/detail/versions/actions remain instead
of reproducing the four legacy value rows and three buttons. Backend
workflow_step="Xử lý" filtering and the full case/site/GxP/production-line/cycle
context key are unchanged. No filename/path/legacy-ID document lookup is added.
Relative left/right parity improves; complete field or pixel parity is not claimed.

EVIDENCE_MISSING: legacy rendering for the canonical administrative event stream,
runtime document/editor/pending/error states, provenance of the shared Ghi chú,
and a processing-owned projection/action contract for the legacy final/deadline/
approval rows. Retain canonical behavior rather than invent placeholder values.
Timeline has no draft or business-save action, so F2/edit cancel/expected_version
are not applicable there. Registration drafts/tokens remain under their original
owner, including existing unmount/reset semantics across workflow tabs.

Regression: timeline and App layout assertions fail on the baseline, then pass
with the scoped hierarchy and one right-column document workspace. New tests
retain unknown/repeated/null server events and empty context, prohibit accidental
assessment/outcome edits, and keep the timeline read-only under F2/Enter/Escape.
App document tests verify exact document/rendition/version IDs, blocked actions,
focus-only navigation/F6, scope selection, pending duplicate-open protection,
403/404/409 errors without retry, retained selected detail and tab round-trips
without mutation or extra workspace reads. Existing document epoch/late-binary
and registration draft/version tests remain unchanged.

Fixture browser at 1920x1080, 1366x768 and 390x844 uses 18 canonical-shape events
and two documents with the same filename but different IDs. Timeline PageDown,
document Enter/F6/Shift+F6, scope changes and workflow/facility tab round-trips
preserve the proper context. A held PCT detail response cannot replace newer CT
detail. One explicit canonical content GET returns 409 while pending, preserves
selection/version detail and does not retry. No binary success is asserted.
Counters: one search/facility/case read; two explicit selection reads per document
(including re-selection after a replaced epoch/unmounted tab); one content GET;
zero mutations. Desktop page width equals viewport. At narrow width, clientWidth
375 / scrollWidth 384 reproduces the existing header overflow only; processing
right edge stays within 343px and scopes follow the full content.

Local evidence outside git: processing-parity-1920/1366/390.png,
processing-document-1920/390.png, processing-pending-1366.png,
processing-conflict-1366.png, processing-request-counts.json and the fixture
harness. Supplied legacy screenshots/business values remain outside git.
Real-backend integration, successful binary storage, screen-reader acceptance
and production UAT remain unverified. No backend PR #7 changes are incorporated;
no backend/API/database/storage/RBAC/concurrency contract is changed.

Validation: typecheck, lint, all 335 frontend tests / 26 files and production
build PASS. Complete targeted App/timeline/registration/document files pass
169 tests; a subsequent targeted repeat passes 25 timeline/registration/document
tests. One intermediate name-filtered App run failed an existing async query
before reaching the new hierarchy assertion; complete-file and full-suite runs
above pass without changing timeout values or business code. The unchanged A3
frontend-owner guard passes in isolated function execution, not a full backend
test run. Existing non-failing React act warnings remain. Diff review confirms
only processing presentation, scoped CSS, regressions and this matrix change.

## CAPA remediation visual/interaction slice — 2026-10-12

Baseline: 3a46bae5edf6788528370e7525bdfd145c012cf1. Runtime image 3 establishes
Số CV đến, Ngày nộp, Ngày thẩm định and Người thẩm định in aligned rows at left,
two legacy round columns, a separate supervision group and CAPA document buttons
at right. MainForm DataKT(21/22), (10/23), (11/24) and (12) map the reference,
submission, assessment and assessor controls. Their names also exist in the FRX
control stream. These prove relative grouping, not runtime pixel measurements.

Before: requested date interrupted the primary sequence, date/person/result
values shared a mixed grid, and documents followed the entire workspace.
After: the selected canonical round groups Số CV đến, Ngày nhận, Ngày thẩm định
and Người thẩm định vertically, with aligned white values and black labels on
the existing neutral gray form. Requested date, status, result and per-cycle
notes remain beside the primary group. Existing command inputs/actions remain
below. The single unchanged ContextualDocumentSection is in a scrolling right
column; narrow screens stack it before scopes. Inline errors span their field's
width. No other workspace, selection owner or mutation handler changes.

Contract differences retained: ADR 0060 permits open-ended CAPA rounds. Keep the
canonical history selector and one selected round rather than two hardcoded
legacy records. No field, assessor or status is combined across rounds.
submitted_on retains the explicit receipt label Ngày nhận; this is not a claim
that every legacy Ngày nộp value has universal canonical date semantics.
incoming_reference displays Số CV đến; editor input/activation names retain the
canonical reference terminology. Assessor remains the backend-owned display
snapshot, not a new free-text mutation. Documents retain their complete
workflow_step, capa_cycle parent UUID, document/version/rendition/action identity.
The backend supplies families for rounds 1/2; no third-round document is guessed.
Additional canonical result/status/command controls retain existing renderers.
Relative parity improves; full or pixel-perfect parity is not established.

EVIDENCE_MISSING: canonical owner/contracts for legacy Ngày giám sát, Báo cáo
g. sát and Người giám sát; runtime create/edit/save/cancel/error states; legacy
placement of canonical requested date, per-cycle result/status and action forms;
provenance of the shared Ghi chú. No supervision fields, completion ticks or
document buttons are fabricated. Drafts retain existing semantics: same-version
refresh preserves them, cycle/version identity changes rehydrate, workflow or
facility tabs that unmount editors do not promise draft persistence.

Regression: the new primary-order test fails on the baseline and passes after
the presentation change. All four commands preserve their existing drafts on
403/409/422 without retry and use case token 8 for create / cycle token 2 for
other commands. Tests cover readiness, pending duplicate submit/cycle activation,
keyboard selection of a third round, same-version refresh and version rehydration.
App regressions verify a single right-column document workspace, exact cycle
filtering, selection across tab changes and discarded late 403/404/409 responses.
Existing document identity/epoch/binary/focus tests remain unchanged.

Browser fixture evidence outside git: capa-parity-1920/1366/390.png,
capa-detail-390.png, capa-draft-390.png, capa-race-1366.png,
capa-pending-390.png, capa-conflict-1366/390.png and capa-request-counts.json.
Verified 1920x1080, 1366x768 and 390x844, keyboard round selection, F2/Escape/Enter,
F6 focus, independent desktop scrolling and narrow scope following the form.
Cycle 1 detail is held pending, cycle 2 completes, then released cycle 1 cannot
replace it. Scope changes retain the draft; workflow/facility tab round-trips
retain selected cycle/history/production-line UUID. One explicit update with
cycle token 3 receives 409 and retains its reference draft, without retry.
Counters record two page initializations (including explicit reload), one read
of each selected document and one update; navigation/focus adds no duplicate
case/search/document reads or unintended mutation. A certificate-tab visit adds
its expected certificate-list request. Browser date entry could not populate the
native empty assessment date through automation; submit/assess payload and error
behavior are verified by regression tests, not claimed as browser acceptance.

Desktop page widths equal the viewport. Narrow CAPA remains within the content
width and scope does not overlap it. A pre-existing header overflow remains:
document clientWidth 375, scrollWidth 384 at viewport 390; the logout control
extends approximately 9px. The same measurement occurs in untouched General
Information. The protected header is not changed by this CAPA-only slice.
Fixture binaries and a screen reader are unavailable; real-backend integration,
storage verification and production UAT remain unverified.

Validation: typecheck, lint, all 329 frontend tests / 25 files and production
build PASS. CAPA/document targeted files pass 28 tests in each of two repeated
runs; the three new App race regressions also pass. The unchanged A3 frontend
owner guard passes in isolated function execution (not a full backend run).
No timeout increase, disabled test, backend change or draft/mutation handler
change. Existing non-failing React act warnings remain. Diff is frontend-only;
there is no database, storage, RBAC or concurrency-contract impact.

## Actual inspection visual/interaction slice — 2026-10-11

Baseline: 39e80378b71d5cf48d50ebfcc5c509ad2ef4a551. Supplied runtime image 2
establishes decision/date and inspection/report dates at left; inspectors,
standard and outcome at right; contextual document access at the right edge.
MainForm DataKT(5..9) maps edKTNgay, edKTQD, edKTBienban, edKTNguoi and
edKTKetqua. MainForm.frx contains the inspection tab, inspection date, report
date and outcome captions; designer data does not establish runtime pixels.

Before: plan start preceded decision, outcome used a single mixed grid below
the plan/team sections, and documents followed the entire inspection workspace.
After: split canonical decision fields lead the left column; Thanh tra viên
labels the existing read-only team snapshot at right. Inspection dates are
grouped at left and standard/Đánh giá kết quả at right, with white aligned
values, normal-weight text and a neutral gray frame. Ngày kiểm tra displays
the canonical inspection_period_segments (all ordered date ranges), not legacy
scalar dates, executed_on or parsed source text.
Additional plan information follows the primary groups without a second owner.
The single unchanged ContextualDocumentSection occupies an independently
scrolling right column, retaining workflow_step, document/version/status/actions
and the complete canonical context key. Narrow layout stacks and scrolls before
the shared scope pane. Master, history, tabs, FacilitySummary and registration
are untouched. CaseAssessment remains registration-only; InspectionOutcome and
final_evaluation are not conflated.

Contract differences retained: decision_reference and decision_date remain two
independent editors rather than one composite legacy value. The typed
minutes_recorded_on label remains Ngày biên bản/report: the legacy B. bản source
includes text and multi-period values, so this slice does not assert a universal
mapping to Ngày viết báo cáo. Structured team controls/readiness, compatibility
references, period, approval, lifecycle and final-evaluation controls remain;
they are not replaced with legacy free-text edits or moved between owners.
The canonical document table/detail remains instead of four file buttons.
No completion tick, lookup by filename/path, missing mutation or status rule
is fabricated. Relative parity is improved; this is not pixel-perfect parity.

EVIDENCE_MISSING: runtime editors/save/cancel/error states; layout for structured
team, canonical period, approval and lifecycle controls; provenance of shared
Ghi chú; universal report-date mapping. Existing team 409 behavior deliberately
closes/discards its structured draft (covered by the unchanged regression),
whereas plan/outcome 403/409/422 retain their open drafts. This slice preserves
these existing semantics and makes no broader draft-retention claim across
workflow/facility tabs that unmount their editors.

New presentation regression fails before the fix and passes afterward. It
checks primary hierarchy, canonical date ranges without scalar fallback, dossier owner
separation and blocked team/final actions. New keyboard/error regressions cover
F2/Enter/Escape, pending controls, plan token 3 vs outcome token 6, same-context
draft preservation, 403/409/422 and no automatic retry. Existing App, team/period
and contextual-document tests retain selection, cancellation, identity and
stale-response coverage. App additionally asserts a single document workspace
in the right column. No timeout or existing test is removed.

Fixture browser evidence outside git: inspection-parity-1366.png,
inspection-parity-1920.png, inspection-parity-390.png, inspection-editor-390.png,
inspection-conflict-1366.png, inspection-document-390.png and
inspection-request-counts.json. Viewports confirmed 1366x768, 1920x1080,
390x844; page width does not overflow (mobile scrollWidth 384). Scope follows
the full narrow inspection content. Keyboard editing/cancel and document
selection/F6 work; scope tabs retain plan/outcome drafts. Facility tab
round-trips retain selected history and production-line UUID. Counters show
one search, one facility and one case read, one explicit document-detail read,
and one explicit plan save (token 3) rejected with 409; navigation adds no
mutation or duplicate read. Fixtures have no binary content. Real-backend
integration, screen-reader acceptance and production UAT are unverified.

Inspection CI owner correction: the first pushed slice failed the unchanged A3
backend architecture guard because the primary date display referenced a legacy
scalar date projection. The component now uses only canonical period segments,
sharing its date-range formatter with the existing period owner; no scalar
fallback, state inference or backend test change. Multiple periods remain ranges
rather than being collapsed to one legacy date. Missing segments show Chưa có.
A regression proves contradictory scalar data is ignored. Browser evidence was
recaptured with synthetic canonical period segments after this correction.

After the period-owner correction: typecheck, lint, all 320 tests / 25 files
and production build PASS. The final inspection/team-period/document files pass
32 tests in each of two runs. The unchanged A3 frontend-owner guard also passes
in isolated function execution; this alone is not a full backend test run.
No timeout increase, disabled test or backend modification was used.

Validation before the CI period-owner correction: typecheck, lint, all 319 tests / 25 files and
production build PASS. Initial complete targeted run: 169 tests PASS; final
inspection/team-period/document files repeated twice: 31 tests PASS each.
One intermediate full run failed four assertions after the visible outcome-label
change also changed the textarea accessible name. The editor name was restored;
the complete final run above passes. No timeout was raised or test disabled.
Existing non-failing React act warnings remain. Diff is frontend-only; there is
no data, storage, authorization or backend mutation-contract change.

## Dossier assessment placement follow-up

### Registration visual/interaction slice — 2026-10-11

Baseline: c6f9d76473072ffe9a802d8b584b212e9131a47c. Runtime image 1
and MainForm DataKT(0..4) establish four aligned left-hand values (Ngày nộp,
Mã hồ sơ, Ngày thẩm định, Người thẩm định), a taller white result at center,
and assessment document access at right. The registration-only presentation
now follows that arrangement with matching label widths, centered values,
white field backgrounds and a neutral gray frame. The redundant visible
heading is screen-reader-only; additional canonical metadata remains available
in a native Thông tin bổ sung disclosure. Folder lookup is retained unchanged.

EventWorkspace moves its single existing ContextualDocumentSection into a
right-hand column; its implementation, context key, UUIDs, action availability,
workflow_step filtering and callbacks are unchanged. Backend contextual_actions
maps INSPECTION_BBTD_HOSO_DK / Biên bản thẩm định to Hồ sơ. No filename, NAS path
or legacy ID is used to select a document. Desktop document content scrolls
independently. At narrow width the form/result/documents stack before scopes;
registration-specific sizing prevents the scope pane overlapping long content.
Master, GxP rail, history, navigation and FacilitySummary are unchanged.

Remaining differences: retain the canonical document list/detail, versions,
status and action availability instead of reducing them to a single legacy
file button. Retain inline save/cancel controls and the folder lookup helper.
EVIDENCE_MISSING: legacy runtime editor/save/cancel/error states and provenance
of the shared Ghi chú row. No field/action or completion tick is invented.
This slice does not address other workflow steps or complete Issue #1.

Browser evidence (synthetic fixture API only), outside git:
registration-parity-1366.png, registration-parity-1920.png,
registration-parity-390.png, registration-document-focus-390.png,
registration-conflict-390.png and registration-conflict-1920.png.
Viewport DOM measurements confirm 1366x768, 1920x1080, 390x844 and no horizontal
page overflow (narrow scrollWidth 384). Scope bottom follows registration on
narrow layout. F2/Enter editing, Escape cancel, Enter document selection and
F6/Shift+F6 work; scope navigation retains the application draft. Facility and
event-tab round trips retain selected history and production-line UUID.
Fixture counters show one search/facility/case read and one explicit document
detail read; navigation produces no mutations. Two explicit save attempts
(application token 4; assessment token 2) each produce one 409 and keep drafts,
without retry. Fixture omits binary content; no backend/storage integration,
screen-reader acceptance or production UAT is claimed.

Slice validation: typecheck, lint, full 314 tests / 24 files and build PASS.
Targeted App/application/registration/document files: 166 tests PASS. The new
presentation regression failed before implementation and passed afterward.
The initial broad targeted run had async-query failures and two default 5000ms
timeouts; the subsequent complete targeted and full runs pass with unchanged
timeouts and business handlers. Existing non-failing React act warnings remain.
Diff review confirms frontend-only changes and no modification to
ContextualDocumentSection, SearchPage, FacilitySummary or backend contracts.

Image 1 and MainForm DataKT mappings place submitted date, application code,
assessment date/person at left and assessment result at right in registration.
The domain contract identifies CaseAssessment as the dossier assessment owner;
InspectionOutcome owns inspection/final conclusions separately. Registration now
composes the existing application and assessment editors. Processing shows the
administrative timeline. No assessment mutation, row_version, authorization or
document workflow_step mapping changed, and only one assessment editor mounts.

Additional canonical metadata remains below the four primary fields. This and
the document list/detail surface are remaining density/placement differences.
The other inspection/CAPA/final field groups and RecordForm/pickers still need
further parity implementation; this is not acceptance of the whole Issue #1.
Static FRX controls are available, but complete runtime captures of the master,
General Information, RecordForm, FilterForm and pickers remain EVIDENCE_MISSING.

Regression covers registration/timeline round-trips without extra workspace
requests, assessment save, 409 draft retention, same-context refresh preserving
document selection/draft/original concurrency token, and late binary A/B/A.
Fixture browser confirms a draft survives scope-tab navigation, selected history
survives narrow layout, and no horizontal overflow at 390px. Captures:
legacy-dossier-1366.png, legacy-dossier-1920.png, legacy-dossier-390.png.
All browser evidence is fixture API E2E; no real-backend integration or production
UAT is claimed. User screenshots and real business payloads remain outside git.

Latest validation: pnpm typecheck, pnpm lint, pnpm test --maxWorkers=1
(309 passed / 23 files), pnpm build. No timeout was increased. Existing
non-failing React act warnings remain. The three initial failures were outdated
assessment-placement expectations and one mistakenly changed document-step
selector; the backend document workflow_step contract remains authoritative.
Repeated targeted regression: 6 passed (A/B/A late binary, refresh draft/token,
assessment placement and 409). Repository tracked-file hygiene also passed.
