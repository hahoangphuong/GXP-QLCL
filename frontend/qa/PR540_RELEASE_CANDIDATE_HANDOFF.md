# PR #540 — Release candidate handoff

Status: `FRONTEND_CODE_FROZEN_UAT_PENDING` once the exact-head required CI
created by this handoff commit is green. This is a code-level freeze only, not
authenticated operator UAT approval.

## Source boundary

- PR: `#540` (`codex/excel-vba-ui-redesign-20261115`, Draft)
- Main baseline: `3316e29f71817eae681d6ac8a787dc3c8d1eae99`
- Integrated candidate code: `a5354605` (ordinary merge of the current main)
- Required CI: the exact PR-head CI run created after this handoff is committed;
  it must pass the frontend, cross-head integration, PostgreSQL, backend shard,
  hygiene and required-gate jobs before operator UAT begins.

The merge includes server-side service-owner authorization from PRs #549–#552,
persisted current-team revision ownership for QĐKT from PR #553, canonical
read-only PCT/CT document recovery from PR #554, and persisted
Initial/Reassessment readiness from PR #555. No frontend permission fallback
exists: all enabled controls derive from the current canonical
readiness/permission response. The QĐKT panel remains read-only: current Case
team/revision is neither an issued-decision team nor render authorization.

## Supported operator journeys

1. Search → Facility/ProductionLine → History → Case, with URL persistence and
   explicit keyboard activation.
2. Case application, KHKT, inspection team/outcome, CAPA and PCT/CT history,
   including Case A → B → A stale-response fencing.
3. Case Certificate/ĐĐK read/issue readiness, then return to canonical history.
4. Change Request header/detail/approval/state/successor paths, only when
   backend readiness permits the action.
5. Reports → canonical Case/Change Request/document return navigation.

Focused regression after the latest merge covers Case lifecycle and application,
evaluation scope, KHKT/outcome/period/team, CAPA, Change Request, PCT/CT binding,
certificate issue and QĐKT readiness/current-team ownership. It includes 403,
409, 422, terminal/readiness gating, expected-version binding, duplicate-command
prevention and Case A → B → A fencing.

PCT/CT recovery remains bound to the canonical `approval_submission_id` and its
persisted binding/document identities: a timeout or unknown outcome never
replays the mutation, synthesizes a candidate, or moves a document between
rounds/Cases. Initial/Reassessment readiness remains advisory and context-bound
to persisted Company/Site/ProductionLine UUIDs; a changed or occupied context
must be re-read rather than forced through a stale readiness result.

## Candidate validation

- No frontend product-code change was required for PRs #554/#555: the existing
  owners already keep the unknown-outcome lock, exact approval-submission
  identity, Case/round fencing, and canonical Company/Site/ProductionLine UUID
  context.
- Targeted regression on the integrated candidate: 7 files / 86 assertions
  green (`ApprovalRoundDocuments`, `CaseApprovalWorkspace`, initial-Case
  creation/routing/action, Facility table, and History table). It includes
  Case A → B → A, PCT/CT lineage, recovery-lock, no-POST-replay, and
  keyboard/selection checks.
- Local TypeScript typecheck, ESLint, and production build are green. The exact
  PR-head CI URL is recorded in the PR and release handoff report after this
  commit is pushed; its required checks, not the previous candidate's CI, are
  the freeze gate.

## Preconditions for authenticated UAT

- Deploy the exact approved candidate SHA, or a documented descendant, to an
  approved disposable rehearsal environment.
- Record deployed SHA, API readiness result, schema revision and current auth
  mode before any test. Candidate and runtime source must be aligned.
- Provide an approved Google OIDC browser session and authorized synthetic
  actors for the tested permissions. Do not supply credentials, cookies or
  tokens in this document or its evidence.
- Use only designated synthetic records for mutations; retain the canonical
  UUID, initial row version, request/result and GET readback as redacted
  evidence.

## Read-only UAT checks

For each journey: confirm selected Site/ProductionLine/Case UUID, browser
Back/Forward and URL restoration, blocked-readiness explanation, keyboard
focus return, loading/error state, and A → B → A late-response fencing. A
read-only check must not issue a mutation simply by changing tabs, rows or
focus.

## Disposable-only mutation checks

Use backend-provided readiness and permissions to exercise one allowed Change
Request operation and each allowed CAPA action (create/update/submit/assess),
then record canonical readback. Separately prove 403, 409 and 422 behavior:
the draft is preserved where the existing contract says it is, no blind retry
occurs, and an uncertain outcome remains locked until canonical recovery.

## PASS / FAIL / BLOCKED

