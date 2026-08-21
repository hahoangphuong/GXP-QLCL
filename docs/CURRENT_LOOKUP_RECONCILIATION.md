# Current Lookup Reconciliation

## Scope
- This document summarizes the audited consistency between:
  - base-table current-state columns
  - base-table mirror/current-key columns
  - sheet-level lookup grids such as `Ds_IDCs_DC`
- Detailed machine-generated output is stored in:
  - [current_lookup_reconciliation.json](/D:/GXP-QLCL/artifacts/legacy_audit/current_lookup_reconciliation.json)
  - [current_lookup_reconciliation.md](/D:/GXP-QLCL/artifacts/legacy_audit/current_lookup_reconciliation.md)
- Duplicate-current deep-dive evidence is documented separately in:
  - [DUPLICATE_CURRENT_ANALYSIS.md](/D:/GXP-QLCL/docs/DUPLICATE_CURRENT_ANALYSIS.md)
  - [duplicate_current_analysis.json](/D:/GXP-QLCL/artifacts/legacy_audit/duplicate_current_analysis.json)

## Proven findings
### Base-table mirror columns are internally consistent
- `db.cc`
  - `468` rows are marked current with `MỚI NHẤT = "o"`.
  - Every current row has a non-blank `ID MỚI NHẤT`.
  - No current-row key mismatch was found between:
    - status marker
    - `ID MỚI NHẤT`
    - expected composite key `LOẠI CC + "-" + ID CƠ SỞ + MÃ DC`
- `db.dkkd`
  - `258` rows are marked current with `MỚI NHẤT = "o"`.
  - No current-row key mismatch was found between:
    - status marker
    - `ID MỚI NHẤT`
    - expected key `ID CƠ SỞ`
- `db.ktra`
  - `445` rows are marked current with `MỚI NHẤT = "o"` in the audited mirror columns (`AI` / `AJ`).
  - No current-row key mismatch was found between:
    - status marker
    - `ID MỚI NHẤT`
    - expected composite key `LOẠI KT + "-" + ID CƠ SỞ + MÃ DC`

### Duplicate current keys exist in base tables
- `db.cc`
  - `10` duplicate current keys were found.
  - Examples:
    - `GMP-50` appears on `6` current rows
    - `GMP-104` appears on `4` current rows
    - `GMP-24` appears on `4` current rows
- `db.ktra`
  - `4` duplicate current keys were found.
  - Examples:
    - `GMP-103C`
    - `GMP-310A`
    - `GMP-52A`
    - `GMP-75B`
- `db.dkkd`
  - No duplicate current keys were found.

### Sheet-level lookup grids can be stale relative to base truth
- Grid rows audited: `448`
- No missing row indexes were found in the grid pointers.
- But many grid pointers resolve to base rows whose current-key mirror is blank or no longer matches the grid key:
  - grid -> `db.ktra` key mismatches: `418`
  - grid -> `db.cc` key mismatches: `364`
- Direct workbook evidence confirms this is not only an index-offset artifact.
- Example:
  - grid key `GMP / 2B` points to `db.cc` logical row `1485`
  - that row is marked `"-"` and has blank `ID MỚI NHẤT`
  - so the grid is pointing at a non-current certificate row for that site/scope

## Interpretation
- The base-table mirror columns are much closer to business truth than the sheet-level `Ds_IDCs_DC` grid.
- The sheet grid should therefore be treated as an operational cache/read-model that may drift stale.
- Duplicate current keys in `db.cc` and `db.ktra` mean even the base-table current projection is not perfectly one-to-one.

## Migration implication
- Rebuild current projections from transactional/base-row truth during migration.
- Do not import `Ds_IDCs_DC` as authoritative current-state data.
- Use duplicate-current-key findings as reconciliation/anomaly inputs before final cutover logic is frozen.
- Do not silently coerce duplicate current candidates into one winner during projection build.
