# ADR 0044: Phase 16 planning assumption prefers external bridge

## Status
Superseded by ADR 0047

## Context
Phase 15 established two important facts:
- Cloud Run can mount NFS volumes over private networking.
- Cloud Run cannot rely on in-container SMB/Tailscale mounts for Synology access.

The project still has these fixed constraints:
- Cloud Run remains the application runtime.
- Synology remains the file binary system of record.
- Initial private NAS connectivity was expected to use Tailscale.
- Future site-to-site VPN must be swappable without business-layer change.
- All file operations must stay behind `StorageService`.

There are now two viable storage-access patterns for the backend:
- `nfs_volume`: Cloud Run mounts a private NFS export and keeps filesystem-style file IO in-process.
- `external_bridge`: Cloud Run delegates file-touching operations to a private storage adapter service that reaches Synology on the app's behalf.

## Decision
- For planning future phases, prefer `external_bridge` as the recommended long-term architecture target.
- Keep `nfs_volume` as the currently most executable direct-storage path already represented in repository bootstrap artifacts.
- Do not treat `nfs_volume` as the default production assumption unless operations can explicitly prove:
  - secure NFS exposure
  - acceptable startup reliability
  - acceptable no-lock semantics for the backend's actual file-touching workloads
- Continue keeping business and document logic transport-agnostic so either path can be swapped in without domain changes.

## Consequences
- The next storage-focused phase should define the bridge contract before attempting a final production storage rollout.
- Existing Cloud Run bootstrap examples for NFS remain useful as an executable fallback and comparison baseline.
- The repo now has a truthful split between:
  - what is easiest to bootstrap today (`nfs_volume`)
  - what best fits the long-term transport boundary (`external_bridge`)
