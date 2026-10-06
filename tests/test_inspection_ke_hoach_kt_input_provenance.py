from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

import pytest

from tools.trace_inspection_ke_hoach_kt_input_provenance import (
    build_i3_source_audit,
)
from tools.trace_inspection_qd_kt_vba import _branch_context


MODULE = """Public Sub TaoQDKT_KHKT()
    RecordForm.CreateFile foo, 2, old
End Sub
"""

RECORD = """Public s_LoaiKT As String
Public DC_cu As String
Public GHanDC As String
Public TTVdd As String
Public TTV_VKNdd As String
Public TTV_SYTdd As String
Public TenCtydd As String
Public Tinhthanh As String
Public DiachiDD As String

Private Sub btn3_Click():   btnFile 3:  End Sub
Private Sub filler()
End Sub

Public Function Make_RecordKT(a, b, c, d) As Boolean
    If Not PrepareRecordForm Then Exit Function
End Function

Private Function PrepareRecordForm() As Boolean
    If Not GetTT_CsCty Then Exit Function
    If Idx_Ktr > 0 Then
        If Not GetTT_Ktra Then Exit Function
    End If
End Function

Private Function GetTT_CsCty() As Boolean
    TenCtydd = Trim(Rg.Cells(1, ColDBTenCS).Value)
    DiachiDD = DelLastIf(Trim(Rg.Cells(1, ColDBDiachiCS).Value), ".")
    Tinhthanh = Trim(Rg.Cells(1, ColDBTinhTpCS).Value)
End Function

Private Function GetTT_Ktra() As Boolean
    s_MaHsDk = Rg3.Cells(1, ColDB_HSDK_Ktra + 1).Value: s_NgaynopHsDk = Rg3.Cells(1, ColDB_HSDK_Ktra).Value
    s_LoaiKT = Rg3.Cells(1, ColDB_Tieuchuan_Ktra).Value
    DaychuyenRaw = Trim(Rg3.Cells(1, ColDB_Pvi_Ktra).Value)
    New_Form = Get_DCx(DaychuyenRaw, DC_cu, DC_moi, GHanDC)
    ss = Trim(Rg3.Cells(1, ColDB_NgayKtra + 1).Value)
    If Len(ss) > 1 Then
        QDKT = Left(ss, k - 1): NgayQDKT = Right(ss, Len(ss) - m)
    Else
        QDKT = ss: NgayQDKT = ""
    End If
    ss = Rg3.Cells(1, ColDB_NgayKtra + 3).Value
    If Len(ss) > 1 Then TTV = Trim(ss) Else TTV = vbNullString
End Function

Private Sub btnFile(ByVal i, Optional tempf As Boolean = False)
    If (i = 2) Or (i = 3) Or (i = 4) Or (i = 11) Then
        If Len(TTV) > 1 Then
            If TTVForm.Get_TTV2(TTV, "|", i = 2) Then TTVdd = TTVForm.TTVdd: TTV_VKNdd = TTVForm.TTV_VKNdd: TTV_SYTdd = TTVForm.TTV_SYTdd Else Exit Sub
        Else
            If TTVForm.Get_TTV(TTV, "|", i = 2) Then TTVdd = TTVForm.TTVdd: TTV_VKNdd = TTVForm.TTV_VKNdd: TTV_SYTdd = TTVForm.TTV_SYTdd Else Exit Sub
        End If
    ElseIf i = 15 Then
        If TTVForm.Get_TTV2(TTV, "|", False, True) Then TTVdd = TTVForm.TTVdd: TTV_VKNdd = TTVForm.TTV_VKNdd: TTV_SYTdd = TTVForm.TTV_SYTdd
    End If
    If CreateFile(s, i, Me.txtsyear.Text, tempf) Then done = True
End Sub

Private Function Get_Tpl(i, syear, tpl, fname, iFName)
    Select Case i
    Case 2
        tpl = "2. QD KT - " & S_GPs & ".dotx"
    Case 3
        tpl = "3. Ke hoach kiem tra " & S_GPs & ".dotx"
    End Select
End Function

Private Function CreateFile(s, i, syear, tempf) As Boolean
    If Not Get_Tpl(i, syear, tpl, fname, iFName) Then GoTo Quit0
    Tao_QDKT_KHKT_BBKT wdDoc, i
Quit0:
End Function

Private Sub Tao_QDKT_KHKT_BBKT(wdDoc, i)
    Replace_Bookmark wdDoc, "Tencoso", TenCtydd
    Replace_Bookmark wdDoc, "Diachicoso", Del_LastPeriod(Replace(DiachiDD, vbCrLf, ";"))
    If i = 2 Then Replace_Bookmark wdDoc, "VKN", Vkn2
    If i > 2 Then Replace_Bookmark wdDoc, "TT_VKNx", TTV_VKNdd
    If i > 2 Then Replace_Bookmark wdDoc, "TT_SYTx", TTV_SYTdd
    If i = 3 Then
        Replace_Bookmark wdDoc, "Daychuyen", DC_cu
        Replace_Bookmark wdDoc, "GioiHanPvi", IIf(GHanDC = "", "Không", GHanDC)
        Replace_Bookmark wdDoc, "Diachicoso", Replace(DiachiDD, vbCrLf, ";")
        Replace_Bookmark wdDoc, "TieuchuanKT", s_LoaiKT
        If InStr(1, DC_cu, "Cephalosporin") = 0 Then Delete_Bookmark wdDoc, "PVCepha", 1, 2
        If InStr(1, DC_cu, "Penicillin") = 0 Then Delete_Bookmark wdDoc, "PVPeni", 1, 2
        If InStr(1, DC_cu, "Dược liệu") = 0 Then Delete_Bookmark wdDoc, "PVDuoclieu", 1, 2
        If InStr(1, DC_cu, "Tiêm") = 0 Then Delete_Bookmark wdDoc, "PVTiem", 1, 3
        If InStr(1, DC_cu, "Nhỏ mắt") = 0 Then Delete_Bookmark wdDoc, "PVNhomat"
        If InStr(1, DC_cu, "Nang mềm") = 0 Then Delete_Bookmark wdDoc, "PVNangmem", 1, 2
        If InStr(1, DC_cu, "Sủi bọt") = 0 Then Delete_Bookmark wdDoc, "PVSuibot"
    End If
End Sub
"""


