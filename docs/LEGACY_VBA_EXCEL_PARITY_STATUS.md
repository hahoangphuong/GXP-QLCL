# Legacy VBA/Excel business parity status

Version: **1.8 — 2026-11-01**. Historical inventory baseline main
`5062b5a3f50f06d8b8348d95199b0bbe5e8f395c`. Scope: available workbook/add-in
source, approved contracts, current frontend/backend source, regression and
isolated browser fixtures. This is not authenticated staging, production UAT,
Word acceptance, screen-reader verification or a migration completeness certificate.

The v1.1 CaseApplication optional-null observation records its original baseline.
During v1.2 validation, backend main PR226 (`a8318119dae3638d3aa5ec29c26cb03945b59394`)
added create-only-null enforcement at that stage owner. It was audited and
preserved from main, not implemented by this frontend slice. The generic optional
helper is unchanged; do not generalize the application-specific rule to CAPA or
other aggregates. Issue222 closure/transaction acceptance remains backend-owned.

## Classification and evidence rules

- `IMPLEMENTED_VERIFIED`: only the named behavior was exercised by the cited test
  or controlled fixture. It never means every operation of a module is complete.
- `IMPLEMENTED_PARTIAL`: implemented surface with an unverified or missing path.
- `MISSING`: no corresponding implemented capability established.
- `BLOCKED_BY_BUSINESS_DECISION`: requires an explicit owner contract/acceptance.
- `BLOCKED_BY_PRIMARY_EVIDENCE`: cannot establish runtime/output parity from source.
- `UNKNOWN_SOURCE`: source evidence for the claimed behavior is unavailable.

Unit/fixture verification proves payload/event/state behavior. Backend regressions
can prove transactions on disposable databases. Neither proves authentication,
NAS, original legal output or historical reconciliation on production data.
No percentage is computed and no module is called complete because it has a UI.

Primary map: `LEGACY_SYSTEM_MAP.md`, `WORKFLOW_MODEL.md`,
`INSPECTION_CASE_LIFECYCLE_OWNER_MATRIX.md`, `CASE_E2E_LEGACY_PARITY_ACCEPTANCE.md`,
`frontend/qa/LEGACY_UI_PARITY_MATRIX.md`. Local static source references below are
under `artifacts/legacy_audit/vba_sources/GPs/`; original binaries were not opened
in Office or modified. Source representation is evidence, not executed VBA.
Architecture/owner references: ADR0037/0038/0040/0052/0053/0056/0060/0061 and
`GMP_FORWARD_SINGLE_CASE_SITE_CERTIFICATE_20261018.md`; newer decisions override
older architecture text. Frontend files are under `frontend/src/features/search/`
unless otherwise specified. API adapters are in `frontend/src/lib/api.ts`;
server ownership is `backend/app/api/routers/{catalog,workflow,document}.py`,
`backend/app/services/workflow.py`, read models, document services and repositories.

## Module inventory: business and interaction ownership

| Module | Legacy entry point / source owner | Data owner / reads and writes | Interaction and business rule | Current implementation | Tests / evidence | Gap, severity and recommended action |
|---|---|---|---|---|---|---|
| 1 Master Facility | Workbook Main; MainForm; Module1.ReFilter | Legacy db.cty/db.cso/db.DC; web Company/Site/ProductionLine and canonical result_key | Select explicit row/line; focus movement is distinct from activation; preserve full-width table and GMP/GLP/GMPbb rail | FacilityTable + pages/SearchPage; cancellable access-bound search | FacilityTable.test; earlier master/history fixture evidence in parity matrix | IMPLEMENTED_PARTIAL overall; bulk master create/edit parity not established by table existence. Medium: inventory missing mutation contracts before adding commands. |
| 2 Facility Summary | MainForm site/certificate display and GetSetDataCso | Site/Company read projection; certificate scope/version owned by certificate, not display | General information grouping; unknown values remain unknown | FacilitySummary, FacilityWorkspaceTabs | FacilityWorkspaceTabs.test and general-information runtime images/parity matrix | IMPLEMENTED_PARTIAL; summary has no canonical limits value (explicit missing-data text), several details read-only. Medium: request read contract/evidence rather than inventing values. |
| 3 Hồ sơ đăng ký | MainForm.GetSetDataKtra -> GetSetData -> TextForm.GetText | db.ktra fields; web CaseApplication and CaseAssessment are distinct aggregates | Double-click editor; OK commits, Cancel does not; structured dossier/date/assessor/result | CaseApplicationWorkspace + CaseProcessingWorkspace assessment mode; PUT application/assessment with expected_version | CaseRegistrationWorkspace.test; CaseApplicationWorkspace.test; TextForm btnOK/btnCancel/GetText and MainForm GetSetData | IMPLEMENTED_PARTIAL module; shared keyboard action defect fixed in this slice. Real permissions/persistence round-trip needs staging. High: preserve draft/token on pending/409; no auto retry. |
| 4 Case lifecycle/initialization | MainForm.InsertNewKtraDB and reassessment flow; TaiDKForm | db.ktra; web Case, explicit Site/ProductionLine, scoped source_case_id, transition audit | User enters other data; reassessment may reuse approved source-Case data; no KHKT-to-Case backfill | SearchPage createInspectionCase; workflow create_inspection_case copies evaluation scope from an explicit source with matching line; CaseLifecycleActions uses server target_state/token | CaseLifecycleActions.test; test_a3_case_lifecycle_completion; test_phase10_workflow_mutation reassessment tests; QDKT_CASE_ORIGIN_AND_RENDER_SOURCE_CONTRACT | IMPLEMENTED_PARTIAL overall; the specific scope-copy/user-input contract is regression-verified. Medium: authenticated UI/readback acceptance remains; broader inheritance must not be inferred or added without an owner contract. |
| 5 KHKT | Workbook/add-in Module1.Ke_Hoach/List_KH; RecordForm.CreateFile case3 | Legacy KH/KHKT and db.ktra; canonical InspectionPlan/team; document service owns output | Plan/team input; typed readiness and create; Case data does not come implicitly from KHKT | CaseInspectionWorkspace, contextual documents, SearchPage typed KHKT GET/POST with empty body | ContextualDocumentSection.test; test_case_inspection_plan_typed_render/current_version_gate; parity matrix KHKT audit | IMPLEMENTED_PARTIAL; Word/Synology binary parity and true authenticated browser rehearsal unverified. High: approved isolated integration, not generic renderer fallback. |
| 6 QĐKT | Module1.TaoQDKT_KHKT; RecordForm.CreateFile(i=2), Tao_QDKT_KHKT_BBKT; TTVForm | Source/decision/draft/roster evidence and canonical lifecycle owners, not KHKT fallback | Independent draft with blank issuance date vs approved number/date/team; multiple decisions use confirmed explicit lineage, never max date heuristic | QdKtCaseReadinessPanel is read-only; no typed issuance UI enabled | QdKtCaseReadinessPanel.test; QĐKT provenance/lineage suites; Issues74/144 and Draft206 | BLOCKED_BY_PRIMARY_EVIDENCE and BUSINESS_DECISION for remaining business acceptance. Critical: do not activate renderer/legal issuance or polish collector without new evidence. |
| 7 Kiểm tra thực tế | MainForm.GetSetDataKtra, TTVForm; RecordForm inspection documents | db.ktra; InspectionPlan, ordered period segments, team, outcome/final evaluation | Preserve ordered visits, exact roster identities and independent approval actions; no flattening multi-visit dates | CaseInspectionWorkspace + CaseApprovalWorkspace | CaseInspectionWorkspace/Parity and CaseApprovalWorkspace tests; test_a3_case_lifecycle_completion | IMPLEMENTED_PARTIAL; canonical CRUD tested, imported-source vs runtime periods and Word result output remain separate. High: authorized transaction/readback and explicit legacy date acceptance. |
| 8 CAPA | MainForm.GetSetDataKtra and CAPA field/action groups; RecordForm CAPA generation | db.ktra legacy round fields; canonical CapaCycle UUID/round/status/version, authenticated assessor | Create/update/submit/assess distinct; preserve multiple cycles and per-cycle document parent | CaseRemediationWorkspace + contextual parent_scope=capa_cycle | CaseRemediationWorkspace.test; ADR0060/0061; test_a3_capa_incoming_reference_postgres | IMPLEMENTED_PARTIAL; typed CAPA Word document generation missing; runtime layout only partially evidenced. High: backend contract first; retain existing per-action 409 draft semantics. |
| 9 Xử lý tiếp | MainForm processing fields/PCT/CT controls; RecordForm supporting documents | Canonical processing event timeline, approval submissions and outcome; assessment remains dossier-owned | Read all actual events, create/complete authorized approval stage, no made-up completion ticks | CaseProcessingWorkspace timeline + CaseApprovalWorkspace | CaseProcessingTimeline.test; CaseApprovalWorkspace.test | IMPLEMENTED_PARTIAL; risk/PCT/CT document generation and real persisted approval chain UAT absent. High: backend-owned typed documents; no assessment-owner relocation. |
| 10 GMP/GxP certificate | MainForm.Replace_CC/UpdateCCGPsItem_Row; SelectCC; RecordForm certificate generation | db.cc; Certificate/CertificateVersion/scope/history with explicit Case/Site links | Issue differs from promote-current; prospective case-backed GMP at most one certificate; preserve historic exceptions | CaseCertificateIssueWorkspace; GxpCertificateWorkspace; persisted history/metadata hooks | CaseCertificateIssueWorkspace/GxpCertificateWorkspace/PersistedCertificateHistory tests; approved GMP contract; certificate domain tests | IMPLEMENTED_PARTIAL; source metadata is not legal certificate output or global historical integrity proof. Critical: no silent historic normalization or latest_flag identity inference. |
| 11 ĐĐK | MainForm.CapNhat_DDK/GetSetDataDDKDs/ChonDDK_Thaythe; SelectDDK; RecordForm.CreateFilez | db.dkkd four source groups; BusinessEligibilityCertificate/version, canonical basis and provenance | Issue/edit/promote separate; group provenance is backend-owned, not inferred from filenames/type/text | BusinessEligibilityWorkspace, source evidence, persisted history and Case linked view | BusinessEligibilityWorkspace/SourceEvidence and CaseBusinessEligibilityParity tests; version-history API tests | IMPLEMENTED_PARTIAL; preparatory forms and five generated slots not all publicly supported. High: preserve explicit provenance; request typed output contracts. |
| 12 History/audit trail | MainForm.UpdateListHistory/UpdateHistoryItem; certificate source/successor lookup | db.ktra/db.Tdoi; canonical history events, immutable versions and AuditEvent before/after | Exact event/UUID navigation; persisted snapshot is not current edit; no deletion/cleanup inference | HistoryTable, FacilityHistoryPane, PersistedCertificateHistory, SearchPage | HistoryTable/FacilityHistoryPane/PersistedCertificateHistory tests; ADR0056 and version API suites | IMPLEMENTED_PARTIAL; operator-facing consolidated audit browser/export not equivalent to business-event history. Medium: separately scope read-only audit viewer API before adding UI. |
| 13 Search/filter/navigation | Module1.ReFilter; FilterForm persisted named-range queries; MainForm list selection | Legacy List_*/saved names; canonical search query, URL, result_key, access-bound request owner | Two user-approved text filters; canonical line identity; Arrow/Home/End focus-only, Enter/Space activates | FacilityTable, HistoryTable, SearchPage, LegacySearchFilters | FacilityTable/HistoryTable and API request isolation regression; parity matrix | IMPLEMENTED_PARTIAL; saved operational FilterForm query semantics missing/unsupported and explicitly not to be restored as an extra filter row. Medium: keep current exceptions; future contract and owner decision. |
| 14 Word/Excel exports | Workbook Xuat_XLSx2/report macros; RecordForm/ExtRecordForm Word/Excel/PPT generation | DocumentService/StorageService own logical document/variant/version/output; never client NAS | Exact family/template/input/readiness; no generic fallback to imitate unavailable output | ContextualDocumentSection; typed KHKT; many outputs guarded; /reports is PlaceholderPage | ContextualDocumentSection.test; document service/typed KHKT tests; CASE_E2E acceptance | MISSING for operational report/Excel export; IMPLEMENTED_PARTIAL for document families; QĐKT BLOCKED. High: backend payload/template/owner acceptance first, then a complete report slice; no placeholder functionality added here. |
| 15 Keyboard/double-click | MainForm field DblClick -> GetSetData; TextForm.GetText/btnOK/btnCancel/ed_KeyPress | Shared interaction owner only; domain mutations remain in existing handlers | Explicit OK vs Cancel; Escape cancellation; native web button/select/IME semantics must not become unintended save | EditableDetailValue shared by application/assessment/inspection/CAPA; existing rail/table/tab navigation unchanged | New EditableDetailValue.test + registration integration; browser fixture/native keys at three viewports | IMPLEMENTED_VERIFIED for the corrected event boundaries only; native assistive speech and exhaustive legacy shortcuts UNKNOWN_SOURCE/PARTIAL. Do not infer geometry or shortcuts from procedure names. |

