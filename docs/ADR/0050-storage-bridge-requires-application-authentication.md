# ADR 0050: Storage bridge requires application authentication

## Status
Approved

## Context
Private networking is necessary but not sufficient for a storage bridge that can list, read, write, move, and rename regulated document files. A private bridge without caller authentication would still expose high-value file operations if network boundaries were misconfigured or reused.

## Decision
- Storage bridge requests must carry authenticated application-level identity.
- Signed short-lived tokens or equivalent service-to-service identity are required.
- Plain network location or Tailscale reachability alone is not an authorization boundary.
- Bridge implementations must avoid logging token secrets.

## Consequences
- Bridge deployment now needs secret/config-managed signing material or equivalent identity integration.
- Browser clients must never call the bridge directly.