def _zip(tmp_path: Path, *, record: str = RECORD, module: str = MODULE) -> Path:
    path = tmp_path / "source.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Module1.bas", module)
        archive.writestr("RecordForm.frm", record)
    return path


def test_i3_branch_evaluator_preserves_i2_default_and_supports_i3():
    lines = [
        "If i = 2 Then",
        "x",
        "ElseIf i = 3 Then",
        "x",
        "Else",
        "x",
        "End If",
    ]
    assert _branch_context(lines, 1)[1] == "REACHABLE_I2"
    assert _branch_context(lines, 3)[1] == "UNREACHABLE_I2"
    assert _branch_context(lines, 1, target_i=3)[1] == "UNREACHABLE_I3"
    assert _branch_context(lines, 3, target_i=3)[1] == "REACHABLE_I3"
    assert _branch_context(lines, 5, target_i=3)[1] == "UNREACHABLE_I3"


def test_i3_source_audit_follows_recordform_entry_and_real_delete_semantics(tmp_path):
    source = _zip(tmp_path)
    report = build_i3_source_audit(source, expected_sha256=None)

    assert report["status"] == "SOURCE_INSPECTION_KE_HOACH_KT_I3_CAPTURED"
    assert report["schema_version"] == "inspection-ke-hoach-kt-i3-source-audit/v2"
    assert report["target_i"] == 3
    assert report["call_chain"]["recordform_entry_call"]["code"].startswith(
        "Private Sub btn3_Click():"
    )
    assert "CreateFile(s, i" in report["call_chain"]["btnfile_create_call"]["code"]
    assert (
        report["call_chain"]["template_assignment"]["code"]
        == 'tpl = "3. Ke hoach kiem tra " & S_GPs & ".dotx"'
    )
    assert "Get_DCx(DaychuyenRaw, DC_cu, DC_moi, GHanDC)" in report[
        "source_provenance"
    ]["inspection_fields"]["DC_cu_and_GHanDC"]["code"]
    assert len(report["source_provenance"]["team_transfers"]) == 2
    assert set(report["required_writes"]) == {
        "Daychuyen",
        "GioiHanPvi",
        "Diachicoso",
        "TieuchuanKT",
    }
    assert len(report["required_writes"]["Diachicoso"]["write_sequence"]) == 2
    assert (
        report["required_writes"]["Diachicoso"]["effective_write"]["expression"]
        == 'Replace(DiachiDD, vbCrLf, ";")'
    )
    tencoso = next(
        item
        for item in report["active_physical_operations"]
        if item["physical_bookmark"] == "Tencoso"
    )
    assert tencoso["physical_bookmark_targets"] == [
        "Tencoso1", "Tencoso2", "Tencoso3", "Tencoso4",
        "Tencoso5", "Tencoso6", "Tencoso7", "Tencoso8",
    ]
    assert set(report["required_section_suppressions"]) == {
        "PVCepha",
        "PVPeni",
        "PVDuoclieu",
        "PVTiem",
        "PVNhomat",
        "PVNangmem",
        "PVSuibot",
    }
    assert report["required_section_suppressions"]["PVCepha"]["operation_type"] == "DELETE"
    assert report["required_section_suppressions"]["PVCepha"][
        "physical_bookmark_targets"
    ] == ["PVCepha1", "PVCepha2"]
    assert report["required_section_suppressions"]["PVTiem"][
        "physical_bookmark_targets"
    ] == ["PVTiem1", "PVTiem2", "PVTiem3"]
    assert "InStr" in report["required_section_suppressions"]["PVCepha"][
        "branch_predicates"
    ]
    assert (
        report["required_section_suppressions"]["PVCepha"]["reachability_i3"]
        == "CONDITIONAL_I3"
    )
    assert not any(
        item["physical_bookmark"] == "VKN"
        for item in report["active_physical_operations"]
    )
    assert report["invariants"]["database_accessed"] is False
    assert report["invariants"]["modern_owner_inferred"] is False


