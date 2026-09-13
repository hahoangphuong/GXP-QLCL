from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

W = (
    "http://schemas.openxmlformats.org/"
    "wordprocessingml/2006/main"
)


def _make_source(path: Path) -> None:
    styles = f"""
<w:styles xmlns:w="{W}">
  <w:style
    w:type="paragraph"
    w:styleId="BodyText"
  />
  <w:style
    w:type="table"
    w:styleId="TableGrid"
  />
</w:styles>
"""

    document = f"""
<w:document xmlns:w="{W}">
  <w:body/>
</w:document>
"""

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with zipfile.ZipFile(
        path,
        "w",
    ) as archive:
        archive.writestr(
            "word/document.xml",
            document,
        )

        archive.writestr(
            "word/styles.xml",
            styles,
        )


def test_profiles_style_only_fragment_without_blocker(
    tmp_path,
):
    fixture_dir = tmp_path / "fixtures"
    source_root = tmp_path / "sources"

    fixture_dir.mkdir()
    source_root.mkdir()

    source_name = "9. PhamviGMP.docx"

    _make_source(
        source_root / source_name
    )

    fragment = f"""
<w:tbl xmlns:w="{W}">
  <w:tblPr>
    <w:tblStyle w:val="TableGrid"/>
  </w:tblPr>
  <w:tr>
    <w:tc>
      <w:p>
        <w:pPr>
          <w:pStyle w:val="BodyText"/>
        </w:pPr>
      </w:p>
    </w:tc>
  </w:tr>
</w:tbl>
"""

    (
        fixture_dir
        / f"{source_name}.cross-container.json"
    ).write_text(
        json.dumps(
            {
                "filename": source_name,
                "fragments": [
                    {
                        "bookmark": "L1",
                        "fragment_xml": fragment,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [
            sys.executable,
            (
                "tools/"
                "audit_c5e_certificate_detail_"
                "fragment_dependencies.py"
            ),
            "--fixture-dir",
            str(fixture_dir),
            "--source-root",
            str(source_root),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0
    assert (
        "STATUS=FRAGMENT_DEPENDENCIES_PROFILED"
        in proc.stdout
    )
    assert "FRAGMENTS=1" in proc.stdout
    assert "WITH_STYLES=1" in proc.stdout
    assert "BLOCKERS=0" in proc.stdout


def test_unresolved_relationship_fails_closed(
    tmp_path,
):
    fixture_dir = tmp_path / "fixtures"
    source_root = tmp_path / "sources"

    fixture_dir.mkdir()
    source_root.mkdir()

    source_name = "9. PhamviGMP.docx"

    _make_source(
        source_root / source_name
    )

    fragment = f"""
<w:tbl
 xmlns:w="{W}"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <w:tr>
    <w:tc>
      <w:p>
        <w:hyperlink r:id="rId999"/>
      </w:p>
    </w:tc>
  </w:tr>
</w:tbl>
"""

    (
        fixture_dir
        / f"{source_name}.cross-container.json"
    ).write_text(
        json.dumps(
            {
                "filename": source_name,
                "fragments": [
                    {
                        "bookmark": "L1",
                        "fragment_xml": fragment,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [
            sys.executable,
            (
                "tools/"
                "audit_c5e_certificate_detail_"
                "fragment_dependencies.py"
            ),
            "--fixture-dir",
            str(fixture_dir),
            "--source-root",
            str(source_root),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 1
    assert (
        "STATUS=FRAGMENT_DEPENDENCIES_BLOCKED"
        in proc.stdout
    )
    assert (
        "WITH_RELATIONSHIPS=1"
        in proc.stdout
    )
    assert "BLOCKERS=1" in proc.stdout