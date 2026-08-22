# Synology File Storage Contract

## Source of truth
File binaries live on Synology only. Cloud SQL stores metadata, document lineage, and storage bindings.

## Legacy roots observed
- Main inspection tree is referenced in docs as `\\synology\...\01 - Kiểm tra GPs\<YEAR>\...`.
- Workbook/add-in evidence also contains:
  - local add-in fallback `ActiveWorkbook.Path\Addins\`
  - Synology add-in fallback under `\\synology\Hồ sơ nội bộ\01 - Kiểm tra GPs\Addins\`
  - named range `Folder_Hoso = \\synology\Hồ sơ nội bộ\02 - Hồ sơ Kiểm tra GPs`
  - DDKD document area under `ActiveWorkbook.Path\Chứng nhận ĐĐKKDD`
  - document templates referenced indirectly by VBA `Template_Path`

Conclusion:
- Root paths are configuration and environment concerns.
- Business layer must never embed UNC path literals.
- Template roots and generated output paths must also remain configuration-driven, not hard-coded in domain logic.

## Configured roots
- `inspection` for inspection/case document folders
- `dkkd` for business-eligibility document folders
- `template` for managed Word/Excel template binaries used by render adapters

## Folder identity
Observed inspection folder naming uses descriptive text plus stable tokens such as:
- `(ID-103)` site ID
- `(KT-1376-GMP)` inspection/case ID
- parent year

Required resolver contract:
- Input: `year`, `site_legacy_id`, `inspection_legacy_code`
- Output:
  - `RESOLVED`
  - `NOT_FOUND`
  - `AMBIGUOUS`
  - `INVALID`
- `0` matches or `>1` matches must fail closed.

## Folder and file behaviors proven by VBA
- Enumerate year folders.
- Enumerate inspection subfolders.
- Enumerate numbered files by wildcard such as `4.*.doc*`.
- Open files/folders in Explorer or via shell.
- Create folders when planning or DDKD substructure is missing.
- Select historical BBKT/template files from prior year folders.
- Open prior generated Word documents and copy bookmark or table content into new outputs.
- Save generated outputs back into legacy inspection or DDKD folder structures.
- DDKD-specific proven behaviors:
  - resolve the DDKD site folder by searching for `* (<site_id>)*`
  - if absent, create a new folder named `TenCtyx - DiaChi (<site_id>)`
  - resolve or create a child `Lần n` folder for the active issuance/update cycle
  - classify DDKD files into numeric slots `1..5` by the token before the first dot in the filename
  - generate a missing slot file on demand from `RecordForm.CreateFilez` or open the existing file in Explorer

## Legacy document prefix registry baseline
Observed from docs and VBA behavior:
- `3.` inspection plan / planning documents
- `3.2.` GMP assessment minutes
- `4.` report / BBKT family
- `4.2.` KTGS minutes
- `5.1.` CAPA lần 1
- `5.2.` CAPA lần 2
- `6.` phiếu trình PCT
- `6.2.` related variants
- `7.` phiếu trình CT
- `8.` quyết định cấp CC
- `9.` certificate artifacts in current Word-scoped migration baseline
- `10.` risk management

This is still provisional. Formal registry must be reconciled against real folders and templates before cutover.

For DDKD specifically, `LoadFileDDKLists` proves a separate numeric slot family:
- `1.` presentation / phiếu trình cấp ĐĐKKD
- `2.` DDKD certificate
- `3.` DDKD appendix
- `4.` DDKD issuance decision
- `5.` reserved/other generated bucket in the active UI, even if not all slots are always populated

## Document model
Separate:
- logical document type
- technical variant/rendition
- version

Typical variants:
- editable `.docx`
- generated `.pdf`
- scanned `.pdf`
- signed `.pdf`

## StorageService contract
Allowed operations:
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

Delete is privileged and should default to archive-or-soft-delete behavior.

Required adapter set:
- `LocalStorageAdapter` for development/integration tests
- `Fake/MockStorageAdapter` for automated tests
- `SmbStorageAdapter` for the current VM production baseline
- `BridgeStorageAdapter` for dormant Cloud Run / future bridge-based production

Bridge authentication contract:
- `BRIDGE_AUTH_MODE=google_oidc`
  - use for Cloud Run / private Google service-to-service callers
  - bridge verifies Google-issued OIDC identity against the configured audience
- `BRIDGE_AUTH_MODE=hmac_jwt`
  - use for non-Google bridge hosts such as office VM / mini PC / temporary PoC bridge
  - verify issuer, audience, subject/client identity, expiry, and signing key
- auth mode must be explicit; no implicit fallback from one scheme to the other

The business/domain layer must never:
- mount NAS storage directly
- embed UNC, SMB, NFS, WebDAV, Tailscale, or bridge-host details
- infer file semantics from transport-specific behavior

Binding/log ownership:
- storage adapters do not persist `StorageBinding`
- storage adapters do not persist `StorageResolutionLog`
- application-level storage binding service owns:
  - binding reuse
  - live resolve fallback
  - binding upsert/update
  - resolution log persistence
- request/use-case boundary owns transaction commit/rollback for binding/log persistence

Non-responsibilities:
- template selection
- bookmark mutation
- document copy-forward business rules
- issuance/version semantics

## Document-generation boundary
- `DocumentService` may derive `SourceBinaryRequirement` records that say:
  - which prior logical document version is needed
  - which storage folder binding is associated
  - which exact source binary locator is registered on the source version
  - which bookmarks must be available
  - whether render may proceed
- `StorageService` still does not decide which family or dependency to use.
- A resolved folder alone is insufficient for copy-forward execution.
- Exact file identity lives on `document_version`, not on `storage_binding`.
- Inspection-scoped outputs may carry both exact locator and inspection-style `storage_binding_id`.
- DDKD-scoped outputs may carry an exact locator with `storage_binding_id = NULL` until a DDKD-specific binding key is formally proven.
- Current Phase 4 evidence is sufficient to standardize the DDKD site-folder resolver on the durable token `(<site_id>)`.
- The DDKD site folder display-name prefix remains mutable presentation text only.
- The DDKD `Láº§n n` issuance-cycle subfolder and exact file placement remain higher-level issuance/document concerns.
- Output writes also target a preallocated exact locator on `document_version`; the render adapter must not invent storage paths on its own.
- Template-aware renderers must read managed template binaries through the `template` storage root, not through ad-hoc local paths.
- Because legacy DDKD folder creation uses a display-name prefix plus `(<site_id>)`, the storage adapter must treat the site ID token as the durable resolver key and the descriptive prefix as mutable presentation text only.

## Inspector desktop requirement
Storage integration must support:
- Windows Explorer navigation
- Microsoft Word desktop direct open/edit/save
- no manual download/upload loop

This implies the integration contract needs a desktop-friendly private-network path strategy, but the business layer must still go only through `StorageService`.

## Production storage topology
- Current production baseline:
  - `Compute Engine VM main app -> SmbStorageAdapter -> SMB -> Tailscale -> Synology`
  - the direct SMB path is implementation detail inside `StorageService`; business code still stays storage-agnostic
- Dormant optional baseline:
  - `Cloud Run main app -> authenticated Cloud Run storage bridge -> Tailscale userspace SOCKS5 -> SMB -> Synology`
  - bridge runtime uses SMB client operations against Synology private share roots; it does not use Cloud Run NFS `no-lock`
- In both modes:
  - no business/domain code may own UNC paths or transport-specific logic
  - no frontend client receives NAS credentials

## Cloud Run deployment implication
- Cloud Run NFS may exist as an experimental transport or comparison PoC only.
- Cloud Run NFS `no-lock` is not the default production storage baseline for this system.
- Current Cloud Run storage-integration order is:
  - dormant path: `Cloud Run main app -> authenticated Cloud Run storage bridge -> Tailscale userspace SOCKS5 -> SMB -> Synology`
  - bridge runtime uses SMB client operations against Synology private share roots; it does not use Cloud Run NFS `no-lock`
  - fallback only if needed: deploy a separate bridge host near Synology without changing the business-layer contract
- In either PoC path, business code remains unchanged because all file operations stay behind `StorageService`.

## Security
- Reject path traversal and root escape.
- Keep SMB/DSM/WebDAV non-public.
- Never send NAS credentials to frontend.
- Tailscale or future site-to-site VPN must remain replaceable infrastructure.
- Storage bridge endpoints must authenticate callers even on a private network.
