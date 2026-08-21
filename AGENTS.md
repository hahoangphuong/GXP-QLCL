# AGENTS.md — GxP Web

## Mission
Build a safe, testable web replacement for the legacy Excel/VBA GxP system while preserving business behavior and Synology compatibility during migration.

## Source-of-truth priority
1. Explicit current user task
2. `docs/DECISIONS.md`
3. Approved ADRs
4. `docs/ARCHITECTURE.md`
5. `docs/FILE_STORAGE_CONTRACT.md`
6. `docs/MIGRATION_PLAN.md`
7. Reverse-engineering docs
8. Legacy VBA behavior

## Always read before substantial work
- `AGENTS.md`
- `docs/DECISIONS.md`
- relevant ADR/domain/storage/data docs
- relevant tests
- legacy artifacts when task touches legacy behavior

## Architectural invariants
- App: Google Cloud Run.
- Business DB: Cloud SQL PostgreSQL.
- File binaries: Synology only.
- Current NAS: DS115j; file storage only.
- Initial connectivity: Tailscale.
- Future site-to-site VPN must be swappable without domain changes.
- All file operations through `StorageService`.
- Frontend never gets NAS credentials or raw storage ownership.

## Legacy identity
Inspection folders use stable identifiers:
- `(ID-xxx)` site ID
- `(KT-yyyy-<GP>)` inspection code
- parent year

Display names are not keys.

Folder resolution must fail closed on 0 or >1 match.

## Migration rules
- Do not 1:1 clone Excel sheets into SQL by default.
- Normalize actual business entities.
- Preserve legacy IDs/mappings.
- Migration scripts must have deterministic rerun semantics.
- Produce reconciliation reports.
- `db.dkkd ID=385`: exact duplicate confirmed; keep one.
- Same key + different payload = hard migration error.

## One-way ownership
One business rule, one owner:
- workflow -> domain/workflow service
- file access -> StorageService
- document generation -> DocumentService
- authorization -> auth/RBAC
- persistence -> repositories/data layer

No downstream rescue patches.

## Document model
Separate:
- logical document
- rendition/variant
- version

DOCX/PDF/scan/signed may represent one logical document.

## Security
- least privilege
- RBAC
- no secrets in git
- no sensitive payload logging
- path traversal protection
- storage-root boundary validation
- business mutation audit
- transactions
- concurrency control
- checksum where applicable
- no public SMB/DSM/WebDAV
- destructive file operations require strong tests

## Stack baseline
Backend: Python, FastAPI, SQLAlchemy 2.x, Alembic, Pydantic, pytest, type hints.
Frontend: TypeScript + React; one framework chosen by ADR; no duplicated backend business logic.

## Test expectations
For behavior: happy path, edge case, negative path.
Especially:
duplicate IDs, orphans, ambiguous folders, missing folders, path traversal, storage outage, interrupted writes, concurrent updates, checksum mismatch, permission denial, migration rerun.

## Legacy reverse engineering
Never infer purpose from procedure name alone.
Capture for each procedure:
module/form, callers, callees, reads, writes, named ranges/sheets, filesystem ops, COM ops, side effects, replacement owner.

## Completion report
Every substantial task ends with:
Summary; Files changed; Behavior changed; Tests/commands; Results; Data impact; Storage impact; Security impact; Compatibility; Known risks; Next recommended task.
