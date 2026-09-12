# db.ktra Semantic Discovery

## Coverage
- Physical fields: `88`
- Physical rows: `1543`; valid-ID rows: `1533`
- Rehearsal comparison: `BLOCKED_NO_EXPLICIT_DATABASE_URL_ENV`
- Mapped/declared fields: `23`; not mapped: `65`
- Semantic `0..N` proven fields: `1`; composite-evidence fields: `24`

## Risk Summary
- `CRITICAL`: `2`
- `HIGH`: `7`
- `INFORMATIONAL`: `51`
- `LOW`: `5`
- `MEDIUM`: `23`

## Owner Summary
- `COMPOSITE_REQUIRES_SPLIT`: `1`
- `LEGACY_ONLY`: `2`
- `MULTIPLE_COMPETING_OWNERS`: `1`
- `NOT_MAPPED`: `65`
- `OWNER_COMPATIBILITY_ONLY`: `3`
- `OWNER_MISMATCH`: `1`
- `OWNER_MISSING`: `5`
- `OWNER_PROVEN`: `9`
- `SOURCE_SEMANTICS_UNPROVEN`: `1`

## Mapping Evidence
- `CODE_EVIDENCE_VERIFIED`: `18`
- `NOT_APPLICABLE_NO_DECLARED_MAPPING`: `70`
- Contract drift findings: `0`; fallback/coalescing findings: `1`.
- Semantic cardinality: `{"0..1_OBSERVED": 1, "0..N_PROVEN": 1, "0..N_SUSPECTED": 2, "UNKNOWN": 84}`.

## Highest-Risk Facts
- `Kết quả`: `MULTIPLE_COMPETING_OWNERS`; One legacy scalar currently populates two distinct canonical facts.
- `Q. định`: `COMPOSITE_REQUIRES_SPLIT`; Composite currently copied to incompatible compatibility fields.
- `B. bản`: `OWNER_MISMATCH`; Timestamp-dominant; not an actual inspection-date source.
- `T.tra viên`: `OWNER_MISSING`; Display source is observed; structured identity mapping is not proven.
- `ĐÁNH GIÁ CUỐI`: `OWNER_MISSING`; Distinct from assessment/outcome result.
- `PHIẾU TRÌNH PCT`: `OWNER_MISSING`; owner/semantic contract requires review.
- `PHIẾU TRÌNH CT`: `OWNER_MISSING`; owner/semantic contract requires review.
- `HẠN KT TUÂN THỦ`: `OWNER_MISSING`; owner/semantic contract requires review.
- `ID CC GPs`: `SOURCE_SEMANTICS_UNPROVEN`; Potential foreign/multi-reference source; no declared importer owner.

## Cross-Field Coupling Signals
- Automatic correlation findings: `27`. These are discovery signals, not ownership proof.
- `IDENTICAL_NONEMPTY_VALUES`: `Ngày g.sát` <-> `Biên bản` (`1185` paired rows)
- `EMBEDDED_VALUE_RELATIONSHIP`: `TIẾN ĐỘ XỬ LÝ` <-> `Thẩm định HSĐK` (`1506` paired rows)
- `IDENTICAL_NONEMPTY_VALUES`: `TIẾN ĐỘ XỬ LÝ` <-> `Cấp CC` (`1506` paired rows)
- `EMBEDDED_VALUE_RELATIONSHIP`: `TIẾN ĐỘ XỬ LÝ` <-> `Kiểm tra` (`1506` paired rows)
- `EMBEDDED_VALUE_RELATIONSHIP`: `TIẾN ĐỘ XỬ LÝ` <-> `Khắc phục 1` (`1506` paired rows)
- `EMBEDDED_VALUE_RELATIONSHIP`: `TIẾN ĐỘ XỬ LÝ` <-> `Khắc phục cuối` (`1506` paired rows)
- `IDENTICAL_NONEMPTY_VALUES`: `TIẾN ĐỘ XỬ LÝ` <-> `Trình lãnh đạo Cục` (`1506` paired rows)
- `EMBEDDED_VALUE_RELATIONSHIP`: `Thẩm định HSĐK` <-> `Cấp CC` (`1506` paired rows)

