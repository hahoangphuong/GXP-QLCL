# Phase 5 Real Template Compatibility Audit

## Scope
- Evidence source: active top-level files under `legacy/Templates`.
- Archived revisions under `legacy/Templates/Cũ` are intentionally excluded from the compatibility baseline.
- Active files scanned: `91`.
- Registry families scanned: `26`.

## Family Matrix
- `INSPECTION_BBTD_HOSO_DK` | status=`bookmark_contract_mismatch` | files=8 | expected=4 | actual=15 | header/footer=False | table-bookmarks=True
  files: `1. BBTD Ho so DK - GLP - Moi.dotx`, `1. BBTD Ho so DK - GLP - Tai.dotx`, `1. BBTD Ho so DK - GMP - Moi.dotx`, `1. BBTD Ho so DK - GMP - Tai.dotx`, `1. BBTD Ho so DK - GMPbb - Moi.dotx`, `1. BBTD Ho so DK - GMPbb - Tai.dotx`, `1. BBTD Ho so DK - GSP - Moi.dotx`, `1. BBTD Ho so DK - GSP - Tai.dotx`
  missing bookmarks: `Daychuyen`, `Diachicoso`, `Fulldate`, `Tencoso`
  extra bookmarks: `DayChuyen1`, `DayChuyen2`, `DayChuyen3`, `DiaChiCoSo1`, `DiaChiCoSo2`, `DiaChiCoSo3`, `Fulldate1`, `Fulldate2`, `Fulldate3`, `TenCoSo1`, `TenCoSo2`, `TenCoSo3`, `TenNguoiPhuTrach1`, `TenNguoiPhuTrach2`, `TenNguoiPhuTrach3`
- `INSPECTION_QD_KT` | status=`bookmark_contract_mismatch` | files=4 | expected=35 | actual=22 | header/footer=False | table-bookmarks=True
  files: `2. QD KT - GLP.dotx`, `2. QD KT - GMP.dotx`, `2. QD KT - GMPbb.dotx`, `2. QD KT - GSP.dotx`
  missing bookmarks: `Daychuyen`, `Diachicoso`, `Diadiem`, `Diadiemx`, `Fulldate`, `GhPviCN`, `GhPviDG`, `GioiHanPvi`, `HsDK`, `MoiDel`, `NgayKT`, `NgayKTx`, `NgaynopHsDK`, `NgayQDKT`, `PVCepha`, `PVDuoclieu`, `PVNangmem`, `PVNhomat`, `PVPeni`, `PVSuibot`
  extra bookmarks: `CTky`, `Diadiemx1`, `Diadiemx2`, `Diadiemx3`, `MoiDel2`, `PCTky`, `TaiDel1`, `TaiDel2`, `TaiDel3`, `TaiDel4`, `Tencoso1`, `Tencoso2`, `Tencoso3`, `TT1x`, `TT2x`, `TT_ext`, `VKN1`, `VKN2`
- `INSPECTION_KE_HOACH_KT` | status=`bookmark_contract_mismatch` | files=4 | expected=35 | actual=33 | header/footer=False | table-bookmarks=True
  files: `3. Kế hoạch kiểm tra GLP.dotx`, `3. Kế hoạch kiểm tra GMP.dotx`, `3. Kế hoạch kiểm tra GMPbb.dotx`, `3. Kế hoạch kiểm tra GSP.dotx`
  missing bookmarks: `Daychuyen`, `Diachicoso`, `Diadiem`, `GhPviCN`, `HsDK`, `MoiDel`, `NgayKT`, `NgayKTx`, `NgaynopHsDK`, `PVCepha`, `PVDuoclieu`, `PVNangmem`, `PVPeni`, `PVTiem`, `TaiDel`, `Tencoso`, `ThoigianKT`, `TT`, `TT1`, `TT2`
  extra bookmarks: `DayChuyen`, `DGMoi`, `DiaChiCoSo`, `Diadiemx1`, `PVCepha1`, `PVCepha2`, `PVDuoclieu1`, `PVDuoclieu2`, `PVNangmem1`, `PVNangmem2`, `PVPeni1`, `PVPeni2`, `PVTiem1`, `PVTiem2`, `PVTiem3`, `TenCoSo1`, `TT1x`, `TT2x`, `TT_ext`
