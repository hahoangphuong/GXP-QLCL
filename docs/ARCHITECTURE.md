# Target Architecture

```text
Users --HTTPS--> Cloud Run web/api
                       |
                       +--> application services
                       |    - MasterDataService
                       |    - CaseService
                       |    - InspectionService
                       |    - CertificationService
                       |    - ChangeManagementService
                       |    - DocumentService
                       |    - StorageService
                       |    - AuditService
                       |
                       +--> Cloud SQL PostgreSQL
                       |
                  StorageService port
                       |
                       +--> LocalStorageAdapter (dev/integration)
                       +--> Fake/MockStorageAdapter (automated tests)
                       +--> BridgeStorageAdapter (production Synology integration)
                                |
                           authenticated storage API
                                |
                        private network adapter
                        initial: Tailscale
                        future: site-to-site VPN
                       |
                       v
                  Synology DS115j
                  FILE STORAGE ONLY
```

## Phase 0 findings that affect architecture
- The legacy workbook is only a shell. Core behavior lives in add-in forms and document/file automation.
- `db.ktra` is a wide-row workflow aggregate and should not be mirrored 1:1.
- Word automation and folder resolution are core operational flows, not optional edge cases.
- Folder and file operations are deeply coupled to business logic in VBA today; target architecture must separate them.

## Separation
- Application/business state: Cloud SQL PostgreSQL.
- File binaries: Synology only.
- File metadata, document lineage, workflow state: Cloud SQL.
- Network transport to NAS: replaceable infrastructure adapter.

## Backend layering
`API -> Application -> Domain -> Ports`

Infrastructure adapters implement:
- repositories
- `StorageService`
- document template/rendering adapter
- auth integration
- audit sink

Hard rule:
- domain/application code must not know UNC path, Tailscale IP, SMB share name, or Explorer mechanics.
- domain/application code must not know NFS mount points, WebDAV endpoints, bridge host placement, or transport-specific retry rules.
- auth verification must stay in the auth adapter boundary; workflow/document/storage services only consume `AuthenticatedUser`.
- production bootstrap must fail before serving if database/auth/storage invariants are not met.
- production schema evolution must go through Alembic revisions rather than implicit metadata creation in runtime paths.

## Domain slices
- Master Data
- Case / Application
- Inspection Planning and Execution
- Certification
- Business Eligibility
- Change Management
- Document Management
- Administration / RBAC / Audit

## Document architecture
- `DocumentService` owns template selection, generation, variant tracking, and issuance lifecycle.
- `StorageService` owns folder resolution and file IO only.
- Logical document, variant, and version are separate entities.
- Phase 5 evidence adds two more requirements:
  - `DocumentService` must keep a template registry and a bookmark/section contract per logical document family.
  - copy-forward flows from prior legacy documents must be explicit dependencies, not hidden ad-hoc file reads.
- Generation attempts must be auditable first-class records, not inferred only from final files.
- Pre-render orchestration must expose whether all source-document binaries are concretely locatable before any render/copy-forward starts.
- Exact source/output file identity belongs at `document_version` level; folder binding alone is not sufficient for binary lineage.
- Render adapters should consume a preallocated output target and return bytes/stream, not perform path-planning themselves.
- The current DOCX adapter is a synthetic baseline for pipeline validation, not yet a legacy-template-faithful renderer.
- Template binaries are separate managed assets with their own storage root and locator metadata on `template_definition`.
- A second DOCX baseline now performs scalar bookmark replacement against managed templates, but still does not cover the full legacy Word feature set.
- A third baseline now supports narrow repeated-row table rendering, but table semantics are still renderer-local rather than promoted into the family registry.
- Scalar template-aware rendering now spans body, header, and footer parts, while advanced multi-part table/section semantics remain deferred.
- A runtime template-contract gate now sits between payload builders and DOCX bookmark mutation so exact-safe families can use real-template bookmark evidence without promoting ambiguous families prematurely.
- Current migration scope for document generation is Word/Excel-backed flows only; the PowerPoint-backed legacy branch is excluded.

## Storage architecture
- Folder resolver accepts year + legacy site ID + legacy inspection code.
- Resolver must fail closed on 0 or >1 matches.
- DDKD site-folder resolver accepts `site_legacy_id` and matches only the durable token `(<site_id>)`, never the full display name.
- DDKD issuance-cycle subfolders such as `Láº§n n` are downstream document-placement concerns, not business identity keys.
- Desktop open/edit/save workflows remain possible through private-network storage access, but domain APIs stay storage-agnostic.
- `StorageService` is the only business-visible file boundary.
- adapter responsibilities stop at physical resolution and file IO.
- `StorageBinding` / `StorageResolutionLog` persistence are application services layered above the adapter boundary.
- Required storage operations are:
  - `resolve_inspection_folder`
  - `resolve_dkkd_folder`
  - `list`
  - `stat`
  - `read_stream`
  - `write_stream`
  - `create_folder`
  - `copy`
  - `move`
  - `rename`
  - `checksum`
