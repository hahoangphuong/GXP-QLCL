# Phase 4.4 - Non-Production Private-Share Runbook

## Goal
Prepare the team to test the storage contract against a non-production private share over Tailscale without changing business code or touching production NAS data.

## Current adapter position
- `FilesystemStorageService` is the named adapter for filesystem-accessible roots.
- It is compatible with:
  - local test directories
  - mapped drives
  - UNC/private-share paths
- Business code still depends only on the storage contract, not on UNC literals.

## Config files
- Example env file: [backend/.env.storage.nonprod.example](/D:/GXP-QLCL/backend/.env.storage.nonprod.example)

Required variables:
- `STORAGE_INSPECTION_ROOT`
- optional `STORAGE_DKKD_ROOT`
- optional `STORAGE_CLASS`

Recommended non-production value:
- `STORAGE_CLASS=synology_private_share_nonprod`

## Preconditions
1. A dedicated non-production share or read-only mirror exists.
2. The app host can reach the share only through private networking.
3. No SMB, DSM, or WebDAV endpoint is exposed publicly.
4. Test credentials are least-privilege and separate from production operator accounts.

## Tailscale/private-share checklist
1. Connect the app host to Tailscale.
2. Verify the target hostname/IP is reachable only on the private network.
3. Mount or access the share from the host OS using a dedicated non-production account.
4. Set env vars from the non-production example file.
5. Start the app and confirm `/healthz` reports `storage_configured=true`.
6. Run the inspection-folder probe using known-safe sample triplets.
   Preferred CLI: [tools/probe_phase4_storage_nonprod.py](/D:/GXP-QLCL/tools/probe_phase4_storage_nonprod.py)
7. Run the DDKD site-folder probe using known-safe site IDs.
8. Confirm:
   - resolved paths are relative only
   - stale bindings refresh correctly
   - ambiguous folders fail closed
   - missing folders return `NOT_FOUND`
   - DDKD folders resolve by the durable `(<site_id>)` token rather than display-name text
9. Run write tests only inside an explicitly approved scratch area.

## Write-operation safety checklist
- Use a dedicated scratch subtree, never live business folders.
- Test:
  - create folder
  - write temp file
  - checksum
  - copy/move/rename
- Verify interrupted or denied writes surface explicit failures.
- Clean up scratch artifacts manually after verification.

## Evidence to capture
- exact env profile used
- probe inputs and returned statuses
- generated `probe_report.json` / `probe_report.md`
- sample `storage_resolution_log` rows
- any stale-binding refresh behavior
- permission errors
- latency or locking anomalies

## DDKD caution
DDKD site-folder identity is now standardized on the durable `(<site_id>)` token.
However, DDKD issuance-cycle handling and any future DDKD binding persistence still require explicit business and storage evidence before production writes expand there.

## Exit criteria for this phase
- The app can resolve known inspection folders from a private share using config only.
- `storage_binding` refresh works from live fallback.
- No absolute UNC path leaks through the read-only probe response.
- No production NAS mutation occurs.
