from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def _write(path: Path):
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:body><w:p>
<w:bookmarkStart w:id="1" w:name="Pvi"/>
<w:bookmarkEnd w:id="1"/>
</w:p></w:body></w:document>"""
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", xml)

def test_profiles_empty_same_paragraph_pvi_anchor(tmp_path):
    template = tmp_path / "9. Chung chi GMP (moi).dotx"
    _write(template)
    proc = subprocess.run(
        [
            sys.executable,
            "tools/profile_c5e_certificate_detail_destination_anchors.py",
            "--template", str(template),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "STATUS=DESTINATION_ANCHORS_PROFILED" in proc.stdout
    report = json.loads(
        (ROOT / "artifacts/legacy_audit/c5e_certificate_detail_destination_anchor_profile.json")
        .read_text(encoding="utf-8")
    )
    anchor = report["documents"][0]["anchors"][0]
    assert anchor["bookmark"] == "Pvi"
    assert anchor["same_parent"] is True
    assert anchor["same_paragraph"] is True
    assert anchor["between_text_same_parent"] == ""

def test_fails_when_no_pvi_anchor(tmp_path):
    template = tmp_path / "9. Chung chi GMP (moi).dotx"
    with zipfile.ZipFile(template, "w") as z:
        z.writestr(
            "word/document.xml",
            b'<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body/></w:document>'
        )
    proc = subprocess.run(
        [
            sys.executable,
            "tools/profile_c5e_certificate_detail_destination_anchors.py",
            "--template", str(template),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 2
    assert "STATUS=DESTINATION_ANCHOR_PROFILE_FAILED" in proc.stdout
