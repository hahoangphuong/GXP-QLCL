# ADR 0051: Bridge authentication modes are explicit

## Status
Accepted

## Context
The storage bridge can run in two materially different environments:
- Cloud Run / private Google infrastructure, where Google-issued OIDC identity is the correct ingress/auth primitive.
- Non-Google bridge hosts near Synology, where application-level signed tokens are still required.

Previous code mixed Google ID token fetch and custom HMAC token issuance implicitly, which made runtime behavior ambiguous and could produce mode mismatch failures.

## Decision
- Require explicit `BRIDGE_AUTH_MODE`.
- Supported values:
  - `google_oidc`
  - `hmac_jwt`
- `google_oidc` verifies Google-issued OIDC identity against the configured audience.
- `hmac_jwt` verifies issuer, audience, subject/client identity, expiry, and signing key.
- The bridge must not silently fall back between schemes.

## Consequences
- Cloud Run bridge and host bridge remain supported without changing business-layer code.
- Deployment config becomes clearer and fail-closed.
- Tests must cover mode mismatch and invalid-token cases per mode.
