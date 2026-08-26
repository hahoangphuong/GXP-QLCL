# Phase 5 Template Contract Reconciliation

## Scope
- Input 1: curated payload registry from VBA-derived bookmark evidence.
- Input 2: real active template bookmark audit from `legacy/Templates`.
- Goal: produce a safe reconciliation layer before any runtime aliasing is introduced.

## Families
- `INSPECTION_BBTD_HOSO_DK` | status=`bookmark_contract_mismatch` | payload_fields=4 | real_bookmarks=15 | resolutions=prefix_variant_group=4
  files: `1. BBTD Ho so DK - GLP - Moi.dotx`, `1. BBTD Ho so DK - GLP - Tai.dotx`, `1. BBTD Ho so DK - GMP - Moi.dotx`, `1. BBTD Ho so DK - GMP - Tai.dotx`, `1. BBTD Ho so DK - GMPbb - Moi.dotx`, `1. BBTD Ho so DK - GMPbb - Tai.dotx`, `1. BBTD Ho so DK - GSP - Moi.dotx`, `1. BBTD Ho so DK - GSP - Tai.dotx`
  unmatched real bookmarks: `TenNguoiPhuTrach1`, `TenNguoiPhuTrach2`, `TenNguoiPhuTrach3`
- `INSPECTION_QD_KT` | status=`bookmark_contract_mismatch` | payload_fields=35 | real_bookmarks=22 | resolutions=exact=4, prefix_variant_group=5, unresolved=26
  files: `2. QD KT - GLP.dotx`, `2. QD KT - GMP.dotx`, `2. QD KT - GMPbb.dotx`, `2. QD KT - GSP.dotx`
  unresolved fields: `Daychuyen`, `Diachicoso`, `Fulldate`, `GhPviCN`, `GhPviDG`, `GioiHanPvi`, `HsDK`, `NgayKT`, `NgayKTx`, `NgaynopHsDK`, `NgayQDKT`, `PVCepha`, `PVDuoclieu`, `PVNangmem`, `PVNhomat`, `PVPeni`, `PVSuibot`, `PVTiem`, `QDKT`, `ThoigianKT`
  unmatched real bookmarks: `CTky`, `PCTky`, `TT1x`, `TT2x`, `TT_ext`, `VKN1`, `VKN2`
- `INSPECTION_KE_HOACH_KT` | status=`bookmark_contract_mismatch` | payload_fields=35 | real_bookmarks=33 | resolutions=case_insensitive_exact=2, exact=14, prefix_variant_group=7, unresolved=12
  files: `3. Kế hoạch kiểm tra GLP.dotx`, `3. Kế hoạch kiểm tra GMP.dotx`, `3. Kế hoạch kiểm tra GMPbb.dotx`, `3. Kế hoạch kiểm tra GSP.dotx`
  unresolved fields: `GhPviCN`, `HsDK`, `MoiDel`, `NgayKT`, `NgayKTx`, `NgaynopHsDK`, `TaiDel`, `ThoigianKT`, `TT`, `TT1`, `TT2`, `VKN`
  unmatched real bookmarks: `DGMoi`, `TT1x`, `TT2x`, `TT_ext`
- `INSPECTION_BB_KT` | status=`bookmark_contract_mismatch` | payload_fields=35 | real_bookmarks=56 | resolutions=exact=18, prefix_variant_group=4, unresolved=13
  files: `4. BB KT - GLP.dotx`, `4. BB KT - GMP.dotx`, `4. BB KT - GSP.dotx`
  unresolved fields: `Fulldate`, `GioiHanPvi`, `MoiDel`, `PVCepha`, `PVDuoclieu`, `PVNangmem`, `PVNhomat`, `PVPeni`, `PVSuibot`, `PVTiem`, `TieuchuanKT`, `TT`, `VKN`
  unmatched real bookmarks: `CapDDKKD1`, `DiachiTruso1`, `DsTT`, `EU_Ref`, `NoWHO_Del1`, `TT1x`, `TT2x`, `TT_ext`, `TTs1`, `TTs10`, `TTs11`, `TTs12`, `TTs13`, `TTs2`, `TTs3`, `TTs4`, `TTs5`, `TTs6`, `TTs7`, `TTs8`
