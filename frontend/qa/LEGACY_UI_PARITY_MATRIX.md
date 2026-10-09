# LEGACY_UI_PARITY_MATRIX — Issue #1

Direction: the user decision dated 2026-10-10 supersedes earlier aesthetic
recommendations in UI_REDESIGN_VBA_REFERENCE and PHASE12. Preserve legacy UI where
evidenced. Baseline: `50576b0b383161e26e27b6cdc4a1a469aff1ae17`; work branch:
`codex/legacy-ui-parity-20261010`. This delivery is partial; it does not close #1.

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

## Dossier assessment placement follow-up

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