- Required adapter set:
  - `LocalStorageAdapter` for development and integration tests
  - `Fake/MockStorageAdapter` for automated tests
  - `BridgeStorageAdapter` for production Synology integration
- The business application must not mount or manipulate Synology directly in the production baseline.
- Cloud Run NFS `no-lock` is not the default production storage baseline.
- NFS may still exist as an experimental transport adapter or comparison PoC, but not as the owner of production file semantics unless locking, atomicity, and concurrent-write invariants are separately proven.
- Current storage integration order is:
  - production baseline: `Cloud Run main app -> authenticated Cloud Run storage bridge -> Tailscale userspace SOCKS5 -> SMB -> Synology`
  - the storage bridge runtime owns SMB/Tailscale mechanics; the business app still sees only `StorageService`
  - fallback path only if needed: deploy a dedicated bridge host near Synology without changing business-layer code
- If PoC B becomes necessary, the bridge host remains an infrastructure adapter only; business application code must remain unchanged.
- Bridge API authentication is application-level, not just network-level:
  - `BRIDGE_AUTH_MODE=google_oidc` for Cloud Run/private Google service-to-service identity
  - `BRIDGE_AUTH_MODE=hmac_jwt` for non-Google bridge hosts
  - no implicit auth-scheme mixing
  - no plaintext hardcoded bearer secret in source

## Read model / reporting
- Legacy sheets such as `DsCB*`, `DsCs`, `DsCty`, `KH`, and `Thống kê` should become query/read-model endpoints or export pipelines.
- They should not dictate physical table design.

## Reliability and integrity
- Do not report write success before Synology write succeeds.
- Prefer temp-write + verify + final rename where supported.
- Track checksum, timestamps, and storage-relative path.
- Surface NAS/network failure explicitly.
- Never silently fall back to persistent cloud file storage.
- Transport swaps such as Tailscale today and site-to-site VPN later must not require business-layer rewrites.
- Streaming file paths must avoid whole-file RAM buffering for large payloads.

## Identity and access boundary
- Local/dev may use `header_stub`, but production-compatible mode is `google_iap_jwt`.
- Google Cloud identity should be verified from `X-Goog-IAP-JWT-Assertion` against the configured direct-Cloud-Run IAP audience.
- Direct Cloud Run IAP audience format is `/projects/{PROJECT_NUMBER}/locations/{REGION}/services/{SERVICE_NAME}`.
- Plain identity headers are not the primary trust anchor; any fallback must be explicit and temporary.
- Production role/permission ownership is database-backed:
  - external identity -> `AppUser` -> `AppUserRole` -> `RbacRole` / permissions
  - authenticated but unprovisioned users fail closed
  - browser-submitted production role headers are not trusted
  - when both email and subject claims are present, subject-backed identity is preferred and cross-user ambiguity fails closed

## Transaction and concurrency
- Request/use-case boundary owns transaction commit/rollback.
- Success responses for mutation routes are returned only after the request boundary commits; optimistic-concurrency failures must surface as HTTP `409` before any response body is emitted.
- Lower-level collaborators such as workflow/document/storage binding services may `flush()` but do not independently commit.
- Mutable aggregates use `row_version` optimistic concurrency.
- Stale update attempts must fail with conflict rather than silently overwriting prior changes.
- Mutation audit records must capture:
  - structured before values
  - structured after values
  - field-level diffs
  - non-secret operational payload snapshots only

## Testability and repository contract
- Normal CI and local test runs must not depend on production `legacy/` or `artifacts/` directories.
- Test semantics that need historical workbook/template context use committed sanitized fixtures under `tests/fixtures/`.
- Operator-mode migration/template tools may still default to real `legacy/` or `artifacts/` roots when those directories are intentionally supplied outside CI.

## Deployment baseline
- Production runtime target is a single Linux Cloud Run container image that contains:
  - FastAPI backend
  - built Vite frontend static assets
- The Cloud Run service serves the operator web app and API from the same origin.
- Container builds install Python runtime dependencies from compiled lockfiles, not floating manifests.
- Frontend assets are built during the production image build, not committed under `frontend/dist/`.
- Runtime DB connectivity may come from a full `DATABASE_URL` or from Cloud SQL component env vars composed at startup.
- Secret values belong in Secret Manager-backed injection, not committed literal values in repository env files.
- Deployment contract validation should run before rollout so auth, database, and Synology storage prerequisites fail closed.
- Production rollout order is:
  - preflight validation
  - immutable image build
  - Alembic migration job
  - Cloud Run service deploy
  - health/readiness verification
- Direct VPC egress is the recommended private-network path for Cloud Run when VPC access is required.
- No production baseline currently assumes direct NAS mounting from the business application container.
- The current repository-owned storage bridge baseline also avoids NFS mount semantics:
  - bridge container joins the tailnet in userspace mode
  - bridge container reaches Synology over private SMB
  - main app reaches the bridge over authenticated Cloud Run HTTPS
- Explorer/Word desktop access for inspectors is an intentionally separate private-network workflow:
  - inspector laptop -> Tailscale/private network -> SMB -> Synology
  - backend -> `StorageService` -> transport adapter -> Synology
