from pathlib import Path
import json, subprocess, sys, zipfile
ROOT=Path(__file__).resolve().parents[1]
def write_doc(path,name="Pvi",text=""):
    path.parent.mkdir(parents=True,exist_ok=True)
    run=f"<w:r><w:t>{text}</w:t></w:r>" if text else ""
    xml=f"""<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:pPr/><w:bookmarkStart w:id="1" w:name="{name}"/><w:bookmarkEnd w:id="1"/>{run}</w:p></w:body></w:document>"""
    with zipfile.ZipFile(path,"w") as z: z.writestr("word/document.xml",xml)
def load():
    return json.loads((ROOT/"artifacts/legacy_audit/c5e_certificate_detail_destination_block_context.json").read_text(encoding="utf-8"))
def test_safe_anchor(tmp_path):
    p=tmp_path/"9. Chung chi GMP (moi).dotx"; write_doc(p)
    subprocess.run([sys.executable,"tools/audit_c5e_certificate_detail_destination_block_context.py","--template",str(p)],cwd=ROOT,check=True,capture_output=True,text=True)
    r=load(); assert r["status"]=="DESTINATION_BLOCK_REPLACEMENT_PROVEN"; assert r["summary"]["document_count"]==1
def test_text_blocks(tmp_path):
    p=tmp_path/"9. Chung chi GMP (moi).dotx"; write_doc(p,text="keep")
    subprocess.run([sys.executable,"tools/audit_c5e_certificate_detail_destination_block_context.py","--template",str(p)],cwd=ROOT,check=True,capture_output=True,text=True)
    assert load()["status"]=="DESTINATION_BLOCK_REPLACEMENT_BLOCKED"
def test_root_scope_does_not_expand_to_arbitrary_pvi_docs(tmp_path):
    write_doc(tmp_path/"9. Chung chi GMP (moi).dotx")
    write_doc(tmp_path/"random-working-document.docx",name="PviOther",text="not target")
    subprocess.run([sys.executable,"tools/audit_c5e_certificate_detail_destination_block_context.py","--template-root",str(tmp_path)],cwd=ROOT,check=True,capture_output=True,text=True)
    r=load(); assert r["summary"]["document_count"]==1; assert r["documents"][0]["filename"]=="9. Chung chi GMP (moi).dotx"; assert r["invariants"]["candidate_scope_matches_destination_anchor_profile"] is True