- `INSPECTION_CAPA_LAN_1` | status=`template_verified_copy_forward_pending` | payload_fields=11 | real_bookmarks=27 | resolutions=exact=11
  files: `5. Danh gia CAPA - GLP.dotx`, `5. Danh gia CAPA - GMP.dotx`
  unmatched real bookmarks: `DsTT_Title`, `DsTTDel`, `DsTTx`, `TTs10x`, `TTs11x`, `TTs12x`, `TTs13x`, `TTs1x`, `TTs2x`, `TTs3x`, `TTs4x`, `TTs5x`, `TTs6x`, `TTs7x`, `TTs8x`, `TTs9x`
- `INSPECTION_CAPA_LAN_2` | status=`template_verified_copy_forward_pending` | payload_fields=11 | real_bookmarks=27 | resolutions=exact=11
  files: `5. Danh gia CAPA - GLP.dotx`, `5. Danh gia CAPA - GMP.dotx`
  unmatched real bookmarks: `DsTT_Title`, `DsTTDel`, `DsTTx`, `TTs10x`, `TTs11x`, `TTs12x`, `TTs13x`, `TTs1x`, `TTs2x`, `TTs3x`, `TTs4x`, `TTs5x`, `TTs6x`, `TTs7x`, `TTs8x`, `TTs9x`
- `INSPECTION_PT_PCT` | status=`bookmark_contract_mismatch` | payload_fields=14 | real_bookmarks=19 | resolutions=exact=10, prefix_variant_group=4
  files: `6. PT.PCT - GLP.dotx`, `6. PT.PCT - GMP.dotx`
- `INSPECTION_PT_CT` | status=`bookmark_contract_mismatch` | payload_fields=14 | real_bookmarks=18 | resolutions=exact=10, prefix_variant_group=3, unresolved=1
  files: `7. PT.CT - GLP.dotx`, `7. PT.CT - GMP.dotx`
  unresolved fields: `GioihanPvi`
- `CERTIFICATE_DECISION` | status=`bookmark_contract_mismatch` | payload_fields=15 | real_bookmarks=16 | resolutions=case_insensitive_exact=1, exact=6, prefix_variant_group=2, unresolved=6
  files: `8. QD cap CC - GLP.dotx`, `8. QD cap CC - GMP.dotx`, `8. QD cap CC - GMPbb.dotx`, `8. QD cap CC - GSP.dotx`
  unresolved fields: `Chuthich`, `ChuthichDel`, `iBoth`, `iNgLieu`, `iThanhpham`, `NgayHethan`
  unmatched real bookmarks: `HsTai`, `vaBCKP`
- `CERTIFICATE_ISSUANCE_WORD` | status=`powerpoint_or_non_word_variant_present` | payload_fields=17 | real_bookmarks=30 | resolutions=exact=13, prefix_variant_group=3, unresolved=1
  files: `9. Chung chi GLP (moi).dotx`, `9. Chung chi GMP (moi).dotx`, `9. Chung chi GMPbb.dotx`, `9. Chung chi GMPbb.potx`
  unresolved fields: `OECD_Del`
  unmatched real bookmarks: `EU_Del1`, `EU_Del2`, `PICS_Del1`, `PICS_Del2`, `PICS_Del3`, `PICS_Del4`, `Pvi`, `WHO_Del1`, `WHO_Del2`
- `RISK_MANAGEMENT_WORKSHEET` | status=`bookmark_contract_mismatch` | payload_fields=7 | real_bookmarks=8 | resolutions=case_insensitive_exact=1, exact=6
  files: `10. Bảng công cụ quản lý rủi ro.dotx`
  unmatched real bookmarks: `BM15`
- `STATUS_CONFIRMATION_LETTER` | status=`bookmark_contract_mismatch` | payload_fields=37 | real_bookmarks=17 | resolutions=exact=10, prefix_variant_group=15, unresolved=12
  files: `a. CV xác nhận tình trạng.dotx`
  unresolved fields: `ChoKT`, `CoQDKT`, `MahsDKKT`, `MahsDKKT2`, `MahsDKKT3`, `NgaycapDDK`, `NgaycapDDK2`, `NgayQDKT`, `NgayQDKT2`, `NgayQDKT3`, `QDKT2`, `QDKT3`
