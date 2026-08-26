# Duplicate Current Analysis

## Scope
- This document summarizes audited legacy cases where more than one row is marked current for the same workbook-maintained current key.
- Canonical reproducible input is `artifacts/phase3c/legacy_snapshot.json`.
- `tools/analyze_duplicate_current_keys.py` now derives this analysis from the canonical snapshot itself, so a clean repository checkout does not need the live `.xlsb` workbook to rebuild the duplicate-current artifact chain.
- Machine-generated detail is stored in:
  - [duplicate_current_analysis.json](/D:/GXP-QLCL/artifacts/legacy_audit/duplicate_current_analysis.json)
  - [duplicate_current_analysis.md](/D:/GXP-QLCL/artifacts/legacy_audit/duplicate_current_analysis.md)

## Provenance chain
1. `tools/export_legacy_snapshot.py` exports the authoritative legacy workbook into `artifacts/phase3c/legacy_snapshot.json`.
2. `tools/analyze_duplicate_current_keys.py` reads that snapshot and emits `artifacts/legacy_audit/duplicate_current_analysis.json`.
3. `tools/build_phase3p_current_projection_conflicts.py` reads the duplicate-current analysis and emits `artifacts/phase3p/current_projection_conflicts.json`.

Each generated JSON artifact now records:
- source path
- source SHA256
- conflict/classification counts
- manual-review policy evidence

## Proven patterns
### `db.cc`: current-key collapse on blank `MÃ DC`
- All audited duplicate-current groups in `db.cc` are currently explained by one repeated pattern:
  - multiple rows are marked current
  - they share the same `LOẠI CC + "-" + ID CƠ SỞ + MÃ DC` key
  - `MÃ DC` is blank on every row in the group
  - `ID ĐỢT KTRA` is blank on every row in the group
- This means the legacy projection is collapsing multiple non-case-backed certificates for the same site and GP stream onto one current key.
- Evidence examples from the audited workbook:
  - `GMP-50` has `6` current rows
  - `GMP-104` has `4` current rows
  - `GMP-24` has `4` current rows

Interpretation:
- This is not just random duplication.
- It is a structural limitation of the legacy current-key formula when `MÃ DC` is blank.
- Therefore the target system must not assume `gp_type + site_id + ma_dc` is unique when `ma_dc` is blank.

### `db.ktra`: more than one inspection row can remain current
- Duplicate-current groups in `db.ktra` do not follow the same pattern as `db.cc`.
- At least two proven subtypes exist:
  - `completed_plus_pending_both_current`
  - `multiple_completed_both_current`

Observed examples:
- `GMP-103C`
  - one completed row remains current
  - one pending row also remains current
- `GMP-52A`
  - one completed row remains current
  - one future/pending row also remains current
- `GMP-310A`
  - two completed rows are both marked current

Interpretation:
- Legacy `db.ktra` current markers cannot be treated as a strict one-row invariant.
- Some cases look like operator workflow overlap.
- Some cases look like historical promotion/demotion logic that did not fully clear an older row.

## Migration implications
### Projection design
- The target system should build current-state read models from transactional truth.
- Projection builders must fail closed on non-unique current candidates.
- The target design should explicitly support:
  - conflict detection
  - adjudication queueing
  - operator-visible reconciliation results

### Data model
- A derived projection such as `current_certificate_projection` or `current_case_projection` should not silently choose one winner from duplicate legacy candidates.
- Instead, projection refresh should be able to emit a `conflict` outcome or write a conflict/anomaly row for review.

### Import and cutover
- Migration import can still preserve all source rows.
- But cutover logic must not promote a duplicate-current legacy key into a single authoritative current row without an explicit rule or adjudication decision.

## Open questions
- For non-case-backed `db.cc` groups with blank `MÃ DC`, what is the real business discriminator between concurrent certificates at the same site:
  - certificate family variant
  - scope wording
  - replacement lineage
  - administrative reason
- For `db.ktra` groups where two completed rows are both current, which rule should pick the active inspection context in the target read model:
  - newest completion
  - newest certificate-linked row
  - manual adjudication only
