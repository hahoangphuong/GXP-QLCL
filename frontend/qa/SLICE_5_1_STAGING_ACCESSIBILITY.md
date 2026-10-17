# Slice 5.1 — staging integration and screen reader handoff

## Scope and prerequisites

This is a frontend verification plan, not a deployment instruction. Real-backend
integration and screen reader speech verification have **not been run** for this
remediation. Fixture results below do not establish production UAT readiness.

Before running integration, record the approved staging URL, frontend/backend
commit SHAs, provisioned least-privilege test accounts, and disposable synthetic
facility/production-line/history/document fixtures. Credentials stay outside this
document. Confirm that any permitted document generation uses dedicated test
storage and the existing backend StorageService path. Do not use production data,
change permissions, invent storage locators, or deploy to obtain a test environment.

Record browser/OS versions and the chosen NVDA or JAWS version. A human tester
must verify actual speech and browse/focus-mode behavior; DOM snapshots and unit
tests cannot replace this check.

## Integration matrix

Use the actual application and backend. Capture a sanitized network trace with
request timing/counts and exact fixture identities; exclude credentials and file
contents. Exercise only actions marked available by the backend. An unsupported
action is reported as unavailable, not simulated as a supported mutation.

| Scenario | Expected result and evidence |
| --- | --- |
| External deep link, Back/Forward, refresh | Facility ID, production-line UUID, history event and tab remain correct. Document selection is not restored by filename or prefix. Record actual URL and selection behavior. |
| Open A pending, select B, select A, release A | Superseded binary is never opened. A fresh explicit open can succeed after pending ends. Confirm no automatic retry. |
| Metadata A pending, B completes, select A again | Only the newest selected request owns detail/error. Use an approved test proxy to delay responses; record whether the browser allows the newer same-URL response to complete first. |
| Same context/slot, document A replaced by B during refresh | Valid B action reaches the backend while A remains pending; A completion/error cannot clear B's pending state. Preserve backend concurrency tokens. |
| Two checklist slots share one document ID | Each slot selection displays detail for the exact backend ID and matching family/parent. Shared filename/prefix is never a key. |
| Change facility, production line, history event while pending | No detail, error, binary open or focus restoration from the previous context. |
| Late 403/404/409 | Stale responses do not overwrite current detail or operation state. Current responses show the appropriate error, with no blind retry. |
| Real supported mutation conflicts | With approved disposable fixtures and two provisioned sessions, obtain a real 409 using the original concurrency token. Draft and token remain intact; explicit reconciliation precedes resubmission. Do not manufacture backend support. |
| Renditions and versions | Document ID, rendition ID, version ID and current flags match backend metadata. Binary access uses the existing backend endpoint; no client storage fallback. |
| Arrow keys, Home/End, F6, Shift+F6 | Focus changes independently of selection. Zero API calls caused by focus-only movement. Explicit selection/action has the expected request count. |
| Refresh with an unsaved form | Record draft preservation and concurrency token before/after refresh; no implicit submission or retry. |
| Permissions and missing data | Use provisioned accounts/fixtures for real 403/404. No additional access grant or destructive deletion to force the test. |

## Screen reader procedure

Run at 1366×768, 1920×1080 and a narrow viewport with the real application. Record
speech output and focus target for each step, including NVDA/JAWS mode changes.

1. Reach the document section by headings and table navigation. Confirm the
   section/table names, column headers, action button names and selected state.
2. Move with arrows/Home/End in focus mode. Verify that speech follows focus while
   selection and request counts remain unchanged. Enter/Space explicitly selects.
3. Use F6 to reach the detail heading and Shift+F6 or the return button to return
   to the selected list control. Confirm visible focus and sensible speech.
4. During delayed requests, confirm loading and error announcements are useful
   and focus is not stolen. Verify current 403/404/409 messages and stale-response
   silence. Check empty document and empty version states.
5. Repeat A → B → A, shared-ID slots and slot replacement. Speech, selection and
   detail must describe the current owner, including exact version/rendition IDs.
6. Check certificate dialogs with zero, one and multiple enabled controls,
   pending save, controls re-enabled, Escape, Cancel and trigger unmount. Focus
   remains contained; closing restores an existing trigger. A 409 retains draft.
7. Navigate/refresh with unsaved data and a pending operation. Confirm draft,
   token and focus behavior; record any limits separately from fixture coverage.

## Remediation evidence

- Baseline: `5770f1194aea2db51f7ebaad2dbe3b199722b248`.
- Before the owner fix: the three R1/R2/R3 regression tests failed (7 existing
  component tests passed).
- After the fix: typecheck, lint, build and 298 tests across 21 files passed.
  The 17 component tests passed in three consecutive targeted runs without
  increasing timeouts. App coverage exercises the actual SearchPage binary guard.
- Browser: actual ContextualDocumentSection with local HTTP fixture API at
  1366×768. R1 superseded binary count stayed zero; R2 issued one create request
  each for A and B and ignored late A 409; R3 issued two detail requests for the
  shared ID and displayed detail for selected slot B. Focus-only navigation
  issued zero requests.
- Browser late metadata 403: A → B → A completed with current A detail and no
  stale alert. The newer A response was not visible until the held older A
  response was released; the stronger out-of-order assertion is covered by
  deterministic unit tests. Stale 403/404/409 metadata and mutation cases are
  parameterized in those tests.
- Fixture harness uses a binary-open counter rather than an actual binary tab.
  Real SearchPage `window.open` rejection is checked in App tests. This browser
  fixture does not verify backend lineage, storage binding, real conflicts,
  authentication, full-app routing, assistive speech or production behavior.

## Acceptance record to complete

Record environment approval, fixture IDs, browser/reader versions, each matrix
result, sanitized request counts, speech/focus evidence and unresolved issues.
Real-backend integration, screen reader testing and production UAT remain separate
results. Staging URL, provisioned accounts, disposable data and reader choice are
currently awaiting environment details from the user.
