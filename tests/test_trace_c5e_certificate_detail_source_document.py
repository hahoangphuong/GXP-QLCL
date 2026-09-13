from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_trace_finds_active_caller_and_nearby_source_document_assignment(tmp_path):
    vba = """
Private Sub BuildCertificate()
    Set wdDoc2 = Documents.Open(scopeTemplate)
    If Not Input_DC_to_CC(wdDoc, wdDoc2, DC_All, True, "GMP") Then Exit Sub
End Sub

'Private Sub OldCaller()
'    Input_DC_to_CC wdDoc, wdDoc2, oldScope, False
'End Sub
"""
    archive_path = tmp_path / "legacy.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("RecordForm.frm", vba.encode("utf-8"))

    proc = subprocess.run(
        [
            sys.executable,
            "tools/trace_c5e_certificate_detail_source_document.py",
            "--vba-zip", str(archive_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "STATUS=SOURCE_DOCUMENT_CALL_PATH_CAPTURED" in proc.stdout
    report = json.loads(
        (ROOT / "artifacts/legacy_audit/c5e_certificate_detail_source_document_trace.json")
        .read_text(encoding="utf-8")
    )
    assert len(report["callers"]) == 1
    window = report["callers"][0]["call_windows"][0]
    assert window["call_code"].startswith("If Not Input_DC_to_CC")
    assert any(item["variable"] == "wdDoc2" for item in window["object_assignments"])
    assert report["invariants"]["commented_calls_used"] is False


def test_trace_ignores_commented_caller(tmp_path):
    archive_path = tmp_path / "legacy.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(
            "RecordForm.frm",
            b"Private Sub X()\n' Input_DC_to_CC wdDoc, wdDoc2, DC_All, True\nEnd Sub\n",
        )
    proc = subprocess.run(
        [
            sys.executable,
            "tools/trace_c5e_certificate_detail_source_document.py",
            "--vba-zip", str(archive_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "STATUS=SOURCE_DOCUMENT_TRACE_INCOMPLETE" in proc.stdout
