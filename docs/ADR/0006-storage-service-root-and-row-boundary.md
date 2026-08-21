# ADR 0006: StorageService root boundary and replaceable transport

## Status
Approved

## Date
2026-08-13

## Context
Legacy VBA directly uses Synology paths, shell operations, and Office desktop behaviors. The target system must preserve folder compatibility without leaking UNC paths, SMB details, or Tailscale transport concerns into the business layer.

The migration also needs a testable local backend before wiring a dedicated non-production NAS share.

## Decision
- All file operations go through `StorageService`.
- `StorageService` uses configured roots, not hardcoded UNC literals.
- Inspection folder resolution is keyed by:
  - `year`
  - `site_legacy_id`
  - `inspection_legacy_code`
- The resolver must fail closed on `0` or `>1` matches.
- Storage adapters must enforce root-boundary validation and reject path traversal.
- A local filesystem adapter is the first contract implementation for Phase 4.
- NAS transport details remain replaceable infrastructure concerns.

## Consequences
Positive:
- business code stays storage-agnostic
- contract can be tested locally before NAS integration
- future Tailscale-to-VPN swap does not require domain rewrites

Negative:
- adapter boundaries and configuration become mandatory plumbing
- some legacy file behaviors must be re-expressed explicitly instead of relying on shell side effects

## Open point
DDKD folder identity is still only partially evidenced. The current local adapter supports a provisional site-token-based resolver, but that rule must be confirmed against live NAS samples before production use.
