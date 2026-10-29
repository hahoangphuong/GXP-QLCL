# Legacy VBA/Excel business parity status

Version: **1.2 — 2026-10-29**. Audit baseline main
`5062b5a3f50f06d8b8348d95199b0bbe5e8f395c`. Scope: available workbook/add-in
source, approved contracts, current frontend/backend source, regression and
isolated browser fixtures. This is not authenticated staging, production UAT,
Word acceptance, screen-reader verification or a migration completeness certificate.

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
is implemented. Server readiness still owns permission and status eligibility.

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
