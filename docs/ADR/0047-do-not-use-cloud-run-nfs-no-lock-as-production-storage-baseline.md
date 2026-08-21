# ADR 0047: Do not use Cloud Run NFS no-lock as production storage baseline

## Status
Approved

## Context
By August 20, 2026, the repository already supported three storage-related directions:
- filesystem-style adapters for local and private-share execution
- a bridge-backed runtime path for `external_bridge_http`
- Cloud Run bootstrap artifacts that could target NFS-backed storage access

However, the project has stronger invariants than "a file can be mounted and opened":
- business/application code must remain ignorant of NAS transport details
- Tailscale today and site-to-site VPN later must be swappable without business-layer changes
- Synology remains the file system of record
- the system is a GxP document-management workflow, so file semantics must not quietly degrade under concurrency or interrupted writes

Cloud Run's documented NFS mode uses `no-lock`. That is not sufficient evidence to make NFS the default production semantic owner for document operations such as write, rename, move, checksum, and concurrent access.

At the same time, the project prefers not to add a separate long-lived bridge host until evidence shows it is necessary.

## Decision
- Do not use Cloud Run NFS `no-lock` as the default production storage baseline.
- Keep all business-visible file operations behind `StorageService`.
- Standardize the adapter set as:
  - `LocalStorageAdapter` for development/integration
  - `Fake/MockStorageAdapter` for automated tests
  - `BridgeStorageAdapter` for production Synology integration
- Continue the current phase without provisioning a dedicated bridge host yet.
- Sequence integration work as:
  - PoC A: evaluate `Cloud Run -> Tailscale userspace networking -> Synology` through an application-level client/protocol hidden behind `BridgeStorageAdapter`
  - PoC B: only if PoC A fails reliability, performance, or security goals, deploy a dedicated storage bridge host near Synology
- Keep NFS support, if retained, experimental or comparison-only until locking, atomicity, and concurrent-write invariants are explicitly proven.

## Consequences
- The main application remains transport-agnostic and can proceed without hard-coding NAS details.
- Existing bridge runtime and deployment-pack artifacts remain useful, but as fallback infrastructure rather than the default next rollout.
- Future storage validation must explicitly test:
  - list/read/streaming download/streaming upload
  - create folder, rename, move, checksum
  - large files
  - Vietnamese Unicode paths
  - interruption/retry
  - concurrent operations
  - latency/timeout
  - NAS unavailable behavior
- Inspector desktop SMB/Word workflows remain a separate operational path and do not force the backend to use the same transport.