## Separate parity dimensions

Legend: P = IMPLEMENTED_PARTIAL, V = IMPLEMENTED_VERIFIED only for explicit tested
scope, M = MISSING, E = BLOCKED_BY_PRIMARY_EVIDENCE, B = BLOCKED_BY_BUSINESS_DECISION.
These are independent dimensions, not a roll-up score. Server authorization
regressions do not imply authenticated browser/UAT acceptance.

| Module | UI | Workflow | Data | Persistence | Document output | Authorization |
|---|---|---|---|---|---|---|
| Master | P | P | P | P (master mutation parity not established) | M (lists/export) | P |
| Facility Summary | P | P (read view) | P | P (read projection only) | M | P |
| Registration | P; V for corrected keyboard boundary | P | P | P; disposable/API tests exist | P (contextual inventory) | P; server403 tested, field readiness not uniformly exposed |
| Case lifecycle | P | P | P | P | P | P |
| KHKT | P | P | P | P | P/E (original binary UAT) | P |
| QĐKT | P (readiness only) | B/E | B/E | P (internal components, not public issuance) | B/E | P (read only) |
| Inspection | P | P | P | P | P/E | P |
| CAPA | P | P | P | P | M/P | P |
| Processing | P | P | P | P | M/P | P |
| GxP | P | P | P/B (historic exceptions) | P | E/P | P |
| ĐĐK | P | P | P | P | M/P/E | P |
| History/audit | P | P | P | P | M (audit export) | P |
| Search/filter | P | P | P | P (saved filters absent) | M | P |
| Word/Excel | P | P/B | P/B | P | M/P/E/B by family | P |
| Keyboard/double-click | V for fixed owner; P elsewhere | V for no unintended save/pending cancellation | P (unchanged) | P (unchanged) | Not applicable | P (unchanged) |

`UNKNOWN_SOURCE` applies to live legacy runtime focus/IME behavior and unsupported
picker/auxiliary form geometry not established by the supplied images/source. The
web IME/native-button rule is a browser interaction safety contract, not a claim
of VBA pixel equivalence. Existing approved UI exceptions remain: header/master,
vertical rail/action panel/history, two list filters, no additional FilterForm row.

## Selected implementation: inline edit action boundaries

Last-correct: TextForm GetText returns success only after OK, while Cancel/Escape
sets Canceled; web Save/Cancel buttons already separated and Cancel disabled
during pending. First-incorrect: EditableDetailValue handled every bubbled Enter
as a save, including Cancel/Save/select, and Escape called onCancel even when
pending. IME Enter could also save before composition finished. Other read-only
fields could activate while the same aggregate was pending, replacing the editor.

A second owner defect was demonstrated in CaseApplicationWorkspace: its draft
survived refresh but Save read the refreshed prop's row_version instead of the
version at edit start. That could submit older input with a newer optimistic
token. Two RED cases (existing version4 and new-row null, both refreshed to5)
proved the token changed incorrectly. The application owner now captures the
token when each field opens, just as assessment already does.409 retains the
original draft/token; Cancel/reopen adopts the newly reviewed value/version.
No API/schema or backend concurrency rule changes, merge heuristic or retry.

Version1.1 corrects an important limit found in post-merge source verification:
backend `_assert_expected_version(None)` skips version checking, even on an
existing application. The earlier null/409 fixture proved client error handling,
not server create-only semantics. Actual service reproduction in disposable SQLite
confirmed the optional-null behavior; backend review is Issue #222. The application
draft owner now refuses to submit an absent-row draft **after observing** a newly
created row via refresh, retaining text for explicit Cancel/reopen/review. This is
an editor ownership boundary, not a synthetic HTTP409 or repair of server races.
Null creation without an observed owner change keeps the existing API contract.
An unobserved concurrent creation race still requires the backend owner; no client
claim of complete concurrency protection is made.

Reproduced on unchanged source: shared9cases had5FAIL/4PASS; registration7cases
had2FAIL/5PASS. The registration failures demonstrated an unexpected application
mutation from Enter on Cancel and a lost assessment draft after pending Escape
followed by409. No backend or domain rule changed.
An additional focused regression on the first fix was RED1FAIL/10PASS for pending
field activation; the shared owner now blocks F2/Enter/double-click while pending
and exposes aria-disabled without changing selection or adding a request.

Minimal fix at shared owner: ignore composition; leave Enter on native buttons,
selects, textareas and links to those controls; allow Escape cancellation only
when not pending. Ordinary single-line Enter, multiline newline, disabled-save,
double-click/F2/Enter activation, backend403/409/422 feedback, original tokens and
no automatic retry remain unchanged. Explicit Cancel after settlement works.
Buttons still use their existing click handlers; no downstream rescue added.

