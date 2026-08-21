# Storage Deployment Options

## Purpose
This document compares the viable backend-to-Synology storage access patterns after Phase 15 established that Cloud Run cannot use in-container SMB/Tailscale mounts as ordinary filesystem mounts.

## Options

### Option A: `cloud_run_tailscale_application_protocol`
Cloud Run keeps business logic behind `StorageService`, while `BridgeStorageAdapter` speaks an authenticated application-level protocol over Tailscale userspace networking to reach Synology-capable storage integration.

Pros:
- Best matches the requirement that business code should not know or depend on NAS transport details.
- Preserves the ability to swap Tailscale for site-to-site VPN later without rewriting the business layer.
- Avoids making Cloud Run NFS `no-lock` the owner of document-management semantics.
- Avoids committing to a separate long-lived bridge host before proving one is needed.

Cons:
- Requires an application-level storage client/protocol rather than simple in-process filesystem calls.
- Needs explicit evaluation of streaming, retries, large files, concurrency, timeouts, and NAS unavailability.
- Cloud Run + Tailscale userspace viability must be proven experimentally before it can be trusted.

When this is a good fit:
- the team wants transport-swappability without committing yet to a separate bridge host
- Cloud Run can reach Synology reliably enough through an application protocol over Tailscale
- repository work should continue now without provisioning more infrastructure first

### Option B: `external_bridge_host`
Cloud Run delegates file-touching operations to a private storage bridge service running on a dedicated host near Synology.

Pros:
- Keeps Cloud Run away from low-level NAS mount lifecycle, file-share quirks, and file-share client behavior.
- Usually gives the cleanest operational control if Cloud Run userspace networking or direct transport experiments prove weak.
- Still preserves the same `StorageService` boundary in the business layer.

Cons:
- Adds another infrastructure component to secure, deploy, patch, and monitor.
- Increases operational footprint, which the project prefers to avoid unless evidence shows it is necessary.
- Requires host placement, hardening, and lifecycle ownership outside the current app container path.

When this is a good fit:
- PoC A fails reliability, performance, or security requirements
- private connectivity is materially easier to operate from a host near Synology than from Cloud Run
- the team accepts one extra infrastructure adapter to preserve business-layer purity

### Option C: `nfs_volume` experimental only
Cloud Run mounts a private NFS export and the backend continues using filesystem-style `StorageService` operations directly.

Pros:
- Supported by Cloud Run today.
- Useful as a comparison transport or diagnostic path.
- Reuses the current filesystem-style adapter shape with minimal extra code.

Cons:
- Cloud Run NFS is explicitly `no-lock`.
- `no-lock` is not acceptable as the default production semantic owner for this document-management system without further proof.
- Startup health and request behavior depend on mount/network characteristics that the project does not want to entangle with business semantics.

When this is a good fit:
- experimental validation only
- transport comparison only
- temporary diagnostics only

## Current recommendation
- Current implementation direction: continue application and storage-contract development without provisioning a dedicated bridge host yet.
- First integration gate: PoC A (`Cloud Run -> Tailscale userspace networking -> Synology`) behind `BridgeStorageAdapter`.
- Fallback only if PoC A fails: PoC B with a dedicated external bridge host near Synology.
- `nfs_volume` is not the production baseline.

## Decision trigger
The project should only promote a storage path to production baseline when it proves:
- list/read/stream/write/create-folder/rename/move/checksum behavior
- large-file handling
- Vietnamese Unicode path handling
- interruption/retry behavior
- concurrent-operation behavior
- acceptable latency and timeout posture
- explicit NAS-unavailable failure behavior
