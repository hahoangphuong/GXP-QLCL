# Frontend mutation recovery: backend contract gaps

Status: proposal for backend ownership; no operation identity, idempotency or status endpoint is asserted to exist. This is not authorization to retry. Review against the actual endpoint before implementation.

| Workflow / current mutation | Owner and current request | Current response and canonical readback | Unresolved outcome |
| --- | --- | --- | --- |
| Registration | `PUT /cases/{caseId}/application`, `PUT /cases/{caseId}/assessment`; Case and corresponding record, `expected_version` | Versioned mutation response; `GET /cases/{caseId}/workspace` | A lost response or failed GET cannot attribute the current row to this command. |
| Inspection | `PUT /cases/{caseId}/plan`, `/outcome`, `/outcome/period-segments`, `/team`; `POST /cases/{caseId}/outcome/final-evaluation` and `/transition`; Case and applicable record, `expected_version` | Mutation response; Case workspace GET | A newer row, same values, 409 or matching state cannot prove which actor or command produced it. Finalization and transition can have side effects. |
| CAPA | `POST /cases/{caseId}/capa-cycles`; `PUT /capa-cycles/{cycleId}`, `POST /capa-cycles/{cycleId}/submit` and `/assess`; Case for creation, cycle for changes; expected Case or cycle version | Cycle mutation response; Case workspace GET | An absent response cannot distinguish committed creation from no creation, especially after reload. |
| Approval | `POST /cases/{caseId}/approval-submissions/{stage}` and `POST /approval-submissions/{id}/complete`; Case, stage/submission and expected version | Submission mutation response; Case workspace GET | A similar or later submission does not prove a particular operation committed. |
| Change Request | `POST /sites/{siteId}/change-requests`; `PUT /change-requests/{id}`; detail/approval/transition and successor mutations under the Change Request APIs | Mutation response; `GET /change-requests/{id}/workspace` and facility workspace | A lost create response, update, transition or successor issuance cannot be attributed using the current version alone. |

Request types for these workflows expose resource identifiers and optimistic versions; they do not expose a general recoverable operation identity in the inspected frontend contracts. Other endpoints, including some document-related contracts, may have distinct idempotency support and must be assessed separately.

A successful authenticated GET establishes a resource snapshot, not the outcome of a specific uncorrelated command. HTTP 401 requires authentication; 409 reports a conflict under the endpoint contract; 503/network failure is not verification. Stale or wrong-owner GET responses cannot reconcile a newer selection. Duplicate creation, transitions or issuance can have side effects; a stale draft can overwrite newer data if version checks are bypassed. The frontend must not automatically retry or use a browser marker, timestamp, matching content, version or 409 as proof.

## Proposed backend capabilities

A server-issued or server-recognized operation identity, atomically bound to authenticated actor, Case, resource and command type, should support a durable transaction outcome and an authenticated operation-status lookup with explicit pending, committed, rejected/conflict and unknown states. Define bounded idempotency, payload mismatch and concurrency behavior through the approved backend contract. Authorization must prevent cross-user or cross-resource disclosure; do not expose an operation's existence to an unauthorized principal. TTL, retention, uniqueness, retry behavior and stale-marker handling require owner approval and are deliberately unspecified here.

After approval, test lost responses after commit and before commit, concurrent identical/different payloads, conflicting versions, operation lookup after reload and session renewal, wrong user/Case/resource/command, 401/403/404/409/503, storage or transaction failure, status lookup races and no cross-user data leakage. Frontend tests must verify no automatic replay, correct owner/generation, preserved draft and fail-closed behavior when status cannot be resolved. Real Google A/B UAT remains separate.

## Client envelope and status lookup: decisions required

For a future approved contract, the caller must be able to associate a server-recognized operation with the command type, canonical Site/Case and record identities, the reviewed `expected_version`, and the authenticated actor. The client access generation is a UI isolation boundary, not a durable principal identifier or proof of authorization. Define how a server-verified payload fingerprint is computed and how a reused identity with a different payload is rejected; no client hash or timestamp may substitute for a receipt.