## Inspection-Period Reference Contract
- `Ngày K.tra` is the source for ordered `InspectionPeriodSegment`; `B. bản` remains a non-timing reference with `OWNER_MISMATCH`.
- Lexical morphology: `{"ANNOTATED_DATE": 901, "DATE_RANGE": 36, "EMPTY": 59, "MULTI_DATE_OR_PERIOD": 10, "SENTINEL_NOT_APPLICABLE": 4, "SENTINEL_PENDING_INPUT": 54, "SINGLE_DATE": 1, "TEXT": 478}`
- Authoritative parser facts: `{"authority": "backend.app.domain.inspection_periods.parse_legacy_inspection_periods", "segment_count_distribution": {"0": 109, "1": 1412, "2_or_more": 12}, "semantic_shape_distribution": {"MULTI_SEGMENT": 12, "NO_SEGMENT": 109, "SINGLE_SEGMENT": 1412}, "source_state_counts": {"KNOWN": 1424, "MISSING": 49, "NON_DATE_EXPRESSION": 1, "NOT_APPLICABLE": 4, "PENDING_INPUT": 54, "UNRESOLVED": 1}}`

## Domain Coverage
- `A`: `6` physical headers
- `B`: `4` physical headers
- `C`: `3` physical headers
- `D`: `2` physical headers
- `DERIVED_DIAGNOSTIC`: `8` physical headers
- `E`: `4` physical headers
- `F`: `12` physical headers
- `G`: `10` physical headers
- `H`: `6` physical headers
- `UNASSIGNED`: `33` physical headers

## Recommended Domain Order
1. `A` - Identity / case linkage
2. `B` - Application / dossier
3. `C` - Assessment / inspection outcome separation
4. `D` - Inspection planning / decision
5. `E` - Inspection execution
6. `F` - CAPA / approval follow-up
7. `G` - Certificate linkage
8. `H` - Evaluation scope / standards

## Unresolved Questions
- `B. bản` (BLOCKING, 1391 rows): Trường B. bản biểu thị chính xác loại bằng chứng nào: biên bản, thời điểm, hay tham chiếu tài liệu? Nó không được dùng làm ngày kiểm tra.
- `Kết quả` (BLOCKING, 1177 rows): Kết quả là kết quả thẩm định hồ sơ, kết quả kiểm tra thực tế, hay hai giá trị khác nhau đang bị gộp chung?
- `Q. định` (BLOCKING, 1315 rows): Có thể xác nhận quy tắc tách số quyết định và ngày quyết định từ Q. định, kể cả trường hợp không tách được tự động không?
- `HẠN KT TUÂN THỦ` (HIGH, 751 rows): HẠN KT TUÂN THỦ là hạn khắc phục, hạn tái kiểm tra hay hạn tuân thủ sau cấp chứng nhận?
- `ID CC GPs` (HIGH, 1343 rows): ID CC GPs có thể chứa nhiều chứng nhận hay chỉ một ID; quan hệ với certificate hiện hành là gì?
- `PHIẾU TRÌNH CT` (HIGH, 547 rows): PHIẾU TRÌNH CT thuộc một bước phê duyệt có thể lặp lại hay chỉ một hồ sơ duy nhất cho mỗi đợt kiểm tra?
- `PHIẾU TRÌNH PCT` (HIGH, 595 rows): PHIẾU TRÌNH PCT thuộc một bước phê duyệt có thể lặp lại hay chỉ một hồ sơ duy nhất cho mỗi đợt kiểm tra?
- `T.tra viên` (HIGH, 1355 rows): T.tra viên có phải danh sách đoàn kiểm tra có thứ tự/vai trò không, và nguồn định danh cá nhân nào là authoritative?
- `ĐÁNH GIÁ CUỐI` (HIGH, 1313 rows): ĐÁNH GIÁ CUỐI khác gì Kết quả và có phải một trạng thái cuối độc lập không?

The full machine-readable inventory is `artifacts/legacy_audit/db_ktra_semantic_inventory.json`.
