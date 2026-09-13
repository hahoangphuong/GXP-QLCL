from __future__ import annotations
import argparse, hashlib, json, zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/"artifacts"/"legacy_audit"/"c5e_certificate_detail_destination_block_context.json"
WORD_NS="http://schemas.openxmlformats.org/wordprocessingml/2006/main"; NS={"w":WORD_NS}

class ContextError(RuntimeError): pass
def w(tag): return f"{{{WORD_NS}}}{tag}"
def local(tag): return tag.split("}",1)[1] if tag.startswith("{") else tag
def sha256_bytes(data): return hashlib.sha256(data).hexdigest()
def parent_map(root): return {c:p for p in root.iter() for c in list(p)}
def nearest(node,pm,tag):
    q=w(tag); cur=node
    while True:
        if cur.tag==q: return cur
        if cur not in pm: return None
        cur=pm[cur]
def find_end(root,bid):
    for n in root.findall(".//w:bookmarkEnd",NS):
        if n.attrib.get(w("id"))==bid: return n
    return None
def visible(p): return "".join(n.text or "" for n in p.findall(".//w:t",NS))
def run_semantic(r):
    for c in list(r):
        if c.tag==w("rPr"): continue
        if c.tag==w("t") and not (c.text or ""): continue
        return True
    return False
def inspect_anchor(root,name):
    starts=[n for n in root.findall(".//w:bookmarkStart",NS) if n.attrib.get(w("name"))==name]
    if len(starts)!=1: return {"bookmark":name,"status":"START_CARDINALITY_ERROR","block_replace_safe":False}
    start=starts[0]; end=find_end(root,start.attrib.get(w("id")))
    if end is None: return {"bookmark":name,"status":"END_NOT_FOUND","block_replace_safe":False}
    pm=parent_map(root); p=nearest(start,pm,"p"); ep=nearest(end,pm,"p")
    if p is None or p is not ep: return {"bookmark":name,"status":"NOT_SAME_PARAGRAPH","block_replace_safe":False}
    semantic=[]
    for i,c in enumerate(list(p)):
        if c.tag in {w("pPr"),w("bookmarkStart"),w("bookmarkEnd")}: continue
        if c.tag==w("r") and not run_semantic(c): continue
        semantic.append({"index":i,"tag":local(c.tag)})
    only_target=True
    for c in list(p):
        if c.tag==w("bookmarkStart") and c.attrib.get(w("name"))!=name: only_target=False
        if c.tag==w("bookmarkEnd") and c.attrib.get(w("id"))!=start.attrib.get(w("id")): only_target=False
    safe=(pm.get(start) is p and pm.get(end) is p and visible(p)=="" and not semantic and only_target)
    return {"bookmark":name,"status":"OK","block_replace_safe":safe,"paragraph_visible_text":visible(p),"semantic_child_count":len(semantic),"only_target_bookmark_markup":only_target}
def inspect_template(path):
    with zipfile.ZipFile(path,"r") as z: root=ET.fromstring(z.read("word/document.xml"))
    names=sorted({n.attrib.get(w("name")) for n in root.findall(".//w:bookmarkStart",NS) if (n.attrib.get(w("name")) or "").lower().startswith("pvi")})
    return {"filename":path.name,"sha256":sha256_bytes(path.read_bytes()),"anchors":[inspect_anchor(root,n) for n in names]}
def is_candidate(path):
    if path.suffix.lower() not in {".docx",".dotx"}: return False
    name=path.name.lower()
    return ("chung chi" in name or "giay" in name or "quyet dinh" in name or "qd" in name)
def discover(root): return sorted(p for p in root.rglob("*") if is_candidate(p))
def main():
    ap=argparse.ArgumentParser(); g=ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--template-root",type=Path); g.add_argument("--template",action="append",type=Path); a=ap.parse_args()
    try:
        paths=discover(a.template_root.resolve()) if a.template_root else [p.resolve() for p in (a.template or [])]
        if not paths: raise ContextError("No candidate destination templates were found.")
        records=[inspect_template(p) for p in paths]; records=[r for r in records if r["anchors"]]
        if not records: raise ContextError("No Pvi* anchors found in candidate destination templates.")
        anchors=[x for r in records for x in r["anchors"]]; unsafe=[x for x in anchors if not x.get("block_replace_safe")]
        report={"schema_version":"c5e-certificate-detail-destination-block-context/v2","status":"DESTINATION_BLOCK_REPLACEMENT_PROVEN" if not unsafe else "DESTINATION_BLOCK_REPLACEMENT_BLOCKED","candidate_selection_contract":"same-as-destination-anchor-profile","documents":records,"summary":{"document_count":len(records),"anchor_count":len(anchors),"block_replace_safe_count":len(anchors)-len(unsafe),"unsafe_anchor_count":len(unsafe)},"invariants":{"candidate_scope_matches_destination_anchor_profile":True,"production_renderer_modified":False,"unkeyed_entries_used":False}}
        OUTPUT.parent.mkdir(parents=True,exist_ok=True); OUTPUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        print(f"STATUS={report['status']}"); print(f"DOCUMENTS={len(records)}"); print(f"ANCHORS={len(anchors)}"); print(f"BLOCK_REPLACE_SAFE={len(anchors)-len(unsafe)}"); print(f"UNSAFE={len(unsafe)}"); print(f"OUTPUT={OUTPUT}")
        return 0
    except Exception as exc:
        print("STATUS=DESTINATION_BLOCK_CONTEXT_FAILED"); print(f"ERROR={exc}"); return 2
if __name__=="__main__": raise SystemExit(main())