- `INSPECTION_BB_KT` | status=`bookmark_contract_mismatch` | files=3 | expected=35 | actual=56 | header/footer=False | table-bookmarks=True
  files: `4. BB KT - GLP.dotx`, `4. BB KT - GMP.dotx`, `4. BB KT - GSP.dotx`
  missing bookmarks: `Daychuyen`, `Diachicoso`, `Fulldate`, `GioiHanPvi`, `MoiDel`, `PVCepha`, `PVDuoclieu`, `PVNangmem`, `PVNhomat`, `PVPeni`, `PVSuibot`, `PVTiem`, `TaiDel`, `Tencoso`, `TieuchuanKT`, `TT`, `VKN`
  extra bookmarks: `CapDDKKD1`, `Daychuyen1`, `Daychuyen2`, `Daychuyen3`, `Diachicoso1`, `Diachicoso2`, `DiachiTruso1`, `DsTT`, `EU_Ref`, `NoWHO_Del1`, `TaiDel2`, `Tencoso1`, `Tencoso2`, `Tencoso3`, `Tencoso4`, `Tencoso5`, `Tencoso6`, `Tencoso7`, `Tencoso8`, `Tencoso9`
- `INSPECTION_CAPA_LAN_1` | status=`template_verified_copy_forward_pending` | files=2 | expected=11 | actual=27 | header/footer=False | table-bookmarks=True
  files: `5. Danh gia CAPA - GLP.dotx`, `5. Danh gia CAPA - GMP.dotx`
  extra bookmarks: `DsTT_Title`, `DsTTDel`, `DsTTx`, `TTs10x`, `TTs11x`, `TTs12x`, `TTs13x`, `TTs1x`, `TTs2x`, `TTs3x`, `TTs4x`, `TTs5x`, `TTs6x`, `TTs7x`, `TTs8x`, `TTs9x`
- `INSPECTION_CAPA_LAN_2` | status=`template_verified_copy_forward_pending` | files=2 | expected=11 | actual=27 | header/footer=False | table-bookmarks=True
  files: `5. Danh gia CAPA - GLP.dotx`, `5. Danh gia CAPA - GMP.dotx`
  extra bookmarks: `DsTT_Title`, `DsTTDel`, `DsTTx`, `TTs10x`, `TTs11x`, `TTs12x`, `TTs13x`, `TTs1x`, `TTs2x`, `TTs3x`, `TTs4x`, `TTs5x`, `TTs6x`, `TTs7x`, `TTs8x`, `TTs9x`
- `INSPECTION_PT_PCT` | status=`bookmark_contract_mismatch` | files=2 | expected=14 | actual=19 | header/footer=False | table-bookmarks=True
  files: `6. PT.PCT - GLP.dotx`, `6. PT.PCT - GMP.dotx`
  missing bookmarks: `Daychuyen`, `Diachicoso`, `NgayKT2`, `Tencoso`
  extra bookmarks: `Diachicoso1`, `Diachicoso2`, `NgayKT21`, `NgayKT22`, `Tencoso1`, `Tencoso2`, `Tencoso3`, `Tencoso4`, `Tencoso5`
- `INSPECTION_PT_CT` | status=`bookmark_contract_mismatch` | files=2 | expected=14 | actual=18 | header/footer=False | table-bookmarks=True
  files: `7. PT.CT - GLP.dotx`, `7. PT.CT - GMP.dotx`
  missing bookmarks: `Diachicoso`, `GioihanPvi`, `NgayKT2`, `Tencoso`
  extra bookmarks: `Diachicoso1`, `Diachicoso2`, `NgayKT21`, `NgayKT22`, `Tencoso1`, `Tencoso2`, `Tencoso3`, `Tencoso4`
- `CERTIFICATE_DECISION` | status=`bookmark_contract_mismatch` | files=4 | expected=15 | actual=16 | header/footer=False | table-bookmarks=False
  files: `8. QD cap CC - GLP.dotx`, `8. QD cap CC - GMP.dotx`, `8. QD cap CC - GMPbb.dotx`, `8. QD cap CC - GSP.dotx`
  missing bookmarks: `Chuthich`, `ChuthichDel`, `iBoth`, `iNgLieu`, `iThanhpham`, `NgayHethan`, `TenCoso`, `Tencoso5`, `TenCty`
  extra bookmarks: `HsTai`, `Tencoso`, `Tencoso1`, `Tencoso2`, `Tencoso3`, `Tencoso4`, `TenCty1`, `TenCty2`, `TenCty3`, `vaBCKP`