Regression evidence includes native Edge fixture Cancel Enter with zero save
calls, Save Enter once, Tab/Shift+Tab order, pending Escape, retained draft after409
with expected_version7 and explicit post-error cancellation. Application refresh
keeps its token4; only Cancel/reopen adopts5 (three explicit fixture saves total,
tokens7/4/5). Browser fixtures use
synthetic canonical-shaped identities and local promise callbacks, not real
backend mutations. No real company/case is hardcoded. At1366x768,1920x1080,390x844
document scroll/client widths match1366/1366,1920/1920,390/390; screenshots and
measurements are outside Git under `.codex/evidence/legacy-business-parity-20261029/`.
This is FIXTURE_VERIFIED, not authenticated integration or SCREEN_READER_PASS.

Keyboard-stage local validation: targeted41PASS on two implementation runs; strengthened
shared/registration subset18PASS; full frontend544PASS/0FAIL/0SKIP across37files;
lint/typecheck/production build PASS. Relevant backend contract/hygiene subset
29PASS, plus two named reassessment persistence tests PASS (86 unrelated tests
deselected by the explicit selection, not skipped). No timeout or assertion was
weakened. Exact tested SHA and six required CI gates are recorded in the delivery
PR. Main drift #219 (`85c258fc37a4da81dd3b8a9dfda695ae2b927aae`) was audited:
one PostgreSQL failure-injection test-only change, preserved without editing.
The added application-token regression was RED2FAIL/7PASS, then combined targeted
coverage64PASS including the application/folder owner, inspection and CAPA.
Final combined full-suite and exact-HEAD CI totals are recorded in the PR handoff.

## Business contracts retained / backend handoff

1. Reassessment inherits only source-Case data supported by the approved contract
   and implementation; current create explicitly passes source_case_id and copies
   evaluation scope after canonical line validation. Other fields stay user input.
   The approved scope-copy/user-input path is covered by the existing reassessment
   regression; a future expansion would require its own owner contract.
2. KHKT is not a Case-data backfill owner. Team suggestion/reuse requires explicit
   canonical team linkage. Draft QĐKT date stays blank; approved number/date/team
   is another process. Multi-decision selection uses explicit confirmed lineage,
   not MAX(date) or a filename. No change to any QĐKT source/renderer/collector.
3. Prospective case-backed GMP is **at most one** certificate per one Case/Site;
   zero is valid before/refused issuance. A second issue is409 even when the older
   certificate is noncurrent. Historical exceptions require evidence-bound review,
   not a blanket unique constraint or silent relinking.
4. ChatGPT backend follow-ups: typed CAPA/PCT/CT/other output readiness and payloads;
   operational reports/Excel export contract; uniformly explicit field mutation
   readiness if desired; independent historical integrity/reconciliation and full
   optional broader inheritance only if requested by the owner. This audit records gaps, not new APIs or
   database/storage changes. Source-level component existence is not an issue
   claiming that a production defect has been demonstrated.
5. Remaining acceptance: authenticated A/B role tests, persisted readback/reload,
   private template/Word display and Synology write/recovery, source corpus data
   reconciliation and owner/legal acceptance. Runtime evidence cannot replace them.

PR206 remains OPEN/DRAFT with UNVERIFIED_VERSION_BINDING; Issues74/144 OPEN.
decision=UNDECIDED, ready_to_render=False, WordUAT=NOT_EXECUTED; renderer/legal
issuance disabled. No production DB/NAS/GCS, deployment, original binary/template,
Trust Center, VBA execution, API/schema/RBAC or document-finalization changes.

## Inspection / CAPA workflow audit and draft ownership — v1.2

Slice baseline: `657f0ea7c854373d5b115172a47ac84c8aa75cb9`.
No module-wide parity status is promoted. Sources are the lifecycle owner matrix,
WORKFLOW_MODEL, CASE_E2E_LEGACY_PARITY_ACCEPTANCE, ADR0037/0060/0061 and the
current typed requests, workflow service and frontend owners. MainForm
GetSetDataKtra first resolves the selected history row with Get_List_RngKtra,
then dispatches GetSetData; only a valid accepted edit refreshes the site/history.
TextForm.GetText returns output only when not Canceled. RecordForm.CreateFile
cases5/6 and Tao_BB_CAPA use distinct round outputs and copy DsTT/CAPAx through
Word COM. These are static source facts, not VBA runtime/Word acceptance.

| Audited owner / operation | Evidence and finding | Disposition |
|---|---|---|
| Inspection periods | InspectionPeriodSection retains ordered canonical segments, renumbers explicit reorder/removal, never flattens to legacy scalar dates; existing tests exercise create-only null versus existing version and denied readiness | Unchanged; specific regressions rerun. Authenticated persistence/legacy date acceptance remains partial. |
| Inspection team | Structured inspector_profile/person/organization identity, explicit order/roles and backend edit readiness; no parsing display text or KHKT backfill | Unchanged. Existing 409 contract intentionally discards the team editor, unlike CAPA; do not globally replace it with CAPA retention semantics. |
| Inspection plan/outcome/final evaluation | Separate plan/outcome tokens and typed final-evaluation readiness; dossier CaseAssessment stays registration-owned | Unchanged. Source-level risk: several handlers read current prop/readiness versions when saving retained input. Refresh-before-save and Case-switch ownership need a separate RED audit before changing these independent owners. Existing no-refresh 403/409/422 and pending regressions pass; exhaustive refresh concurrency is not claimed verified. |
| PCT/CT approvals | Canonical stage/round/UUID, completed PCT parent explicitly selected for CT, separate create/complete actions and readiness token | Unchanged; exact payload/denied readiness tests rerun. Shared completion draft, async Case change and refresh-before-complete need focused follow-up; no invented latest-round rule or legal output. |
| CAPA create | Form retained input while taking current Case version; no Case-bound completion guard | Fixed frontend ownership: capture Case token when opening create; Case/cycle change discards the replaced editor and invalidates late completion, including A→B→A/unmount. |
| CAPA update/submit/assess | Existing same-version drafts and per-cycle identity were correct. Version-key hydration cleared pending/editor/draft on a newer version, and saving could adopt the refreshed token | Fixed: Case+cycle UUID owns operation generation; a separate hydrated draft token stays with dirty/open/pending input. New server data hydrates only clean idle input, explicit cancel/row activation, or successful callback plus newer readback. |
| Return from create to the already selected cycle | Row activation closed create but did not reset its draft because the selected cycle/version key did not change | Fixed: explicit row activation cancels/reloads the draft before selecting. It never creates or updates by itself. Focus alone does not activate. |
| Contextual documents | EventWorkspace filters workflow_step and exact parent_scope=capa_cycle/parent_id; one ContextualDocumentSection retains document/version/rendition/action identity and stale-response generations | Unchanged; contextual identity/binary regressions rerun. Metadata is not proof of an accessible/valid Word file or legal output. |

Last-correct: same-version refetch and canonical cycle switching already worked.
First-incorrect: CaseRemediationWorkspace used cycle UUID+row_version as both
request identity and draft hydration boundary, while create lacked Case ownership.
Version advancement is not a new aggregate and must not unlock an in-flight
command or silently authorize old input with a new token. The owner now keeps
these boundaries separate. No backend rule, optional-null helper or Issue222 fix
is implemented by this frontend slice; the independent main PR226 is preserved
as noted above. Server readiness still owns permission and status eligibility.

Specific corrected behavior is IMPLEMENTED_VERIFIED by regression/fixture:
edited and unsent command drafts keep their original cycle token; create keeps
its edit-start Case token; refresh does not clear pending or permit duplicate
activation; current 403/409/422 errors retain CAPA drafts without automatic retry;
late replaced create/update/submit completion cannot publish into a new owner;
Cancel/reselect explicitly adopts reviewed server data. Successful callback and
readback tests prove UI state only, not a production commit or audit row.

Initial RED:6FAIL/14PASS. Additional create→selected-cycle RED:1FAIL/20PASS.
The corrected CAPA suite has27 tests, including404/network failure on all four
commands. Targeted Inspection/CAPA/Approval/document suite68PASS; full/CI final
counts are recorded in the delivery PR and local
handoff. Existing contract-related backend CAPA tests14PASS,74 explicitly
deselected, not skipped. No timeout increase, disabled tests or weaker assertions.
Final local frontend560PASS/0FAIL/0SKIP across37 files; targeted68PASS in each
of two final runs; typecheck/lint/production buildPASS. Lifecycle/owner backend
regression12PASS. The first full run had one stale409-copy assertion (557PASS,
1FAIL); App regression now asserts the complete revised guidance while retaining
draft and request-count checks. No act/unhandled warning in the final test log.

Controlled headless Edge uses actual React owners/styles and fixture callbacks.
At1366x768,1920x1080,390x844 document scroll/client widths are respectively
1366/1366,1920/1920,390/390. Baseline loses the open draft on version refresh;
fixed fixture retains it, token2, pending, and409. Explicit Cancel/reopen uses3;
create uses Case8 despite refresh9; submit/assess keep2; late create is ignored.
Five explicit fixture callbacks per viewport, zero API requests, zero Cancel
mutations. F2/double-click/Tab/Shift+Tab/Enter/Escape and cycle Space/Enter work.
Screenshots/measurements are outside Git under
`.codex/evidence/inspection-capa-20261029/`. FIXTURE_VERIFIED only; this isolated
component harness does not verify full-shell navigation, authenticated backend,
screen-reader speech, original VBA, Word formatting or NAS binaries.

