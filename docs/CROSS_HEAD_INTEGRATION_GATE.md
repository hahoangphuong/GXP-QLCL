# Cross-head frontend / backend HTTP integration gate

This is a **disposable CI integration gate**, not a merge, rebase,
staging deployment, or production UAT. It combines two independently
reviewed Git snapshots without changing either source branch.

- Backend owner branch: `chatgpt/backend-bridge-auth-20261009`.
  Initial reviewed baseline: `e51d45ca9d709d3659a38497597d0fffc5ac445b`.
- Exact Codex frontend revision: `50576b0b383161e26e27b6cdc4a1a469aff1ae17`.
  This SHA is pinned in the workflow, not inferred from a moving branch.
- Workflow: `.github/workflows/ci.yml`, job `cross-head-integration`.
  It only runs on pushes to the backend-owner branch. Both normal CI
  suites remain independent.

The GitHub runner boots an isolated PostgreSQL 16 service with the fixed
`gxp_qlcl_test` name and migrates it with the backend Alembic head.
A purpose-built Python fixture refuses to initialize unless opted into
`GXP_CROSS_HEAD_DISPOSABLE_GATE=1`, and requires loopback PostgreSQL
port 5432 with exactly that disposable database name. It creates only
synthetic company, site, case, document, document variant/version records
and one binary under a temporary `LocalStorageService` directory.
No live NAS, cloud database, external identities, or production host is
accessed.

An actual FastAPI server is launched on loopback. The workflow checks out
the exact Codex SHA under `cross-head-frontend/` (without editing its
tracked files). A backend-owned Vitest probe is copied temporarily into
the frontend checkout, imports its **real** `src/lib/api.ts`, and calls
the FastAPI server over actual loopback HTTP. The probe models the
deployment's `/api` proxy prefix stripping explicitly; requests outside
the expected prefix are blocked. The API client, not a mock, processes
JSON errors and binary responses.

## Covered checks

- Status API through the real client and real server.
- Document detail with exact synthetic document, parent and version UUID.
- Case-scoped binary read through the registered LocalStorageService,
  returning the exact fixture bytes and filename.
- Wrong parent / unknown document 404 responses.
- Missing current document binary 409, with a single network request.
- Persisted current-version binary missing on disk or checksum mismatch:
  409 with no binary response and exactly one network request.
- Reader role cannot call the case creation mutation (403).
- Real version-token 409 conflict: two distinct inspector identities
  update an application on a synthetic disposable case; an older token is
  rejected, the winning persisted value/version remains unchanged, and
  the client issues exactly one request without implicit retry.
- Case and facility workspace reads on synthetic UUID identities.
- Ref identity checked before and after the probe.

The client fixture is not a browser. This gate **does not** certify
real device focus/ARIA speech, NVDA/JAWS, navigation behavior, production
authentication/OIDC/IAP, real live-backend staging, legacy SMB/Tailscale,
simultaneous racing transaction ordering or browser draft persistence. Those
remain separate staging/UAT gates.

The selected frontend SHA changes **only** through a reviewed update
to this workflow. Do not auto-follow branch HEAD, auto-merge, swap
production credentials, or treat a green gate as deploy approval.
