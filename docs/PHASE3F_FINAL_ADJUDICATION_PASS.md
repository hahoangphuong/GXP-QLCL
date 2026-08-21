# Phase 3f - Final Adjudication Pass

## Goal
Resolve the highest-value remaining non-certificate anomaly using direct business evidence from the legacy change-detail row itself.

## Historical note
This document records a real deterministic adjudication rule that was derived before the later blanket confirmation of the review-report scope.

It should now be read as:
- historical evidence of how one specific override was justified;
- not proof that the surrounding unresolved queue still represents current migration backlog after Phase 3q.

## Rule
For a change-detail row that:

- points to a missing root `db.Tdoi` change request
- has classification `Điều chỉnh cách ghi địa chỉ`
- and whose `THÔNG TIN MỚI` address matches exactly one imported site after conservative address normalization

promote that exact site as the missing root `db.Tdoi.site_legacy_id`.

## Findings
On August 13, 2026:

- Phase 3e merged overrides carried forward: `10`
- New final adjudicated suggestions: `1`
- Final merged override set: `11`

Resolved suggestion:
- `db.Tdoi ID=187` -> `site_legacy_id=85`

Evidence:
- `db.Tdoi2 ID=155` references root `ID Gốc=187`
- classification is `Điều chỉnh cách ghi địa chỉ`
- `THÔNG TIN MỚI` is `102 phố Chi Lăng, phường Thành Đông, thành phố Hải Phòng, Việt Nam`
- exactly one imported site matches that normalized address:
  - `legacy_site_id=85`
  - `Công ty cổ phần Dược Vật tư Y tế Hải Dương`

## Replay impact
After replaying the final merged overrides:

- `applied_override_count`: `11`
- `db.cc` target rows remain: `1468`
- `db.Tdoi` target rows: `202 -> 203`
- `db.Tdoi2` target rows: `183 -> 184`
- `db.Tdoi` skipped rows: `22 -> 21`
- `db.Tdoi2` skipped rows: `2 -> 1`
- `migration_anomaly`: `294 -> 293`

This is the first pass that reduces both:
- the persisted anomaly count
- and the unresolved `db.Tdoi` / `db.Tdoi2` chain

## Output artifacts
- [artifacts/phase3f/final_adjudication_analysis.json](/D:/GXP-QLCL/artifacts/phase3f/final_adjudication_analysis.json)
- [artifacts/phase3f/adjudicated_overrides.json](/D:/GXP-QLCL/artifacts/phase3f/adjudicated_overrides.json)
- [artifacts/phase3f/final_merged_overrides.json](/D:/GXP-QLCL/artifacts/phase3f/final_merged_overrides.json)
- [artifacts/phase3f/reconciliation_final.json](/D:/GXP-QLCL/artifacts/phase3f/reconciliation_final.json)

## Remaining queue after Phase 3f
Still unresolved:

- `db.cc`: `160` skipped rows
- `db.dkkd`: `50` skipped rows
- `db.Tdoi`: `21` skipped rows
- `db.Tdoi2`: `1` skipped row

The remaining low-width certificate queue is now mostly:
- Huro cluster `1456-1461`
- Phil Inter Pharma `1619`

These still lack an evidence signal strong enough to choose between competing case timelines without outside confirmation.

## Next recommended step
Historical next step at the time:
- proceed to a post-remediation closeout pass:

- freeze the current accepted override set as the audited baseline
- export the final unresolved review pack
- classify the remaining rows into `needs external evidence`, `archival placeholder`, or `hard unresolved`

Current successor state:
- the confirmed review-report rows are excluded by policy and should not be reinterpreted as newly unresolved.
