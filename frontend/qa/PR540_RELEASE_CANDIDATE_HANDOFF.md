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

## Current release gates

The public rehearsal probe is read-only only. On 2026-11-15 it reported Google
OIDC mode, runtime SHA `3bd3c0eae4d118b8bb7b2fb1393a8764ea563107`, and schema
revision `20261113_0031`; that runtime is older than this candidate, so it is
not an authenticated candidate UAT environment. `AUTHENTICATED_UAT_BLOCKED`
therefore remains.
Existing fixture and CI browser evidence is synthetic only; it is not evidence
of Google OIDC, real storage/Word output, or production acceptance.

Remaining non-frontend-contract gaps: QĐKT render/approved-decision source
contract (Issues #74/#144), full legacy FilterForm semantics, RecordForm runtime
evidence, document provenance/Word-NAS binary validation and native
screen-reader verification. These must not appear as available operator actions.
