# Workflow mutation outcome recovery — backend contract gap

Status: **PROPOSAL / NO RUNTIME IMPLEMENTATION**  
Baseline: `94bb991c38876338b09c377215eb60613a602e37`  
Owners: Backend transaction/API design; frontend implementation remains Codex-owned.

## Reproduced contract limitation (source audit)

The workflow router authenticates the request, invokes a service mutation, calls `commit_or_409(session)`, then returns a resource projection. This ordering permits a committed transaction whose HTTP response is not received by the client. A 401/409/503 or lost response on subsequent readback cannot prove whether a *specific* prior command committed. A matching snapshot, `expected_version`, local pending registry or HTTP 409 is not a durable operation receipt.

Directly inspected paths:
- `backend/app/api/routers/workflow.py`: Case application upsert (lines 109–129); CAPA create/update/submit/assess (296–374); Change Request create/update and certificate-successor issuance (438–520).
- `backend/app/services/workflow.py`: `_assert_expected_version` handles stale resource versions (approx. 322–331); this is optimistic concurrency, **not** durable operation identity.
- Frontend recovery evidence PR #290: unknown-result lock survives Case switching within the current in-memory session; reload or access generation change remains unresolved.

This is an architectural gap, **not** proof of a duplicate-write incident in production. No authenticated Google A/B recovery UAT was performed as part of this audit.

## Contract decisions required before an implementation PR

| Axis | Owner decision needed | Fail-closed default |
|---|---|---|
| Operation identity | Which commands accept a server-recognized opaque operation ID and how it is generated and scoped | Do not infer identity from payload or version |
| Submission binding | Actor/OIDC subject, tenant/access generation, Case/Site, resource, command kind and request fingerprint | Reject mismatches without revealing another actor's operations |
| Atomic recording | Outcome record and business mutation must commit or roll back together | Never claim success from a pre-commit reservation |
| Duplicate semantics | Same ID/same payload, same ID/different payload, concurrent requests, uncertain network response | No automatic replay or duplicate business side effect |
| Status lookup | Authenticated, authorized lookup; terminal/unknown/in-progress states; redaction | No cross-actor/Case disclosure |
| Authorization drift | Recheck access on status lookup, changes to role/Case access or account identity | Fail closed; do not reuse old auth identity |
| Retention | Approved lifespan and archival/audit obligations, purge restrictions | No invented TTL |
| Rollback/revocation | Command outcome vs current resource state, later edits and supersession | A past success cannot certify the present version |
| HTTP response shape | Distinguish committed, rejected, conflict, and genuinely unknown; exact correlation | Never interpret 409 as successful replay without receipt |

## Suggested bounded proof suite (synthetic/disposable only)

1. Request accepted and committed, response dropped: same operation is lookup-resolvable without issuing the mutation again.
2. Request fails before commit: no durable committed receipt; retry behavior follows **approved** contract.
3. Concurrent duplicate same operation ID: at most one mutation effect; deterministic observable outcome.
4. Reused ID with different command/payload/Case/actor: fail closed.
5. Transaction rollback: no falsely committed outcome.
6. Actor deactivated or Case privilege revoked after commit: status query remains authorized and redacted.
7. Another actor changes the resource after initial success: operation receipt remains historical; current version remains distinct.
8. Wrong-user reauthentication: old operation cannot be resumed or queried without permission.
9. Application, CAPA, Inspection and Change Request commands each meet their own authorized scope.
10. PostgreSQL locking, restart/recovery and concurrent clients are verified with disposable DB, not mocked browser success.

## Non-goals and controls

- Do **not** add a client-only idempotency key, guessed unique constraint, retry loop or mutable global marker.
- Do **not** treat an existing resource GET 200, event audit row, `expected_version`, or similar payload as proof that one exact command committed.
- Do **not** change Case/Certificate issuance, GMP coverage adjudication, QĐKT provenance gates, schema, API, OAuth, permissions or deployment in this documentation PR.
- Preserve `AUTHENTICATED_UAT_BLOCKED` and `CUTOVER_NO_GO`.

## Engineering handoff

An implementation is **BLOCKED_PENDING_DOMAIN_AND_SECURITY_CONTRACT** until the decision table has an approved owner response. Once approved, start with a single low-risk mutation family, implement atomic server-side operation recording and authorized lookup with PostgreSQL concurrency tests, then expand to CAPA, Inspection and Change Request without introducing silent compatibility fallbacks.