- **PASS:** exact candidate/runtime identity, required CI green, operator action
  matches backend readiness, canonical readback agrees, and no stale/duplicate
  mutation occurs.
- **FAIL:** an enabled action bypasses readiness, wrong UUID/context is shown,
  a stale response replaces current state, or a command is replayed.
- **BLOCKED:** no approved authenticated candidate session, runtime SHA/schema
  mismatch, unavailable browser automation, missing server contract, Word/NAS
  binary path, or native screen-reader evidence.

## Candidate identity and main compatibility

- **Frozen candidate:** `419fef55c788dfde3f61001fd9adc7ea2d25863c`.
- **Exact-head CI:** [run 43778464751](https://github.com/hahoangphuong/GXP-QLCL/actions/runs/43778464751), SUCCESS (10/10): frontend, cross-head Chromium/API fixture,
  hygiene, three backend shards, PostgreSQL gates, B6 integration and required
  CI gate.
- **New main compatibility checkpoint:**
  `70d0004c9282bff450316e350379b5d600a5e935` (PR #556).
  Its persisted, no-autoflush Site lookup changes only backend Change Request
  create-readiness implementation. The public API shape, action key, UUID
  identity, permissions and frontend types are unchanged. Assessment:
  `NO_FRONTEND_INTEGRATION_CHANGE_REQUIRED`; main is deliberately not merged
  into the frozen candidate merely to advance a SHA.
- **Candidate identity:** `CANDIDATE_IDENTITY_VERIFIED`. The frozen executable
  candidate is `419fef55`; any later PR head is permitted only as a
  documentation-only descendant and must not alter frontend product code. The
  only local untracked path is `.codex/` evidence.

## 2026-11-16 backend-main compatibility preflight

**Backend checkpoint examined:**
`a8b6cd13bbe243e0440c9aaccb89ca51354ff272` (PRs #558–#563). Direct source
comparison from `70d0004c` to that checkpoint changes only
`backend/app/services/workflow.py` and backend regression tests. It changes
readiness implementation from cached ORM refreshes to persisted scalar reads
inside `no_autoflush`; it does not change API routes, request/response schemas,
frontend TypeScript types, permissions, action keys, reason-code vocabulary, or
optimistic-version fields. This is source evidence, not a substitute for an
authenticated HTTP run.

| Contract | Classification | Evidence and frontend outcome |
| --- | --- | --- |
| Change Request create/action readiness; Site/Company root ownership | `COMPATIBLE_WITH_EVIDENCE` | #558/#560 use persisted root/Site and target projections only. `ChangeRequestMutationWorkspace` sends backend readiness `expected_version`, preserves dirty intent, fences A→B→A, and never derives owner identity from labels. |
| Affected/issued artifact links | `COMPATIBLE_WITH_EVIDENCE` | #559/#560 retain canonical certificate/ĐĐK IDs while reading links from committed scalars. Existing Change Request regressions assert target-owned tokens, exact successor identity and no late-result cross-owner change. |
| ĐĐK issue and version/current readiness | `COMPATIBLE_WITH_EVIDENCE` | #561/#562 preserve Site UUID, action keys and tokens while eliminating draft autoflush. `BusinessEligibilityWorkspace` tests cover unavailable readiness, exact parent token, 403/409/422, refresh, version edit/promotion and Site A→B→A. |
| GxP certificate version/current readiness | `COMPATIBLE_WITH_EVIDENCE` | #563 preserves certificate/site/Case/line validation and response shape using persisted projections. `CaseCertificateIssueWorkspace` retains typed drafts, blocks duplicate/unknown issuance, and fences Case A→B→A. |
| PCT/CT canonical document recovery | `COMPATIBLE_WITH_EVIDENCE` | Candidate recovery remains keyed by `approval_submission_id`, persisted document/binding IDs and expected version; `ApprovalRoundDocuments` rejects stale/ineligible bindings and unknown-outcome replay. |
| 401/403/404/409/422, timeout and binary/document isolation | `COMPATIBLE_WITH_EVIDENCE` for synthetic behavior | Read-only probe records failure status without server details/retry; workspace regressions retain draft/lock behavior. Authenticated runtime and binary storage behavior are `ENVIRONMENT_BLOCKED`. |
| Exact frozen frontend against backend `a8b6cd13` over authenticated HTTP | `ENVIRONMENT_BLOCKED` | Rehearsal runtime SHA differs and no approved candidate deployment/OIDC actor exists. This is not a frontend defect or a test-coverage waiver. |

No item is currently classified `FRONTEND_DEFECT` or
`BACKEND_CONTRACT_QUESTION`. No QA-only code PR was created: the existing test
and preflight owners already cover the observable contract, and adding a
duplicate harness would not increase confidence.

### Executed synthetic and preflight evidence

- `pnpm test --run src/qa/rehearsalSmoke.test.ts
  src/features/search/BusinessEligibilityWorkspace.test.tsx
  src/features/search/CaseCertificateIssueWorkspace.test.tsx
  src/features/search/ChangeRequestMutationWorkspace.test.tsx
  src/features/search/ApprovalRoundDocuments.test.tsx
  src/features/search/InitialCaseCreationDialog.test.tsx`: **165/165 PASS**
  across 6 files.
- `src/qa/rehearsalSmoke.ts` is the executable read-only, fail-closed preflight
  harness. Its 24 assertions prove GET/HEAD-only behavior, one in-flight owner,
  canonical Site/line/Case/document/version identity, no filename deduplication,
  no anonymous OIDC fallback, and non-disclosure of sensitive response detail.
  Fixture output is deliberately `FIXTURE_ONLY`, never authenticated UAT.
- The live preflight below was read-only and did not invoke this fixture mode,
  login, mutation, document binary, or storage operation.
- `pnpm typecheck`, `pnpm lint`, and `pnpm build`: **PASS** on the frozen
  frontend source plus this documentation-only descendant. The existing Vite
  advisory that the production JavaScript chunk exceeds 500 kB remains a
  non-blocking warning; no limit was raised or warning suppressed.

To run the future authenticated read-only preflight, start the already provided
`qa/rehearsal.vite.config.ts` proxy only after an approved loopback tunnel is
verified, then run `runRehearsalSmoke()` from the existing signed-in browser as
documented in `frontend/qa/REHEARSAL_READ_ONLY.md`. A `BLOCKED` report is the
required outcome for missing session, empty fixture or identity mismatch; do not
substitute fixture mode for live authentication.

### Version binding table

| Component | SHA / revision | Evidence | Verification |
| --- | --- | --- | --- |
| Frozen frontend executable | `419fef55c788dfde3f61001fd9adc7ea2d25863c` | exact-head CI run 43778464751 | `CI_VERIFIED` |
| PR documentation baseline | `b8252d6de02473ff344249f980a33ab5b1b7d525` | docs-only diff from frozen executable | `CANDIDATE_IDENTITY_VERIFIED` |
| Backend main assessed | `a8b6cd13bbe243e0440c9aaccb89ca51354ff272` | #558–#563 source/API diff and backend CI checkpoint | `COMPATIBLE_WITH_EVIDENCE` |
| Rehearsal runtime | `3bd3c0eae4d118b8bb7b2fb1393a8764ea563107` | public read-only `/api/healthz` and `/api/app/status` | `ENVIRONMENT_BLOCKED` |
| Rehearsal schema | `20261113_0031` | read-only `/api/readyz`, actual equals expected | current only for old runtime; `ENVIRONMENT_BLOCKED` for candidate |

## UAT status vocabulary

| Status | Meaning |
| --- | --- |
| `NOT_EXECUTED` | Procedure designed but not run in an approved authenticated browser. |
| `SYNTHETIC_FIXTURE_VERIFIED` | Disposable CI/browser/API fixture ran; it is not real OIDC UAT. |
| `AUTHENTICATED_BROWSER_VERIFIED` | Approved operator session performed the browser journey. |
| `PERSISTED_RESULT_VERIFIED` | Canonical GET/readback and permitted audit evidence confirm the mutation. |
| `BLOCKED` | Required environment, authorization, data, or contract evidence is missing. |

## Workflow UAT matrix

All rows below are `NOT_EXECUTED` for authenticated UAT unless explicitly noted.
Use only approved synthetic records and record UUIDs/redacted evidence; never
infer identity from names, codes, filenames, or visible round numbers.

| ID | Objective / actor | Persisted preconditions and operator action | Expected result and evidence |
| --- | --- | --- | --- |
| UAT-CS-01 | Create Company/Site — `company.site.edit` actor | Approved synthetic company name; create once, then canonical GET. | UUIDv4 Company/Site relation persists; one intent makes one POST; audit receipt and redacted GET captured. |
| UAT-CS-02 | Unknown Company/Site outcome | Interrupt response after one authorized POST; do not repeat. | Recovery lock remains; GET proves result or remains unverified. No implicit GxP, Case, line or certificate. |
| UAT-CS-03 | Deactivate and select Site A → B → A | Two persisted Sites under authorized company. Navigate/filter without write. | Current UUID, URL, selected row and loading fence stay correct; no GET/mutation caused by focus only. |
| UAT-PL-01 | Create physical ProductionLine | Persisted active Site UUID; create two different physical lines, then canonical GET. | Each line has its own UUID distinct from display code; no implicit Case/certificate. |
| UAT-PL-02 | Invalid/reparent/concurrent line | Inactive/missing Site and a stale row-version fixture. | Readiness/POST deny with 403/409/422 as applicable; no reparent guess or UUID substitution. |
| UAT-CASE-01 | Initial Case | Active persisted Company → Site → ProductionLine UUID chain, eligible GxP. Create once. | Draft Case opens by returned UUID; backend readiness is advisory and mutation rechecks ownership. No implicit KHKT/certificate. |
| UAT-CASE-02 | Reassessment Case | Eligible source Case, valid selected history/GxP context. | Exact source Case identity is retained; stale/occupied context is blocked and read back, not forced through readiness. |
| UAT-CASE-03 | Case recovery / competing actor | Site A → B → A, concurrent change or lost create response. | Expected-version/409 behavior follows backend; no blind POST replay; canonical GET/readback decides outcome. |
| UAT-INSP-01 | Inspection plan/outcome/period/team | Persisted Draft Case and permissions for each available action. | Only readiness-enabled action is exposed; team revision is persisted and Case-bound; audit/readback retained. |
| UAT-INSP-02 | QĐKT distinction | Inspection data sufficient for draft/readiness only. | Draft decision is never displayed as approved decision; do not invoke Word renderer or infer issuance. |
| UAT-CAPA-01 | CAPA cycle lifecycle | Case with backend-enabled CAPA readiness. Create/update/submit/assess one permitted cycle. | Cycle ID and expected version remain stable; duplicate submit prevented; accepted/rejected/pending state is canonical. |
| UAT-CAPA-02 | CAPA recovery/navigation | Two cycles or Case A → B → A; pending/error response. | Draft ownership and document context remain per cycle; uncertain result is not retried blindly. |
| UAT-PCT-01 | PCT/CT creation/completion | Eligible Case, exact parent submission ID and allowed readiness. | PCT/CT identity and round lineage are backend-issued, never derived from display round number. |
| UAT-PCT-02 | Binding/recovery | Canonical `approval_submission_id`, exact eligible document ID/version; response-loss fixture if approved. | GET `/approval-submissions/{id}/documents` confirms persisted binding; no filename inference, synthetic candidate or POST replay. |
| UAT-PCT-03 | Round and Case fencing | PCT1 → PCT2 → PCT1 and Case A → B → A during delayed response. | Late response cannot replace current Case/round/document state. |
| UAT-CERT-01 | GxP/ĐĐK issuance | Case/site ownership, certificate issue readiness and authorized synthetic actor. | Candidate/current version follows backend readiness; GMP one-Case/one-Site/one-certificate invariant remains enforced. |
| UAT-CERT-02 | Version/history/filter | Multiple canonical versions and historical exception fixture. | Latest-version edit/promotion stays canonical; legacy exceptions read-only; no source/lineage inference. |
| UAT-CR-01 | Change Request create | Persisted Site UUID and backend create readiness. | PR #556 behavior: readiness observes committed Site state; stale/deleted Site cannot appear available from UI cache. No client fallback. |
| UAT-CR-02 | Change Request state/successors | Existing authorized synthetic request and expected version. | Header/detail/approval/transition/successor actions honor readiness, 403/409/422 and canonical successor identity. |
| UAT-NAV-01 | Search/Documents/Reports/history | Read-only authorized actor and seeded canonical records. | URL, Back/Forward, refresh, return queue and selected history restore exact canonical context; permissions remain read-only where denied. |

### Adversarial matrix applied to every mutation row

For every authorized write above, execute only if the environment owner permits
it: rapid duplicate activation, dialog close while pending, response timeout
after server commit, recovery GET with no result, refresh while recovery lock
exists, session expiry, 401/403/409/422, lost network, concurrent second actor,
persisted source change and workspace switch during a late response. Expected
behavior is one intent/one POST, no browser-derived recovery fallback, no blind
replay, no cross-Case/document transfer, and an explicit blocked/unverified
state until canonical readback resolves it.

## Operator runbook (Vietnamese)

### Before starting

1. Obtain written approval for an exact candidate deployment (or documented
   descendant), a disposable rehearsal database and named synthetic fixtures.
2. Record the deployed SHA, `/api/readyz` revision, auth mode and actor role.
   Stop immediately if SHA/schema differs from the approved record.
3. Confirm two approved Google OIDC actors where a permission/concurrency test
   needs them. Do not collect passwords, tokens or cookies in evidence.
4. Create an evidence folder outside source control. For each scenario retain
   timestamp, scenario ID, redacted URL, actor role, request result, canonical
   UUID/version and GET readback; preserve screenshots only where permitted.

### Read-only journey

1. Open Search, filter by the approved synthetic facility, select its canonical
   row and verify the URL/context.
2. Open history, Case, Documents and Reports; use browser Back/Forward and
   refresh once. Check that selected Site/ProductionLine/Case UUID does not
   drift and focus-only keyboard navigation creates no mutation.
3. Visit unavailable actions and permission-denied state. Capture their
   explanation. Do not attempt to bypass disabled controls or invoke APIs
   manually.

### Synthetic mutation journey

1. Run the applicable matrix row in dependency order: Company/Site → Line →
   Case → Inspection → CAPA → PCT/CT → Certificate/ĐĐK → Change Request.
2. Before each write, record readiness, canonical owner UUID and expected
   version. Submit exactly once.
3. Wait for the returned result; then perform the stated canonical GET/readback
   before continuing. If response is unknown, stop, retain the recovery lock,
   and use the documented GET only—never submit a second time.
4. For a negative case, use only pre-approved synthetic data. Capture 401/403/
   409/422 or network/session evidence and verify draft behavior defined by the
   existing contract.

### Stop conditions and prohibited actions

Stop on wrong SHA/schema, missing approval, unexpected real-data context,
identity mismatch, action enabled without readiness, cross-context response,
or any uncertainty about a mutation outcome. Do not operate production data,
run migrations/deployments, configure OAuth, use Word/NAS binary paths, invoke
QĐKT rendering, or claim an approval decision from a draft.

## Environment and deployment prerequisites

| Requirement | Current evidence | Gate |
| --- | --- | --- |
| Approved deployment authorization and rollback owner | Not supplied | `BLOCKED` |
| Candidate SHA or documented descendant deployed | Rehearsal remains at `3bd3c0eae4d118b8bb7b2fb1393a8764ea563107` | `BLOCKED` |
| Runtime/schema compatibility | Read-only probe: revision `20261113_0031`, schema current for old runtime | `BLOCKED` for candidate UAT |
| Google OIDC actors and role matrix | Not supplied | `BLOCKED` |
| Isolated synthetic fixture/data reset plan | Not supplied | `BLOCKED` |
| Storage/document/Word binary authorization | Not supplied; not part of this candidate acceptance | `BLOCKED` |
| Backup, rollback and operator escalation procedure | Must be approved by deployment owner | `BLOCKED` |
| Browser environment and evidence retention | CI Chromium fixture passed; authenticated browser not run | `NOT_EXECUTED` |

The read-only rehearsal probe on 2026-11-16 reported Compute Engine VM runtime
SHA `3bd3c0eae4d118b8bb7b2fb1393a8764ea563107`, ready schema
`20261113_0031`, Google OIDC mode, and unauthenticated `/api/auth/me` status
`401`. It performed no login or mutation. This runtime is older than the frozen
candidate and is not an authenticated candidate UAT environment.

## Current release gates and recommendation

- `FRONTEND_CODE_FROZEN_UAT_PENDING`: **met at code level** for frozen SHA
  `419fef55`; no frontend product change is pending.
- `UAT_PACKAGE_READY_ENVIRONMENT_BLOCKED`: **met**. This document supplies the
  procedures and evidence criteria, but the environment gates remain blocked.
- `AUTHENTICATED_UAT_BLOCKED`: **remains blocked**; no approved candidate
  deployment, authorized OIDC operator session, role matrix, or synthetic write
  scope exists.
- `DURABLE_RECOVERY_NOT_PROVEN`, `UNVERIFIED_VERSION_BINDING` and
  `CUTOVER_NO_GO`: **remain blocked**, not waived by fixture/CI success.

**Recommendation: NO-GO for deployment/cutover; GO only for preparing an
authorized disposable UAT environment.** The Technical Lead/deployment owner
must authorize a candidate deployment and rollback plan; the UAT owner must
approve actors, roles and synthetic records. Only then may an operator execute
the matrix and replace `NOT_EXECUTED` evidence with authenticated browser and
persisted-readback results.

Remaining non-frontend-contract gaps: QĐKT render/approved-decision source
contract (Issues #74/#144), full legacy FilterForm semantics, RecordForm runtime
evidence, document provenance/Word-NAS binary validation and native
screen-reader verification. These must not appear as available operator actions.