- `CERTIFICATE_ISSUANCE_WORD` | status=`powerpoint_or_non_word_variant_present` | files=4 | expected=17 | actual=30 | header/footer=False | table-bookmarks=True
  files: `9. Chung chi GLP (moi).dotx`, `9. Chung chi GMP (moi).dotx`, `9. Chung chi GMPbb.dotx`, `9. Chung chi GMPbb.potx`
  missing bookmarks: `NoEU_Del`, `NoPICS_Del`, `NoWHO_Del`, `OECD_Del`
  extra bookmarks: `EU_Del1`, `EU_Del2`, `NoEU_Del1`, `NoEU_Del2`, `NoPICS_Del1`, `NoPICS_Del2`, `NoWHO_Del1`, `NoWHO_Del2`, `NoWHO_Del3`, `NoWHO_Del4`, `PICS_Del1`, `PICS_Del2`, `PICS_Del3`, `PICS_Del4`, `Pvi`, `WHO_Del1`, `WHO_Del2`
- `RISK_MANAGEMENT_WORKSHEET` | status=`bookmark_contract_mismatch` | files=1 | expected=7 | actual=8 | header/footer=False | table-bookmarks=True
  files: `10. Bảng công cụ quản lý rủi ro.dotx`
  missing bookmarks: `Tday`
  extra bookmarks: `BM15`, `TDay`
- `STATUS_CONFIRMATION_LETTER` | status=`bookmark_contract_mismatch` | files=1 | expected=37 | actual=17 | header/footer=False | table-bookmarks=False
  files: `a. CV xác nhận tình trạng.dotx`
  missing bookmarks: `ChoKT`, `CoQDKT`, `DiachiCty`, `MahsDKKT`, `MahsDKKT2`, `MahsDKKT3`, `NgaycapDDK`, `NgaycapDDK2`, `NgayDKKT2`, `NgayDKKT3`, `NgayGCN2`, `NgayGCN3`, `NgayKT2`, `NgayKT3`, `NgayQDKT`, `NgayQDKT2`, `NgayQDKT3`, `PhamviKT`, `QDcapDDK2`, `QDGCN2`
  extra bookmarks: `DiachiCty1`, `PhamviKT1`, `TenCtydd1`, `TenCtydd2`, `TenCtydd3`, `TenCtydd4`, `TenCtydd5`
- `NAME_ADDRESS_CHANGE_LETTER` | status=`bookmark_contract_mismatch` | files=1 | expected=6 | actual=16 | header/footer=False | table-bookmarks=False
  files: `b. CV trả lời đồng ý đổi tên, địa chỉ.dotx`
  missing bookmarks: `DiachiCty`, `NgayGCN`, `SoGCN`, `SoQD`, `TenCtydd`, `TenCtyTA`
  extra bookmarks: `DiachiCty1`, `DiachiCty2`, `NgayCVden`, `NgayGCN1`, `NgayGCN2`, `SoCVden`, `SoGCN1`, `SoGCN2`, `SoQD1`, `SoQD2`, `TenCtydd1`, `TenCtydd2`, `TenCtydd3`, `TenCtydd4`, `TenCtyTA1`, `TenCtyTA2`
- `CHANGE_REPORT_ROUTE_LETTER` | status=`bookmark_contract_mismatch` | files=1 | expected=6 | actual=5 | header/footer=False | table-bookmarks=True
  files: `11. Đánh giá báo cáo thay đổi.dotx`
  missing bookmarks: `HsDKKT`, `NgayDKKT`, `NgayGCN`, `QDGCN`, `SoGCN`, `TenCtydd`
  extra bookmarks: `Daychuyen`, `Diachi`, `NXL`, `TDay`, `TenCty`
- `ASSESSMENT_MINUTES` | status=`bookmark_contract_mismatch` | files=2 | expected=5 | actual=38 | header/footer=False | table-bookmarks=True
  files: `3.2. Biên bản đánh giá GLP.dotx`, `3.2. Biên bản đánh giá GMP.dotx`
  missing bookmarks: `Daychuyen`, `Diachi`, `NXL`, `Tday`, `TenCty`
  extra bookmarks: `DayChuyen`, `Diachicoso`, `DsTT`, `GioiHanPvi`, `NgayKTe`, `NgayKTs`, `NgayKTx`, `TenCoSo1`, `Tencoso2`, `Tencoso3`, `Tieuchuan`, `TieuchuanKT`, `Tinhthanh`, `TT1`, `TT1x`, `TT1xxx`, `TT2`, `TT2x`, `TT3`, `TT3_Del`
