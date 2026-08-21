# ADR 0058: Tests use sanitized fixtures independent of production artifacts

## Status
Accepted

## Context
The repository intentionally ignores production `legacy/` and `artifacts/` because they contain large operator data and sensitive historical materials. Normal CI still needs to prove migration, document, and reconciliation semantics from a fresh checkout.

Earlier tests and runtime defaults still reached directly into repository-root `legacy/` and `artifacts/` paths. That made `pytest` depend on operator-only files that are absent in CI and in a fresh clone.

## Decision
- Normal tests must use committed sanitized fixtures under `tests/fixtures/`.
- Runtime helpers that load artifacts or template metadata must resolve their roots through injectable project-path helpers.
- Operator-mode tools may still default to real `legacy/` and `artifacts/` roots when those directories are intentionally present outside CI.
- CI must assert that a checkout does not contain production `legacy/` or `artifacts/` directories before running tests.

## Consequences
- Fresh-checkout test behavior is deterministic and repository-owned.
- Production-sensitive workbooks, templates, and generated artifacts stay out of Git.
- Migration/document tooling can still run against real operator data without changing business semantics for tests.