Document-output status remains **BLOCKED_BY_TYPED_DOCUMENT_CONTRACT** for CAPA
Word: current contextual metadata/content actions are not a complete approved
CAPA render payload/readiness/template contract. No placeholder DOCX, inferred
storage locator, extra document button or legal generation is introduced.
Backend handoff remains typed CAPA/PCT/CT output contracts and Issue222; no new
backend defect was established by this slice. Frontend next priority is a
separate refresh-token/Case-owner audit for Inspection/Approval editors above.
PR206, Issues74/144 and QĐKT evidence/render/issuance gates stay unchanged.

## Inspection / Approval editor ownership — v1.3

Starting main `7eb0f0ad6e04f0928de460407170a8307436d46f`. The preceding main
drift from PR227 was only PR228's disposable PostgreSQL application-creation
test; it was audited and preserved. During work, backend PR229
`bf9fe2545a63a5debb241df8fc938220fd0bdfbe` added CaseAssessment-specific
create-only-null enforcement and tests. Both backend diffs remain untouched.
This slice does not extend those rules to InspectionPlan/Outcome.

Evidence: current typed requests/read models/service methods, lifecycle owner
matrix and CASE_E2E acceptance, ADR0037/0052, MainForm.GetSetDataKtra's selected
history/base-row resolution and accepted-edit refresh, DataKT inspection/final
controls, TextForm.GetText/OK/Cancel and TTVForm's explicit accepted/canceled
team input. Static VBA establishes dispatch/ownership and cancel behavior, not
runtime concurrency or an exact web approval-round layout. PCT/CT stages/rounds,
explicit completed PCT parent, immutable final evaluation and backend readiness
are current canonical contracts; no MAX(date)/filename/latest heuristic is added.

### Editor audit: one draft, one owner

All Case editor lifetimes below are keyed by canonical Case UUID. Returning
A→B→A creates a new editor instance, even if the UUID string equals the earlier
one. A server version change alone does not replace that instance.

| Editor / aggregate identity | Token and hydration | Pending / response acceptance | Cancel / errors | Readiness owner |
|---|---|---|---|---|
| Plan: Case + InspectionPlan (Case-keyed API; no plan UUID exposed in this projection) | Capture plan_row_version and current data on explicit field activation; refresh retains open input/token | One pending field; native controls stay disabled; replaced Case instance cannot receive old completion | Cancel/Escape reloads reviewed data; 403/404/409/422/network retain open draft, no auto retry | Existing backend write contract; no client role map |
| Outcome metadata: Case + InspectionOutcome | Capture outcome_row_version on field activation; separate from dossier CaseAssessment | Same field pending boundary; readback cannot publish another Case or superseded response | Same retained-draft error contract; reviewed version only after Cancel/reopen | Existing typed metadata mutation; compatibility refs remain read-only |
| Periods: Case + outcome replacement | Capture inspection_period_edit_readiness.expected_version when opening; ordered 0..n ranges stay id-free and unflattened | Refresh does not re-enable/reopen the active replacement; Save remains single-attempt | Local Hủy discards; errors retain editor. Null initialization versus existing version stays server-owned | Backend period readiness/mode, including source-owned non-KNOWN guards |
| Team: Case + team_id (or absent aggregate) | Capture token before loading identity options; freeze the matching members while loading/editing. UUID replacement unmounts old editor; version-only refresh does not | Loading and Save share the existing pending boundary; no parsing of display_text, no KHKT backfill | **Existing 409 closes/discards team editor**, other errors retain it. Reopen uses reviewed structured members/token | Backend team readiness and canonical identity options |
| Final evaluation: Case + outcome finalization | First input change captures readiness.expected_version; even a concurrently published final value does not erase the open draft | Pending prevents second finalize; explicit local cancel disabled while pending | Error retains input/token; local Hủy nhập đánh giá resets intent. Success clears only its own editor | Backend finalization readiness, required numeric version and immutable-value rules |
| Approval create: Case + explicitly invoked PCT/CT stage | Existing create contract has no client version field; none invented. CT requires the explicitly selected parent still present in completed PCT readback | One pending action disables create/parent/completion controls; Case replacement invalidates old component completion | Failure retains create fields; success clears accepted input. No automatic POST retry | Backend create action readiness; client only validates the explicit selection still exists |
| Approval complete: Case + approval_submission_id + stage/round metadata | Each canonical UUID owns separate date/time/reason draft; capture readiness token on first change, not at Complete | One workspace command at a time; refreshing/reordering does not transfer draft to another row | Local Hủy nhập hoàn tất clears only that row; 403/404/409/422/network retain it/token, no retry | Matching backend complete_approval:UUID action; no inferred parent/round |

### Proven gaps and owner corrections

1. Last-correct baseline already retained inline drafts while editing and
   disabled pending buttons. First-incorrect Save handlers used **current props**
   instead of the token matching that draft. Snapshot tokens are now captured at
   the actual edit/intent boundary, including Team's async options interval. Team
   re-entry while already editing is disabled: its RED regression otherwise
   reloads options twice and recaptures a refreshed token for old members.
2. CaseInspectionWorkspace and CaseApprovalWorkspace could reuse local state
   across Case changes. React Case keys now define the owner generation; Team
   UUID and approval UUID additionally define their child aggregate lifetimes.
3. A shared completion draft fed any row's Complete button. It now lives at each
   exact approval row. This minimal presentation difference is required by the
   multi-round canonical contract; no new server action or approval state exists.
4. SearchPage Plan/Outcome bypassed the case request sequence and could publish
   old readback over a newer one. They now use the existing shared readback
   owner/sequence, with a committed Case/context generation captured **before**
   mutation. Inspection/Approval follow-ups from replaced/unmounted owners do
   not initiate GETs; older GETs cannot publish into a new owner/sequence.
5. The old post-write fallback patched a saved response into an old workspace
   when GET failed. Removed only for Plan/Outcome: failed readback reports that
   a save response was received but canonical workspace could not be read. Draft
   remains; no synthetic confirmation or automatic retry is produced. Wrong-Case
   summary or foreign-Case approval rows fail closed at the readback owner,
   without filtering/relinking rescue. Facility refresh cannot force the old
   preferred Case selection after navigation.
6. DOM measurements found Approval controls clipped beyond its narrow pane even
   though document width stayed390. Scoped wrapping/min-width rules make the
   existing create controls and new per-row completion controls reachable;
   readable row metadata remains in its existing order. No body/ancestor
   overflow hiding or other master/history/workflow presentation change.

RED evidence: Inspection7FAIL, Approval5FAIL; corrected parent setup proves6
readback failures against baseline parent source; unmount guard removal produces
an extra GET (3 instead of2); foreign approval-row and team-UUID replacement
tests also fail before their specific guards. Source swaps for owner-isolated
RED were backed up and restored byte-for-byte. Early unmount/foreign-row runs
that did not reach the intended action are setup failures, not defect evidence.
Parent tests now explicitly wait for registration content and open Inspection,
with the existing URL microtask boundary; no timeout/production guard is relaxed.

UNIT_VERIFIED behavior is limited to these editor/request boundaries, not whole
workflow completion. New owner suites run under StrictMode; coverage includes
V1 draft/V2 refresh, pending, A→B→A, Team UUID/options replacement, per-round
completion, explicit Cancel/reopen, readback ordering/ownership and errors.
Final targeted/full/CI counts and exact SHAs are recorded in the delivery PR and
local handoff. Final local frontend599PASS/0FAIL/0SKIP across39 files; targeted
owner/document/keyboard83PASS and parent readback8PASS in repeated final runs.
Typecheck/lint/buildPASS; no act/unhandled warnings in the final log and no
timeout/assertion weakening. Existing >500kB bundle advisory is unchanged.
Relevant backend contract suites45PASS; backend PR229-related
selection8PASS/84 explicitly deselected. No backend source/tests were edited.

FIXTURE_VERIFIED: actual React owners/styles in headless Edge at1366x768,
1920x1080,390x844. Baseline sends refreshed plan token3 for draft2; correction
sends2, then3 only after explicit Cancel/reopen. Approval similarly keeps2 then
reviewed3; period/team/finalization keep2. Nine explicit controlled callbacks per
viewport, zero API requests or Cancel mutations. F2/double-click/Tab/Shift+Tab,
Enter/Escape, select interaction, pending and late Case completion exercised.
Document scroll/client widths1366/1366,1920/1920,390/390; rightmost Approval
control after wrap is1339,1893,363px. Before wrap the mobile create group reached
547px and completion buttons425px, despite the unchanged390px document width.
Original measurements, screenshots, fixture source and logs are outside Git:
`.codex/evidence/inspection-approval-20261030/`. This component fixture does not
claim authenticated persistence or full-shell Back/Forward acceptance.
The pre-existing narrow final-action label wrapping/clipping remains a visual
follow-up; its accessible name and explicit action were exercised. This is not
a claim of complete mobile/legacy visual parity.