- `CONSENT_CHANGE_LETTER` | status=`bookmark_contract_mismatch` | files=1 | expected=37 | actual=25 | header/footer=False | table-bookmarks=False
  files: `d. CV đồng ý thay đổi.dotx`
  missing bookmarks: `ChoKT`, `CoQDKT`, `DiachiCty`, `MahsDKKT3`, `NgaycapDDK`, `NgaycapDDK2`, `NgayDKKT3`, `NgayGCN3`, `NgayKT3`, `NgayQDKT`, `NgayQDKT2`, `NgayQDKT3`, `PhamviKT`, `QDGCN2`, `QDGCN3`, `QDKT2`, `QDKT3`, `SoDDK_3`, `SoGCN3`, `TenCtydd`
  extra bookmarks: `DiachiCty1`, `PhamviKT1`, `TenCtydd1`, `TenCtydd2`, `TenCtydd3`, `TenCtydd4`, `TenCtydd5`, `TenCtydd6`
- `DDKD_PRESENTATION` | status=`bookmark_contract_mismatch` | files=2 | expected=34 | actual=86 | header/footer=False | table-bookmarks=True
  files: `z1. PT TT - Cấp ĐĐKKDD.dotx`, `z1. PT TT - Cấp ĐĐKKDD.pdf`
  missing bookmarks: `Cap_DC`, `cb`, `Co_Doiten`, `Co_KSDB`, `Comment`, `Diadiemx`, `GCN_GPs`, `GiayDK_cu`, `Loaihinh`, `NgaycapDK_cu`, `Nguoi_DBCL_Ten`, `Nguoi_PTCM_Ten`, `PviCN_Rg`, `QDcap_cu`, `TenCty`, `TenCty_cu`
  extra bookmarks: `Cap_DC1`, `Cap_DC2`, `Cap_DC3`, `Cap_DC4`, `cb1`, `cb2`, `cb3`, `cb4`, `cb5`, `cb6`, `cb7`, `Co_Doiten1`, `Co_Doiten2`, `Co_KSDB1`, `Co_KSDB2`, `Co_Ng_DBCL`, `Comment1`, `Comment2`, `Comment3`, `Comment4`
- `DDKD_CERTIFICATE` | status=`template_verified_word_ooxml` | files=2 | expected=18 | actual=18 | header/footer=False | table-bookmarks=False
  files: `z2. Giấy chứng nhận ĐĐKKDD (Mới).dotx`, `z2. Giấy chứng nhận ĐĐKKDD (Điều chỉnh).dotx`
- `DDKD_APPENDIX_OR_DECISION` | status=`bookmark_contract_mismatch` | files=2 | expected=28 | actual=46 | header/footer=False | table-bookmarks=False
  files: `z3. Phụ lục GCN ĐĐKKDD.dotx`, `z4. QĐ cấp ĐĐKKDD.dotx`
  missing bookmarks: `All`, `Chuthich`, `Co_Chuthich`, `Co_Doiten`, `GCN_GMP`, `GiayDK_cu`, `NgaycapDK_cu`, `QD_GMP`, `QDcap_cu`, `TenCty`, `TenCty_ddk_cu`
  extra bookmarks: `AllGDP`, `AllGLP`, `AllGMP`, `AllGSP`, `ChuthichGDP`, `ChuthichGLP`, `ChuthichGMP`, `ChuthichGSP`, `Co_ChuthichGDP`, `Co_ChuthichGLP`, `Co_ChuthichGMP`, `Co_ChuthichGSP`, `Co_DoiTen`, `GiayDK_cu1`, `NgaycapDK_cu1`, `NgaycapDK_cu2`, `NgaycapDK_cu3`, `PviGDP`, `PviGLP`, `PviGMP`
