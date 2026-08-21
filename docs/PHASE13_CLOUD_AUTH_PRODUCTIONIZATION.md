# Phase 13 Cloud Auth Productionization

## Goal
Replace the provisional Phase 9 header-stub trust model with a Google Cloud compatible auth boundary while preserving a simple local/dev path.

## Delivered
- backend auth adapter: [backend/app/auth.py](/D:/GXP-QLCL/backend/app/auth.py)
- config expansion: [backend/app/config.py](/D:/GXP-QLCL/backend/app/config.py)
- frontend auth-mode awareness:
  - [frontend/src/App.tsx](/D:/GXP-QLCL/frontend/src/App.tsx)
  - [frontend/src/lib/api.ts](/D:/GXP-QLCL/frontend/src/lib/api.ts)
- tests: [tests/test_phase9_authenticated_read_models.py](/D:/GXP-QLCL/tests/test_phase9_authenticated_read_models.py)
- ADR: [docs/ADR/0041-phase13-google-cloud-auth-uses-iap-jwt-first.md](/D:/GXP-QLCL/docs/ADR/0041-phase13-google-cloud-auth-uses-iap-jwt-first.md)

## What changed
- `header_stub` remains available for local/dev and compatibility tests.
- A new production-oriented auth mode, `google_iap_jwt`, now expects the signed `X-Goog-IAP-JWT-Assertion`.
- Server-side role assignment no longer depends on browser-supplied role headers in production mode.
- Optional identity-domain restriction is available through `AUTH_IAP_ALLOWED_EMAIL_DOMAIN`.
- Optional trusted-header fallback exists only behind explicit configuration and stays off by default.
- The frontend now fetches `/app/status` first and sends stub headers only when the backend reports `auth_mode=header_stub`.

## Config contract
- `AUTH_MODE`
  - `header_stub`
  - `google_iap_jwt`
- `AUTH_DEFAULT_ROLE`
- `AUTH_ROLE_MAP`
  - semicolon-separated `email=role` pairs
  - example: `alice@example.com=manager;bob@example.com=admin`
- `AUTH_IAP_EXPECTED_AUDIENCE`
- `AUTH_IAP_ALLOWED_EMAIL_DOMAIN`
- `AUTH_TRUSTED_HEADER_FALLBACK`

## Scope boundary
- This phase does not implement a full enterprise RBAC administration UI yet.
- This phase does not push Google Cloud infrastructure resources itself.
- This phase does not change business workflow, document generation ownership, or Synology access patterns.

## Operational note
`google_iap_jwt` requires the Python `google-auth` package at runtime for assertion verification. If it is missing, the backend now fails closed with a clear error instead of silently trusting weaker headers.
