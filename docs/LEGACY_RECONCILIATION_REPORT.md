# Legacy Reconciliation Report

## Source
- Generated from `tools/legacy_audit.py`.
- Latest machine-readable outputs:
  - `artifacts/legacy_audit/anomalies.json`
  - `artifacts/legacy_audit/report.md`

## Row counts
- `db.cty`: 333
- `db.cso`: 380
- `db.ktra`: 1549
- `db.cc`: 1632
- `db.dkkd`: 835
- `db.Tdoi`: 225
- `db.Tdoi2`: 186

## Duplicate checks
No duplicate `ID` values were found in the seven audited core sheets.

## Orphan checks
No simple FK orphan was found for:
- `db.cso.ID Cty`
- `db.ktra.ID CƠ SỞ`
- `db.cc.ID ĐỢT KTRA`
- `db.cc.ID CƠ SỞ`
- `db.dkkd.ID CC`

## Known baseline cleanup
- Prior documentation says `db.dkkd ID=385` was an exact duplicate safe to deduplicate.
- In the workbook snapshot audited in Phase 0, only one row with `ID=385` is present.

## Important caveats
- This report validates only the workbook snapshot currently in `legacy/`.
- It does not prove historical snapshots were clean.
- It does not yet validate physical Synology folder duplication or ambiguity, because the actual NAS tree is not mounted into this workspace snapshot.
