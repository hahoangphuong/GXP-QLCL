# ADR 0052: Request boundary owns transaction commit

## Status
Accepted

## Context
Lower-level services previously called `session.commit()` internally. That allowed partial persistence inside larger use-cases, especially around storage binding, workflow mutation, and document-generation orchestration.

## Decision
- Commit/rollback ownership belongs to the top-level request/use-case boundary.
- Lower-level collaborators may call `session.add()` and `session.flush()` only.
- Conflict-at-commit cases such as optimistic concurrency failures map to request-level `409 Conflict`.
- Mutation routes must commit before returning a success response body so a stale-write failure cannot occur after the HTTP response has already started.

## Consequences
- Request-path integration tests become the source of truth for persistence semantics.
- Older unit tests that assumed service-level commit semantics must be updated.
- Audit rows, workflow mutations, and binding persistence now share one transaction boundary.
- Request-boundary helpers need explicit coverage for stale-update behavior at the API level, not only at service level.
