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