### Backend handoff and remaining acceptance

**Issue230:** actual workflow service on disposable SQLite memory confirms
InspectionPlan and InspectionOutcome null-token writes can overwrite existing
version1 rows; stale numeric1 is409. This probe uses current owner logic, not a
simulated lock algorithm. It does not prove a PostgreSQL competing-create race.
Frontend pins the original token, including null, and **does not** add a rescue
or invent create-only semantics. Backend must decide/audit those stage-specific
contracts and callers; never generalize Application/Assessment fixes silently.

Post-write readback failure is not a verified UI persistence readback. Approval
creation has no client version/idempotency token in the current contract; this
slice prevents overlapping UI commands, not all manual/network replay. Reconcile
canonical state before deciding whether a new create is intended. Server
transaction/idempotency policy remains backend-owned.

Inspection/Approval remain IMPLEMENTED_PARTIAL overall. Authenticated A/B roles,
real persistence/audit reload, original VBA editor/runtime acceptance and native
screen-reader verification are NOT_EXECUTED in this slice. Workflow-tab unmount
does not promise draft restoration; it guarantees old completion isolation.
PCT/CT and other missing legal output remain BLOCKED_BY_TYPED_DOCUMENT_CONTRACT;
metadata/version presence is not a valid Word/NAS binary. No placeholder DOCX,
path/template inference, original binary/VBA execution, API/schema/RBAC/storage
change, production operation or QĐKT renderer/legal issuance activation.
PR206 stays OPEN/DRAFT, Issues74/144 OPEN. Next: backend Issue230 adjudication,
then authorized readback/reload integration and remaining transition-intent/
typed-document acceptance, each with its own proven owner and scope.

## Inspection/Approval integration and session lifecycle — v1.4, 2026-10-31

Starting fetched main `09ebb20d6de60b9452c990a5276876cf5e604065` includes
PR231 and backend PR232. The latter makes null tokens create-only for Plan and
Outcome, with Case/stage locks; the frontend does not emulate that rule. During
this pass PR233 advanced main to `35771fe33b99ef654b1bfb9483d838aedf36a1ce`;
its isolated PostgreSQL CaseAssessment test was audited and preserved unchanged.
Issue230 remains backend-owned; this report does not close it or generalize its
contract to other stages. PR235 is a separate backend test workstream.

### Proven frontend defects and corrections

Last-correct: App already checks the existing 30-second OIDC validity margin
when accepting/loading session state, and credential changes invalidate access
ownership. First-incorrect: an idle session never changes that state, so an open
Inspection/Approval editor and its pending completion survive expiry. App now
schedules validity rechecks and rechecks on window focus/visible resume, using
the same predicate/margin. Cleanup invalidates old callbacks/listeners on refresh
and unmount. Expiry clears the session and advances the existing access owner;
late Plan/approval completions cannot start old-owner readback. This is client
lifecycle containment, not a replacement for server authentication or token
refresh. Google GIS may supply another credential; no refresh token or silent
refresh protocol has been invented.

Confirmed baseline RED: missing expiry timer and retained pending input after
expired-window focus (2 failures). Final regressions cover timer, focus,
visibility during approval completion, refreshed-session callback isolation and
unmount cleanup. An earlier diagnostic used the wrong tab's text as its wait
boundary; it is not defect evidence. Tests use observed scheduling callbacks and
a controlled clock without increasing timeouts or changing business assertions.

The final-evaluation action also inherited a fixed 26px button height and a
nonwrapping, shrinking flex row. Browser Range measurements showed text bottom
outside the button at 320/360/390px despite document width equalling viewport.
Only its named `inspection-final-actions` group now wraps, constrains the input
and lets buttons grow with text. Desktop button height remains26px. At all five
widths320/360/390/1366/1920 the label fits and document scrollWidth=clientWidth;
no global hiding rule was added. Native F2/Tab/Shift+Tab/Enter/Escape/select,
Cancel, pending, conflict and Case replacement were exercised in actual Edge
fixtures at1366x768/1920x1080/390x844. This closes the v1.3 narrow final-action
label gap, not all mobile/legacy visual acceptance.

### Acceptance matrix — keep verification layers separate

| Behavior / aggregate | Concrete evidence | Status / remaining dependency |
|---|---|---|
| Plan and Outcome metadata | Real loopback FastAPI HTTP, typed frontend API client and actual editors, committed SQLite, canonical GET and browser reload; stale numeric and create-only-null409 | DISPOSABLE_API_VERIFIED with header_stub; not Google OIDC or PostgreSQL acceptance |
| Ordered periods | Two independently entered ranges persist through canonical GET/reload, with id-free write payloads | DISPOSABLE_API_VERIFIED; no source-owned period semantics changed |
| Team | Actual identity-options GET, canonical profile UUID, committed roster and reload | DISPOSABLE_API_VERIFIED; existing Team409 discard contract unchanged |
| Immutable final evaluation | Actual explicit finalize, canonical GET and reload | DISPOSABLE_API_VERIFIED; backend finalization/readiness remains authoritative |
| Reader denial | Actual server403 in the open Plan editor retains draft; reader final readiness disabled | Local header_stub permission test only, not authenticated A/B identities |
| Failure boundaries | Actual missing-Case404, invalid time/date422, stale409 with one request and retained input; existing owner unit/fixture errors and late responses | UNIT_VERIFIED / FIXTURE_VERIFIED / disposable HTTP by the named scenario; not a blanket fault-injection or network replay claim |
| Approval PCT/CT lifecycle | PCT create/complete, second round, explicit CT parent accepted by real HTTP; persisted rows and structured audit checked read-only in disposable DB | REQUEST_ACCEPTED + AUDIT_VERIFIED only. Canonical workspace GET/reload BLOCKED by backend Issue236 |
| Late completion / navigation | Existing owner fixtures keep per-UUID drafts and A→B→A response isolation; new App tests discard expired-owner Plan/approval follow-ups | UNIT_VERIFIED / FIXTURE_VERIFIED; full-shell authenticated Back/Forward and reload-during-pending remain unverified |
| Persistence audit | Fourteen structured audit events in the local acceptance snapshot, including finalization and approval; Case/parent identities checked in the disposable DB | AUDIT_VERIFIED_DISPOSABLE_SQLITE_ONLY; no external audit/production claim |
| Google OIDC, session refresh and two valid test identities | No active old loopback frontend/tunnel at preflight; native browser tools fail initialization. User confirms writable disposable environment; URL/record scope and account/session details requested | NOT_EXECUTED_AUTHENTICATION_DEPENDENCY. No profile/token/cookie extraction or credential logging |
| VBA/Word/speech | MainForm DataKT(5..9,16), TextForm explicit OK/Cancel, TTVForm structured selection and RecordForm separate PCT/CT source families re-audited statically | Original VBA runtime, native screen reader, Word/NAS and production UAT NOT_EXECUTED; source is not runtime acceptance |

### Backend readback blocker and remaining lifecycle gaps

Issue236: catalog Case workspace projection omits `case_id` in each persisted
approval row although `InspectionApprovalSubmissionRead` requires it. Empty list
GET succeeds; actual PCT POST returns200 and commits the UUID/audit; the next GET
returns500 (`inspection.approval_submissions.0.case_id` missing). Confirmed with
both real browser/API and an independently seeded real-HTTP RED probe. The first
TestClient attempt could not collect because the installed Starlette requires
httpx2; only the subsequent actual-HTTP assertion failure is defect evidence.
No backend source or schema was edited; no client injection/filter/rescue or
mutation-response fallback was added. Do not count Approval readback/reload as
PASS or retry create blindly after this committed-write/readback failure.

The UI pending lock is not HTTP replay idempotency or database uniqueness.
Workflow-tab unmount does not promise draft restoration or exactly-once manual
re-entry; request interruption after server commit and reload while pending still
need authorized acceptance. No such guarantee is inferred from component tests.
Real authenticated environment, sessions and disposable record scope must be
established before that run. No staging was deployed or remote DB touched.

Evidence/scripts/screenshots are local-only under
`.codex/evidence/inspection-approval-integration-20261031/`. Temporary fixture
source was moved out of frontend before the final checks. Existing master,
history, rail, registration, CAPA, certificates and document owners are unchanged.
PCT/CT legal output remains BLOCKED_BY_TYPED_DOCUMENT_CONTRACT. PR206 stays
OPEN/DRAFT at its frozen SHA, Issues74/144 remain OPEN, ready_to_render=False,
legal issuance disabled and Word UAT NOT_EXECUTED. Next priority: backend Issue236
canonical projection repair followed by permitted authenticated persistence,
A/B roles and interruption/re-entry acceptance; do not fabricate parity.

