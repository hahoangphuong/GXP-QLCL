# Phase 5 Document Contract Report

## Evidence summary
- Procedures with document automation signals: 25
- Applications observed: {"Excel": 2, "Word": 3}
- Legacy template files found under `legacy/`: 0
- Excluded by scope: PowerPoint-backed certificate branch

## Template inventory inferred from VBA
- `(moi).dotx` <- RecordForm.Get_Tpl
- `*.docx` <- Module1.Mo_QDKT
- `- Moi.dotx` <- RecordForm.Get_Tpl
- `- Tai.dotx` <- RecordForm.Get_Tpl
- `.Uy quyen thanh toan CTP.dotx` <- ExtRecordForm.CreateFile
- `GPs.dotx` <- ExtRecordForm.CreateFile
- `KHKT.xltx` <- Module1.UNItoVBA
- `KKDD.dotx` <- RecordForm.Get_Tpl, RecordForm.Get_Tplz
- `i máy bay.dotx` <- ExtRecordForm.CreateFile
- `i ro.dotx` <- RecordForm.Get_Tpl
- `i).dotx` <- RecordForm.Get_Tplz
- `i.dotx` <- RecordForm.Get_Tpl
- `m tra GPs.dotx` <- ExtRecordForm.CreateFile
- `m tra.dotx` <- ExtRecordForm.CreateFile
- `n.dotx` <- ExtRecordForm.CreateFile
- `ng.dotx` <- ExtRecordForm.CreateFile, RecordForm.Get_Tpl
- `ng.xltx` <- ExtRecordForm.CreateFile
- `nh).dotx` <- RecordForm.Get_Tplz
- `thanh toán.xltx` <- ExtRecordForm.CreateFile

## Copy-forward / reuse flows
- `RecordForm.Tao_BB_CAPA`
- `RecordForm.Tao_PT_PCT_CT`

## High-signal procedures
- `ExtRecordForm.CreateFile` apps=Word,Excel templates=9 writes=33 copy=0/0 outputs=.dotx,.xltx
- `Module1.Mo_QDKT` apps=- templates=1 writes=0 copy=0/0 outputs=.docx
- `Module1.UNItoVBA` apps=- templates=1 writes=0 copy=0/0 outputs=.xltx
- `RecordForm.Get_Tplz` apps=- templates=3 writes=0 copy=0/0 outputs=.dotx
- `RecordForm.Get_Tpl` apps=- templates=7 writes=0 copy=0/0 outputs=.dotx
- `RecordForm.Tao_BBTD` apps=- templates=0 writes=4 copy=0/0 outputs=-
- `RecordForm.Tao_QDKT_KHKT_BBKT` apps=- templates=0 writes=25 copy=0/0 outputs=-
- `RecordForm.Tao_BB_CAPA` apps=- templates=0 writes=9 copy=2/0 outputs=-
- `RecordForm.Tao_PT_PCT_CT` apps=- templates=0 writes=12 copy=1/1 outputs=-
- `RecordForm.Tao_QD_CapCC` apps=- templates=0 writes=11 copy=0/0 outputs=-
- `RecordForm.Tao_CC_Thongtinchung` apps=- templates=0 writes=8 copy=0/0 outputs=-
- `RecordForm.Tao_CC_ThongtinKT` apps=- templates=0 writes=2 copy=0/0 outputs=-
- `RecordForm.Tao_PL_QD_GiayDDK_Thongtinchung` apps=- templates=0 writes=22 copy=0/0 outputs=-
- `RecordForm.Tao_PL_QD_GiayDDK` apps=- templates=0 writes=1 copy=0/0 outputs=-
- `RecordForm.Tao_CC_GPs_moi` apps=- templates=0 writes=2 copy=0/0 outputs=-
- `RecordForm.Tao_BB_QLRR` apps=- templates=0 writes=7 copy=0/0 outputs=-
- `RecordForm.Tao_BB_DGTD` apps=- templates=0 writes=5 copy=0/0 outputs=-
- `RecordForm.Tao_CV_XNTT` apps=- templates=0 writes=34 copy=0/0 outputs=-
- `RecordForm.Tao_CV_Doiten_diachi` apps=- templates=0 writes=6 copy=0/0 outputs=-
- `RecordForm.Tao_CV_ChuyenKD` apps=- templates=0 writes=6 copy=0/0 outputs=-
- `RecordForm.Tao_PT_cap_DDK` apps=- templates=0 writes=22 copy=0/0 outputs=-
- `RecordForm.Tao_Giay_DDK` apps=- templates=0 writes=17 copy=0/0 outputs=-
