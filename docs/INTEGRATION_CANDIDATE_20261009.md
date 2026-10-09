# GXP QLCL — Integration Candidate 2026-10-09

## Immutable source contract

- **Integration branch:** `integration/frontend-backend-20261009` — isolated; **not** `main`.
- Backend parent: `b5e0ebd7c5e047c4cdc8c7cdc206872b8b68cb14`.
- Frontend parent: `50576b0b383161e26e27b6cdc4a1a469aff1ae17`.
- Merge base: `7119c4d6847a1b30ba772c274b7d290ee746af47`.
- Pure two-parent merge: `69396dab3fd9d5be95ea2b86ccea34517d05009d`.
- Review of both parent diffs confirmed disjoint changed file paths
  (backend: 23, frontend: 22); no content-level conflict resolution
  or rewriting was necessary.
- Source ref invariants: both parents must remain ancestors of the
  integration candidate. `HEAD:frontend` **must equal** the frontend
  parent's `frontend` tree object byte-for-byte. CI enforces both.
- Follow-on integration-only commits may adjust CI/test/docs but may not
  modify product source, runtime database schema or published assets
  without an independent review and updated manifest.

## Validation gate

In this branch, GitHub CI runs backend unit/integration, frontend
typecheck/lint/tests/build, hygiene/locks and the explicit
`cross-head-integration` job. Unlike the backend-only branch, the
integration job uses the actual merged `frontend/` source directly,
not a secondary checkout. It verifies the exact Codex subtree, then
runs FastAPI on loopback, a disposable local PostgreSQL database,
temporary local storage and only synthetic document/case data.
The real merged frontend API client performs HTTP 200/403/404/409
tests, including optimistic-concurrency and storage-integrity
fail-closed cases. Chromium E2E exercises a synthetic inspector account,
document navigation and focus-only keyboard behavior at 1366x768,
1920x1080 and 390x844; screenshots are retained for 7 days.

The B6 PostgreSQL integration job may legitimately be skipped on this
branch by its existing branch policy. The absence of production SMB/
Synology, IAP or Google OIDC integration is **not** a PASS for those
concerns.

## Release controls — not yet approved

1. Confirm combined GitHub CI **completed/success** at this candidate
   commit; retain action logs and browser artifacts.
2. Audit application migrations against disposable PostgreSQL and
   separately plan backup/downgrade for any future production migration.
   No migration or schema change was introduced in this merge.
3. Provision a separate staging identity, hostname, database and
   storage root with explicit access policy before any external deploy.
   Do **not** expose `AUTH_MODE=header_stub` publicly.
4. Test actual Google OAuth/IAP allowlist, role boundaries, reverse-proxy
   `/api` mapping, real browser races, invalid document/stale-token cases,
   audit logs, monitoring, rollback and backup procedures on staging.
5. Perform NVDA/JAWS human screen-reader verification with authorized
   testers. Chromium automation does not validate speech output.
6. Require an explicit release/merge/deploy decision before modifying
   `main`, production VM, database or Synology.

This document is not deployment authorization. The CI environment
contains no durable/public staging URL or production credentials.
