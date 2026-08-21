# ADR 0010: Use a filesystem adapter for local and private-share roots

## Status
Approved

## Date
2026-08-13

## Context
The Phase 4 storage contract needs one adapter that can be exercised locally during development and also pointed at a non-production private share during Tailscale-based testing.

At this stage, the business layer should not care whether the root is:
- a local directory
- a mapped drive
- a UNC/private-share path

## Decision
- Introduce `FilesystemStorageService` as the named adapter for any host-accessible filesystem root.
- Keep `LocalStorageService` behavior as the underlying implementation for now.
- Construct the adapter from environment-driven root configuration.
- Treat UNC/private-share path handling as infrastructure configuration, not business behavior.

## Consequences
Positive:
- one contract implementation covers local tests and private-share tests
- adapter naming now better matches intended use
- future refactors can specialize UNC/share handling without changing callers

Negative:
- the current implementation still relies on host filesystem semantics
- real SMB/network locking behavior still needs non-production validation
