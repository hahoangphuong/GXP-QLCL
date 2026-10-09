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

## No-replace atomicity after destination preflight

An existence check alone is never the safety boundary for `move` or
`rename`: another writer may create the destination between the check and
the operation. On Linux, the filesystem-backed adapter requires
`renameat2(RENAME_NOREPLACE)`; on Windows it uses non-replacing
`os.rename`. If a platform, kernel, filesystem or mount cannot guarantee
no-replace, the adapter fails closed instead of falling back to potentially
overwriting `shutil.move` or POSIX `os.rename`. On SMB, `smbclient.rename`
uses `replace_if_exists=False` server-side; destination collisions returned
as generic SMB OSErrors are mapped to `StorageTargetExistsError` (HTTP 409).
The no-replace operation prevents implicit replacement. It does not provide
a multi-file transaction, version ownership, or document-business locking.

## Filesystem copy publication and metadata rollback

Local filesystem `copy` stages the complete byte copy and metadata in a
temporary file within the destination directory. Only after both succeed
does it publish via the same atomic no-replace primitive as `move` and
`rename`. An error cleans up the private temporary path only, never an
already published destination: this preserves data written by a concurrent
actor during a metadata failure or late target collision. Unsupported
atomic publication fails closed; business code must not replace it with
an overwrite/copy fallback. SMB copy retains its independent exclusive
create (`xb`) contract; no SMB semantics change in this patch.

## Exclusive write publication

The filesystem adapter now stages all `write_stream` content before exposing
the requested path. `overwrite=False` publishes by atomic no-replace and
returns `StorageTargetExistsError` (HTTP 409) if another writer won the
destination. A failed stream or unsupported no-replace operation cleans up
only the private staging file. `overwrite=True` retains its intentional
atomic `os.replace` behavior. This guarantee applies to the local/mounted
filesystem adapter; the SMB-native adapter's exclusive stream operation
requires separate parity review.

## SMB exclusive-write publication parity

Native SMB `write_stream(overwrite=False)` stages a complete file on the
same share using exclusive mode `xb`, then publishes with
`smbclient.rename` (server-side `replace_if_exists=False`).
Collisions return `StorageTargetExistsError` (HTTP 409). Interrupted writes
only remove their private staging file, never another writer's destination.
The final requested path is not exposed until the write completes.
`overwrite=True` retains its existing intentional SMB replace behavior.

## Read-only staging candidate inventory

Successful writes publish a fully completed temporary file. Unexpected
process death may leave unpublished private staging files on Synology.
New filesystem and native SMB staging files use a distinct
`.gxp-stage-<random>.tmp` name. A bounded, read-only operator command can
inventory their metadata:

`python -m tools.audit_storage_staging --root inspection --max-directories 250 --max-entries 10000 --max-depth 8`

Add `--root dkkd` and/or `--root template` only when authorized and
configured. Output contains candidate paths/sizes and a mandatory
`truncated` indicator with the limit reached; an incomplete scan is not
proof of no staging files. There is **no automatic deletion**, age-based
purge, background task or mutation endpoint. A matching name does not prove
orphan ownership: an active transfer or an ordinary similarly named file
may exist. Operator review and external ownership verification are required
before any separately approved cleanup.

Old SMB `<target>.tmp-<32 hex>` paths are reported as
`legacy_smb_candidate`. Older filesystem-backed `tmpXXXXXX` files
cannot be reliably distinguished from unrelated files using their names,
so they are intentionally **not** classified or deleted. This inventory
does not assert exhaustive recovery of earlier staging artifacts.

## Audit failure and recovery boundaries

The metadata-only staging inventory reports `truncated=true` and
`incomplete_reason=storage_access_failed` if the NAS becomes unavailable,
a scanned path becomes unreadable, or an adapter rejects a path. Earlier
candidate metadata is retained in the report, together with the failed
logical root and relative folder, but the scan **stops immediately**.
No underlying exception messages, SMB credential values or UNC connection
details are included. A storage adapter initialization failure reports
`storage_setup_failed`, zero scanned entries and an incomplete result.

CLI exit status: `0` for a complete inventory, `2` for a scan budget
limit, and `3` for storage setup/access failure. A successful command
execution is not evidence that an unreported folder has no staging files.
Directories whose names look like staging files are not staging-file
candidates. The scanner does not retry, create folders, read binary
contents, delete files or attempt recovery after a connection outage.

The entry budget limits **processed** entries, but the current
`StorageService.list` contract materializes one complete directory listing
per call. Therefore, it does not guarantee bounded NAS enumeration cost or
RAM for a single exceptionally large directory. Any future streaming
enumeration must be implemented at the storage adapter owner, not by
silent client-side post-filtering.
