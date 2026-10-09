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

## HMAC bridge-token integrity

When `BRIDGE_AUTH_MODE=hmac_jwt` is enabled, the bridge accepts only the
token format produced by `issue_bridge_token`: canonical unpadded Base64URL
components, an `HS256` JWT header, a JSON-object payload and an exact HMAC
signature. Identity claims (`iss`, `aud`, `sub`) must match the configured
service identity. Integer `iat` and `exp` claims must describe a bounded,
not-yet-expired lifetime within `STORAGE_BRIDGE_TOKEN_TTL_SECONDS`, with a
small tolerance for issuance clock skew.

Malformed, tampered, unsupported, expired or out-of-contract tokens return
HTTP 401 and must never expose storage contents or produce an unhandled
server error. These checks are owned by the bridge authentication adapter;
the business workflow, frontend and storage backends do not duplicate JWT
validation. Google OIDC verification remains a separate explicit auth mode.

## Collision safety of storage file operations

`copy`, `move` and `rename` do not have an overwrite flag and therefore
must reject an existing destination with `StorageTargetExistsError`
(HTTP 409 through the storage bridge). The pre-existing content and source
remain unchanged. The only explicit overwrite operation is
`write_stream(overwrite=True)`, whose caller must already own that action.
Storage adapters must never silently turn a collision into a rename into an
existing directory or a replaced document. Exclusive creation is used for
copy destinations; moves and renames check destination occupancy before
invoking their backend-specific operation.