The backend owner must specify atomic mutation-and-receipt persistence, how concurrent duplicate submissions are resolved, and a permission-checked status lookup whose result distinguishes pending, committed, rejected/conflict and genuinely unknown outcomes. Test lookup by a different principal and by a user whose authorization changed, loss of the write response after commit, failed or wrong-generation readback, session expiry, and same identity with different payload. Do not infer a committed operation from matching values, `expected_version`, HTTP 409 or a browser marker. Identity scope, payload canonicalization, retention/TTL, status visibility and replay policy are **design decisions required**, not approved implementation choices.

## Source audit and recovery contract proposal — 2026-11-03

**Status: OWNER DECISION REQUIRED.** Audited against `134d9b34f9bd8effab4761f896b9ac03e42aedb4`; this section proposes no approved API, migration, retention period, retry policy or implementation. Existing clients and endpoints are unchanged. `AUTHENTICATED_UAT_BLOCKED`, `DURABLE_RECOVERY_NOT_PROVEN`, `CUTOVER_NO_GO`, and QĐKT `UNVERIFIED_VERSION_BINDING` remain in force.

### Observed transaction and identity boundaries

`backend/app/api/routers/workflow.py` checks permissions, calls `CaseWorkflowService`, then `commit_or_409` before returning success. `get_session_from_request_factory` rolls back on exception; `StaleDataError` is translated to 409. The workflow audit helper adds and flushes `AuditEvent` in the same SQLAlchemy session; audit/row atomicity does not make an audit row a client-addressable operation receipt. `X-Request-Id` in `backend/app/main.py` is an HTTP logging/response correlation value; workflow calls do not bind it as a unique command key. It is not evidence of outcome or duplicate prevention. A success response contains audit identifiers for some mutations, but those identifiers are unavailable if the response is lost.

The production identity baseline is verified external identity resolved to database-backed `AppUser` and roles; permission checks below are observed route-level requirements. Per-object outcome-lookup authorization and a policy for permission changes have **not** been established. Do not equate a valid UUID, a session/access generation, or possession of a former credential with current authorization. `payload.model_fields_set` is used on partial updates: omitted and explicit null fields can mean different commands and must not be collapsed by a future fingerprint.

In a disposable PostgreSQL test, invoking the actual Change Request create route twice with the same synthetic payload after discarding the first committed response created two distinct requests and two audit records. This is **observed duplicate risk**, not a finding that legacy create is contractually idempotent. The safety expectation test fails at the count assertion; no operation identity was provided because the existing request contract has none. A route-level probe does not simulate a TCP response drop, Google OIDC, or a full browser reload.

### Mutation inventory

All rows below are **PARTIALLY_PROVEN** for the explicitly observed route, permission, version and request transaction facts, and **BLOCKED** for authoritative per-command recovery, stable operation identity, payload fingerprint and safe automatic replay. Service owner for these workflow routes is `CaseWorkflowService`; canonical outcome lookup by operation is absent. Audit events are recorded in the business transaction where the service invokes its audit helper; neither audit nor a later resource snapshot is a receipt attributable to an unknown caller operation. After timeout, network failure, a lost response, 401 or failed readback, outcome remains unknown: do not auto-retry. Stale UI responses are a separate client generation problem. Domain locking/version guards may reject or serialize specific races but do not establish command-level exactly-once semantics.

