from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def _doc_cross_paragraph(path: Path):
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:body>
  <w:p><w:bookmarkStart w:id="1" w:name="L1"/><w:r><w:t>A</w:t></w:r></w:p>
  <w:p><w:r><w:t>B</w:t></w:r><w:bookmarkEnd w:id="1"/></w:p>
</w:body>
</w:document>"""
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", xml)

def test_profiles_cross_paragraph_geometry(tmp_path):
    source = tmp_path / "9. PhamviGMP.docx"
    _doc_cross_paragraph(source)
    proc = subprocess.run(
        [
            sys.executable,
            "tools/profile_c5e_certificate_detail_cross_container_bookmarks.py",
            "--source-doc", str(source),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "STATUS=CROSS_CONTAINER_GEOMETRY_PROFILED" in proc.stdout
    report = json.loads(
        (ROOT / "artifacts/legacy_audit/c5e_certificate_detail_cross_container_profile.json")
        .read_text(encoding="utf-8")
    )
    item = report["documents"][0]["bookmarks"][0]
    assert item["shape"]["same_parent"] is False
    assert item["shape"]["same_paragraph"] is False
    assert item["shape"]["lca"] == "body"
    assert item["start_path"][-2:] == ["p", "bookmarkStart"]
    assert item["end_path"][-2:] == ["p", "bookmarkEnd"]

def test_profile_fails_when_no_docs(tmp_path):
    proc = subprocess.run(
        [
            sys.executable,
            "tools/profile_c5e_certificate_detail_cross_container_bookmarks.py",
            "--source-root", str(tmp_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 2
    assert "STATUS=CROSS_CONTAINER_PROFILE_FAILED" in proc.stdout
