# ADR 0053: Production RBAC is database-backed

## Status
Accepted

## Context
Production bootstrap already required `AUTH_ROLE_SOURCE=database`, but runtime authorization still depended on env role maps and default-role fallback.

## Decision
- In production-compatible mode, authorization owner is:
  - external authenticated identity
  - `AppUser`
  - `AppUserRole`
  - `RbacRole` / permissions
- Authenticated but unprovisioned users fail closed with `403`.
- `AUTH_ROLE_MAP` remains for local development, tests, and controlled bootstrap only.

## Consequences
- Provisioning users/roles becomes a database concern instead of environment config drift.
- Route authorization can move from coarse role strings toward permission checks.
- Startup validation rejects env-owned production authorization.
