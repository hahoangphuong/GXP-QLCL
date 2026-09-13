from pathlib import Path
import json, subprocess, sys, zipfile

ROOT = Path(__file__).resolve().parents[1]

def write_doc(path: Path):
    xml = """<?xml version="1.0"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:body><w:p>
<w:pPr/>
<w:bookmarkStart w:id="1" w:name="Pvi"/>
<w:r><w:rPr><w:b/></w:rPr></w:r>
<w:bookmarkEnd w:id="1"/>
</w:p></w:body></w:document>"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", xml)

def test_profiles_exact_child_sequence(tmp_path):
    p = tmp_path / "9. Chung chi GMP (moi).dotx"
    write_doc(p)
    subprocess.run(
        [sys.executable, "tools/profile_c5e_certificate_detail_destination_anchor_children.py", "--template", str(p)],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )
    report = json.loads(
        (ROOT/"artifacts/legacy_audit/c5e_certificate_detail_destination_anchor_child_profile.json")
        .read_text(encoding="utf-8")
    )
    anchor = report["documents"][0]["anchors"][0]
    assert anchor["tag_sequence"] == ["pPr", "bookmarkStart", "r", "bookmarkEnd"]
    assert anchor["children"][2]["text"] == ""
