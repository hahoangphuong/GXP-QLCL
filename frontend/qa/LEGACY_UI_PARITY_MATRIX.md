# LEGACY_UI_PARITY_MATRIX — Issue #1

## Inline editor business-action boundaries — 2026-10-29

Baseline main `5062b5a3f50f06d8b8348d95199b0bbe5e8f395c`. The versioned
cross-module business inventory is `docs/LEGACY_VBA_EXCEL_PARITY_STATUS.md`;
UI, workflow, data, persistence, output and authorization are classified separately.
MainForm.GetSetData/TextForm.GetText establish distinct OK/Cancel behavior.
EditableDetailValue previously intercepted bubbled Enter on native buttons/selects,
cancelled pending work through Escape, and allowed another field to activate while
its aggregate was pending. The shared owner now preserves native control/IME
semantics and the pending boundary; no mutation payload or backend rule changed.
Application drafts also snapshot expected_version at edit start; refresh cannot
silently upgrade an old draft to the new token. Null (new row) remains null until
explicit Cancel/reopen, preserving the existing backend conflict contract.
Post-merge audit correction (Issue #222): null is an optional server version check,
not create-only. When refresh proves a previously absent application now exists,
the editor retains the draft and requires Cancel/reopen before submitting. No fake
409 or request is generated; unobserved creation races remain a backend gap.
Regression is RED-before-GREEN for both shared callbacks and registration draft409.
Edge fixtures at1366x768,1920x1080,390x844 show equal page/client widths, zero save
calls from native Cancel Enter, one explicit Save call with original token, retained
409 draft and no API requests. Evidence is outside Git under
`.codex/evidence/legacy-business-parity-20261029/`. FIXTURE_VERIFIED only; no live
authentication, storage, Word or screen-reader acceptance is claimed. Master/history,
rail, action panel, two filters and all approved layout exceptions remain unchanged.

Direction: the user decision dated 2026-10-10 supersedes earlier aesthetic
recommendations in UI_REDESIGN_VBA_REFERENCE and PHASE12. Preserve legacy UI where
evidenced. Baseline: `50576b0b383161e26e27b6cdc4a1a469aff1ae17`; work branch:
`codex/legacy-ui-parity-20261010`. This delivery is partial; it does not close #1.

## QĐKT readiness provenance closure — 2026-10-26

Baseline: `dc935f0d8a0ebbd770055796d54fb684f97ceba0`. The Case QĐKT panel
continues to use the backend-owned, read-only readiness and current-team routes.
It now exposes the returned opaque `decision_source_id` and
`registered_site_id` when present, labels the response as draft preparation
rather than an issued decision, and provides an explicit retry only after a
readiness failure. Case changes abort the superseded request; a late Case A
response cannot replace Case B. No create/issue action, draft snapshot,
official number/date, or confirmed issued-team state is inferred.

| Capability | Evidence/status |
| --- | --- |
| Readiness blockers and current Case team | `BACKEND_CONTRACT_VERIFIED`, read-only; merged baseline behavior retained. |
| Decision-source and registered-Site provenance | `UNIT_VERIFIED`; opaque canonical identifiers are displayed without relinking or latest-record inference. |
| Explicit retry after readiness failure | `UNIT_VERIFIED`; no automatic retry, mutation, or generic renderer fallback. |
| Late response after Case change | `UNIT_VERIFIED`; superseded AbortSignal ownership remains fail-closed. |
| Responsive disclosure | `FIXTURE_VERIFIED` at 1366×768, 1920×1080 and 390×844; document scroll width equaled client width at each viewport, and mobile Enter activation issued only the two read-only GETs. |
| QĐKT draft DOCX creation | `BLOCKED_BY_BACKEND`; typed render contract remains unavailable. |
| Immutable proposed-team snapshot and issued QĐKT transaction | `BLOCKED_BY_BACKEND`; persistence components are not treated as public APIs. |
| Legacy runtime geometry for a QĐKT-specific panel | `EVIDENCE_MISSING`; the canonical web presentation is retained rather than guessed. |
| Authenticated real-backend browser verification | `UAT_PENDING`; fixture/unit evidence is not reported as integration evidence. |
| Narrator/NVDA speech verification | `DEFERRED_BY_USER_PRIORITY`. |

## Frontend business-function audit and typed KHKT integration — 2026-10-22

Baseline: `af4abf6df7e3f11ddeb0c120924f082f22645096`. The audit compares the
active MainForm/RecordForm/ExtRecordForm sources, the workbook/add-in maps,
approved domain/storage decisions, current React owners and the API schema on
that exact `main`. `NATIVE_SPEECH_EVIDENCE_MISSING` is **DEFERRED — NOT REQUIRED
FOR CURRENT DEVELOPMENT** by the user's decision; it is not a PASS claim and is
not an acceptance blocker for this business slice.

| Priority / business capability | Classification before this slice | Evidence and exact remaining boundary |
| --- | --- | --- |
| 1. Case Kế hoạch kiểm tra: create from the typed document row | `PARTIAL` | RecordForm case 3 and the document registry prove the command. Backend now advertises an authorized Case-owned POST target and canonical-input readiness, but the frontend still called the generic renderer with client-selected family/GxP/storage/output values. This slice changes it to `IMPLEMENTED` through the advertised typed target. |
| 2. Hồ sơ registration and dossier assessment editing | `IMPLEMENTED` | CaseApplication and CaseAssessment have distinct owners, optimistic versions, readiness/RBAC error handling and legacy-supported layout. Folder lookup remains fail-closed. |
| 3. Inspection plan, periods, team, outcome, final evaluation and approval chain | `IMPLEMENTED` | Canonical editors/actions exist with Case/team/outcome tokens. Legacy composite strings remain projections rather than mutation identities. |
| 4. Quyết định kiểm tra, biên bản thẩm định/kiểm tra creation | `BLOCKED_BY_BACKEND` | Legacy families and placement are proven; contextual rows exist, but typed input/render contracts remain `BUSINESS_INPUT_CONTRACT_MISSING`. |
| 5. CAPA cycles and assessment | `PARTIAL` | Multi-cycle create/update/submit/assess is implemented. CAPA 1/2 document creation remains `BLOCKED_BY_BACKEND`; no typed create contract is advertised. |
| 6. Xử lý tiếp and approval documents | `PARTIAL` | Canonical timeline plus PCT/CT submission workflows are implemented. Legacy risk/PCT/CT/certificate-decision document generation remains `BLOCKED_BY_BACKEND`. |
| 7. GxP certificate issue/edit/promote, scope and persisted history | `IMPLEMENTED` | Case and Facility owners, version UUIDs, scopes, readiness and concurrency are present. Binary/legal attestation remains separate from metadata. |
| 8. ĐĐK issue/edit/promote, basis links, source provenance and persisted history | `PARTIAL` | Canonical Facility/Case views and mutations are implemented. The five legacy DDKD generated-document slots and preparatory forms remain `BLOCKED_BY_BACKEND`. |
| 9. Facility search, exact line identity, history and change workflow | `IMPLEMENTED` | Search/history/deep-link and ChangeRequest create/detail/approval/successor flows are canonical. Full persisted FilterForm queries are omitted by explicit user decision and unsupported API semantics. |
| 10. RecordForm/ExtRecordForm auxiliary generation and direct Explorer/Word editing | `BLOCKED_BY_BACKEND` | Static VBA proves the commands, but most typed payload/render contracts and a frontend-safe desktop-open contract do not exist. Runtime picker geometry/states are also `EVIDENCE_MISSING`. |

Last-correct for priority 1 was the contextual row's canonical Case/family and
server-owned availability. First-incorrect was `SearchPage.handleCreateDocument`:
it discarded `create_endpoint`/`create_http_method` and posted client-composed
business/storage parameters to `/documents/render-template-docx`. The frontend
now accepts only the exact Case endpoint advertised for the selected Case, POST,
`CANONICAL_INPUT_READY`, matching family and parent identity. It sends the typed
empty request body, so Case, GxP, template, output name and storage destination
remain backend-owned. Mismatched or incomplete action metadata fails before a
request. Pending deduplication and 403/409/422/no-retry behavior remain in the
existing contextual-document owner; successful creation refreshes the selected
Case and Facility workspaces exactly as before.

### KHKT runtime readiness consistency — 2026-10-22

Current-main integration baseline `97ba11265751441c661a8e1085ec61a237696880`
retains the Case-owned KHKT GET and POST contracts. Before this extension the
read-only runtime readiness GET was represented by the API client but unused by
the UI, so a create button could remain enabled while the template binary,
inspection folder or an already-current KHKT made the attempted render known to
be blocked.

`SearchPage` now owns one cancellable readiness probe for the exact selected
Case and advertised KHKT contract. The document row distinguishes loading,
ready, blocked and transport/error states, keeps create disabled until the
matching response is ready, explains backend blocker codes and retries only on
an explicit user action. Request sequence plus AbortSignal reject Case A → B → A
and reversed completions. Case/family/GxP response identity and the advertised
Case endpoint/method are checked before enabling create. The typed POST with `{}`
remains authoritative at render time and is never retried or replaced by the
generic renderer. QĐKT and all other families without an advertised typed create
contract remain blocked.

Real Synology binary generation, authenticated staging and production UAT remain
unverified in this frontend slice.

## Evidence closure and staging-readiness audit — 2026-10-13

### GxP / ĐĐK document metadata ownership — 2026-10-17

Baseline `1b769563d64fa007a54cc7aa8604a1af7c59bca7`; local, remote and
OPEN/DRAFT PR #3 matched before the slice. The read contract was audited from
backend PR #7 commit `ffbef6217bbd7dfe98a91892d1517bef96be74c6` without merging or
cherry-picking it. The two owners remain distinct: GxP uses
`/certificates/{certificate_id}/document-metadata`; ĐĐK uses
`/business-eligibility-certificates/{business_eligibility_certificate_id}/document-metadata`.

Last-correct was each Facility certificate's canonical selected UUID and detail.
First-incorrect was the absence of a frontend read owner and presentation for the
new metadata inventory. `SearchPage` now supplies one cancellable read per active
certificate tab. Its key includes the existing access-bound Site/line context,
certificate kind and canonical owner UUID. Selection, Site, tab or access changes
close the old result before passive cleanup; abort and operation ownership reject
late success and 401/403/404/409. Focus-only renders do not read again.

The compact read-only group appears inside the existing Facility detail pane. It
shows only family/type, title and registered variant/version/current counts. Empty
metadata explicitly does not prove that an original is absent. Registered metadata
is labelled unverified; no filename, locator, checksum, binary URL, download action,
signature claim or linkage inferred from Case/Site/Excel is rendered. Mismatched
owner kind/UUID, duplicate document UUID, invalid counts, impossible empty/status
combinations or a response claiming binary/signature verification fail closed.
Existing certificate actions, drafts, optimistic versions, source evidence and
persisted histories remain separate owners.

The runtime images establish legacy certificate details and document commands but
do not establish an exact metadata-inventory location, table geometry or empty/error
wording. Those presentation details remain `EVIDENCE_MISSING`; this is a minimal
web-contract presentation rather than claimed pixel parity. The currently deployed
VM does not expose these endpoints, so its expected 404 is not frontend evidence.
Validation for this slice uses the exact backend contract commit or controlled
frontend fixtures. Live authenticated integration remains blocked by the previously
recorded unauthorized local OAuth origin (0 authenticated success / 0 denied-role
success / 7 blocked scenarios); it is not rerun or reported as PASS.

Regression first failed on the untouched checkpoint because the metadata owner and
component did not exist. Final targeted runs pass 93/93 across the metadata, both
Facility certificate workspaces and API routing; the full frontend suite passes
489/489. Typecheck, lint and production build pass. The exact backend SHA passes
its disposable SQLite metadata inventory tests 4/4. Controlled browser fixtures
cover both owner kinds at 1920×1080, 1366×768, 390×844 and 375×812: document/client
widths are respectively 1920/1920, 1366/1366, 390/390 and 375/375. A's pending
read aborts before B publishes; focus/Tab causes zero extra reads; Site/access and
GxP↔ĐĐK changes each cause one new read; logout removes the metadata. The fixtures
contain no links or binary/download controls. Evidence is stored outside Git under
`.codex/evidence/certificate-document-metadata/`.

### Persisted GxP / ĐĐK version history — 2026-10-14

Baseline `2f7c46eede547e8b711d782022fd5559d219a8c0`; local/remote/OPEN-DRAFT
PR #3 matched. Existing untracked script remains untouched. Read backend PR #7
SHA `97182e58c3a673938d1b263c7eeaab41d28147b4` docs/Pydantic and live OpenAPI:
GxpCertificateVersionHistoryRead, BusinessEligibilityVersionHistoryRead and
both exact aggregate `/versions` paths. Live app/status reports that SHA,
Google OIDC and `gxp_legacy_rehearsal`; readyz confirms schema `20261012_0023`.
No backend commits merged/cherry-picked and no runtime configuration changed.

Both APIs: `BACKEND_API_DEPLOYED`. Facility UI: `FRONTEND_FIXTURE_VERIFIED`.
Original source endpoint remains `PROVENANCE_API_DEPLOYED`, unchanged.
Authenticated browser remains `REAL_AUTHENTICATED_UI_PENDING`: the previously
rejected local OAuth origin has no newly verified permitted dev origin. Live
OpenAPI/readiness is not an authenticated business-response test.

Last-correct: aggregate/current detail owners and mutations. First-incorrect:
no separate persisted snapshot presentation/client. Native collapsible read-only
history now follows current detail, using cyan legacy fields without changing
runtime image 7/9 current list/detail placement. MainForm DataCC2/DataDDK2 and
those images establish current fields, not a persisted-version picker; exact
legacy history-picker appearance remains `EVIDENCE_MISSING`. New snapshot region
is explicitly authorized by this task, not a claimed exact legacy form clone.

SearchPage keeps aggregate selection; its cancellable history read owns only
context/UUID/access/revision and local snapshot choice. Old requests abort and
late success/error cannot publish under a replacement owner. Settled reads and
snapshot choice survive tab round-trips. Current detail revision changes cause
fresh history, while focus-only navigation causes none. No bulk list history
fetch, retry, current-detail fallback or write action is added.

GxP: exact version UUID, version_no, row_version, version/latest-aggregate flags
remain separate. Each snapshot renders its own scope UUID/text/language/order
without copying current scopes; null lifecycle stays unconfirmed despite dates.
DDK: maximum-persisted-version selection, stored professional/license fields,
scalar issuance prose and exact-version FK rows stay distinct. FK presence is
not validity/approval; source tokens are excluded and original provenance remains
separate. Zero versions means an existing aggregate has no saved version; one
means exactly “1 phiên bản đã lưu”; multiple versions exist in synthetic fixtures
only. User-supplied rehearsal counts are 1,601 GxP versions, 1,564 scopes, 780 DDK
versions, zero multiversion DDK/recorded canonical links, 3,120 source groups and
861 tokens. This slice does not claim authenticated verification of these rows.

Owner presentation regression fails against the untouched checkpoint component
at the absent history caption, then passes. Regression covers 0/1/N, independent
historical scopes/FKs, null lifecycle, scalar prose, 401/403/404/409/server errors,
A→B→A ownership, abort, access/canonical identity, tab reuse, snapshot selection,
current-detail/draft isolation and original mutation token. No timeout changed.

Browser fixture: both Facility tabs at 1920×1080, 1366×768, 390×844, 375×812.
client/scroll: 1920/1920, 1366/1366, 375/375, 360/360 respectively (mobile vertical
scrollbar 15px). DDK A pending→B stays B after late A; identical numbers keep
separate UUIDs. GxP old scope and DDK old empty FK snapshot remain independent.
Enter toggles/activates, native select and Tab/Shift+Tab work; Home/End only move
list focus. Tab round-trips retain snapshot/current selection and canonical
line/history URL. Version counters remain unchanged across settled tab/focus
round-trips. No browser mutation performed; read-only proxy blocks writes.
Evidence outside Git: persisted-history-geometry.json, persisted-counts-*.json,
persisted-gxp/ddk-*.jpg and persisted-gxp-proof.jpg. Browser screenshot capture
can clip the task panel; DOM measurements are the viewport evidence.

Real authenticated UI, binary storage, screen reader and production UAT are not
verified. RecordForm/ExtRecordForm/picker runtime/action gaps remain unchanged.

Accessibility follow-up: the native disclosure retains its legacy-compatible
compact presentation and the history region has a named heading and labelled
native version selector. Selecting a snapshot keeps focus on that selector and a
polite, atomic status announces the displayed ordinal/count. Loading and empty
states use status announcements; 401/403/404/409/server failures remain alerts.
Aggregate replacement never moves focus into history, and stale reads cannot
publish content or focus under their former owner. The read-only rehearsal probe
now includes both aggregate `/versions` calls, validates nested version identity
and fails closed on malformed/conflated GxP scope or ĐĐK FK/source-token payloads
without logging IDs or record values.

`REAL_AUTHENTICATED_UI_BLOCKED`: no approved development origin or provisioned
least-privilege interactive session is available. The exact missing condition is
an Authorized JavaScript Origin for `http://127.0.0.1:4173`, or an already-approved
HTTPS development origin, plus the existing provisioned test account. Fixture
checks are `FIXTURE_VERIFIED_ONLY`; DOM/accessibility regressions are not a real
screen-reader test, so `SCREEN_READER_PASS` is not claimed.

### Facility ĐĐK original GxP source integration — 2026-10-13

Baseline `e428cf0ad1965e9bdcc50f6df525e233e9a0e1e0`: local/remote/PR #3 matched;
OPEN/DRAFT, existing untracked script preserved. Backend contract was read from
PR #7 commit `1ee38180549c5aa6c69d577413311c81431069fc`, including its Pydantic
read models and `docs/DDK_GXP_SOURCE_READ_API_20261013.md`. No backend commits
were merged/cherry-picked; fetching the branch was read-only source inspection.

| Evidence | State | Observed boundary |
| --- | --- | --- |
| Physical four-group source import | `PROVENANCE_DB_VERIFIED` | Existing-key SSH/IAP reached `gxp_legacy_rehearsal`. A `BEGIN READ ONLY` aggregate query followed by ROLLBACK confirmed 780 each GMP/GLP/GSP/GDP (3,120 groups), 861 reference tokens and revision `20261012_0023`. No record contents or credentials were published. |
| Source-only read endpoint | `PROVENANCE_API_DEPLOYED` | Live `/readyz` is healthy; `/app/status` reports Google OIDC, rehearsal DB and runtime `1ee3818`. OpenAPI contains `/business-eligibility-certificates/{business_eligibility_certificate_id}/gxp-source-evidence` with `BusinessEligibilityGxpSourceEvidenceRead`. Types match that deployed schema, including integer column anchors, raw strings, source UUIDs and `canonical_links_included=false`. |
| Facility source panel | `FRONTEND_FIXTURE_VERIFIED` | Existing API client adds one GET with AbortSignal. SearchPage keeps canonical selection ownership; a cancellable, context/UUID/access-owned read hook supplies the Facility-only panel. It loads only after the selected canonical detail/site matches, never all 780 records. |
| Authenticated live source/UI response | `REAL_AUTHENTICATED_UI_PENDING` | Current local PR source reaches Google OIDC through the read-only proxy. Google again rejects `http://127.0.0.1:4173` with “The given origin is not allowed for the given client ID.” VM Nginx's verified HTTPS host is `gxp.qlcl-dav.cc`, not evidence of a development origin permitted for local PR source. No HTTPS development origin was found in available repo/runtime configuration; the Google Console allowlist is not available here. Infrastructure owner needs to approve/add exactly `http://127.0.0.1:4173` under Authorized JavaScript Origins for the existing web client reported by `/app/status`, or supply an already-approved HTTPS development origin. OAuth/CORS/IAP/RBAC remain unchanged. |

The panel “Dữ liệu GxP từ hồ sơ ĐĐK gốc” explicitly separates Excel comparison
data from confirmed canonical links. Four independently collapsible native
groups appear GMP/GLP/GSP/GDP, each with ID CC, scope, standard and business
activity. Raw text, whitespace/newlines, empty cells and repeated ordered tokens
are preserved. Tokens are plain text with their token_index, not links, checkboxes,
Certificate identity or issuance actions. Cyan source values use the existing
legacy field pattern. The canonical left basis list and right Facility fields,
actions/readiness, drafts/version tokens and Case ĐĐK remain unchanged.

Request ownership closes old visibility before passive effects. Selection/context
or access changes abort the old GET; late success/403/404/409 cannot publish over
the current selection. Available source requires exactly the four independent
groups and the source-only contract; a malformed/mismatched response fails closed
at the read owner. Loading, missing legacy identity, not-in-import, 401/403/404/409
and network/server error are distinct. Source presence/absence never produces
business status or completion ticks, and no automatic retry is added.

Presentation regression fails on the checkpoint BusinessEligibilityWorkspace
(missing the named source region), then passes on the new owner. Regression
covers distinct groups, multi-ID/repeated tokens, GDP activity without ID CC,
multiline values, source-missing/error states, A→B and A→B→A, abort, stale errors,
access ownership, focus-only reads and canonical basis/mutation isolation.

Browser fixture at 1920×1080, 1366×768, 390×844, 375×812: client/scroll widths
1920/1920, 1366/1366, 375/375, 360/360; all 16 source cells and four groups remain
available. Arrow/Home/End leave request counters unchanged; Enter activates exact
DDK UUIDs sharing the same number. A pending→B retains B after A's late response,
and returning through the GPs tab retains selection and URL line/history context.
No source links/checkboxes/mutations appeared. Evidence is outside Git as
`ddk-provenance-*`. Authenticated real data, binary storage and speech remain
unverified. CertificateVersion history/historical scope is superseded by the deployed history integration below; RecordForm/picker/color/tick runtime remains
`LEGACY_RUNTIME_EVIDENCE_MISSING`.

Validation: typecheck/lint/build PASS; final targeted source/Facility/API suite
passes 78/78 twice, including 24 dedicated source regressions. Full frontend
passes 401/401 in 29 files. One earlier final-shape full run failed only the
pre-existing CAPA assessment-date test (400/401): it waits for the detail heading
while CAPA draft hydration is still owned by a passive effect. That timing boundary
is outside provenance (the source read is inactive in CAPA). The exact test passed
twice in isolation, and the subsequent full gate passed without code/assertion/
timeout changes to CAPA. Existing act warnings and this instability are retained
as a separate risk, not hidden by a product fallback or skipped gate.

### Authorized rehearsal follow-up — 2026-10-13

Baseline `e5a7dc764b2049b3466fbd8b59db07b12066564e`: local/remote/PR #3 agree,
OPEN/DRAFT, pre-existing untracked script preserved. User authorization now
covers the existing `gxp-web-prod` VM and `gxp_legacy_rehearsal` database. The
user confirms schema `20261012_0023`, 3,120 source-only ĐĐK groups (780 per
GMP/GLP/GSP/GDP), 861 reference tokens and no new canonical Certificate links.
This supersedes migration-BLOCKED notes; it does not establish an API contract.

`VERIFIED` live runtime boundary: Google Cloud CLI was found in Ubuntu/WSL;
control-plane discovery verified the VM and zone. IAP with an existing SSH key
and strict known-host validation connected without IAM/auth/config changes.
FastAPI listens on VM loopback port 8000. `/healthz` and `/readyz` return 200,
schema `20261012_0023` is current; `/app/status` confirms Google OIDC,
`gxp_legacy_rehearsal` and deployment `f96d9336fde453ac50db04f6b3df2193a03e5035`.
Tooling SHA `2ef975901592125f897767a2c920d7858d87f54d` is not assumed deployed.
No-token `/auth/me` and `/search/facilities?limit=1` return 401. The actual PR #3 source was served through a
loopback read-only proxy and rendered the login boundary at all four viewports:
client/scroll widths 1920/1920, 1366/1366, 390/390 and 375/375.
Google sign-in rejects `http://127.0.0.1:4173` with "The given origin is not
allowed for the given client ID". The live API-client probe reports BLOCKED/401
after two reads. Authenticated nine-workspace UI remains `REAL_BACKEND_NOT_VERIFIED`:
it requires an approved OAuth origin and interactive sign-in with a provisioned
account. No token/stub-auth injection or OAuth/RBAC change was used.

Prepared a repeatable, development-only harness (`qa/REHEARSAL_READ_ONLY.md`,
`qa/rehearsal.vite.config.ts`, `qa/rehearsal.html`, `src/qa/rehearsalSmoke.ts`,
`src/qa/rehearsalProxy.ts`). It uses the existing API client/OIDC session, forces
same-origin loopback proxying, explicitly strips /api only for direct FastAPI
(matching VM Nginx's route mapping), rejects live header_stub, and blocks non-GET/HEAD
API/health requests before forwarding. No auth headers are injected in live
mode. Reports omit record values/IDs, cookies/tokens and backend error detail.
The bounded probe uses selected Site/ProductionLine/Case/Certificate/document
identity and distinct rendition/version IDs; repeated document UUIDs are read
once while different UUIDs sharing numbers/filenames stay distinct. Overlapping
probe runs are rejected. Empty/unavailable data is explicitly SKIPPED, not live
PASS; `READ_API_PASS` never declares browser UI or binary verification.

Synthetic upstream browser validation of the actual current frontend through
this proxy: nine surfaces activated at 1920×1080, 1366×768, 390×844 and 375×812.
Document client/scroll widths were 1920/1920, 1366/1366, 375/375 and 360/360.
Canonical history/line URL selection remained present across workflow steps.
The browser probe passed with 10 GETs, `FIXTURE_ONLY`, `uiVerified=false`,
`binaryVerified=false`. The older local fixture initially lacked evaluation_scope;
the strict owner check failed, then passed after adding its canonical empty shape
to the temporary fixture only. No product fallback or weakened assertion was used.
A local POST returned 405 and upstream counters stayed identical. Arrow/Home/End
changed history focus with identical upstream counters and unchanged selection URL.
Sanitized evidence is outside Git as `rehearsal-tooling-*`.

At that checkpoint provenance and CertificateVersion history were pending. The provenance gap is superseded by the deployed API/current integration above; persisted CertificateVersion/historical scopes are now available through the deployed history integration below; RecordForm/picker/color/tick semantics remain
`LEGACY_RUNTIME_EVIDENCE_MISSING`. All nine live workspace checks, live
authenticated 403/network/409 behavior, real binary storage and speech verification remain
`STAGING_VALIDATION_PENDING`. No frontend product defect was identified; no
business component, API contract, backend, database, storage or RBAC changed.

Validation: final targeted runner/API tests pass 55/55 twice (23 new harness
tests plus 32 existing API-client tests). Typecheck, lint and production build
PASS; final full frontend suite passes 374/374 in 28 files. Existing React act
warnings remain; no final test failures occurred. No timeouts, product assertions
or concurrency behavior were relaxed.

Baseline: `c02718f54029f3fae49104629dd071c152e60502`. Local, remote and
OPEN/DRAFT PR #3 matched before this read-only audit. The pre-existing untracked
`Verify-GxpLegacyCertificateLinks.ps1` remains untouched.

| Gap | Classification | Evidence and boundary |
| --- | --- | --- |
| Current Facility/Case GPs certificate identity and scope snapshot | `VERIFIED` | `GxpCertificateDetailRead` and the matching TypeScript type expose canonical certificate UUID, Site/Case/ProductionLine identity, `row_version`, `latest_flag`, scalar certificate values, `scope_summary`, ordered `scopes[]` with scope UUIDs, limitation, status and readiness. The detail service loads scopes only for the selected latest CertificateVersion. Existing Facility and Case owners consume that response without deriving IDs from certificate number, filename or text. |
| Persisted GxP / ĐĐK version history | `BACKEND_API_DEPLOYED` / `FRONTEND_FIXTURE_VERIFIED` | Runtime `97182e5` provides both canonical aggregate `/versions` GETs. Separate read-only Facility snapshots retain version UUIDs, ordinals, concurrency tokens, per-version ordered scopes and per-version stored FK rows. This is persisted history, not immutable/legal attestation. Authenticated UI remains `REAL_AUTHENTICATED_UI_PENDING`. |
| Facility ĐĐK GMP/GLP/GSP/GDP source groups | `PROVENANCE_API_DEPLOYED` / `FRONTEND_FIXTURE_VERIFIED` | The separate source-only endpoint deployed at `1ee3818` exposes the four original groups; the Facility-only panel consumes it by canonical DDK UUID with context/access ownership and AbortSignal. Independent read-only DB aggregates confirm 3,120 groups / 861 tokens. The flat `linked_gxp_certificates` list retains its canonical meaning and is not classified/merged from provenance. Authenticated live UI remains `REAL_AUTHENTICATED_UI_PENDING` because the local OAuth origin is rejected. |
| Canonical certificate actions | `VERIFIED` | GPs and ĐĐK issue/edit/promote controls are sourced from backend readiness, permissions and `expected_version`. Change-request successor actions have their own readiness identities. Existing 403/409/422 behavior and draft retention remain the owners of error handling; no legacy button is enabled from visual evidence alone. |
| Canonical contextual document actions | `VERIFIED` | `ContextualDocumentActionRead` permits only `open`, `create` and `history`, with availability, disabled reason and required permissions from the backend. `DocumentDetail` exposes logical document UUID, rendition UUID and version UUID separately. Binary access remains through case/CAPA content endpoints and StorageService; the frontend has no path/NAS fallback. |
| RecordForm / ExtRecordForm / picker command equivalence | `BACKEND_CONTRACT_PENDING` | VBA proves real side effects: RecordForm and ExtRecordForm generate/open documents; SelectCC/SelectDDK can delegate mutations; ChonMauCC/SelectFile browse legacy folders and templates. The current web mappings are DocumentService/StorageService, CertificationService and BusinessEligibilityService contracts. Commands outside existing readiness/action models require an approved backend owner before a web button can be added. |
| RecordForm, SelectCC, SelectDDK, ChonMauCC and SelectFile runtime appearance/states | `LEGACY_RUNTIME_EVIDENCE_MISSING` | FRM/FRX and procedure evidence establish structure and side effects, but complete runtime captures for enabled/disabled, selection, editor, error and confirmation states are absent. Existing canonical workspaces remain in place rather than guessing those states. |
| Current certificate scope/status display | `VERIFIED` | `scope_summary`, selected-version `scopes[]`, limitation and authoritative status are displayed without parsing prose or calculating status from dates. Multiple scope records retain API order and UUID identity. |
| Historical scope and green completion strip / legacy status colors | `BACKEND_API_DEPLOYED` for scope; `BACKEND_CONTRACT_PENDING` for completion strip | Historical scope now comes only from its exact persisted version response. No per-stage completion projection exists for the legacy green ticks, and completion is not inferred from documents, dates or status text. Existing canonical lifecycle/readiness values remain unchanged. |
| Exact runtime color/tick semantics | `LEGACY_RUNTIME_EVIDENCE_MISSING` | Supplied images show presentation, but no approved mapping ties the VBA colors/ticks to canonical states for every runtime condition. StatusBadge and workflow state remain authoritative. |
| Authorized real staging | `STAGING_VALIDATION_PENDING` | The follow-up user request authorizes `gxp-web-prod` / `gxp_legacy_rehearsal` for read-only rehearsal verification. WSL Google Cloud CLI + IAP + existing-key SSH verified healthy runtime, current schema 0023, Google OIDC and rehearsal DB identity. The local PR frontend reaches the login boundary, but Google rejects its local OAuth origin; authenticated nine-workspace UI remains unverified. No VM/OAuth configuration or mutation was performed. |

No item is classified `FRONTEND_FIX_REQUIRED`: source/type/API-owner comparison and
the current fixture pass found no unsupported display inference, duplicate owner
or identity defect that can be corrected solely in the frontend.

Fixture validation uses the actual App and two local synthetic API fixtures. All
nine completed surfaces (General Information, registration, inspection, CAPA,
processing, Case GPs, Case ĐĐK, Facility GPs and Facility ĐĐK) were activated at
1920×1080, 1366×768, 390×844 and 375×812. For every surface,
`document.scrollWidth === document.clientWidth`: 1920/1920, 1366/1366,
375/375 and 360/360 respectively (the narrow 15px difference is the vertical
scrollbar). Facility/history/case tab changes retain site ID, production-line UUID
and history ID in the URL. ArrowDown/Home/End changed history focus with unchanged
request counters and selection URL; no mutation was issued.

The document fixture selected PCT A while its metadata was pending, then CT B with
the same filename. B displayed `processing-document-2`, `rendition-uuid-2` and
`version-uuid-2`; releasing late A did not replace B. Counters contain one read for
each exact document UUID and zero mutations. The disabled create/open controls
follow backend availability. Captures, geometry and sanitized request counters are
stored outside Git as `evidence-closure-*`.

Fixture validation is `PASS`. Authenticated real-backend UI/OIDC login, actual binary storage,
assistive speech and production UAT remain `STAGING_VALIDATION_PENDING`.
Schema 0023 is now independently confirmed by live /readyz; import counts remain user-provided. A DOM/accessibility-tree check is not a screen-reader PASS.

Validation: the related ten-file target passes 242/242 twice. Typecheck and lint
PASS. The final full run passes 351/351 in 27 files. Two earlier diagnostic full
runs each produced one different pre-existing asynchronous App-test failure: the
selected-history CSS assertion, then the known CAPA assessment-date initialization
assertion. Each exact failed test passed twice immediately afterward, both were
already included in the two clean targeted runs, and no related source changed;
they are recorded as test instability rather than product fixes. Timeouts and
assertions were not changed. Production build PASS.

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
| tbGMP, tbGLP, tbGMPbb top row | FacilityTable / CSS | Legacy horizontal selector differs from the preserved vertical web rail | User-approved web exception retains the vertical rail and canonical GMPbb; roving focus now gives the group one Tab stop without changing selection | High for current placement/interaction; exact legacy keyboard behavior EVIDENCE_MISSING |
| edSearch, Label29 “Lọc:” | SearchPage URL ownership; no mounted filter surface | Legacy quick-filter row differs from the preserved web master | Latest user correction removes the entire Lọc / Lọc dữ liệu row and retains only the two master-table inputs; URL-owned filters remain supported without restoring the removed surface | User-approved web exception; no exact FilterForm parity claim |
| MainForm facility page captions | FacilityWorkspaceTabs / facilityTabs | GxP / expanded eligibility label | Displays “Các đợt kiểm tra & Thay đổi”, “Giấy chứng nhận GPs”, “Giấy chứng nhận ĐĐK”; existing URL keys unchanged | High; caption/key regression and existing tab keyboard tests |
| Nested case tabs: Hồ sơ đăng ký, Kiểm tra thực tế, Báo cáo khắc phục, Xử lý tiếp, Cấp chứng nhận GPs | EventWorkspace | Shortened labels and numbered stepper | Verified captions restored; numbered connector presentation removed in search | High for all six case captions, including image 6 for ĐĐK |
| Label/value rows, frames, dense tab controls | Scoped search CSS | Rounded cards and larger controls | Reduced corner radius/spacing; runtime grey frames, blue/green tabs and white inset values applied; cyan certificate values | Partial; no exact appearance claim |
| Application page date then dossier code | CaseApplicationWorkspace | Same order, currently two-column grid | Order retained; runtime images establish vertical date/code and assessment grouping; implementation remains partial | Runtime evidence available |
| FilterForm named condition groups | Unmounted legacy filter components / SearchPage URL ownership | API cannot represent the complete legacy condition set | Latest user correction keeps FilterForm absent from the search layout; no client-only filtering or invented backend semantics | EVIDENCE_MISSING for runtime FilterForm; user-approved web exception |
| RecordForm MultiPage1, document bundle | ContextualDocumentSection / EventWorkspace | Web list/detail with canonical versions | Existing owner preserved, inherited compact frame styling; no invented tabs or filename-based keys | `LEGACY_STATIC_VERIFIED` for structure/actions and `WEB_FIXTURE_VERIFIED` for canonical interaction; runtime geometry/states remain `EVIDENCE_MISSING` |
| GPs / ĐĐK historical lists and details | Certificate workspaces | Existing two-pane model; different chrome | Legacy facility tab captions and scoped density applied; fields/provenance retained | Partial; existing certificate/draft/modal tests, runtime references now available; exact field grouping remains partial |
| SelectCC, SelectDDK, ChonMauCC, SelectFile, ExtRecordForm, DCForm, TTVForm | Existing selectors/editors | Full runtime appearance unknown | Audited as related forms; no guessed replacement screens | SelectFile structure/double-click are `LEGACY_STATIC_VERIFIED`; runtime states and visual comparison remain `EVIDENCE_MISSING` |
| GMP/GLP/GMPbb workbook worksheets, list/planning outputs | Search/results/report screens | UserForm and worksheet roles differ | Workbook inventory reviewed; worksheet rendering not cloned without evidence | EVIDENCE_MISSING for rendered workbook baseline |

### RecordForm document workspace interaction — 2026-10-14

**LEGACY_EXPECTED →** The operator selects a concrete file in the RecordForm
document slot and can open that selected file directly. SelectFile additionally
opens the exact selected list item by double-click.

**SOURCE_EVIDENCE →** `RecordForm.frm` defines paired `cb1..cb16` selectors and
`btn1..btn16` commands. `btnFile` opens the selected combo value when present.
`SelectFile.frm` handles `lb_DblClick`/`lb_MouseUp` and passes the selected list
value to `LoadFile`. Static FRX site records corroborate the paired controls and
tab order; they do not establish runtime pixels or colors.

**CURRENT_CONTRACT →** `ContextualDocumentSection` owns one canonical workspace.
Every row retains `parent_scope`, `parent_id`, `workflow_step`, `checklist_key`
and `document_id`; open remains available only through the backend-provided
action. Rendition/version identity stays in the read-only detail response.

**CHANGE →** Double-clicking a document selector invokes its existing available
`open` action through the same request-generation, full-identity deduplication,
stale-response and focus-restoration path as the explicit Mở button. Enter still
selects/loads detail. Missing or unavailable open actions do nothing; the client
does not synthesize a command.

**REGRESSION →** The new test fails on the baseline because double-click performs
no open. It now proves the exact UUID is used even when two rows share one
filename, repeated click events add no duplicate metadata request, focus remains on the selector, and an
unavailable action cannot open. Existing A→B→A, same-slot replacement, shared-ID
slots, 403/404/409, F6 and duplicate-request tests remain applicable.

**REMAINING_GAP →** `EVIDENCE_MISSING`: RecordForm/SelectFile runtime geometry,
colors, enabled/disabled appearance, confirmations and complete picker keyboard
behavior. The web keeps its canonical list/detail/version model instead of
recreating prefix/path-based selectors or raw Explorer ownership.

### RecordForm / SelectFile evidence closure — 2026-10-15

The available local evidence was re-inventoried without executing VBA. The
exported FRM sources and `legacy/GXP-VBA code.zip!/xl/vbaProject.bin` FRX streams
were parsed read-only. All 45 accessible `codex-clipboard-*.png` files were also
visually inventoried: they contain the supplied MainForm/workflow/certificate
captures and web fixture captures, but no RecordForm or SelectFile runtime view.
The generated control inventory and contact sheets are stored outside Git under
`.codex/evidence/gxp-recordform-b13095c/`.

| Claim | Evidence and result | Classification | Confidence | Current web difference / decision |
| --- | --- | --- | --- | --- |
| RecordForm is a tabbed document surface | Root FRX contains `MultiPage1`; its two child pages are present below `RecordForm/i85` | `LEGACY_STATIC_VERIFIED` | High | Keep one contextual document workspace per owning workflow; do not introduce a global duplicate workspace |
| First page contains 16 selector/open pairs | Static sites contain `cb1..cb16` and `btn1..btn16`; VBA routes all sixteen open buttons to `btnFile` | `LEGACY_STATIC_VERIFIED` | High | Web rows/actions are data-driven rather than sixteen permanent filename slots |
| First page has separate create commands | Static sites contain `btnx1..btnx16`; VBA routes them to `btnFile <slot>, True` | `LEGACY_STATIC_VERIFIED` | High | Render create only when the backend action is present and available; never infer it from an empty slot |
| Second page is another grouped file/note surface | Static sites contain eight `btny`/`cbz`/`btnz` groups plus `cbLanDC`, `btnFolder2`, `txtFolder2` and `btnAddNote` | `LEGACY_STATIC_VERIFIED` | High for structure; Low for runtime appearance | Do not add a second web document owner or a note mutation without canonical API ownership |
| Selected file can be opened | `btnFile` opens the selected combo value; SelectFile passes the selected list value to `LoadFile` after double-click | `LEGACY_STATIC_VERIFIED` | High | Existing open action uses exact `document_id` and backend availability; raw path/Explorer ownership is intentionally excluded by C2 |
| SelectFile is a single list picker | FRX contains one `lb` ListBox at tab index 0; VBA populates it from the supplied file list | `LEGACY_STATIC_VERIFIED` | High | Web preserves a list plus canonical detail/version pane so duplicate filenames remain distinct by full identity |
| Double-click opens the selected item | `lb_DblClick` marks the action and `lb_MouseUp` loads the item at `ListIndex` | `LEGACY_STATIC_VERIFIED`; web behavior is `WEB_FIXTURE_VERIFIED` | High | Implemented at the existing selector and action owner; unavailable open actions remain inert |
| Arrow/Home/End, Enter, Escape and F6/Shift+F6 behavior | No explicit RecordForm/SelectFile keyboard handlers were found; native MSForms defaults and runtime focus order cannot be proven from static files | `EVIDENCE_MISSING` for legacy; `WEB_FIXTURE_VERIFIED` for current web behavior | High that source is insufficient | Retain accessible web roving focus, Enter selection and F6 pane transfer; do not claim those keys reproduce legacy runtime |
| Selected/available/unavailable/loading/disabled visuals | FRX supplies controls and VBA supplies some progress/status writes, but macro-driven visibility/enabled state and rendered appearance are absent | `EVIDENCE_MISSING` | High | Keep backend-owned availability, disabled reasons and live pending/error messages; no color/spacing change in this slice |
| Exact geometry, colors, fonts and scaling | Designer structure is available; no native runtime capture or Windows scaling evidence exists for either form | `EVIDENCE_MISSING` | High | No CSS change is justified; designer twips are not converted to browser pixels |
| Same filename on different logical documents | Legacy selection is filename/path based; static evidence cannot establish collision behavior | `EVIDENCE_MISSING` for legacy; `WEB_FIXTURE_VERIFIED` for web | High for the contract difference | Preserve `checklist_key` + `document_id` + action identity and version/rendition IDs; never merge by filename or prefix |
| Focus and announcements during select/open/error | No runtime accessibility or screen-reader evidence exists | `EVIDENCE_MISSING` for legacy; unit/fixture verified for web | High | Preserve current focus restoration, status/alert semantics and stale-response ownership |

#### Static control to canonical workspace crosswalk

| Legacy control group | Proven static role | Canonical web owner / mapping | Constraint |
| --- | --- | --- | --- |
| `MultiPage1`, Page1, Page2 | Two-page RecordForm container | Owning `EventWorkspace` renders one `ContextualDocumentSection` for its current workflow context | Tabs are not recreated until captions, runtime visibility and owner mapping are evidenced |
| `cb1..cb16` | File selection slots | Document selector rows keyed by `checklist_key` and exact `document_id` | Filename/prefix is display data only |
| `btn1..btn16` | Open selected slot | Existing backend-provided `open` action | No available action means no open side effect |
| `btnx1..btnx16` | Create from the corresponding slot/template path | Existing backend-provided `create` action | No client template/path fallback; permissions and disabled reasons stay authoritative |
| `btny1..btny8`, `cbz1..cbz8`, `btnz1..btnz8` | Second-page grouped file actions | No additional owner introduced | Exact business mapping and runtime presentation remain `EVIDENCE_MISSING` |
| `btnFolder`, `btnFolder2`, `cbFolder`, `cbFolder2`, `txtFolderName`, `txtFolder2`, `txtsyear` | Legacy folder/path navigation and display | No raw folder control in the frontend | Storage resolution remains behind StorageService; see C2 |
| `lbProgress`, `lbStatus` | VBA generation progress/status text | Existing scoped pending status and action error region | Semantic relationship is grounded; visual equivalence is not claimed |
| `SelectFile.lb` | Multiple-file picker and double-click target | Document list selection and available open action | Exact UUID, rendition and version remain canonical identities |
| `btnRefresh`, `btnRefresh2`, `btnAddNote`, `btnHelp11`, `cbLanDC` | Legacy refresh/help/note/round controls | No new command in this slice | Requires an approved backend/domain owner and runtime evidence before mapping |

#### Minimum runtime capture checklist

Capture read-only, redacted images at native Excel/VBA runtime and record Windows
display scaling. Do not expose filenames, paths, facility names or personal data.

1. RecordForm Page1 and Page2 in their complete native window, including tab
   captions, progress/status region and the full control boundaries.
2. One empty slot, one single-file slot and one multi-file slot, with the relevant
   create/open/select controls shown in normal, focused and disabled states.
3. SelectFile immediately after opening, with one row focused/selected, plus the
   state after Escape/window close and immediately before a confirmed double-click.
4. A safe generation/open operation showing loading/progress, success and one
   non-destructive error/confirmation state if those states can be reached without
   mutating production data.
5. Keyboard focus evidence for Arrow/Home/End, Enter, Escape and tab traversal;
   record explicitly when F6/Shift+F6 have no legacy behavior.

Until that set exists, RecordForm/SelectFile visual parity is `PARTIAL`: structure
and the double-click interaction are verified, canonical web behavior is fixture
verified, and exact runtime presentation remains `EVIDENCE_MISSING`. No visual
micro-slice is applied at this checkpoint.

## CONFLICT_REGISTER

| ID | LEGACY_EXPECTED | CURRENT_CONTRACT / WHY_CONFLICT | Minimal resolution and affected checks |
| --- | --- | --- | --- |
| C1 | Full FilterForm flags: registration, inspection, compliance, product classification, dosage form and date ranges; persisted workbook names | Existing search API supports q, facility/scope/province, canonical states, certificate state/expiry; no equivalent for all legacy flags or saved workbook names | Superseded by the later user correction at lines 346–354: do not mount Lọc / Lọc dữ liệu; retain only the two master-table inputs. URL-owned filters remain supported, with no client-only filtering of a paginated subset. |
| C2 | Native Explorer/Word, opening raw folders and prefix-selected files; RecordForm slots and SelectFile values are populated from filesystem names | Backend owns storage binding/access, logical document/rendition/version identity; frontend cannot resolve NAS paths or use a filename/prefix as identity | Preserve available backend open/create/history commands and full IDs. Do not reproduce fixed path slots, raw-path fallback or fake file actions. Duplicate-filename, document-race and storage-contract checks apply. |
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
and general information page, RecordForm, FilterForm and related pickers; use the
RecordForm/SelectFile minimum checklist above and include Windows
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

## Facility GPs read-layout slice — 2026-10-13

Baseline: `c7becfe71b367bea9ccdc5561d48da9015ca74ae`, matching local,
remote and OPEN/DRAFT PR #3 before edits. The pre-existing untracked
`Verify-GxpLegacyCertificateLinks.ps1` is preserved. This is Facility GPs;
Case GPs, both ĐĐK owners and the other workflow tabs are unchanged.

Evidence: supplied runtime image 7 (Facility GPs), not images 5/8 (Case).
`MainForm.frm` DataCC2 maps number, issue/expiry dates, scope, facility/address,
company/headquarters, standard, status, issuer and limitation to the corresponding
read controls. `UpdateCCGPsItem` clears prior values before loading the selected
list row through `UpdateCCGPsItem_Row` / `Load_row2CCCtrlsDs`. FRX control names
in the source archive confirm edMaCCDs, edCCCapDs, edCCHHDs, edTieuchuanCC,
edPviCC, edGioihanCC and edCoquanCap. No workbook writes are reproduced.

Last-correct/first-incorrect presentation boundary: the existing canonical fields
and order were already correct. The generic certificate breakpoint collapsed the
four-field Facility header at 1366px, and the flat body did not provide the large
scope/limitation areas or issuer-left/status-and-source-right footer seen in image
7. This identifies the current owner boundary, not a historical commit bisect.

The Facility-only renderer now groups those same values, retains cyan read fields,
uses the evidenced pale-yellow standard field, and preserves multiline standards
without splitting or classifying them. Its header stays four columns at 1366 and
1920, with stacked narrow layouts and independent desktop list/detail scrolling.
Case rendering and mutation/state owners are untouched. Selected snapshot scope
records are displayed separately below the primary legacy form, in API array
order, keyed by scope UUID; summary text remains intact. No summary-to-record,
language, version, provenance or GxP-group inference is introduced.

Browser fixture geometry (viewport width: document client/scroll width, before →
after): 1920: 1920/1920 → 1920/1920; 1366: 1366/1366 → 1366/1366;
390: 375/375 → 375/375; 375: 360/360 → 360/360. The 15px difference is the
vertical scrollbar, not horizontal overflow. At 1366, header field y coordinates
change from 359/359/390/390 to 363/363/363/363; at 1920 they remain one row.
Case GPs header geometry at 1366 is exactly unchanged. Captures and geometry JSON
are outside Git under `facility-gps-before-*` / `facility-gps-after-*`.

Fixture interactions: same-number UUID A/B selection via Enter/Space; ArrowDown
changes focus with identical request counters; pending A replaced by B, then late
A released without overwriting B; production_line_id changes to line-uuid-2 with
only its certificate/scope, then returns to line-uuid-1. Refresh and Forward
restore the canonical line-B URL. Selection changes use the existing replace URL
behavior: Back exits to the prior browser entry, rather than fabricating a history
entry per row. Facility/Case tab round-trip retains canonical history context.
The one explicit test save sends B's expected_version 9 and its scope record;
pending Tab/Shift+Tab/Escape retain modal focus. Fixture 409 keeps the draft,
disables retry, and Escape returns focus to the trigger. No navigation mutation
occurs; the final counter contains exactly that one intentional PUT. The fixture
intercepts metadata/mutations only and writes no business data.

Regression: presentation test failed on baseline (1 FAIL / 13 PASS), then passed;
an additional test preserves raw multiline standards/summary, long text, limits
and null values without invented tabs/documents. A first run of the new multiline
test exposed Testing Library text normalization; its assertion now checks exact
DOM textContent so newlines are verified rather than normalized away. Both final
targeted runs pass 54/54 across five files, including Case issuance/ĐĐK,
document ownership and dialog focus. Typecheck, lint, full suite (351 tests / 27
files, 0 failures) and production build PASS. No timeout/test-skip changes. The
previous CAPA date-field CI flake did not occur in this local full run.

EVIDENCE_MISSING / remaining differences: API does not expose a complete immutable
CertificateVersion history and per-historical-version scope snapshots. row_version
and latest_flag are not treated as version IDs. Runtime placement of structured
scope records is not evidenced; they remain a canonical web addition below the
form. Existing authoritative StatusBadge is retained instead of inventing legacy
red/full-field status colors or completion ticks. Legacy document/source commands,
all-lines controls and certificate creation/reissue/replacement controls are not
added without contracts. Existing edit readiness/RBAC/expected_version are retained.
No provenance groups are assumed: VM uses gxp_legacy_rehearsal and migration
20261012_0023 is independently confirmed current by live /readyz; source-only import counts and deployed source API are now independently verified; Facility fixture integration is complete (see current provenance slice). Real-backend integration,
binary storage, screen-reader UAT and production UAT remain unverified. No backend,
API, database, migration, storage or authorization changes are part of this slice.

## Facility ĐĐK read-layout slice — 2026-10-13

Baseline: bd0f1c773f71aa3ddb6babf437d490d3680fd906; local/remote/PR agree,
PR #3 remains OPEN/DRAFT and existing untracked script is preserved. Evidence:
runtime image 9 is Facility Giấy chứng nhận ĐĐK, unlike Case image 6. Its left
pane contains the list, dossier/handler and GPs basis; the right contains header,
company/facility, professional/license, activity, status and replacement fields.
MainForm.frm/FRX confirms lbCCDDK, edHsDC_DDK/edNgXL_DDK and DataDDK2 controls.
UpdateListDDKCs reads the site's mapping and populates lbCCDDK;
UpdateCCDDKItem clears controls, resolves the selected row in db_ddk and calls
UpdateCCDDKItem_Row/Load_row2DDKCtrlsDs. DataDDK2(0..11) is four distinct legacy
scope/activity/standard groups, not a certificate-type classification algorithm.
Their workbook writes/add-link/edit procedures are not copied into the web.

Root cause/presentation boundary: the already-correct four header fields and
identity order were followed by generic vertical professional fields and
dossier/basis at the bottom of the right pane. Shared Case/Facility rendering
had no Facility grouping owner. Source 94e79af introduced the initial partial
legacy field groups; no historically complete Facility parity is claimed.
Baseline runtime/regressions establish the incorrect side, current layout the
corrected side. Do not mistake this for a historical full-app browser bisect.

BusinessEligibilityWorkspace now uses Facility-only fields: left dossier/handler
and one flat basis list; right company/facility, primary PTCM/qualification/CCHN/
license date, QA name, ungrouped business activity, status and paired replacement
texts. Extra canonical license/issuance/notes/expiry data remains below. Cyan
inset values and yellow issuance-sequence value follow the pictured fields.
Both desktop panes scroll independently, the list uses remaining height and
narrow screens stack/wrap without page clipping. Case still uses its original
read-only field hierarchy; its pure basis renderer is extracted without DOM,
request or state changes. No document list or new activity tab is created.

One selected UUID remains owned by SearchPage; row focus is separate. Moving
read-only metadata does not introduce a fetch/state owner. Both panes suppress
detail/basis on mismatched UUID, loading or error. All payload fields, multiple
basis UUID/link-role entries, row_version/readiness and issue/edit/promote
handlers remain unchanged; no dedupe by number/name or local business rules.
Existing commands retain backend labels/placement: legacy Tạo/Điều/Hồ copy,
revision and folder commands are not equated to current issue/edit/promote.

Superseded provenance gap: a separate source-only endpoint now provides the four groups; Facility fixture integration is verified above. The existing detail still has scalar business_activity_text and flat canonical basis links. Do not
derive these from certificate_type, linked IDs or prose. Backend PR #7 remains
separate. QA qualification/license fields pictured in legacy have no matching
current detail fields; no second license or date ownership is inferred. Existing
responsible-license date/issuer labels are retained as canonical extras rather
than assigned to QA. The raw status text has no authoritative legacy color
classification, so its cyan value is retained without inferring active/expired
from prose or dates. Version history IDs, legacy folder/doc commands, live OIDC,
real backend, binary storage and screen-reader acceptance remain unverified.

Regression: new Facility hierarchy/owner and stale-left-metadata tests FAIL on
baseline (2 FAIL / 17 PASS), then PASS. A third test preserves null/multiline/
long text and two equal-number basis UUIDs without derived activity tabs.
Existing tests cover equal certificate numbers with distinct UUIDs, focus-only
arrows, loading/error/refresh, expected_version and 403/409/422/draft semantics.
Case/document/modal regressions remain unchanged.

Actual App + synthetic fixture at 1920x1080, 1366x768, 390x844, 375x812:
document clientWidth/scrollWidth before AND after are 1920/1920, 1366/1366,
375/375 and 360/360 respectively. The responsive header fix remains intact.
Desktop basis viewport position: 1920 x558/y1106 -> x23/y968; 1366 x403/y1107 ->
x23/y656, now visible in the left pane. Mobile coordinates depend on scroll;
full rect/width records and screenshots are kept rather than claiming pixel
parity. Arrow/Home/End move focus; Enter/Space activate exact UUID, Tab/Shift+Tab
between list/editor works. F2 has no Facility editor shortcut and stays inert;
Enter opens its existing button, Escape closes only when allowed.

Held A detail, selected B, released A: B's fields/basis remain. Pending editor
traps focus, disables controls and ignores Escape; one explicit PUT receives
409 and retains number/notes, expected_version=7 and two exact basis UUIDs with
no retry. Case/Facility round-trip retains selected B; hard refresh keeps canonical
URL but initializes the local certificate selection from the first item as
before. External URL Back/Forward preserves site/line/history context. Counters
include explicit selections, refresh/page initializations and existing per-detail
basis reloads; only one deliberate rejected edit, no navigation write or new
request source. No real mutation was applied.

Evidence outside Git: facility-ddk-before/after-1920/1366/390/375.png,
facility-ddk-before/after-geometry.json, facility-ddk-conflict-1920.png,
facility-ddk-request-counts.json and fixture harness. No backend/API/DB/storage/
authorization/concurrency change, merge/rebase/cherry-pick or deploy. Partial
parity only at that checkpoint; four-group source-only provenance is now integrated through the separately deployed API above.

Validation: typecheck, lint, production build and all 349 frontend tests / 27
files PASS. Targeted Facility/Case/document/modal regressions pass 50 tests in
each of two completed runs; no timeout increase or disabled test. Existing
non-failing act warnings remain. Self-review: five frontend/QA files, presentation
and pure rendering only; mutation handlers/dialog state/readiness untouched.
Provenance consumption is now complete for fixture validation; next obtain a permitted OAuth origin for authenticated verification,
then authorized staging integration and screen-reader verification.

## Mobile web-shell overflow slice — 2026-10-13

Baseline: f3ddd44b233836a14b45d5d4584b18a02172ebc7 (the supplied checkpoint
has one extra trailing `c`; local/remote/PR agree on this 40-character SHA).
This section supersedes the historical ~9px header limitation recorded below.
The accepted desktop web shell remains outside VBA form styling (exception C6).

DOM diagnosis: at viewport 390 the document clientWidth is 375 and scrollWidth
384. Header identity flex item shrinks to 128.63px while its contents need about
150px; logout ends at x=384.46, past the document boundary. The nowrap brand
subtitle also paints outside its shrunken copy box into navigation. At 375 the
document is 360px wide but scrollWidth reaches 375px. No workspace pane is the
owner of this header overflow. Source-history audit: 9b1ef335 changed the narrow
topbar from grid to a non-wrapping flex row; its parent used grid. This locates
the relevant structural change, not a claim of a historical browser bisect.

Fix only in styles.css, existing max-width:760px header owner: wrap the topbar's
groups, bound their width, let brand/identity text wrap, and preserve logo/button
widths. No body/parent overflow hiding, positioning workaround or duplicate
header. Header order, content, route links, auth/RBAC handlers and focus order
remain unchanged; mobile groups occupy additional rows instead of compressing
their children. Desktop geometry is identical at 1366/1920. Master/rail/actions,
history, six workflow tabs, General Information, certificate owners, scope tabs
and all business/data/document/concurrency state are untouched.

| Viewport | Before clientWidth / scrollWidth | After clientWidth / scrollWidth |
| --- | --- | --- |
| 390x844 | 375 / 384 — FAIL | 375 / 375 — PASS |
| 375x812 | 360 / 375 — FAIL | 360 / 360 — PASS |
| 1366x768 | 1366 / 1366 — PASS | 1366 / 1366 — PASS |
| 1920x1080 | 1920 / 1920 — PASS | 1920 / 1920 — PASS |

Regression: qa/headerOverflowRegression.js is a read-only real-browser probe;
wrap its function source as an invoked expression in browser evaluate. It
asserts document.scrollWidth <= document.clientWidth, checks header element
boundaries (1px fractional geometry tolerance, no document-width tolerance),
and rejects mobile clipping on html/body/root/shell/header. The same assertions
fail on both mobile baselines, then pass twice at all four viewports. jsdom has
no layout engine: these are actual fixture-browser checks, not fabricated
jsdom widths or an automatically executed CI browser suite. Breakpoint 760/761
also passes (745/745 and 761/761). Desktop header box measurements match exactly
before/after, checking the unaffected side of the responsive change.

Actual App + synthetic API fixture: Tab/Shift+Tab between navigation links;
Arrow/Enter selects the exact linked certificate; F2 opens a dossier draft,
viewport resize retains it, Escape cancels without a save. Six workflow tabs
and General Information/Facility GPs/Facility ĐĐK/history round-trips remain
375/375. F6 has no header behavior; the empty fixture document list cannot
prove populated document F6 behavior, covered by existing document tests.
Counters: one search/site/Case read for initial context; deliberate Facility
certificate visits use their own list/detail/basis requests once; zero mutations,
no duplicate workspace read due to resizing or focus/tab navigation.

Local evidence outside Git: shell-before/after-375/390/1366/1920.png,
shell-before/after-measurements.json, shell-regression-repeat.json and
shell-request-counts.json. EVIDENCE_MISSING remains for live Google OIDC/GIS
iframe rendering, real-backend integration, binary storage and screen-reader
acceptance; no claim of production UAT or full legacy parity. Existing missing
RecordForm/picker/expanded Case/version-history evidence is unchanged; no work
on those independent scopes. No backend/DB/API/storage/RBAC/data change,
merge/cherry-pick/rebase or deployment.

Validation: typecheck, lint, production build and all 346 tests / 27 files PASS.
Related tab/history/document/modal files pass 34 tests in each of two completed
targeted runs. One overlapping diagnostic invocation was stopped before completion;
the completed runs and full suite above have no failed tests or timeout changes.
Browser geometry assertions: two expected mobile baseline failures, then eight
PASS checks across two complete four-viewport runs. Existing act warnings remain
non-failing. This probe is not loaded by the production App. Diff is three files;
pre-existing untracked files are preserved. Next: authorized staging and live
OIDC/screen-reader verification; independent legacy evidence gaps remain separate.

## Case ĐĐK read-only visual/interaction slice — 2026-10-12

Baseline: c841098ac390d331c4f4fd62deaa8be45f651459. Runtime image 6 is the
Case Cấp chứng nhận ĐĐK page: a compact, white, three-column list at upper left,
caption “Giấy ĐĐK đã cấp căn cứ GCN GPs này”, blue selected row and a legacy
issuance command. Image 9 is the separate Facility ĐĐK page: company/facility,
professional persons, CCHN, business activities, status, replacements and basis
certificates. Its full detail form is not runtime evidence of an expanded Case
form. MainForm.frm's OleObjectBlob points to MainForm.frx; the original FRX
contains lbDDKLQx and btnCapDDK control names. No twips-to-runtime pixel inference.

MainForm UpdateHistoryItem calls Load_ListDDKLQ with the selected GPs certificate
row. Load_ListDDKLQ reads db_IDCs_ddk/db_ddk, filters certificate IDs, loads/sorts
number/date/issuance text and populates lbDDKLQ/lbDDKLQx. btnCapDDK_Click confirms,
calls Get_List_IDCCGPs/InsertNewDDKDB, writes certificate linkage in db_CC_Gps,
refreshes history/facility lists or calls btnDieuChinhDDK_Click, then opens the
Facility page. Those workbook writes and implicit copy/relink semantics are not
ported into the read-only Case component.

Root cause: LinkedBusinessEligibilityCertificates reused generic certificate
chrome with no Case layout owner, generic caption/full-width list and individually
tabbable rows without arrow navigation. The Case owner now has an explicit grid,
compact upper-left list (about 46% of desktop width), correct caption/column
order and scoped blue selection. Existing canonical detail content remains below
the list in cyan inset values; its shared renderer and Facility presentation/actions
are unchanged. Desktop step content scrolls independently; narrow layout expands
before the unchanged scope panel. Long/null/multiline values remain readable.

Ownership: CaseWorkspace supplies read-only linked BusinessEligibilityDetail
snapshots. Catalog resolves them via GxP Certificate links to the selected
BusinessEligibilityVersion and returns all basis links. UUIDs and link roles are
retained, including equal display numbers; no client deduplication/relink/version
inference. Site issue/edit/promote readiness never becomes a Case mutation. No
new token, API, storage locator or workflow state; no business handler change.
One existing selected-certificate state remains, with useCertificateRows handling
focus separately. Valid selection survives props refresh/reorder; removed IDs
fall back to the first supplied item; empty/stale/loading/error contexts hide
details. Workflow/Facility unmount or full page reload still initializes the
local certificate selection from the first item, as before; history/line URL
identity is preserved. No certificate-selection URL contract is invented.

EVIDENCE_MISSING: Case-level issuance/edit/renew/promote owner/readiness (Site
owns these actions); expanded Case detail runtime geometry; immutable version IDs
and historical version collection in BusinessEligibilityDetail; contextual
document actions for this workflow step. Image 6 has no document workspace and
current case context specs define none for Chứng nhận ĐĐK. Keep no document
workspace here; F6/Shift+F6 document navigation is not applicable. Existing raw
issuance/replacement/status text is displayed, not parsed into history/actions.
Legacy activity tabs/completion ticks and implicit copying are not fabricated.

Regression evidence: on baseline, new presentation-owner and ArrowDown-focus
tests fail (2 failed / 5 passed); after the owner/CSS change, all seven pass.
Coverage includes hierarchy/labels, same-number UUID selection, focus-only arrows,
Home/Space, props replacement/reorder/removal, multiple same-number basis entries,
snapshot fields/null/multiline values, absence of Case mutation/document/editor
controls even with available Site action readiness, and stale/loading/error
context. Existing Site concurrency/draft and document identity/focus tests remain
unchanged and pass in the related suite.

Actual App with synthetic fixture API: 1920x1080, 1366x768 and 390x844. Checked
equal-number A/B selection, arrows/Home/End/Enter/Space, inert F2/Escape in this
read-only list, workflow/Facility round-trips, canonical history/production-line
URL, external URL Back/Forward and refresh. Held a Case A read, selected empty
Case B, then released A: no stale detail appeared. Focus/list/tab operations
cause no Case detail fetch or write; the deliberate Facility visit uses its own
list/detail/basis reads. Counters record zero mutations; full page navigations
and explicit history changes do refetch their canonical workspace.

Desktop page width equals viewport. Narrow page clientWidth 375 / scrollWidth
384 at viewport 390 is the unchanged header overflow (~9px); Case content and
long unbroken notes fit the pane and do not overlap the scope below. Evidence
outside git: case-ddk-parity-1920/1366/390.png, case-ddk-late-response-390.png,
case-ddk-request-counts.json and fixture harness. Real-backend integration,
binary storage, historical-version selection, screen-reader acceptance and
production UAT are unverified. No backend/DB/API/storage/RBAC changes, merge,
cherry-pick or deployment. This is partial presentation parity, not full legacy
business parity or closure of Issue #1.

Validation: typecheck, lint, all 346 frontend tests / 27 files and production
build PASS. Related Case/Site/document/modal tests pass 47 tests in each of three
targeted runs, including one after final CSS changes. No timeout increase,
disabled test or backend guard change; existing non-failing act warnings remain.
Diff: four frontend/QA files. Data/storage/security contracts and all other
workflow/Facility owners are unchanged. Next: audit Facility ĐĐK activity groups
only with approved evidence/contracts, or run authorized staging integration and
screen-reader verification against these completed Case slices.

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

Superseded history limitation: the new separate `/versions` GET supplies persisted
version UUIDs and their scopes; current GxpCertificateDetail remains independent; it exposes row_version and
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

### CAPA draft hydration stability follow-up — 2026-10-16

Historical behavior below is superseded for newer-version dirty/open/pending
drafts by the 2026-10-29 ownership correction below; cycle version is no longer
treated as an operation identity change.

Baseline `01416846c9d24ba476479c0d0bf5f2f7527f5bad` could overwrite command
input after an unrelated field editor closed because the passive hydration effect
reset the complete draft whenever no field was being edited, even when the
canonical CAPA cycle and `row_version` were unchanged. The same effect boundary
also allowed a superseded cycle-A mutation response to publish after an external
A → B → A selection sequence.

Hydration is now committed before paint only when the selected canonical
`capa_cycle_id:row_version` changes. Each such transition advances an operation
generation, so late update/submit/assess completion can no longer publish pending
state or errors into the replacement selection. Same-version rerenders preserve
input; a new server version intentionally rehydrates; 403/409/422 on the current
cycle preserve the draft and remain single-attempt mutations. This is an
interaction-stability correction only; legacy presentation and business/API
contracts are unchanged.

Regression evidence: the editor-close test failed on baseline with
`submitted_on` reset from `2026-09-05` to empty and passes after the owner fix.
Controlled A → B → A tests cover both late update and late submit conflicts.

### CAPA Case/cycle draft and request ownership — 2026-10-29

Baseline657f0ea7c854373d5b115172a47ac84c8aa75cb9. Same-version refetch and
explicit cycle replacement were already correct. New regressions demonstrate
that a newer row_version incorrectly closed an open editor, discarded input and
unlocked pending; create adopted a refreshed Case token and could keep its draft
or publish completion into a replaced Case. Returning from create to the same
selected row also leaked the new-cycle draft into an existing cycle editor.

Only CaseRemediationWorkspace state/handlers change: canonical Case+cycle UUID
owns the operation generation; hydrated draft version is independent. Dirty,
editing and pending input retains its token across refresh/409. Clean idle input
and successful callback/newer readback can hydrate; explicit Cancel or row
activation reloads current data. Create captures its Case token on opening;
Case/cycle replacement and unmount invalidate old completion. No auto retry,
extra action, status, limit on cycle count, document lookup or business rule.
409 text explains the retained token and explicit review/reset boundary.

RED6FAIL/14PASS plus same-row return RED1FAIL/20PASS. CAPA27 tests and targeted
Inspection/CAPA/Approval/document68PASS, including404/network errors, StrictMode, unsent draft,
refresh during pending, success readback and A→B→A late completion. Full and exact
CI counts are in the delivery PR. Final local frontend560PASS/0FAIL/0SKIP,
37files; targeted68PASS twice; typecheck/lint/buildPASS. Backend CAPA
contracts14PASS/74deselected, lifecycle/owner12PASS. The full run initially found
one outdated409-copy assertion; it now verifies the complete review guidance
without relaxing draft or request-count checks.
Controlled Edge1366x768/1920x1080/390x844 has scroll/client widths1366/1366,
1920/1920,390/390. Cancel Enter causes zero callbacks; five explicit fixture
commands/viewport keep tokens2/3 and Case8; no API requests or navigation writes.
Evidence `.codex/evidence/inspection-capa-20261029/` is outside Git.

FIXTURE_VERIFIED, not authenticated persistence, screen reader, full-shell
navigation or VBA runtime acceptance. Workflow-tab unmount still does not promise
draft restoration. EVIDENCE_MISSING remains supervision fields/notes provenance,
legacy concurrent editing behavior, authorized A/B readback, Word/NAS and legal
acceptance. CAPA Word remains BLOCKED_BY_TYPED_DOCUMENT_CONTRACT; metadata is not
binary/output proof. Existing narrow action-label clipping is not changed by
this state-only slice. Inspection/Approval refresh-token ownership needs its own
RED audit; no broad parity promotion or changes to those owners are made here.
The final CAPA file passes 14/14 in three independent runs, and the exact App
integration test from workflow `38789920326` passes 10/10 independent runs
without sleeps, retries, timeout changes or relaxed assertions.

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

## Deterministic React test synchronization follow-up — 2026-10-16

Baseline `aa59b3858816f4e0700fa8e39378a13cd250e714` passed all tests but CI run
`38796123840` emitted 25 React `act(...)` warnings: 24 from twelve App cases and
one from the document keyboard/focus case. Local reproduction emitted the same
document warning and 22 App warnings; the stale-history case was intermittent.
These warnings supersede the historical “act warnings remain” notes above.

The App warnings were test synchronization debt around SearchPage's intentional
one-microtask state-to-URL ownership boundary. Assertions or cleanup could run
before the queued SearchPage and MemoryRouter updates joined a React test
transaction. A focused test helper now flushes that named boundary after the
events under test. The document warning came from calling native `focus()`
directly; `fireEvent.focus` now owns the same focus event and resulting
`setFocusKey` update. No product component, routing behavior, request, mutation,
CSS or business contract changed.

The thirteen affected cases pass with zero warnings in ten independent targeted
runs. The final complete suite passes 435/435 in 32 files with zero stderr blocks
and zero `act(...)` warnings. No warning suppression, console mock, delay,
timeout increase, retry or relaxed assertion was introduced.

## Inspection-folder lookup context ownership — 2026-10-16

Baseline `aab8c7367c10357b2aa6f9dfca4a4e2d0ff660f5` kept lookup pending,
result and error as component-wide state. `CaseApplicationWorkspace` remains
mounted while the selected Case changes, so a late A response could publish in
B, keep B's button disabled, or let A-generation-1 overwrite A-generation-2.
The request callback reads the selected Case at `SearchPage`, but callback
reference changes are not business identity and the folder endpoint has no
AbortSignal contract.

Lookup publication is now owned by one state record with the full available
identity (canonical Case UUID, canonical Site UUID, legacy Site ID and legacy
inspection code) plus an operation generation. A context change invalidates the
owner before stale state can render; same-identity object refresh preserves the
current result. Success, infrastructure error and pending completion publish
only for the captured owner. `resolved`, `ambiguous`, `not_found` and `invalid`
presentation remains unchanged; no client-side folder fallback or StorageBinding
is introduced. Access/auth identity is `EVIDENCE_MISSING` at this component
boundary because no such value is provided by its current props or endpoint.

Regression evidence: seven new baseline assertions failed before the fix.
The final file passes 15/15 in three independent runs; the controlled
A → B → A reversed-response case passes 10/10 repeated runs. Coverage includes
late success/error, each identity field, same-context refresh, duplicate pending
click and focus-only navigation. Synthetic browser fixture evidence is stored
outside Git under `.codex/evidence/inspection-folder-ownership/`: at 1366×768
and 390×844, late A is absent, B is enabled, the second click produces request
2, only B's resolved path appears, and document scrollWidth equals clientWidth.
This is fixture verification only; authenticated backend, NAS, binary storage,
screen-reader acceptance and production UAT remain unverified.

## Authentication-bound workspace and folder lookup ownership — 2026-10-16

Baseline `5c450ef843a65495bb887fdcdc474c0f09a144f5` owned the selected
facility workspace only by facility/line identity. A credential change that
kept the same Case could therefore expose the previous access owner's workspace
in the first committed render, before passive cleanup ran. Inspection-folder
lookup ownership likewise had no access boundary, so a late result from the old
credential could publish into the same Case under the new credential.

`App` now issues an opaque, monotonic access generation whenever an OIDC
credential is accepted, removed or expires. Because the frontend has no
authoritative session/authorization revision, credential refresh is handled
fail-closed as a new generation. The generation contains no bearer token,
subject, email or other identity data and is not written to URL, DOM or logs.
`SearchPage` combines it with canonical facility identity and suppresses the
transitioning context in the first render; the subsequent authenticated search
produces exactly one new workspace read. `CaseApplicationWorkspace` adds that
generation to its existing Case/Site/legacy-anchor operation owner and disables
lookup when access is absent. Backend authorization and 401/403 semantics remain
authoritative and there is no automatic retry.

Regression coverage includes same Case A → B, logout during pending lookup,
role/access generation change, reversed A → B → A responses, harmless rerender,
current and stale 401/403, first-render workspace projection and request counts.
This is synthetic frontend evidence. Authenticated live backend/RBAC, token
refresh behavior against the deployed identity provider, NAS, binary storage,
screen-reader acceptance and production UAT remain unverified.

## Access-bound search result ownership — 2026-10-16

Baseline `76aa24b8053b461ceabfbd32ca89a6be129975f1` stored search rows,
total count, loading/error metadata and selected result independently of the
access generation that loaded them. The first committed render after credential
A → B therefore projected A's rows and selected key; passive effect cleanup was
the first incorrect boundary. A retained page-two offset could also start B at
A's pagination position.

`SearchPage` now owns status, rows, total count and error as one atomic request
record keyed by the opaque access generation, complete effective search/filter
identity and request operation. Pagination has its own query owner, so a new
access or filter starts at offset zero while pages for the same query append by
full `result_key`. A resolved deep-link row is additionally bound to its access
generation. Render projection excludes mismatched owners immediately; bearer
tokens and principal data are absent from owner keys, URLs, DOM and logs. The
existing API, backend authorization, UUID identity and keyboard behavior are
unchanged, and permission failures are not retried.

Regression failed on the baseline at the first B commit and passes after the
fix. Coverage includes loaded A → B, logout, late A success/error, reversed
A → B → A, access change after page two, explicit deep links and harmless
same-session rerenders. Synthetic actual-`SearchPage` browser evidence is stored
outside Git under `.codex/evidence/search-result-ownership/`. At 1366×768 and
390×844 the first B commit has zero rows and no selected row; requests are
A offset 0, A offset 100 and B offset 0. After explicitly selecting B, a
harmless rerender retains one row and one selection without another search.
Logout removes the table and B text. Document client/scroll widths are
1366/1366 and 390/390.

This is synthetic fixture validation. Real OAuth refresh, live RBAC/backend,
screen-reader acceptance, NAS/binary storage and production UAT remain
unverified.

## Master selection keyboard parity — 2026-10-18

Baseline `ec696ec21f9d72f3f5591a05566a857ad83de0c6`. MainForm FRX evidence
places `lbDsCoso` as the master list and `tbGMP` / `tbGLP` / `tbGMPbb` as its
GxP selector; the approved web exception preserves the current table, vertical
rail, action panel and palette. The latest user correction also keeps the
separate Lọc / Lọc dữ liệu surface removed, so this slice does not remount
`LegacySearchFilters` or invent unsupported FilterForm semantics.

The first incorrect web behavior was in `FacilityTable`: every facility row and
every `role="tab"` GxP control was a separate Tab stop, while Arrow/Home/End did
nothing. The owner now exposes one entry Tab stop for each group. ArrowUp/
ArrowDown and Home/End move facility-row focus; the vertical GxP rail additionally
accepts Left/Right and wraps at its ends. Focus movement does not change the
selected canonical result or GxP filter, so it cannot issue a request. Existing
click and native Enter/Space activation remain the only selection boundary.
The selected identity is the entry point when present; otherwise the first item
is used. An off-screen instruction describes the facility-row keys.

Regression evidence was RED on the baseline: all three tests observed tabIndex
`0` for every row/tab and no roving behavior. The same focused file passes 3/3
twice after the owner fix, covering exact result-key activation, focus-only
navigation, the active/selected entry points and missing-selection fallback.
Actual component + synthetic browser fixture at 1366×768, 1920×1080 and
390×844 records document client/scroll widths of 1366/1366, 1920/1920 and
390/390. Arrow navigation produced zero selection/filter callbacks; Enter issued
one exact result-key selection, then one explicit GxP activation. Browser network
traffic contained no mutation methods. The preserved desktop rail/table and the
existing narrow stacked presentation were visually checked. Screenshots,
measurements and the temporary harness are outside Git under
`.codex/evidence/master-keyboard/`; this is `FIXTURE_VERIFIED`, not live backend
validation.
Exact native MSForms key handling and screen-reader speech remain
`EVIDENCE_MISSING`; the web behavior follows the already-established History and
certificate workspace focus/selection contract.

### Master selection async focus continuity — 2026-10-19

Baseline `444f2fb354a4d0845e3429b990b7ab1d97dc76ff`. The previous roving-keyboard
slice kept its only `tabIndex=0` on the selected result/GxP value. Arrow navigation
moved DOM focus without moving that entry point, and removing the focused result
during an async result replacement left focus on the document body. Selection,
URL and request ownership were already correct; no `SearchPage` change was needed.

`FacilityTable` now owns focused row/GxP identity separately from business
selection. A surviving canonical `result_key` remains focused and is the sole row
Tab stop through append/reorder. If that identity disappears while the row group
still owns focus, focus moves to the nearest surviving row by its previous index;
an empty/loading list uses the named master-list region as a non-Tab fallback.
Search failures remain alerts inside that stable region, so a filter retains focus
instead of being unmounted. If focus already moved to another filter or workspace
control, result replacement does not move it back. None of these transitions
select a replacement result or invoke a request callback. Existing `SearchPage`
access/request sequence guards continue to reject late A → B → A responses.

The regression was RED on the baseline in four cases: focused row and GxP controls
were not the sole Tab stop, removed-row focus fell to `body`, and empty/loading had
no focus fallback. The focused component file is GREEN 9/9 twice; a separate
RED→GREEN `SearchPage` regression covers asynchronous search failure without
unmounting the focused filter. Coverage includes append, reorder, removal, missing
selected identity, filter ownership, empty/loading/error recovery, exact
`aria-selected` separation and GxP activation. Actual-component Edge fixture runs
at 1366×768, 1920×1080 and 390×844 record client/scroll widths of 1366/1366,
1920/1920 and 390/390. Reorder retains the focused key; removal uses the nearest
survivor; filter focus is not stolen; empty state focuses the named region; each
group retains one Tab stop. Focus-only steps issue zero HTTP requests and zero
selection callbacks, and the explicit GLP Enter activation issues one filter
callback. Evidence is outside Git under `.codex/evidence/master-focus-continuity/`.
This is `FIXTURE_VERIFIED`; authenticated real-backend behavior and screen-reader
speech remain `EVIDENCE_MISSING`.

### Master / history accessibility verification — 2026-10-19

Baseline `82885ac43105fb383ca926b966a4dedd2b00fa3a`. Browser accessibility-tree
inspection exposes the GxP rail as the named `Bộ lọc GxP` tablist with one
selected tab, the master as the named `Danh sách cơ sở` region and table, and
history as a named panel/table whose event-row name includes type, standard,
date and authoritative state. DOM verification confirms that `aria-selected`
continues to describe business selection while Arrow/Home/End only move focus.

Two defects were reproduced RED at their component owners. `HistoryTable`
derived its only Tab stop solely from selected history identity, so a focused
event that survived reorder ceased to be the Tab entry; removal dropped focus
to `body`. `FacilityTable` exposed visible loading/error text but no polite live
status or busy state for loading, completion and empty results. History now owns
focused event identity separately from selected identity, retains a surviving
canonical event UUID through reorder/append, moves removal focus to the nearest
survivor, and uses a named non-Tab history region when the list becomes empty.
It does not restore focus after the user has moved to another control. Master
search now has one atomic polite status for loading/ready/empty, `aria-busy` on
the stable master region and one assertive error alert, including a failed
pagination request while retained rows remain visible; the visible loading copy
is hidden from the accessibility tree to prevent duplicate output.

The RED run failed 4/18 assertions and the focused GREEN suite passes 18/18
twice. Actual-component Edge fixture at 1366×768, 1920×1080 and 390×844 records
client/scroll widths of 1366/1366, 1920/1920 and 390/390, one Tab stop per
roving group, stable focus across reorder/removal/empty, zero selection callbacks
and zero HTTP requests for focus-only navigation, followed by exactly one GLP
activation callback on Enter. Evidence is outside Git under
`.codex/evidence/master-history-a11y/`. This is `ACCESSIBILITY_TREE_VERIFIED`
and `FIXTURE_VERIFIED`. The available automation surface did not expose native
Microsoft Edge, Windows Narrator or NVDA, so actual speech remains
`EVIDENCE_MISSING` and must not be classified as `SCREEN_READER_VERIFIED`.
Authenticated real-backend behavior is `REAL_BACKEND_NOT_VERIFIED`; no Google
token or `header_stub` bypass was used.

## Access-bound certificate workspace ownership — 2026-10-16

Baseline `09cca33406ed8d19e8022631a643f9d794b57d1c` kept each Facility
certificate list, selected UUID, detail, readiness, basis list, pending state
and error in independent component state. Passive cleanup ran after commit. A
same-Site A → B selection therefore committed the previous certificate detail
once, and a new access generation could retain a same-UUID selection long
enough to start a detail read under the wrong owner.

`SearchPage` now projects both the GxP and ĐĐK workspaces only when their owner
matches the opaque access generation, canonical Site and GxP/ProductionLine
context, active certificate tab, canonical certificate UUID and request
operation. ĐĐK issue readiness and GxP basis data use the same boundary.
Request generations reject reversed A → B → A completion even when the UUID is
identical. The owner contains no token, email or principal data and is absent
from URL, DOM and logs. Existing edit/issue/promote payloads, expected-version
handling, draft behavior, HTTP 403/409/422 presentation and backend contracts
remain unchanged.

Baseline regressions failed for the first B commit in both workspaces and pass
after the fix. Coverage includes same-UUID access changes, logout during a
pending detail, late success, late HTTP 403/409, reversed A → B → A, selection
focus/request separation and unchanged request counts. Authenticated live
backend/RBAC, binary storage, screen-reader acceptance and production UAT are
still `EVIDENCE_MISSING`; browser checks in this slice use controlled frontend
fixtures only.
