# ADR 0041: Phase 13 Google Cloud auth uses IAP JWT first

## Status
Approved

## Context
Phase 9 introduced a provisional `header_stub` auth boundary so the backend could stop being anonymous before mutation APIs were added. That baseline was useful for local development, but it is not an acceptable production trust model for Google Cloud Run because request headers such as `X-Auth-User` and `X-Auth-Role` are caller-controlled.

The target deployment platform is Google Cloud. Official Google Cloud IAP guidance distinguishes between convenience identity headers and the signed `X-Goog-IAP-JWT-Assertion`. The signed assertion is the boundary that can be verified by the backend, while plain headers should not become the primary trust anchor.

The business/domain layer must remain unchanged if the private-network adapter later moves from Tailscale to site-to-site VPN. The same principle applies to auth: identity verification belongs in the edge adapter, not in workflow/document/storage services.

## Decision
- Production-compatible backend auth mode is `google_iap_jwt`.
- `google_iap_jwt` verifies `X-Goog-IAP-JWT-Assertion` against the configured IAP audience before creating an application user.
- Role assignment is server-owned through `AUTH_ROLE_MAP` plus `AUTH_DEFAULT_ROLE`; the browser does not submit authoritative roles in production mode.
- `AUTH_IAP_ALLOWED_EMAIL_DOMAIN` may constrain accepted operator identities to the expected Google Workspace domain.
- `header_stub` remains available only for local/dev and explicit non-production test flows.
- A trusted-identity-header fallback exists only as an explicit escape hatch via `AUTH_TRUSTED_HEADER_FALLBACK=true`; it is off by default and does not replace JWT-first design.
- Frontend behavior must key off backend-reported `auth_mode`, sending stub headers only when the backend declares `header_stub`.

## Consequences
- Production no longer depends on forgeable browser-supplied role headers.
- The auth adapter is now aligned with Cloud Run behind Google Cloud IAP.
- Missing IAP verifier dependency or missing expected audience becomes an explicit fail-closed error instead of silent downgrade.
- Operator onboarding now needs environment configuration for IAP audience and role mapping.
- Local development remains simple because `header_stub` still exists.
