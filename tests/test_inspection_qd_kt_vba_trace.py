from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from pathlib import Path

from tools.trace_inspection_qd_kt_vba import EXPECTED_SHA256, build_trace

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "legacy" / "GXP-VBA code.zip"


def test_real_vba_trace_captures_i2_chain_and_field_disposition(tmp_path):
    report = build_trace(SOURCE)
    assert report["source_zip_sha256"] == EXPECTED_SHA256
    assert report["call_chain"] == [
        "Module1.TaoQDKT_KHKT", "RecordForm.CreateFile(i=2)",
        "RecordForm.Get_Tpl(i=2)", "RecordForm.Tao_QDKT_KHKT_BBKT(i=2)",
    ]
    assert report["field_evidence"]["QDKT"]["status"] == "PROVEN_WRITE"
    assert report["field_evidence"]["Daychuyen"]["status"] == "PROVEN_NOT_WRITTEN_I2"
    assert len(report["unresolved_fields"]) == 23
    assert report["invariants"]["commented_code_used"] is False


def test_trace_is_deterministic_and_does_not_accept_similar_procedure(tmp_path):
    first = build_trace(SOURCE)
    second = build_trace(SOURCE)
    assert json.dumps(first, ensure_ascii=False, sort_keys=True) == json.dumps(second, ensure_ascii=False, sort_keys=True)

    archive = tmp_path / "similar.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("Module1.bas", "Sub TaoQDKT_KHKT_Copy()\nEnd Sub\n")
        z.writestr("RecordForm.frm", "Private Function CreateFile_Copy() As Boolean\nEnd Function\n")
    proc = subprocess.run(
        [sys.executable, "tools/trace_inspection_qd_kt_vba.py", "--vba-zip", str(archive), "--expected-sha256", ""],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert proc.returncode == 2
    assert "required procedure missing" in proc.stdout


def test_trace_missing_source_fails_closed(tmp_path):
    proc = subprocess.run(
        [sys.executable, "tools/trace_inspection_qd_kt_vba.py", "--vba-zip", str(tmp_path / "missing.zip")],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert proc.returncode == 2
    assert "SOURCE_DOCUMENT" not in proc.stdout
    assert "not found" in proc.stdout


def test_trace_hash_mismatch_fails_closed(tmp_path):
    archive = tmp_path / "copy.zip"
    archive.write_bytes(SOURCE.read_bytes())
    proc = subprocess.run(
        [sys.executable, "tools/trace_inspection_qd_kt_vba.py", "--vba-zip", str(archive), "--expected-sha256", "0" * 64],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert proc.returncode == 2
    assert "SHA256 mismatch" in proc.stdout