- `NAME_ADDRESS_CHANGE_LETTER` | status=`bookmark_contract_mismatch` | payload_fields=6 | real_bookmarks=16 | resolutions=prefix_variant_group=5, unresolved=1
  files: `b. CV trả lời đồng ý đổi tên, địa chỉ.dotx`
  unresolved fields: `SoQD`
  unmatched real bookmarks: `NgayCVden`, `SoCVden`, `SoQD1`, `SoQD2`
- `CHANGE_REPORT_ROUTE_LETTER` | status=`bookmark_contract_mismatch` | payload_fields=6 | real_bookmarks=5 | resolutions=unresolved=6
  files: `11. Đánh giá báo cáo thay đổi.dotx`
  unresolved fields: `HsDKKT`, `NgayDKKT`, `NgayGCN`, `QDGCN`, `SoGCN`, `TenCtydd`
  unmatched real bookmarks: `Daychuyen`, `Diachi`, `NXL`, `TDay`, `TenCty`
- `ASSESSMENT_MINUTES` | status=`bookmark_contract_mismatch` | payload_fields=5 | real_bookmarks=38 | resolutions=case_insensitive_exact=1, prefix_variant_group=1, unresolved=3
  files: `3.2. Biên bản đánh giá GLP.dotx`, `3.2. Biên bản đánh giá GMP.dotx`
  unresolved fields: `NXL`, `Tday`, `TenCty`
  unmatched real bookmarks: `DsTT`, `GioiHanPvi`, `NgayKTe`, `NgayKTs`, `NgayKTx`, `TenCoSo1`, `Tencoso2`, `Tencoso3`, `Tieuchuan`, `TieuchuanKT`, `Tinhthanh`, `TT1`, `TT1x`, `TT1xxx`, `TT2`, `TT2x`, `TT3`, `TT3_Del`, `TT3x`, `TT3x_Del`
- `CONSENT_CHANGE_LETTER` | status=`bookmark_contract_mismatch` | payload_fields=37 | real_bookmarks=25 | resolutions=exact=17, prefix_variant_group=11, unresolved=9
  files: `d. CV đồng ý thay đổi.dotx`
  unresolved fields: `ChoKT`, `CoQDKT`, `NgaycapDDK`, `NgaycapDDK2`, `NgayQDKT`, `NgayQDKT2`, `NgayQDKT3`, `QDKT2`, `QDKT3`
- `DDKD_PRESENTATION` | status=`bookmark_contract_mismatch` | payload_fields=34 | real_bookmarks=86 | resolutions=exact=18, prefix_variant_group=14, unresolved=2
  files: `z1. PT TT - Cấp ĐĐKKDD.dotx`, `z1. PT TT - Cấp ĐĐKKDD.pdf`
  unresolved fields: `cb`, `PviCN_Rg`
  unmatched real bookmarks: `cb1`, `cb2`, `cb3`, `cb4`, `cb5`, `cb6`, `cb7`, `Co_Ng_DBCL`, `NgayGCN1`, `NgayGCN2`, `SoGCN1`, `SoGCN2`
- `DDKD_CERTIFICATE` | status=`template_verified_word_ooxml` | payload_fields=18 | real_bookmarks=18 | resolutions=exact=18
  files: `z2. Giấy chứng nhận ĐĐKKDD (Mới).dotx`, `z2. Giấy chứng nhận ĐĐKKDD (Điều chỉnh).dotx`
- `DDKD_APPENDIX_OR_DECISION` | status=`bookmark_contract_mismatch` | payload_fields=28 | real_bookmarks=46 | resolutions=case_insensitive_exact=1, exact=17, prefix_variant_group=7, unresolved=3
  files: `z3. Phụ lục GCN ĐĐKKDD.dotx`, `z4. QĐ cấp ĐĐKKDD.dotx`
  unresolved fields: `All`, `GCN_GMP`, `QD_GMP`
  unmatched real bookmarks: `AllGDP`, `AllGLP`, `AllGMP`, `AllGSP`, `PviGDP`, `PviGLP`, `PviGMP`, `PviGSP`
- `DDKD_APPENDIX_OR_DECISION` | status=`bookmark_contract_mismatch` | payload_fields=28 | real_bookmarks=46 | resolutions=case_insensitive_exact=1, exact=17, prefix_variant_group=7, unresolved=3
  files: `z3. Phụ lục GCN ĐĐKKDD.dotx`, `z4. QĐ cấp ĐĐKKDD.dotx`
  unresolved fields: `All`, `GCN_GMP`, `QD_GMP`
  unmatched real bookmarks: `AllGDP`, `AllGLP`, `AllGMP`, `AllGSP`, `PviGDP`, `PviGLP`, `PviGMP`, `PviGSP`