def test_i3_source_audit_does_not_depend_on_module_i3_dispatch(tmp_path):
    source = _zip(
        tmp_path,
        module="""Public Sub TaoQDKT_KHKT()\n    RecordForm.CreateFile foo, 2, old\nEnd Sub\n""",
    )
    report = build_i3_source_audit(source, expected_sha256=None)
    assert report["call_chain"]["recordform_entry_call"]["line"] == 11


def test_i3_source_audit_fails_closed_when_scope_split_disappears(tmp_path):
    source = _zip(
        tmp_path,
        record=RECORD.replace(
            "    New_Form = Get_DCx(DaychuyenRaw, DC_cu, DC_moi, GHanDC)",
            "    ' removed scope split",
        ),
    )
    with pytest.raises(RuntimeError, match="Get_DCx scope split"):
        build_i3_source_audit(source, expected_sha256=None)


def test_i3_source_audit_fails_closed_when_team_transfer_disappears(tmp_path):
    source = _zip(
        tmp_path,
        record=RECORD.replace("TTVForm.TTV_SYTdd Else Exit Sub", "removed Else Exit Sub"),
    )
    with pytest.raises(RuntimeError, match="team transfer"):
        build_i3_source_audit(source, expected_sha256=None)


def test_i3_source_audit_fails_closed_on_hash_and_template_contract(tmp_path):
    source = _zip(tmp_path)
    with pytest.raises(RuntimeError, match="SHA256 mismatch"):
        build_i3_source_audit(source, expected_sha256="0" * 64)

    missing_template = _zip(
        tmp_path,
        record=RECORD.replace(
            'tpl = "3. Ke hoach kiem tra " & S_GPs & ".dotx"',
            "' removed",
        ),
    )
    with pytest.raises(RuntimeError, match="Case 3 requires exactly one tpl assignment"):
        build_i3_source_audit(missing_template, expected_sha256=None)


def test_i3_source_audit_reports_actual_source_hash(tmp_path):
    source = _zip(tmp_path)
    report = build_i3_source_audit(source, expected_sha256=None)
    assert report["source_zip_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