| Method and route | Aggregate / record owner | Route permission | Reviewed concurrency input | Duplicate and readback limitation |
| --- | --- | --- | --- | --- |
| POST `/sites/{site}/inspection-cases` | Site, new Case | `case.edit` | None in request | Creation can have side effects; snapshot does not attribute command. |
| PUT `/cases/{case}/application` | Case/application | `case.edit` | Optional `expected_version` | Version conflict is not proof of earlier commit. |
| PUT `/cases/{case}/assessment` | Case/assessment | `case.edit` | Optional `expected_version` | Same values and audit cannot identify an unknown command. |
| PUT `/cases/{case}/plan` | Case/plan | `inspection.edit` | Optional `expected_version` | A lost response leaves outcome unknown. |
| PUT `/cases/{case}/outcome` | Case/outcome | `inspection.edit` | Optional `expected_version` | Outcome can advance independently of this command. |
| PUT `/cases/{case}/outcome/period-segments` | Case/outcome and segments | `inspection.edit` | Optional `expected_version` | Replacement and event effects are not operation-receipted. |
| PUT `/cases/{case}/team` | Case/team and members | `inspection.edit` | Optional `expected_version` | Same displayed team is not command evidence. |
| POST `/cases/{case}/outcome/final-evaluation` | Case/outcome | `inspection.edit` | Required `expected_version` | Terminal eligibility/version guard does not prove a lost result. |
| POST `/cases/{case}/approval-submissions/{stage}` | Case/new PCT or CT submission | `inspection.edit` | No expected version in request | New record and audit may be duplicated; validate actual domain guards separately. |
| POST `/approval-submissions/{id}/complete` | Case/submission | `inspection.edit` | Required submission `expected_version` | A conflict does not attribute a prior completion. |
| POST `/cases/{case}/capa-cycles` | Case/new cycle | `capa.edit` | Optional `expected_case_version` | Created cycle cannot be attributed to a lost response. |
| PUT `/capa-cycles/{id}` | Case/cycle | `capa.edit` | Required cycle `expected_version` | Concurrent state/version guard is not a receipt. |
| POST `/capa-cycles/{id}/submit` | Case/cycle | `capa.edit` | Required cycle `expected_version` | A later submitted state does not identify actor/command. |
| POST `/capa-cycles/{id}/assess` | Case/cycle | `capa.assess` | Required cycle `expected_version` | Assessor and audit are not a client operation ID. |
| POST `/sites/{site}/change-requests` | Site/new Change Request | `change_request.edit` | None in request | Duplicate creation demonstrated in disposable PostgreSQL. |
| PUT `/change-requests/{id}` | Change Request | `change_request.edit` | Required aggregate `expected_version` | Lost update cannot be attributed from version/snapshot. |
| POST `/change-requests/{id}/details` | Change Request/new detail | `change_request.edit` | Required aggregate `expected_version` | Guard does not prove which command created a detail. |
| PUT `/change-request-details/{id}` | Change Request/detail | `change_request.edit` | Required aggregate `expected_version` | Detail and parent ownership must both be bound. |
| PUT `/change-requests/{id}/approval` | Change Request/approval | `change_request.approve` | Required aggregate `expected_version` | Different operation may produce matching approval. |
| POST `/change-requests/{id}/transition` | Change Request | Permission depends on target state | Required aggregate `expected_version` | Transition and audit do not supply operation lookup. |
| POST `/change-requests/{id}/certificate-successors` | Change Request/affected artifact/new GxP | `change_request.edit` + `certificate.issue` | Required aggregate `expected_version` | Existing lineage/locking protects particular races, not a durable outcome API. |
| POST `/change-requests/{id}/business-eligibility-successors` | Change Request/affected artifact/new ĐĐK | `change_request.edit` + `certificate.issue` | Required aggregate `expected_version` | Same distinction; do not infer issuance from a matching artifact. |
| POST `/sites/{site}/certificates` | Site/optional Case/new GxP | `certificate.issue` | No expected version in request | Issuance can create an independent version/event. |
| PUT `/certificates/{id}/latest-version` | GxP certificate/version | `certificate.edit` | Required certificate `expected_version` | A current version cannot identify an uncorrelated write. |
| POST `/certificates/{id}/promote-current` | GxP certificate/Site | `certificate.approve` | Required certificate `expected_version` | Promotion conflicts are not attribution. |
| POST `/sites/{site}/business-eligibility-certificates` | Site/new ĐĐK | `certificate.issue` | None in request | New certificate and links can be duplicated. |
| PUT `/business-eligibility-certificates/{id}/latest-version` | ĐĐK/version | `certificate.edit` | Required certificate `expected_version` | Current values are not a receipt. |
| POST `/business-eligibility-certificates/{id}/promote-current` | ĐĐK/Site | `certificate.approve` | Required certificate `expected_version` | Existing state does not identify a command. |
| PUT `/cases/{case}/evaluation-scope` | Case/scope | `case.edit` | Required `expected_version` | Scope is serialized after commit; a readback failure can follow a committed write. |
| POST `/cases/{case}/transition` | Case | `case.edit` | Required Case `expected_version` | Terminal state/eligibility locking is not a replay receipt. |

