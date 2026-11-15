# PR #540 — Release candidate handoff

Status: `CODE_INTEGRATED_RELEASE_CANDIDATE_UAT_PENDING`.

## Source boundary

- PR: `#540` (`codex/excel-vba-ui-redesign-20261115`, Draft)
- Main baseline: `f6d23b079d5bc355376932e8e99e0a59fc69e9f9`
- Integrated candidate code: `cad7914d` (ordinary merge of the current main)
- Required CI: the exact PR-head CI run created after this handoff is committed;
  it must pass the frontend, cross-head integration, PostgreSQL, backend shard,
  hygiene and required-gate jobs before operator UAT begins.

The merge includes server-side service-owner authorization from PRs #549 and
#550. No frontend permission fallback exists: all enabled controls derive from
the current canonical readiness/permission response.

## Supported operator journeys

1. Search → Facility/ProductionLine → History → Case, with URL persistence and
   explicit keyboard activation.
2. Case application, KHKT, inspection team/outcome, CAPA and PCT/CT history,
   including Case A → B → A stale-response fencing.
3. Case Certificate/ĐĐK read/issue readiness, then return to canonical history.
4. Change Request header/detail/approval/state/successor paths, only when
   backend readiness permits the action.
5. Reports → canonical Case/Change Request/document return navigation.

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
