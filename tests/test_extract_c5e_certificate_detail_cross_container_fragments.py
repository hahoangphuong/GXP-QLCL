from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _write_doc(path: Path, *, end_directly_under_table: bool) -> None:
    if end_directly_under_table:
        body = """
<w:tbl>
  <w:tr><w:tc><w:p><w:bookmarkStart w:id="1" w:name="L1"/><w:r><w:t>A</w:t></w:r></w:p></w:tc></w:tr>
  <w:tr><w:tc><w:p><w:r><w:t>B</w:t></w:r></w:p></w:tc></w:tr>
  <w:bookmarkEnd w:id="1"/>
</w:tbl>
"""
    else:
        body = """
<w:tbl>
  <w:tr><w:tc><w:p><w:bookmarkStart w:id="1" w:name="L1"/><w:r><w:t>A</w:t></w:r></w:p></w:tc></w:tr>
  <w:tr><w:tc><w:p><w:r><w:t>B</w:t></w:r><w:bookmarkEnd w:id="1"/></w:p></w:tc></w:tr>
</w:tbl>
"""
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:body>{body}</w:body>
</w:document>"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", xml)


def test_extracts_p_to_p_table_range_without_bookmark_markup(tmp_path):
    source = tmp_path / "9. PhamviGMP.docx"
    _write_doc(source, end_directly_under_table=False)
    proc = subprocess.run(
        [
            sys.executable,
            "tools/extract_c5e_certificate_detail_cross_container_fragments.py",
            "--source-doc", str(source),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "STATUS=CROSS_CONTAINER_FRAGMENTS_EXTRACTED" in proc.stdout
    report = json.loads(
        (ROOT / "artifacts/legacy_audit/c5e_certificate_detail_cross_container_extraction.json")
        .read_text(encoding="utf-8")
    )
    fragment = report["documents"][0]["fragments"][0]
    assert fragment["root_tag"] == "tbl"
    assert fragment["visible_text"] == "AB"
    assert fragment["row_count"] == 2
    assert fragment["contains_bookmark_markup"] is False


def test_extracts_p_to_tbl_table_range(tmp_path):
    source = tmp_path / "z3. PhamviGMP.docx"
    _write_doc(source, end_directly_under_table=True)
    proc = subprocess.run(
        [
            sys.executable,
            "tools/extract_c5e_certificate_detail_cross_container_fragments.py",
            "--source-doc", str(source),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "STATUS=CROSS_CONTAINER_FRAGMENTS_EXTRACTED" in proc.stdout
    report = json.loads(
        (ROOT / "artifacts/legacy_audit/c5e_certificate_detail_cross_container_extraction.json")
        .read_text(encoding="utf-8")
    )
    fragment = report["documents"][0]["fragments"][0]
    assert fragment["visible_text"] == "AB"
    assert fragment["row_count"] == 2


def test_unknown_geometry_fails_closed_at_bookmark_level(tmp_path):
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:body><w:p>
<w:bookmarkStart w:id="1" w:name="L1"/>
<w:r><w:t>A</w:t></w:r>
<w:bookmarkEnd w:id="1"/>
</w:p></w:body></w:document>"""
    source = tmp_path / "9. PhamviGMP.docx"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("word/document.xml", xml)
    subprocess.run(
        [
            sys.executable,
            "tools/extract_c5e_certificate_detail_cross_container_fragments.py",
            "--source-doc", str(source),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    report = json.loads(
        (ROOT / "artifacts/legacy_audit/c5e_certificate_detail_cross_container_extraction.json")
        .read_text(encoding="utf-8")
    )
    assert report["status"] == "CROSS_CONTAINER_EXTRACTION_PARTIAL"
    assert report["summary"]["error_count"] == 1
    assert "Unsupported bookmark geometry" in report["documents"][0]["errors"][0]["error"]