### Candidate contract for owner review — not implemented

A future versioned, opt-in command envelope could carry a cryptographically random caller-generated operation ID, stable across a deliberate replay; command type, canonical owner identifiers and reviewed version must be verified by the server, not trusted from duplicated client fields. Resolve authenticated `AppUser` server-side. Compute a server-side, versioned canonical fingerprint covering route/command type, resource owner, expected version, semantically relevant payload and field presence. Exact canonicalization, digest/key policy, uniqueness scope and handling of evolving schemas require approval; never log raw sensitive payload or bearer credentials.

An example *shape for discussion only* is `GET /operations/{operation_id}` under an authenticated API, returning a minimal authorized status and, only when policy permits, the affected canonical IDs and committed version. Existing mutation requests could opt in through a versioned envelope or header, subject to backwards-compatibility review. This is not a registered endpoint or permission grant. Check both principal binding and current permission/object access, including Site/Case, before disclosing existence or content; define non-enumerating denial behavior and whether same-principal reauthentication preserves access. Revocation, impersonation and administrator access require explicit owner decisions. An access-generation value is client-local and cannot authorize lookup.

| Observation | Safe frontend decision before an approved protocol |
| --- | --- |
| Successful mutation response | Treat returned result according to existing endpoint contract; still guard UI owner and generation. |
| 401, 403, 409, timeout, connection loss, failed readback | Do not infer whether a prior unknown command committed; do not silently resend. Present review/recovery guidance without disclosing another user's data. |
| Future authorized receipt says `COMMITTED` | Only after atomic transaction and binding are proven, consume the minimal outcome for the same principal/resource/command. |
| Future `REJECTED` | Only claim a durable rejection if a separately specified, atomic protocol actually persists the rejection; ordinary rolled-back validation/authorization errors do not do so. |
| Future `NOT_FOUND` | Does **not** prove a request cannot commit later. Do not retry without an approved admission/fencing protocol. |
| Future `UNKNOWN` or lookup unavailable | Remain unresolved; do not manufacture success or retry. |
| Future `IN_PROGRESS` | Expose only if a durable reservation protocol and crash/lease/expiry semantics have been designed and proven. An uncommitted row is not durable in-progress evidence. |
| Same operation ID, different actor, owner, type, version or fingerprint | Must not execute as the same operation; exact response and disclosure rules require security approval. |

Atomic mutation + committed receipt requires persistence in the same database transaction and a uniqueness/serialization mechanism proven under concurrent PostgreSQL sessions. A rejected command normally rolls back that transaction; persisting rejection requires a separately designed boundary and must not assert it reflects a transaction that later commits. Concurrent duplicates, rollback after receipt preparation, commit with lost response, late lookup, prior request still in flight, and permission revocation all require explicit tests. Existing audit does not settle these questions.

**Decision blockers:** retention and cleanup; uniqueness scope and operation ID generation; canonicalization/versioning and fingerprint secrecy; authorization and response minimization; rejected/in-progress persistence; pre-commit admission/fencing and crash handling; replay policy and whether lookup may reveal not-found; and migration/rollout/rollback. A durable receipt table/index and Alembic migration are likely, but neither schema nor public API is approved. A vertical slice must define its transaction owner, select an endpoint, preserve legacy clients and prove PostgreSQL concurrency, atomicity and authorization before merge or runtime use.

Required backend tests: commit with dropped response, same-key same/different payload and actor, concurrent duplicates, permission revocation, wrong Site/Case, old versus new command, terminal Case race, rollback after receipt preparation, lookup concurrent with commit, no duplicate audit/event, and readback failure. Required frontend tests: owner/generation and A/B identity boundaries, reload/re-auth with no credential persistence or blind retry, unknown and not-found states, delayed lookup, draft/version retention and no data leakage. These are acceptance requirements, not claims of existing support.
