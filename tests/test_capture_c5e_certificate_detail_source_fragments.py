from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def _doc(path: Path):
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:body><w:p>
<w:bookmarkStart w:id="1" w:name="L1_2"/>
<w:r><w:rPr><w:b/></w:rPr><w:t>Node text</w:t></w:r>
<w:bookmarkEnd w:id="1"/>
</w:p></w:body></w:document>"""
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", xml)

def test_capture_source_fragment_preserves_xml_and_hash(tmp_path):
    source = tmp_path / "9. PhamviGMP.docx"
    _doc(source)
    proc = subprocess.run(
        [
            sys.executable,
            "tools/capture_c5e_certificate_detail_source_fragments.py",
            "--source-doc", str(source),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "STATUS=SOURCE_FRAGMENTS_CAPTURED" in proc.stdout
    report = json.loads(
        (ROOT / "artifacts/legacy_audit/c5e_certificate_detail_source_fragments.json")
        .read_text(encoding="utf-8")
    )
    frag = report["documents"][0]["fragments"][0]
    assert frag["visible_text"] == "Node text"
    assert frag["fragment_sha256"]
    assert frag["run_properties"]
    assert frag["contains_runs"] is True
    assert frag["contains_paragraphs"] is False

def test_capture_fails_when_no_matching_source_docs(tmp_path):
    proc = subprocess.run(
        [
            sys.executable,
            "tools/capture_c5e_certificate_detail_source_fragments.py",
            "--source-root", str(tmp_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 2
    assert "STATUS=SOURCE_FRAGMENT_CAPTURE_FAILED" in proc.stdout