Validation for v1.4: full frontend603PASS/0FAIL/0SKIP in39files; existing
Inspection/Approval/shared keyboard targeted42PASS in each of two runs; four
new session regressions PASS repeatedly. Typecheck/lint/build PASS; existing
>500kB bundle advisory retained. Relevant backend contract suites139PASS.
Issue236's isolated actual-HTTP RED remains an explicit backend handoff, outside
the passing project suite; it was not skipped, fixed downstream or called GREEN.

## Master / Facility / Case lifecycle / History — v1.5, 2026-10-31

Fetched baseline `c3168aac3ee9f2e3516791f8123d5ffd7a7ebccc` contains PR237.
This pass audits FacilityTable, FacilitySummary/FacilityWorkspaceTabs,
FacilityHistoryPane/HistoryTable/PersistedCertificateHistory, CaseLifecycleActions,
CaseApplication/Processing and SearchPage's selection, creation and transition
owners. Legacy MainForm selected-row resolution/InsertNewKtraDB, TaiDKForm's
explicit accepted/canceled return and Module1.ReFilter delegation were read
statically. No Office binary or macro ran. ADR0037 and request-owned commit,
canonical reassessment/line and approved workflow contracts remain authoritative.

### Proven gaps, last-correct / first-incorrect

- **Master reactivation:** roving focus and canonical result_key were already
  correct. SearchPage nevertheless cleared selectedHistoryId whenever that same
  row was activated, discarding the mounted Case draft. Single and repeated-click
  RED plus a real browser double-click RED establish the defect. Settled same-row
  activation now leaves selection, URL and draft unchanged. Pending/failed deep
  links still use the existing explicit-selection escape; different Site/line
  identity still changes context normally. No FacilityTable/layout rewrite.
- **Transition intent:** readiness already supplies opaque action key, typed
  target and Case version. Execute used refreshed action props with an old reason
  (also after a rejected blank-reason attempt). The editor now captures the
  reviewed action/target/version at first input or invocation, retains it on
  failure, and offers local Cancel/review. It requires numeric positive integral
  versions, does not interpret action keys, and still honors current backend
  availability. Immediate in-flight protection prevents pre-render double
  activation; it is not server idempotency. Canonical Case UUID owns its lifetime.
- **Transition completion:** its SearchPage follow-up adopted the current owner
  after await, allowing old A success/409 to start a fourth Case GET after A-B-A.
  Both success and conflict follow-ups now carry the owner captured before POST.
  No transition policy or server locking changed; same-owner409 still performs
  the existing canonical refresh and retains the reviewed intent.
- **Reassessment intent:** the dialog's source formerly followed mutable selected
  history at Submit. It now snapshots selected source UUID/reference, displays it
  read-only, and closes the old intent on Site/line/history replacement. No
  chronology/filename/KHKT inference. Empty history still allows source_case_id
  null when the backend grants creation. An additional commit-level RED found
  activation briefly enabled before the initial history owner was selected;
  action visibility now waits for that client context to settle without changing
  backend permission/readiness policy.
- **Reassessment request:** two submits before the pending render dispatched two
  POSTs. A synchronous, owner-bound flight guard serializes that intent. Success,
  failure and follow-up refresh use the captured owner; old source A completion
  cannot close/error a new A dialog after A-B-A. Isolated guard-removal RED proves
  both cases, with byte-identical source restoration. New-generation manual
  re-entry/network replay remains distinct from duplicate clicks and is not
  claimed exactly-once.
- **Reassessment focus:** the old aria-modal markup lacked a boundary Tab trap.
  A small dialog-lifetime wrapper reuses the unchanged certificate focus hook:
  background inert, Tab/Shift+Tab/programmatic containment, zero-enabled-control
  pending fallback and cleanup. Explicit close restores the trigger after inert
  cleanup. SearchPage retains business state. Source metadata spans one new row;
  existing three context fields/layout remain. Local intent Cancel/source display
  are web concurrency/identity safeguards, not newly inferred VBA fields/actions.

### Acceptance matrix and dimensions

| Surface / dimension | Concrete verification | Limit |
|---|---|---|
| Master UI / interaction | UNIT_VERIFIED and full-App Edge fixture: same canonical row preserves selected history/dossier draft; Arrow/Home/End focus-only; native Enter activates exact line; one Tab entry | User-approved table/rail/two filters/action panel unchanged; no full legacy runtime claim |
| Facility Summary / data | FIXTURE_VERIFIED A/B lines on the same Site and C on another Site, distinct server-projected summary/certificate text, external URL Back/Forward/reload | Summary does not invent certificate UUID/current/coverage policy; multi-certificate server projection remains backend-owned |
| Search / history | FIXTURE_VERIFIED actual held old search after newer response, empty/503 hide old history, canonical history reorder/reload, focus-only keys without GET; existing master/history/persisted-version suites | No chronological identity substitution; business history and audit remain separate evidence |
| Transition workflow / concurrency | UNIT_VERIFIED reviewed numeric token, target replacement,403/409/422/network retention, pending, local Cancel, A-B-A and session expiry; full-App fixture late completion and conflict | No backend optional-version policy change; Issue234 remains separately owned |
| Reassessment workflow / identity | UNIT_VERIFIED explicit source snapshot, initial owner stability, empty source, duplicate submit, replacement, late success/failure, expiry, focus; fixture source/line payload | Backend validates compatible Site/GxP/line and controls permitted copying; no new mutation API |
| Persistence | DISPOSABLE_API_VERIFIED: unchanged FastAPI, actual full frontend/browser and typed API, explicit synthetic SQLite/header_stub. Create Case -> canonical GET -> URL-selected UUID -> reload; user enters dossier; numeric transition -> GET/reload | Not Google OIDC or PostgreSQL acceptance. Seeded source has no populated scope-copy evidence; approved scope-copy coverage stays in backend contracts |
| Authorization / negative writes | Actual server reader403, source-line mismatch422, stale transition409 and duplicate creation409; read-only DB check finds exactly one new Case and three structured audit events | Header_stub roles are local tests, not authenticated A/B identities or production RBAC proof |
| Documents / legacy runtime | Existing QDKT/PCT/CT/CAPA typed-output boundaries preserved | Word/NAS/speech/VBA runtime/production UAT NOT_EXECUTED; metadata/history is not legal binary evidence |

Browser fixture viewports1366x768/1920x1080/390x844 have document/client widths
1366/1366,1920/1920,390/390. Each final full-shell scenario records68 requests,
four explicit POST attempts (three transition intents and one create), zero
focus-only GET/mutation and no duplicate form POST. Existing internal selections
use URL REPLACE; Back/Forward evidence deliberately uses external URL entries.
An initial browser expectation treated internal REPLACE as a pushed entry; that
setup failure is not a product defect and no navigation contract was changed.
The dialog/source metadata fits at each viewport, with pending/error keyboard
and explicit Escape/Cancel restoration. Synthetic screenshots and scripts stay
outside Git in `.codex/evidence/master-lifecycle-history-20261031/`.

Real disposable acceptance has27 browser API requests, one UI create and one UI
transition. Original three closed synthetic Cases remain; one new Case and three
structured audit events persist. Rejected commands add no Case. The new dossier
is user-entered, not copied from source or KHKT. This is REQUEST_ACCEPTED +
CANONICAL_READBACK_VERIFIED + RELOAD_PERSISTENCE_VERIFIED and a separate
AUDIT_VERIFIED_DISPOSABLE_SQLITE_ONLY snapshot, not authenticated acceptance.

### Remaining gates

At this checkpoint Issue236 is OPEN and backend PR238 is OPEN (catalog approval
case_id projection repair). Neither backend branch is imported or edited here;
Approval GET/reload remains BLOCKED until a merged source is available and
retested. PR235 PostgreSQL tests remain independent. Google OIDC A/B acceptance,
native screen reader and original legacy runtime remain NOT_EXECUTED. No deploy,
remote rehearsal/production/NAS/GCS write, schema/API/RBAC/storage change or
original binary modification. PR206 remains frozen OPEN/DRAFT, Issues74/144 OPEN,
ready_to_render=False and legal issuance disabled. Overall modules remain
IMPLEMENTED_PARTIAL; next is canonical Approval readback on merged backend and
permitted authenticated lifecycle acceptance, then separately proven UI gaps.

The new local transition-Cancel control is also measured with browser Range/DOM
bounds: the inherited fixed-height/nowrap action row initially failed containment.
Scoped CaseLifecycleActions wrapping/content height now contains every label at
all three viewports. No global overflow hiding, business mutation or master layout
change. This is presentation verification of the web intent controls, not a VBA
runtime geometry assertion.

Validation for v1.5: final full frontend631PASS/0FAIL/0SKIP in39files
(full-precommit.log,250.13s), no final act/unhandled warnings. Component/master/
history/persisted-version targeted51PASS twice; parent/session22PASS twice.
Typecheck/lint/buildPASS; existing large-bundle advisory retained. Relevant
backend contracts108PASS. No timeout, assertion or test skip was relaxed.
Several earlier local runs had varying unrelated timeouts, one worker RPC error
and unusually extended wall-clock durations; none is counted as PASS. Intermediate
625/629 clean runs are not substituted for the final631-run evidence. The
initial-history activation race was separately proven with a deterministic
commit-level RED and fixed at the owner, not by changing old test assertions.