- `SUPPORT_TRAVEL_AUTHORIZATION` | status=`bookmark_contract_mismatch` | payload_fields=33 | real_bookmarks=8 | resolutions=exact=8, prefix_variant_group=1, signature_exact=1, unresolved=23
  files: `.Giấy đi đường.dotx`
  unresolved fields: `Diachicoso`, `GPs`, `NganHang`, `NgaycapCMT`, `NoicapCMT`, `Phongve`, `Sanbay`, `SoCMT`, `SoTien`, `SoTienBangChu`, `SoTK`, `TenCoSo`, `TenCty`, `TinhTP_Cty`, `TT1x`, `TT2x`, `TT2xx`, `TT3`, `TT_ext`, `TT_SYT`
- `SUPPORT_FLIGHT_REQUEST` | status=`bookmark_contract_mismatch` | payload_fields=33 | real_bookmarks=8 | resolutions=exact=8, signature_exact=1, unresolved=24
  files: `.Xin đi máy bay.dotx`
  unresolved fields: `Chucvu`, `Congtac`, `Diachicoso`, `NganHang`, `NgaycapCMT`, `NgayQDKTx`, `NoicapCMT`, `Phongve`, `SoCMT`, `SoTien`, `SoTienBangChu`, `SoTK`, `TenCoSo`, `Tinhthanh`, `Tinhthanh2`, `TT1x`, `TT2x`, `TT2xx`, `TT3`, `TT_ext`
- `SUPPORT_ATTENDEE_LIST` | status=`bookmark_contract_mismatch` | payload_fields=33 | real_bookmarks=10 | resolutions=exact=7, unresolved=26
  files: `.Ds tham dự đợt kiểm tra.dotx`
  unresolved fields: `Chucvu`, `Congtac`, `GPs`, `NganHang`, `NgaycapCMT`, `NgayQDKT`, `NgayQDKTx`, `NoicapCMT`, `Phongve`, `QDKT`, `Sanbay`, `SoCMT`, `SoTien`, `SoTienBangChu`, `SoTK`, `TenCty`, `Tinhthanh`, `Tinhthanh2`, `TinhTP_Cty`, `TT2x`
  unmatched real bookmarks: `TT1`, `TT2`, `TT3_Del`
- `SUPPORT_DOSSIER_CHECKLIST` | status=`bookmark_contract_mismatch` | payload_fields=33 | real_bookmarks=4 | resolutions=case_insensitive_exact=1, exact=3, unresolved=29
  files: `.Checklist hồ sơ GPs.dotx`, `.Checklist kiểm tra GPs.dotx`
  unresolved fields: `Chucvu`, `Congtac`, `Diachicoso`, `NganHang`, `NgaycapCMT`, `NgayQDKT`, `NgayQDKTx`, `NoicapCMT`, `Phongve`, `Sanbay`, `SoCMT`, `SoTien`, `SoTienBangChu`, `SoTK`, `Tinhthanh`, `Tinhthanh2`, `TinhTP_Cty`, `TT1x`, `TT2x`, `TT2xx`
- `SUPPORT_PAYMENT_TRANSFER` | status=`bookmark_contract_mismatch` | payload_fields=33 | real_bookmarks=26 | resolutions=exact=18, prefix_variant_group=1, signature_exact=1, unresolved=13
  files: `.Giấy xin séc chuyển khoản.dotx`, `.Uy quyen thanh toan CTP.dotx`
  unresolved fields: `Chucvu`, `Congtac`, `Diachicoso`, `GPs`, `Sanbay`, `TenCoSo`, `Tinhthanh`, `Tinhthanh2`, `TinhTP_Cty`, `TT1x`, `TT_ext`, `TT_SYT`, `TT_VKN`
  unmatched real bookmarks: `TT1`, `TT2`, `TT2Del`, `TT3Del`, `TT4`, `TT4Del`, `TT5`, `TT5Del`
- `SUPPORT_PAYMENT_WORKBOOK` | status=`out_of_scope_excel_template` | payload_fields=0 | real_bookmarks=0 | resolutions=
  files: `.Thanh toán tạm ứng.xltx`, `.Đề nghị thanh toánx.xltx`
