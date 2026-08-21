# Phase 3e - Curated Review Pass

## Goal
Promote a small subset of the Phase 3d manual queue into deterministic overrides using a timeline rule that still has explicit evidence:

- parse year from legacy `certificate_number`
- compare it against candidate case timeline years from `case_application`, `case_assessment`, and `inspection_outcome`
- only accept the case when exactly one candidate matches the same year, or exactly one candidate matches the immediately previous year

## Historical note
This phase is still useful as an example of conservative override design, but it belongs to the pre-Phase-3q interpretation of the anomaly queue.

Rows now confirmed as blanked legacy rows should not continue through this adjudication path.

## Inputs
- [artifacts/phase3d/manual_review_queue.json](/D:/GXP-QLCL/artifacts/phase3d/manual_review_queue.json)
- [artifacts/phase3d/high_confidence_overrides.json](/D:/GXP-QLCL/artifacts/phase3d/high_confidence_overrides.json)
- [artifacts/phase2/staging_readonly.db](/D:/GXP-QLCL/artifacts/phase2/staging_readonly.db)

## Tools
- [tools/phase3e_curated_review.py](/D:/GXP-QLCL/tools/phase3e_curated_review.py)
- [tools/analyze_phase3e_curated_review.py](/D:/GXP-QLCL/tools/analyze_phase3e_curated_review.py)
- [tools/run_phase3e_merged_reimport.py](/D:/GXP-QLCL/tools/run_phase3e_merged_reimport.py)

## Findings
On August 13, 2026:

- Phase 3d high-confidence overrides carried forward: `5`
- New curated suggestions added in Phase 3e: `5`
- Merged override set after Phase 3e: `10`

New curated suggestions:
- `db.cc ID=1179` -> `case_legacy_id=1165`
- `db.cc ID=1192` -> `case_legacy_id=730`
- `db.cc ID=1449` -> `case_legacy_id=1388`
- `db.cc ID=1554` -> `case_legacy_id=1480`
- `db.cc ID=1586` -> `case_legacy_id=1480`

Reasoning examples:
- `db.cc ID=1449` carries certificate number `FT116/MH/001/2025`; among its two candidates, only case `1388` has a 2025 inspection timeline.
- `db.cc ID=1192` carries `Báo cáo thanh tra 16-08-2018`; among its three candidates, only case `730` has a 2018 timeline.
- `db.cc ID=1554` and `ID=1586` carry 2026 certificate numbers, and among their two candidates only case `1480` has a 2025 timeline, which satisfies the conservative `previous_year` rule.

## Replay impact
After replaying the merged Phase 3d + Phase 3e overrides:

- `applied_override_count`: `10`
- `db.cc` target rows: `1458 -> 1468`
- `db.cc` skipped rows: `170 -> 160`

Important nuance:
- `migration_anomaly` remains `294` because overridden rows remain persisted for auditability with status `overridden`.

## Output artifacts
- [artifacts/phase3e/curated_review_analysis.json](/D:/GXP-QLCL/artifacts/phase3e/curated_review_analysis.json)
- [artifacts/phase3e/curated_overrides.json](/D:/GXP-QLCL/artifacts/phase3e/curated_overrides.json)
- [artifacts/phase3e/merged_overrides.json](/D:/GXP-QLCL/artifacts/phase3e/merged_overrides.json)
- [artifacts/phase3e/reconciliation_merged.json](/D:/GXP-QLCL/artifacts/phase3e/reconciliation_merged.json)

## Remaining boundaries
This pass still does not infer:

- rows with no parseable year in certificate metadata
- rows whose candidates share the same timeline year window
- `db.Tdoi2 ID=155`, because the missing root `db.Tdoi ID=187` still has no direct timeline payload
- `db.dkkd ID=704`, because no exact imported site match is supported by current evidence

## Next recommended step
Historical next step at the time:
- proceed to a final manual adjudication pass over the remaining queue, prioritizing:

- `db.Tdoi2 ID=155`
- `db.cc` rows with only 2 candidates but no usable year clue
- `db.cc` rows with rename/address-change notes and multi-case ambiguity

Current successor state:
- only rows that remain meaningful after removing the Phase 3q confirmed blanked set should continue into any current adjudication workflow.
