# Phase 5 BBTD Variant Contracts

## Scope
- Family: `INSPECTION_BBTD_HOSO_DK`
- Evidence source: active templates under `legacy/Templates` matched to the BBTD family.
- Mapping source: `artifacts/phase5/template_contract_reconciled.json`

## Variants
- `bbtd_hoso_dk_line_1`
  examples: `1. BBTD Ho so DK - GLP - Moi.dotx, 1. BBTD Ho so DK - GMPbb - Moi.dotx, 1. BBTD Ho so DK - GMPbb - Tai.dotx`
  allowed fields: `Daychuyen, Diachicoso, Fulldate, Tencoso`
  field mappings: `Daychuyen->DayChuyen1, Diachicoso->DiaChiCoSo1, Fulldate->Fulldate1, Tencoso->TenCoSo1`
- `bbtd_hoso_dk_line_2`
  examples: `1. BBTD Ho so DK - GLP - Tai.dotx`
  allowed fields: `Daychuyen, Diachicoso, Fulldate, Tencoso`
  field mappings: `Daychuyen->DayChuyen2, Diachicoso->DiaChiCoSo2, Fulldate->Fulldate1, Tencoso->TenCoSo2`
- `bbtd_hoso_dk_line_3`
  examples: `1. BBTD Ho so DK - GSP - Moi.dotx, 1. BBTD Ho so DK - GSP - Tai.dotx`
  allowed fields: `Daychuyen, Diachicoso, Fulldate, Tencoso`
  field mappings: `Daychuyen->DayChuyen3, Diachicoso->DiaChiCoSo3, Fulldate->Fulldate1, Tencoso->TenCoSo3`
- `bbtd_hoso_dk_all_lines`
  examples: `1. BBTD Ho so DK - GMP - Moi.dotx, 1. BBTD Ho so DK - GMP - Tai.dotx`
  allowed fields: `Daychuyen, Diachicoso, Fulldate, Tencoso`
  field mappings: `Daychuyen->DayChuyen1/DayChuyen2/DayChuyen3, Diachicoso->DiaChiCoSo1/DiaChiCoSo2/DiaChiCoSo3, Fulldate->Fulldate1/Fulldate2/Fulldate3, Tencoso->TenCoSo1/TenCoSo2/TenCoSo3`
