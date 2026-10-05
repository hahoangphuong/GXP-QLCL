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
    RecordForm.CreateFile foo, 3, plan
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

Private Function Get_Tpl(i, syear, tpl, fname, iFName)
    Select Case i
    Case 2
        tpl = "2. QD KT - " & S_GPs & ".dotx"
    Case 3
        tpl = "3. Ke hoach kiem tra " & S_GPs & ".dotx"
    End Select
End Function

Private Sub CreateFile(i, foo, bar)
    If Not Get_Tpl(i, syear, tpl, fname, iFName) Then GoTo Quit0
    Tao_QDKT_KHKT_BBKT wdDoc, i
Quit0:
End Sub

Private Sub GetTT_Ktra()
    s_LoaiKT = Rg3.Cells(1, 8).Value
    DC_cu = DaychuyenDD
    GHanDC = Gioihan
    TTVdd = team_value
    TTV_VKNdd = vkn_value
    TTV_SYTdd = syt_value
    TenCtydd = site_value
    Tinhthanh = province_value
    DiachiDD = address_value
End Sub

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
        If InStr(1, DC_cu, "Cephalosporin") = 0 Then wdDoc.Bookmarks("PVCepha").Range.Delete
        If InStr(1, DC_cu, "Penicillin") = 0 Then wdDoc.Bookmarks("PVPeni").Range.Delete
        If InStr(1, DC_cu, "Dược liệu") = 0 Then wdDoc.Bookmarks("PVDuoclieu").Range.Delete
        If InStr(1, DC_cu, "Tiêm") = 0 Then wdDoc.Bookmarks("PVTiem").Range.Delete
        If InStr(1, DC_cu, "Nhỏ mắt") = 0 Then wdDoc.Bookmarks("PVNhomat").Range.Delete
        If InStr(1, DC_cu, "Nang mềm") = 0 Then wdDoc.Bookmarks("PVNangmem").Range.Delete
        If InStr(1, DC_cu, "Sủi bọt") = 0 Then wdDoc.Bookmarks("PVSuibot").Range.Delete
    End If
End Sub
"""


def _zip(tmp_path: Path, *, record: str = RECORD) -> Path:
    path = tmp_path / "source.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Module1.bas", MODULE)
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


def test_i3_source_audit_captures_template_loai_kt_and_section_deletes(tmp_path):
    source = _zip(tmp_path)
    report = build_i3_source_audit(source, expected_sha256=None)

    assert report["status"] == "SOURCE_INSPECTION_KE_HOACH_KT_I3_CAPTURED"
    assert report["target_i"] == 3
    assert (
        report["call_chain"]["template_assignment"]["code"]
        == 'tpl = "3. Ke hoach kiem tra " & S_GPs & ".dotx"'
    )
    assert report["source_assignments"]["s_LoaiKT"] == [
        {
            "file": "RecordForm.frm",
            "line": 27,
            "code": "s_LoaiKT = Rg3.Cells(1, 8).Value",
        }
    ]
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
    assert set(report["required_section_deletes"]) == {
        "PVCepha",
        "PVPeni",
        "PVDuoclieu",
        "PVTiem",
        "PVNhomat",
        "PVNangmem",
        "PVSuibot",
    }
    assert "InStr" in report["required_section_deletes"]["PVCepha"]["branch_predicates"]
    assert (
        report["required_section_deletes"]["PVCepha"]["reachability_i3"]
        == "CONDITIONAL_I3"
    )
    assert all(
        item["reachability_i3"] != "UNREACHABLE_I3"
        for item in report["active_physical_operations"]
    )
    assert not any(
        item["physical_bookmark"] == "VKN"
        for item in report["active_physical_operations"]
    )
    assert report["invariants"]["database_accessed"] is False
    assert report["invariants"]["modern_owner_inferred"] is False


def test_i3_source_audit_fails_closed_when_loai_kt_assignment_disappears(tmp_path):
    source = _zip(
        tmp_path,
        record=RECORD.replace(
            "    s_LoaiKT = Rg3.Cells(1, 8).Value",
            "    ' s_LoaiKT = Rg3.Cells(1, 8).Value",
        ),
    )
    with pytest.raises(RuntimeError, match="s_LoaiKT"):
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
