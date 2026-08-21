# ADR 0043: Phase 15 Cloud Run bootstrap rejects in-container SMB mounts

## Status
Approved

## Context
Phase 14 established a Cloud Run runtime baseline, but storage connectivity for Synology-backed file operations remained operationally implicit.

This matters because the current backend storage adapter expects normal file-system paths while the approved hosting target is Cloud Run. Google Cloud's current Cloud Run runtime contract explicitly restricts mounting SMB/CIFS or other network file systems from inside the container process. Cloud Run instead supports managed volume mounts such as NFS volumes configured on the Cloud Run resource itself.

That means a production deployment cannot safely assume:
- mounting a Synology SMB share inside the container
- running a Tailscale + SMB mount workflow from inside the Cloud Run container
- treating workstation/private-share behavior as equivalent to Cloud Run service behavior

## Decision
- Add a service-bootstrap validation layer for Cloud Run deployment inputs.
- Reject storage bootstrap modes that depend on in-container SMB/Tailscale mounting.
- Treat direct Synology access from Cloud Run as one of two explicit modes:
  - `nfs_volume`: Cloud Run native NFS volume mounts over private networking
  - `external_bridge`: a separate storage-touching adapter/service outside Cloud Run
- Keep a `disabled` mode for rollout validation when storage is intentionally not exercised.
- Record deploy-time inputs in repository-owned example files and scripts instead of leaving them as tribal knowledge.

## Consequences
- The repo now makes the Cloud Run/Synology compatibility boundary explicit instead of implied.
- The current preferred direct-storage path for a Cloud Run-hosted backend is NFS over private networking, not SMB mounting inside the container.
- The earlier Tailscale assumption remains usable for workstation or non-Cloud-Run scenarios, but it is not accepted as an in-container Cloud Run mount strategy.
- A later architecture phase can still choose `external_bridge` if NFS export or network posture is unacceptable.
