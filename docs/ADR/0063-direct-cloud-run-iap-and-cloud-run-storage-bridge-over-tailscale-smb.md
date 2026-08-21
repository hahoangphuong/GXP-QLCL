# ADR 0063: Direct Cloud Run IAP and Cloud Run storage bridge over Tailscale SMB

## Status
Approved

## Context
- The production application runs on Google Cloud Run.
- File binaries must remain on Synology DS115j.
- The business application must not mount or manipulate NAS storage directly.
- Cloud Run NFS `no-lock` is explicitly rejected as the production baseline.
- The operator wants to avoid introducing an additional always-on bridge host unless there is hard evidence that Cloud Run-based bridging is insufficient.
- Google Cloud now supports enabling IAP directly on Cloud Run services, so the old assumption that production IAP required a load balancer is no longer the preferred baseline.

## Decision
- The production web application uses direct Cloud Run IAP.
- Backend verification of `X-Goog-IAP-JWT-Assertion` uses the direct Cloud Run audience format:
  - `/projects/{PROJECT_NUMBER}/locations/{REGION}/services/{SERVICE_NAME}`
- The production Synology integration baseline is:
  - `Cloud Run main app -> BridgeStorageAdapter -> authenticated Cloud Run storage bridge -> Tailscale userspace SOCKS5 -> SMB -> Synology`
- The storage bridge remains an infrastructure adapter only.
- If this Cloud Run bridge baseline fails reliability, performance, or security requirements during real test-folder validation, the next fallback is a separate bridge host near Synology with no business-layer change.

## Consequences
- One-time bootstrap is now explicit:
  - identity/IAP bootstrap
  - storage bridge bootstrap
- Normal application deploy remains fail-closed until real IAP and bridge values exist.
- Production documents and examples must use Cloud Run direct IAP audience values, not load-balancer backend-service placeholders.
- The bridge container now needs:
  - Tailscale userspace runtime
  - SMB client dependencies
  - Synology SMB credentials via secrets