- `DDKD_APPENDIX_OR_DECISION` | status=`bookmark_contract_mismatch` | files=2 | expected=28 | actual=46 | header/footer=False | table-bookmarks=False
  files: `z3. Phụ lục GCN ĐĐKKDD.dotx`, `z4. QĐ cấp ĐĐKKDD.dotx`
  missing bookmarks: `All`, `Chuthich`, `Co_Chuthich`, `Co_Doiten`, `GCN_GMP`, `GiayDK_cu`, `NgaycapDK_cu`, `QD_GMP`, `QDcap_cu`, `TenCty`, `TenCty_ddk_cu`
  extra bookmarks: `AllGDP`, `AllGLP`, `AllGMP`, `AllGSP`, `ChuthichGDP`, `ChuthichGLP`, `ChuthichGMP`, `ChuthichGSP`, `Co_ChuthichGDP`, `Co_ChuthichGLP`, `Co_ChuthichGMP`, `Co_ChuthichGSP`, `Co_DoiTen`, `GiayDK_cu1`, `NgaycapDK_cu1`, `NgaycapDK_cu2`, `NgaycapDK_cu3`, `PviGDP`, `PviGLP`, `PviGMP`
- `SUPPORT_TRAVEL_AUTHORIZATION` | status=`bookmark_contract_mismatch` | files=1 | expected=33 | actual=8 | header/footer=False | table-bookmarks=True
  files: `.Giấy đi đường.dotx`
  missing bookmarks: `Diachicoso`, `GPs`, `NganHang`, `NgaycapCMT`, `NgayQDKT`, `NoicapCMT`, `Phongve`, `Sanbay`, `SoCMT`, `SoTien`, `SoTienBangChu`, `SoTK`, `TenCoSo`, `TenCty`, `TinhTP_Cty`, `TT1x`, `TT2x`, `TT2xx`, `TT3`, `TT_ext`
- `SUPPORT_FLIGHT_REQUEST` | status=`bookmark_contract_mismatch` | files=1 | expected=33 | actual=8 | header/footer=False | table-bookmarks=True
  files: `.Xin đi máy bay.dotx`
  missing bookmarks: `Chucvu`, `Congtac`, `Diachicoso`, `NganHang`, `NgaycapCMT`, `NgayQDKTx`, `NoicapCMT`, `Phongve`, `SoCMT`, `SoTien`, `SoTienBangChu`, `SoTK`, `TenCoSo`, `Tinhthanh`, `Tinhthanh2`, `TT1x`, `TT2x`, `TT2xx`, `TT3`, `TT_ext`
- `SUPPORT_ATTENDEE_LIST` | status=`bookmark_contract_mismatch` | files=1 | expected=33 | actual=10 | header/footer=False | table-bookmarks=True
  files: `.Ds tham dự đợt kiểm tra.dotx`
  missing bookmarks: `Chucvu`, `Congtac`, `GPs`, `NganHang`, `NgaycapCMT`, `NgayQDKT`, `NgayQDKTx`, `NoicapCMT`, `Phongve`, `QDKT`, `Sanbay`, `SoCMT`, `SoTien`, `SoTienBangChu`, `SoTK`, `TenCty`, `Tinhthanh`, `Tinhthanh2`, `TinhTP_Cty`, `TT2x`
  extra bookmarks: `TT1`, `TT2`, `TT3_Del`
- `SUPPORT_DOSSIER_CHECKLIST` | status=`bookmark_contract_mismatch` | files=2 | expected=33 | actual=4 | header/footer=False | table-bookmarks=True
  files: `.Checklist hồ sơ GPs.dotx`, `.Checklist kiểm tra GPs.dotx`
  missing bookmarks: `Chucvu`, `Congtac`, `Diachicoso`, `NganHang`, `NgaycapCMT`, `NgayQDKT`, `NgayQDKTx`, `NoicapCMT`, `Phongve`, `Sanbay`, `SoCMT`, `SoTien`, `SoTienBangChu`, `SoTK`, `TenCoSo`, `Tinhthanh`, `Tinhthanh2`, `TinhTP_Cty`, `TT1x`, `TT2x`
  extra bookmarks: `Tencoso`