## v1.6 — GxP/ĐĐK certificate intent and completion ownership

Starting main `9f26223280b55295420f3997022e18ed5c1ae27e`; approved main drift
`f1002326324c12680f099f241b3a4b734d02fb41` adds Approval `case_id` projection
and its regression only. It was audited and fast-forwarded, without taking any
unmerged backend branch. Certificate issue, latest-version update and promotion
remain independent actions with server-owned readiness, UUIDs and numeric tokens.

Last-correct: a same-certificate refresh retains the editor's draft and original
expected_version. First-incorrect: a selection UUID comparison alone treats the
new A after A → B → A as the previous A. Hidden draft state revived, an old
completion could close a newly opened editor, and old mutation readback could
overwrite current detail. Workspace owners now discard departed edit intents;
identity-checked close callbacks cannot close their successor. SearchPage binds
readback/promotion feedback to committed selection generations as well as context
and certificate UUID. Read/source/history/document owners are unchanged.

Two activations before React's pending render previously bypassed state-only
guards. Synchronous guards now cover the three certificate dialogs and the two
promotion handlers. Case issuance captures its Case/type/basis intent; changed
readiness blocks save without replacing the draft. ĐĐK issue also observes live
readiness. Successful PUT/POST followed by GET409 is distinguished from a rejected
mutation409: the canonical GET is not replayed as conflict recovery. Existing
mutation409 refresh, draft/token retention, 403/422 errors and no automatic write
retry remain intact. A failed GET is not canonical success.

Static legacy evidence: MainForm Replace_CC/UpdateCCGPsItem_Row and
CapNhat_DDK/GetSetDataDDKDs/ChonDDK_Thaythe use explicit selected row/Site references;
SelectCC/SelectDDK and RecordForm remain evidence, not authority to infer current
identity, normalize historical exceptions, fabricate source groups or generate
legal binaries. No legacy macro execution or original binary changes.

FIXTURE_VERIFIED full React browser at1366×768,1920×1080,390×844: respectively
client/scroll widths1366/1366,1920/1920,390/390; focus-only navigation0requests.
Same-number UUID selection, old readback after A-B-A, new draft retention,
409/no retry, readonly historical snapshots and modal keyboard containment were
exercised. Programmatic row activation models external context replacement during
pending; it does not claim background mouse interaction through a modal.

DISPOSABLE_API_VERIFIED: actual FastAPI HTTP/SQLite plus actual React/typed API
browser. Synthetic two-Site/three-line data: issue3GMP +1ĐĐK, update and promote
each, canonical GET/history, browser update/reload, server reader403, Case/Site422,
stale409, duplicate GMP409 and cross-Site ĐĐK basis409. Eight API audit events plus
two browser updates; numeric tokens and canonical basis UUID retained. Issue234's
HTTP missing/null promotion token is rejected422 at this baseline; this does not
prove PostgreSQL simultaneous promotion safety or close the backend audit.

Evidence: `.codex/evidence/certificate-integrity-20261101/` outside Git. OIDC A/B,
PostgreSQL concurrent writers, original VBA runtime, native screen reader,
Word/signed output, NAS/GCS and production UAT remain NOT_EXECUTED. Metadata is
not a verified binary. Modules10/11 stay IMPLEMENTED_PARTIAL; QĐKT PR206,
Issues74/144, ready_to_render=False and legal-output barriers are unchanged.

Validation v1.6: full frontend648PASS/0FAIL/0SKIP,39files; no final act/unhandled
warnings. Targeted owners/history/source/metadata126PASS twice; SearchPage
acceptance12PASS twice. Typecheck/lint/buildPASS (existing bundle advisory);
backend contracts20PASS on mainf100232.28 actual HTTP checks match contract;
two actual browser writes/reloads and ten structured audit events verified.
Earlier full diagnostic640PASS/4FAIL is retained: one5s timeout, two globally
ambiguous list/detail text selectors and one focus assertion waiting for callback
entry instead of dialog closure. Tests now query the actual list/stepper owner
and await closure before focus; no timeout increase, assertion removal or skip.

## v1.7 — Cross-workflow disposable acceptance and Approval recovery

Starting main `22b7aa29a48b5b9fb0f571aace5488c49c8cabf0`. Approved drift
`13670d957d617cfa5acdad6299f7878b35dafaea` (PR245) adds a Site lock and candidate
refresh for GMP promotion plus a PostgreSQL race regression. It was audited and
fast-forwarded; this frontend work does not modify that backend owner or PR242.

The serial HTTP acceptance server loaded22b7aa2. Its own fresh SQLite contains
synthetic Sites/ProductionLines and closed source Cases only. Actual HTTP then
creates three new Cases, writes intake/assessment, Plan/Outcome, performs explicit
state transitions, exercises rejected→accepted CAPA rounds, completed PCT→CT
parents and multiple Approval rounds, issues/updates/promotes GMP, GLP and GMPbb,
and creates ĐĐK with three explicit canonical basis UUIDs. All166 HTTP checks
match the observed contract;68 successful commands have68 structured audit events.
Transitions are audit facts, not invented proof of stage completion. Direct DB
readback separately verifies stored dossier/assessment values and that promoting
one GxP type did not clear another type's current flag. No GMP-only prospective
rule is imposed on GLP/GMPbb. Sourcegroup provenance stays unknown when no legacy
identity exists; canonical basis links are not reclassified as Excel sourcegroups.

Actual defects reproduced before fixes:

- Two Approval activations before pending render issued two commands. A local
  state-only pending check was the first incorrect boundary; synchronous guards
  now cover create/complete, without changing permissions or numeric tokens.
- Accepted PCT creation followed by canonical GET503 retained input but permitted
  another POST, creating a second round. A lost POST response is equally
  unverified. SearchPage now owns pending/review state by access generation and
  canonical Case UUID. It survives workflow/facility tab remount and blocks blind
  manual replay; known HTTP403/409/422 handling is preserved. Canonical readback
  failure never becomes success or a fabricated mutation response.
- A component-local recovery barrier disappeared on tab remount. RED covers that
  boundary as well as pending remount; the final owner is SearchPage, exposed by
  a narrow React context. Existing editor inputs/tokens remain editor-owned.
  Drafts stay readable after failure; users can copy them before authoritative
  reload. No draft is persisted to browser storage. Existing tab-unmount loss of
  unsaved inline input is recorded below, not represented as draft persistence.

Acceptance matrix (named scenarios only; no full-parity promotion):

| Boundary/category | Evidence and result | Remaining limit |
| --- | --- | --- |
| Master→Site/Line→Case; Workflow/Data | Actual React search/deep-link and HTTP Case creation; UUIDs retained through type/context navigation | Not imported-data reconciliation |
| Intake/Assessment→Inspection; Persistence | Actual writes, canonical workspace and stored values; Plan/Outcome owners remain distinct from assessment | Original VBA runtime not executed |
| Inspection→CAPA; Workflow | Two real rounds: first rejected, second accepted; transition denied while unaccepted; assessor bound to server AppUser | New round after accepted is correctly409, not a parity defect |
| Inspection→PCT/CT; Persistence | Create/complete, fresh GET/reload, multiple rounds, explicit completed PCT parent, stale409, viewer403, wrong-Case parent422 | Legal PCT/CT output is separate |
| Case→GxP→ĐĐK; Data | Real GMP/GLP/GMPbb issue/update/promote/readiness/versions and three-basis ĐĐK | No original signed binary or legal output claim |
| Certificate source/history/successor; Workflow/Data | Canonical Case/Line source and persisted-history reads; unknown legacy provenance remains unknown | Successor issuance scenario NOT_EXECUTED; do not infer replacement links |
| Audit/history; Persistence/UI | Structured DB audit; actual Case/history URL, cross-module and Back/Forward navigation | No unsupported global audit UI added |
| Authorization | Real header_stub viewer403 and foreign CT parent422; synthetic session expiry/role/logout fixture | NOT_EXECUTED_AUTH_DEPENDENCY for Google OIDC A/B; relationship checks are not tenant-authorization proof |
| Error recovery; Runtime/UI | Actual committed writes with injected GET failure/lost response; pending/remount/reload and no replay | NOT_EXECUTED for real network infrastructure failures |
| Legal documents; Document output | Existing readiness barriers retained; no rendering or storage fallback | PR206/Issues74/144, ready_to_render=False unchanged; Word/NAS acceptance NOT_EXECUTED |

Full React/actual HTTP browser at1366×768,1920×1080,390×844: client=scroll at
1366/1920/390; no new overflow or clipped Approval buttons. Verified PCT/CT
reloads, expected_version, parent UUID, six workflow steps, Facility GxP/ĐĐK
round-trip, readonly history/source state, modal Tab/ShiftTab/Escape and focus
return, history identity, Back/Forward and focus-only0requests. Actual committed
write/lost-response and GET-outage probes keep one command per intent, including
tab remount. A held real response also keeps the Case's Approval busy through
remount until canonical readback. Synthetic-token browser scenarios exercise
A→B→A, late response, expiry, role change and logout; they are explicitly
SYNTHETIC_SESSION_FIXTURE, never AUTHENTICATED_VERIFIED.

