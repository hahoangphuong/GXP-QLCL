# Storage Bridge Contract

## Purpose
This contract defines what a bridge-backed Synology integration is and is not allowed to own, whether the transport is a direct Cloud Run application-level client path or a later dedicated bridge host.

## Ownership
- The bridge is an infrastructure adapter only.
- It implements the same storage-facing responsibilities currently assigned to `StorageService`.
- It does not own workflow rules, document-family decisions, or authorization policy.
- `BridgeStorageAdapter` is the only business-visible client surface; transport specifics stay below it.

## Required operations
- `resolve_inspection_folder`
- `resolve_dkkd_folder`
- `list`
- `stat`
- `read_stream`
- `write_stream`
- `create_folder`
- `exists`
- `copy`
- `move`
- `rename`
- `checksum`

## Non-responsibilities
- template selection
- bookmark mutation
- source-document dependency choice
- certificate issuance semantics
- case workflow transitions
- frontend/operator identity

## Request identity
- Cloud Run should call the bridge using service-to-service identity.
- Browser clients must never call the bridge directly.
- NAS credentials, if any are needed by the bridge host, must remain bridge-side only.

## Data expectations
- Every write response should include enough metadata for the caller to persist exact document-version lineage:
  - storage root
  - relative path
  - original filename
  - checksum
  - byte size
- Reads should support streaming rather than requiring full file buffering in memory for every request.

## Failure model
- The bridge must fail closed when:
  - folder resolution is ambiguous
  - target paths escape the configured root
  - underlying Synology storage is unavailable
  - checksum verification fails where required
- The bridge must not silently fall back to alternate cloud file storage.

## Transport posture
- The bridge may use Tailscale now and site-to-site VPN later.
- That transport change must not require business-layer changes in Cloud Run.
- The first integration PoC may use Cloud Run with application-level transport over Tailscale without introducing a dedicated bridge host yet.
- If that PoC fails, a dedicated bridge host near Synology is the fallback infrastructure shape.
