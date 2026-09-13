from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _write_minimal_template(path: Path) -> None:
    document = """<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:tbl>
      <w:tr>
        <w:tc><w:p><w:bookmarkStart w:id="1" w:name="PV_TEST"/><w:r><w:t>Scope row</w:t></w:r><w:bookmarkEnd w:id="1"/></w:p></w:tc>
      </w:tr>
    </w:tbl>
  </w:body>
</w:document>"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", document)


def test_capture_extracts_only_active_Input_DC_to_CC_and_template_structure(tmp_path):
    frm = """VERSION 5.00
Private Sub Input_DC_to_CC()
    Load_DC_Nodes
    Call Compile_Node
End Sub

'Private Sub Input_DC_to_CC2()
'    Dangerous_Old_Path
'End Sub

Private Sub Load_DC_Nodes()
End Sub

Private Sub Compile_Node()
End Sub
"""
    vba_zip = tmp_path / "GXP-VBA code.zip"
    with zipfile.ZipFile(vba_zip, "w") as archive:
        archive.writestr("GPs.xlam/RecordForm.frm", frm.encode("utf-8"))

    template = tmp_path / "9. Chung chi GMP (moi).dotx"
    _write_minimal_template(template)
    output = tmp_path / "capture.json"
    fixtures = tmp_path / "fixtures"

    proc = subprocess.run(
        [
            sys.executable,
            "tools/capture_c5e_certificate_detail_evidence.py",
            "--vba-zip", str(vba_zip),
            "--template", str(template),
            "--output", str(output),
            "--fixture-dir", str(fixtures),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "STATUS=EVIDENCE_CAPTURED" in proc.stdout
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["vba"]["active_procedure"]["name"] == "Input_DC_to_CC"
    assert report["vba"]["commented_code_promoted"] is False
    active = (fixtures / "Input_DC_to_CC.active.bas").read_text(encoding="utf-8")
    assert "Dangerous_Old_Path" not in active
    assert {h["name"] for h in report["vba"]["direct_helper_candidates"]} >= {
        "Load_DC_Nodes", "Compile_Node"
    }
    bookmarks = {
        bm["name"]
        for part in report["templates"][0]["parts"]
        for bm in part["bookmarks"]
    }
    assert "PV_TEST" in bookmarks


def test_capture_fails_closed_when_active_procedure_is_absent(tmp_path):
    vba_zip = tmp_path / "legacy.zip"
    with zipfile.ZipFile(vba_zip, "w") as archive:
        archive.writestr(
            "RecordForm.frm",
            b"'Private Sub Input_DC_to_CC()\n'End Sub\n",
        )
    template = tmp_path / "cert.dotx"
    _write_minimal_template(template)

    proc = subprocess.run(
        [
            sys.executable,
            "tools/capture_c5e_certificate_detail_evidence.py",
            "--vba-zip", str(vba_zip),
            "--template", str(template),
            "--output", str(tmp_path / "out.json"),
            "--fixture-dir", str(tmp_path / "fixtures"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 2
    assert "STATUS=EVIDENCE_CAPTURE_FAILED" in proc.stdout
    assert "Active Input_DC_to_CC procedure not found" in proc.stdout