- `SUPPORT_PAYMENT_TRANSFER` | status=`bookmark_contract_mismatch` | files=2 | expected=33 | actual=26 | header/footer=False | table-bookmarks=True
  files: `.Giấy xin séc chuyển khoản.dotx`, `.Uy quyen thanh toan CTP.dotx`
  missing bookmarks: `Chucvu`, `Congtac`, `Diachicoso`, `GPs`, `NgayQDKT`, `Sanbay`, `TenCoSo`, `Tinhthanh`, `Tinhthanh2`, `TinhTP_Cty`, `TT1x`, `TT_ext`, `TT_SYT`, `TT_VKN`, `TTV2`
  extra bookmarks: `TT1`, `TT2`, `TT2Del`, `TT3Del`, `TT4`, `TT4Del`, `TT5`, `TT5Del`
- `SUPPORT_PAYMENT_WORKBOOK` | status=`out_of_scope_excel_template` | files=2 | expected=0 | actual=0 | header/footer=False | table-bookmarks=False
  files: `.Thanh toán tạm ứng.xltx`, `.Đề nghị thanh toánx.xltx`

## Unmatched Active Files
- `.Biểu mẫu ghi chép của TT viên theo SOP đánh giá GLP năm 2025.docx` | type=`docx` | bookmarks=0
- `.Biểu mẫu ghi chép của TT viên theo SOP đánh giá GMP năm 2025.docx` | type=`docx` | bookmarks=1
- `.Bản note cho thanh tra viên.docx` | type=`docx` | bookmarks=0
- `.Danh mục tài liệu cần kiểm tra - Thuốc không vô trùng.docx` | type=`docx` | bookmarks=0
- `.Danh mục tài liệu cần kiểm tra - Thuốc vô trùng.docx` | type=`docx` | bookmarks=0
- `.Thông tin doanh nghiệp kiểm tra GMP (2).docx` | type=`docx` | bookmarks=0
- `.Thông tin doanh nghiệp kiểm tra GMP đóng gói thứ cấp.docx` | type=`docx` | bookmarks=0
- `.Thông tin doanh nghiệp kiểm tra GMP.docx` | type=`docx` | bookmarks=0
- `9. PhamviGLP.docx` | type=`docx` | bookmarks=237
- `9. PhamviGMP.docx` | type=`docx` | bookmarks=112
- `9. PhamviGSP.docx` | type=`docx` | bookmarks=52
- `Biên bản bàn giao hồ sơ.doc` | type=`doc` | bookmarks=0
- `Biên bản thẩm định hồ sơ đăng ký GLP Tái - File sửa.docx` | type=`docx` | bookmarks=5
- `c. CV chuyển hồ sơ cấp Giấy ĐĐKKDD.dotx` | type=`dotx` | bookmarks=13
- `Danh mục file tài liệu.docx` | type=`docx` | bookmarks=0
- `Danh mục hồ sơ cấp ĐĐKKDD.dotx` | type=`dotx` | bookmarks=5
- `Danh mục lưu hồ sơ 1C.docx` | type=`docx` | bookmarks=0
- `Danh mục lưu hồ sơ NN.docx` | type=`docx` | bookmarks=0
- `Danh mục lưu hồ sơ.docx` | type=`docx` | bookmarks=0
- `Danh sách tồn tại GLP.docx` | type=`docx` | bookmarks=13
- `Danh sách tồn tại GMP.docx` | type=`docx` | bookmarks=13
- `Danh sách tồn tại GSP.docx` | type=`docx` | bookmarks=4
- `DDK DUOC.docx` | type=`docx` | bookmarks=0
- `DDK1.png` | type=`png` | bookmarks=0
- `DDK2.png` | type=`png` | bookmarks=0
- `e. CV thông báo kết quả đánh giá GMP.dotx` | type=`dotx` | bookmarks=1
- `Form CAPA.dotx` | type=`dotx` | bookmarks=0
- `Giai trinh cong tac phi.doc` | type=`doc` | bookmarks=0
- `Mau phieu trinh.rar` | type=`rar` | bookmarks=0
- `Phước Sanh - đề nghị bổ sung.docx` | type=`docx` | bookmarks=0
- `PT. CT - Xin ý kiến chỉ đạo.docx` | type=`docx` | bookmarks=20
- `Xin xe ô tô đi công tác.docx` | type=`docx` | bookmarks=0
- `Xin xe ô tô đi kho Vinh phuc.docx` | type=`docx` | bookmarks=0
- `z3. PhamviGLP.docx` | type=`docx` | bookmarks=237
- `z3. PhamviGMP.docx` | type=`docx` | bookmarks=112
- `z3. PhamviGSP.docx` | type=`docx` | bookmarks=52
