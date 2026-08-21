# Legacy Data Dictionary

## Core entity graph
- `db.cty` -> company master.
- `db.cso` -> site/facility master, FK `ID Cty`.
- `db.ktra` -> inspection/case row, FK `ID Cơ sở`.
- `db.cc` -> certificate row, FK `ID ĐỢT KTRA`, `ID Cơ sở`, plus links to changes/other inspections.
- `db.dkkd` -> business eligibility certificate row, links to site/company/certificate.
- `db.Tdoi` -> change request/change outcome row, FK `ID Cơ sở`.
- `db.Tdoi2` -> rename/address change detail, FK `ID Gốc`.

## Sheet-level dictionaries
| Sheet | Legacy role | Notes |
|---|---|---|
| `db.cty` | company master | multilingual names and legal address |
| `db.cso` | site master | site name, address, province, professional lead |
| `db.ktra` | inspection/case lifecycle row | registration, inspection, result, team, document, workflow fields mixed together |
| `db.cc` | issued certificate rows | latest markers, issue/expiry dates, scope fragments, foreign keys |
| `db.dkkd` | DDKD/business eligibility certificates | may point to one or many related `db.cc` IDs through semicolon list |
| `db.Tdoi` | change handling | dossiers, submitter, handling result, decision docs, adjusted-artifact linkage |
| `db.Tdoi2` | structured rename/address detail | subordinate detail table |
| `db.DC` | narrow dictionary sheet | appears to support scope/domain code mapping |
| `Dịch-Viết tắt` | translation/abbreviation dictionary | feeds `Rutgon*` helpers |

## Representative field sets
### `db.cty`
- `ID`
- `MÃ CTY GMP`
- `MÃ CTY GLP`
- `MÃ CTY GMPbb`
- `TÊN CÔNG TY`
- `COMPANY NAME`
- `ĐỊA CHỈ TRỤ SỞ`
- `LEGAL ADDRESS`
- `TÊN VIẾT TẮT`
- `NGỪNG HOẠT ĐỘNG`

### `db.cso`
- `ID`
- `ID Cty`
- `MÃ CS GMP/GLP/GMPbb`
- `TÊN CƠ SỞ`
- `SITE NAME`
- `ĐỊA CHỈ CƠ SỞ`
- `SITE ADDRESS`
- `TỈNH/TP`
- `NGƯỜI ĐỨNG ĐẦU CƠ SỞ`
- `NGƯỜI CHỊU TRÁCH NHIỆM CHUYÊN MÔN`
- `TRÌNH ĐỘ CHUYÊN MÔN`
- `CHỨNG CHỈ HÀNH NGHỀ`

### `db.ktra`
- `ID`
- `LOẠI KT`
- `ID CƠ SỞ`
- `MÃ DC`
- `PHẠM VI KIỂM TRA`
- `TIÊU CHUẨN ÁP DỤNG`
- `LOẠI KIỂM TRA`
- Registration fields:
  - `Ngày nộp`
  - `Mã hồ sơ`
  - `Ngày thẩm định`
  - `Người thẩm định`
  - `Kết quả`
- Inspection fields:
  - `Ngày K.tra`
  - `Q. định`
  - `B. bản`
- Additional fields are exposed through names such as `db_QDKT_ktra`, `db_TiendoXL_ktra`, `db_IDCCGPs_ktra`, `db_Last_ktra`.

### `db.cc`
- `ID`
- `MỚI NHẤT`, `ID MỚI NHẤT`
- `LOẠI CC`
- `ID ĐỢT KTRA`
- `ID TĐ KHÁC`
- `ID CƠ SỞ`
- `MÃ DC`
- Site/legal address fields.
- Issue/expiry fields surfaced by names `db_Ngaycap_CCGPs`, `db_NgayHH_CCGPs`.
- Many scope columns surfaced through `db_PL_*`.
- In live legacy usage, blank `ID ĐỢT KTRA` can be legitimate for reissued or administratively issued certificates that do not originate from a real inspection row.

### `db.dkkd`
- `ID`
- `MỚI NHẤT`, `ID MỚI NHẤT`
- `ID CƠ SỞ`, `ID CTY`
- Site/legal address fields.
- Responsible pharmacist/professional fields.
- `ID CC`
- Certificate numbering and validity via `db_MaDDK_ddk`, `db_NgayCap_ddk`, `db_HHL_DDK`, `db_DBCL_ddk`.

### `db.Tdoi`
- `ID`
- `PHẠM VI`
- `MÔ TẢ`
- `ID CƠ SỞ`
- `Hồ sơ đề nghị`
- `ĐƠN VỊ ĐỀ NGHỊ`
- `Ngày nộp`
- `Ngày xử lý`
- `Người xử lý`
- `PHIẾU TRÌNH PCT`
- `PHIẾU TRÌNH CT`
- `PHIẾU TRÌNH TT`
- `Kết quả`
- `CV chấp nhận & ngày`
- `Ngày hiệu lực của TĐ`
- `IDCC_TD`
- Adjacent successor-link column for newly issued adjusted GPs certificate IDs.
- `IDDDK_TD`
- Adjacent successor-link column for newly issued adjusted DDKD IDs.

### `db.Tdoi2`
- `ID`
- `ID Gốc`
- `ID Phân loại`
- `PHÂN LOẠI`
- `TÌNH TRẠNG CHẤP NHẬN`
- `THÔNG TIN CŨ`
- `THÔNG TIN MỚI`
- `GHI CHÚ`

## Actual data semantics
- `db.ktra` is a wide-row aggregate that mixes application intake, assessment, inspection execution, decision, CAPA/history, and certificate linkage.
- `db.cc` is not just “one file per certificate”; it is a certificate business record with scope fragments and lifecycle markers.
- `db.dkkd.ID CC` can contain semicolon-separated IDs, so the actual relationship is many-to-many and not a simple FK column.
- `MỚI NHẤT` and `ID MỚI NHẤT` fields indicate lineage/version chains inside flat tables.
- `db.Tdoi` is a change-workflow hub, not only a correspondence log.
- `db.Tdoi` separates current artifacts being changed from successor artifacts newly issued because of that change.
- `db.Tdoi2` is the structured child table for before/after change details that operators edit explicitly.

## Audit findings from automated checks
- No duplicate `ID` values were found in the seven audited core sheets after header-row normalization.
- No simple FK orphans were found for:
  - `db.cso.ID Cty`
  - `db.ktra.ID Cơ sở`
  - `db.cc.ID ĐỢT KTRA`
  - `db.cc.ID Cơ sở`
  - `db.dkkd.ID CC`
- Baseline note `db.dkkd ID=385` is present as a single row in the workbook snapshot inspected here, so the previously confirmed duplicate may have already been manually cleaned in this copy or existed in another baseline snapshot.

## Legacy constraints to preserve
- Company/site/case/certificate legacy IDs must be preserved in migration mapping tables.
- Folder identity must not use descriptive names.
- DDKD-to-CC relation must allow multiple source certificates.
- Document scope fragments currently embedded in `db.cc` should migrate into structured scope tables or child records, not stay as one flat wide table.