Remaining gaps: EVIDENCE_MISSING for desired legacy unsaved inline-draft behavior
on workflow tab unmount (current local inputs reset, with no mutation); original
VBA runtime/pixel acceptance; native speech; Google A/B credentials and permitted
synthetic records; successor scenario; Word/PCT/CT/CAPA typed output and binary
storage. No new UI module, template, NAS path, state or business permission map.
Evidence and failed diagnostics remain outside Git in
`.codex/evidence/cross-workflow-acceptance-20261101/`.

Static MainForm DataKT26/27 map edPT_PCT/edPT_CT, and DataKT21–24 map legacy
CAPA reference/date controls. Those scalar fields do not establish a two-round
web limit or authority to flatten canonical PCT/CT/CAPA histories. Original
workbook/add-in/Word binaries were not modified or executed.

Final validation: frontend656PASS/0FAIL/0SKIP in39files, without act/unhandled
warnings; component/Inspection/CAPA regression65PASS twice, parent Approval/
ownership regression9PASS twice. Typecheck/lint/buildPASS; backend contracts
110PASS after audited main13670d9. The existing bundle-size advisory remains.
Earlier intentional REDs and a targeted unrelated Plan5s timeout are retained,
not counted as PASS; no timeout/assertion/skip changes. Final disposable DB has
125 structured audit events including controlled RED and browser probes; initial
serial acceptance has68 events for68 successful commands. No remote DB/NAS/GCS.


## v1.8 — Active Case draft lifetime and OIDC acceptance readiness

Starting main73dcf5a; audited/fast-forwarded main8b171ae (PR248 adds only
PostgreSQL inspection race tests). Runtime backend behavior was not changed.
The last correct boundary was editing a field while its component remained
mounted. The first incorrect boundary was workflow/Facility tab unmount: values,
edit intent and the captured version were discarded. A second defect existed in
Application/Assessment post-write GET failure: mutation response fields were
merged into an old workspace and treated as confirmation.

`CaseDraftSession` now belongs to the active access/Site/GxP/ProductionLine/Case
context at SearchPage. It stores only this active Case's editor state in memory;
there is no global multi-Case history cache and no draft browser storage. Actual
panes still unmount; no hidden duplicate document workspace or extra identity
lookup is introduced. Each feature retains ownership of its input, reset rules,
readiness, captured token and command. CAPA operation generation survives a tab
unmount but still invalidates on cycle changes. Approval's PR247 pending/review
coordinator remains authoritative and unchanged.

| Editor / state owner | Same-Case tabs | Case/access/line change, logout, expiry, full reload | Cancel / fresh edit | Pending / conflict / canonical readback |
| --- | --- | --- | --- | --- |
| Application + Assessment | Values, editing field, original token and errors retained | Discard session; old setters cannot publish | Discard values; reopen captures current canonical token | Pending retained;403/409/422 retain existing errors/input; unknown write/failed canonical GET blocks Save through remount and Cancel until authoritative reload |
| Inspection Plan + Outcome | Draft/edit field/token/pending retained | Discard | Existing Cancel resets; explicit reopen reviews new token | Existing readiness/errors/concurrency rules unchanged; no fabricated readback |
| Period replacement + Team | Structured segments/members, options, token and pending retained | Discard | Existing Cancel retained | No second options GET on remount; source-owned/unavailable readiness still blocks writes |
| Final evaluation | Input and readiness token captured on first change retained | Discard | Existing explicit Cancel resets token | Pending and original token retained; readiness remains backend-owned |
| CAPA | Only selected cycle editor/command draft retained, with its operation generation | Discard; changing cycle also resets existing cycle state, never a per-cycle cache | Existing reset semantics retained | Original cycle token/create Case token retained; create/update/submit/assess409 policies unchanged; no implicit replay |
| Approval create + completion UUID | Draft/error and completion token retained | Draft discarded; PR247 write/review coordinator has its own lifetime | Existing Cancel for completion retained | PR247 duplicate/pending/accepted-unverified/unknown-commit barrier unchanged; canonical GET only |
| Case lifecycle | Reason, reviewed action/token snapshot and pending guard retained | Discard | Existing Cancel clears reviewed intent | Existing readiness/409 behavior unchanged |
| GxP/ĐĐK/Case issuance dialogs | Existing owner/lifetime unchanged; no modal cache | Existing identity invalidation discards; PR244 A-B-A protections retained | Existing Cancel/close discards and restores focus | Existing certificate pending/recovery/conflict/version policies retained |
| Reassessment | Existing SearchPage intent/dialog owner unchanged | Existing invalidation applies | Existing Cancel applies | Existing pending/late-response contract retained |

State interpretation: CLEAN hydrates canonical data; DIRTY keeps the reviewed
version; PENDING cannot be restarted on tab remount; CONFLICT never silently
upgrades that token. READ_ONLY/REVOKED uses existing permission/readiness owners,
not a client permission map. Application/Assessment ACCEPTED_UNVERIFIED now
keeps readable draft and blocks replay, as does the existing Approval owner.
Other command-specific recovery rules are preserved rather than generalized.

Legacy TextForm.GetText returns trimmed input only after OK; Cancel sets Canceled
and hides the form. This establishes commit/cancel, not cross-tab retention.
Same-Case in-memory preservation is an explicit browser safety improvement under
this task, not proven Excel runtime parity. Retention across Case/certificate
switches, full reload or authenticated account changes remains
BLOCKED_BY_BUSINESS_DECISION; no persistence was added for those boundaries.

Google Issue8 remains OPEN. No two authorized Google A/B accounts and current
approved synthetic URL were supplied. AUTHENTICATED_OIDC_VERIFIED=NOT_EXECUTED /
BLOCKED_BY_ENVIRONMENT. Synthetic session fixtures and real disposable
FastAPI/SQLite/header_stub are separate evidence classes, never Google acceptance.
No OAuth configuration/account provisioning/deployment or remote writes occurred.
Native screen reader, original VBA execution, signed binary/Word/NAS output and
production UAT remain NOT_EXECUTED. PR206/Issues74/144 and ready_to_render=False
remain unchanged. No module is promoted to fully IMPLEMENTED_VERIFIED.

Evidence: `.codex/evidence/draft-lifecycle-20261101/` (outside Git): controlled
RED, scoped regression, canonical readback/409/pending browser probes, disposable
HTTP acceptance and synthetic session expiry/A-B-A/role403/logout. Final command
counts and CI are recorded in the completion report after validation.

CAPA readback ownership also had a proven A-B-A race: a replaced command adopted
its readback owner only after await and started a fourth GET in the new A session
(RED expected3, received4). All four CAPA callbacks now capture the Case operation
owner before the command. GREEN and browser fixtures prove no late Case GET or
draft replacement. Back/Forward across the dashboard unmounts SearchPage and
starts a clean draft session on return; preserving drafts across that route is
also BLOCKED_BY_BUSINESS_DECISION, distinct from same-Case workspace tab retention.

Final local validation:676PASS/0FAIL/0SKIP in39 frontend files, no act/unhandled
warnings; parent regression24PASS twice and component87PASS twice. Typecheck,
lint and production buildPASS (existing bundle-size advisory). Relevant backend
contracts136PASS (40 lifecycle/Approval/period/team +94 workflow mutations +2 audited main source-boundary tests).
The first670PASS diagnostic run had pending test-act warnings; async Router
work is now awaited, without changing assertions/timeouts or suppressing warnings.
Disposable API has95 final audit events:68 initial commands plus27 successful
browser/external-writer commands; nine browser409s add no audit writes. Browser
composition events are synthetic IME probes, not a native IME certification.

Self-review also reproduced speculative React navigation closing a still-visible
A session before suspended B committed. red-suspended-owner.log proves typing in
A was ignored. Session retirement now occurs in layout cleanup at actual commit/
unmount; the committed editor remains writable while B is suspended. No draft is
published into B. The additional regression passes without changing timeouts.
Main81df311 drift was audited: PR249 adds only a GMP evidence document and two
fail-closed source-boundary tests; no runtime or frontend change. An existing
legacy-unlinked test waited for an API call, then clicked an uncommitted tab; the
failed full-run diagnostic is retained. It now awaits the actual tab, preserving
all UUID assertions. No production fallback or timing workaround was added.

Keyboard focus-path evidence at all three widths: F2 opens the editor, Tab
reaches the input in one step, keyboard typing/Escape issues0writes. Existing
inline F2/Escape leaves activeElement=BODY on DOM replacement; automatic
input/trigger focus restoration is NOT claimed. Legacy automatic-return policy
is EVIDENCE_MISSING; this separate affordance is recorded, not changed by draft
lifetime work. Certificate modal focus behavior remains covered by existing tests.
