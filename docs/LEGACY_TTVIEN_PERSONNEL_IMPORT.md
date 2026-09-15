# TTviên Personnel Import Contract

The authoritative path is workbook -> Snapshot V2 -> TTviên source planner ->
Person and InspectorProfile -> legacy inspector source provenance. Report sheets
and the obsolete Nhóm 1c region are not personnel-master sources.

Each imported source record is identified by `(snapshot_sha256, source_sheet,
source_row_number)`. This is a snapshot-specific source-record key, not human
identity or a cross-workbook permanent personnel identity. A future authoritative
snapshot must not be assumed to identify the same Person without a separately
approved reconciliation rule. `Person.full_name` is deliberately non-unique, and
import planning never merges records by name.

The import creates a Person, one InspectorProfile, and one
`LegacyInspectorSourceRecord` in a single future transaction. A replay is
`NOOP_IDEMPOTENT` only when the source payload, stored provenance payload digest,
and live linked Person/InspectorProfile payload all match. Either source change or
live canonical drift is `CONFLICT`; neither is overwritten automatically.

Inactive (`x`) roster rows remain importable and queryable for history. Future
active-picker queries filter `InspectorProfile.is_active = true`; historical team
views must not hide inactive linked inspectors.

`TTviên!Chuyên môn` is preserved verbatim in
`InspectorProfile.professional_specialty` for future filtering. It is not a
ProfessionalLicense and the source-wide position/unit fields are not PersonRole
facts. Sensitive identity, payment, and airline/contact-like source values remain
only in Snapshot V2 and are never copied into the personnel schema or normal API.

Team migration is a later, separate step. B2 crosswalk output is evidence only and
must not create unresolved team members.
# Guarded B4B Import

The B4B public importer accepts only source-plan bytes and computes their
SHA256 itself against the pinned audited B2 artifact. It then verifies an
explicit target database identity and Alembic revision `20260914_0015`, then
uses this module's classifier against live canonical state. Only
`INSERT_CANDIDATE` and `NOOP_IDEMPOTENT` records may proceed. Dry-run uses this
preflight path only and does not add or flush personnel ORM rows.

New `Person` IDs use the existing generated system UUID default. Immutable
snapshot/sheet/row provenance, rather than a human name or derived UUID,
owns replay idempotency. The importer never matches names and runs the whole
batch in a savepoint inside the caller-managed transaction; its CLI commits
only after every record succeeds and rolls back on every fence or write
failure. A successful replay with only no-ops reports no database mutation.
Public guarded operations require a clean SQLAlchemy Session: pending new,
dirty, or deleted caller state is rejected without flushing, expiring,
rolling back, or discarding it.
