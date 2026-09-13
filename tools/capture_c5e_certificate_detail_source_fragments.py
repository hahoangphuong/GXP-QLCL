from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts" / "legacy_audit" / "c5e_certificate_detail_source_fragments.json"
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "c5e_certificate_detail" / "source_fragments"

WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": WORD_NS}
BM_PREFIX = "L"

class CaptureError(RuntimeError):
    pass

def w(tag: str) -> str:
    return f"{{{WORD_NS}}}{tag}"

def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()

def serialize_element(element: ET.Element) -> str:
    return ET.tostring(element, encoding="unicode")

def text_of(element: ET.Element) -> str:
    if element.tag == w("t"):
        return element.text or ""
    return "".join(node.text or "" for node in element.findall(".//w:t", NS))

def iter_parent_child(root: ET.Element):
    for parent in root.iter():
        for index, child in enumerate(list(parent)):
            yield parent, index, child

def iter_self_and_descendants_by_tag(element: ET.Element, tag: str):
    qualified = w(tag)
    if element.tag == qualified:
        yield element
    yield from element.findall(f".//w:{tag}", NS)

def find_bookmark_fragment(root: ET.Element, bookmark_name: str) -> dict[str, object] | None:
    start_parent = None
    start_index = None
    start_id = None

    for parent, index, child in iter_parent_child(root):
        if child.tag == w("bookmarkStart") and child.attrib.get(w("name")) == bookmark_name:
            start_parent, start_index = parent, index
            start_id = child.attrib.get(w("id"))
            break
    if start_parent is None:
        return None

    children = list(start_parent)
    end_index = None
    for index in range(start_index + 1, len(children)):
        child = children[index]
        if child.tag == w("bookmarkEnd") and child.attrib.get(w("id")) == start_id:
            end_index = index
            break
    if end_index is None:
        return {
            "bookmark": bookmark_name,
            "supported_same_parent_span": False,
            "reason": "bookmarkEnd not found in same XML parent",
        }

    contents = children[start_index + 1:end_index]
    fragment_xml = "".join(serialize_element(copy.deepcopy(item)) for item in contents)
    visible_text = "".join(text_of(item) for item in contents)

    run_properties = []
    paragraph_properties = []
    for item in contents:
        for run in iter_self_and_descendants_by_tag(item, "r"):
            rpr = run.find("./w:rPr", NS)
            if rpr is not None:
                run_properties.append(serialize_element(rpr))
        for para in iter_self_and_descendants_by_tag(item, "p"):
            ppr = para.find("./w:pPr", NS)
            if ppr is not None:
                paragraph_properties.append(serialize_element(ppr))

    return {
        "bookmark": bookmark_name,
        "supported_same_parent_span": True,
        "bookmark_id": start_id,
        "visible_text": visible_text,
        "fragment_xml": fragment_xml,
        "fragment_sha256": sha256_bytes(fragment_xml.encode("utf-8")),
        "run_properties": run_properties,
        "paragraph_properties": paragraph_properties,
        "contains_runs": any(
            True for item in contents for _ in iter_self_and_descendants_by_tag(item, "r")
        ),
        "contains_paragraphs": any(
            True for item in contents for _ in iter_self_and_descendants_by_tag(item, "p")
        ),
        "contains_tables": any(
            item.tag == w("tbl") or item.find(".//w:tbl", NS) is not None
            for item in contents
        ),
    }

def inspect_document(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise CaptureError(f"Source document not found: {path}")
    if path.suffix.lower() not in {".docx", ".dotx"}:
        raise CaptureError(f"Unsupported source document type: {path}")

    all_fragments = []
    with zipfile.ZipFile(path, "r") as archive:
        if "word/document.xml" not in archive.namelist():
            raise CaptureError(f"{path.name} has no word/document.xml")
        root = ET.fromstring(archive.read("word/document.xml"))
        names = [
            node.attrib.get(w("name"))
            for node in root.findall(".//w:bookmarkStart", NS)
            if node.attrib.get(w("name"))
        ]
        for name in sorted({name for name in names if name.startswith(BM_PREFIX)}):
            fragment = find_bookmark_fragment(root, name)
            if fragment is not None:
                all_fragments.append(fragment)

    unsupported = [
        item["bookmark"] for item in all_fragments if not item.get("supported_same_parent_span")
    ]
    return {
        "source_path": str(path),
        "filename": path.name,
        "sha256": sha256_bytes(path.read_bytes()),
        "detail_bookmark_count": len(all_fragments),
        "detail_bookmarks": [item["bookmark"] for item in all_fragments],
        "unsupported_bookmark_spans": unsupported,
        "fragments": all_fragments,
    }

def discover(root: Path) -> list[Path]:
    patterns = (
        re.compile(r"^9\.?\s*Phamvi.*\.docx$", re.I),
        re.compile(r"^z3\.?\s*Phamvi.*\.docx$", re.I),
    )
    return sorted(
        path for path in root.rglob("*.docx")
        if any(pattern.search(path.name) for pattern in patterns)
    )

def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--source-root", type=Path)
    group.add_argument("--source-doc", action="append", type=Path)
    args = parser.parse_args()

    try:
        docs = (
            discover(args.source_root.resolve())
            if args.source_root is not None
            else [path.resolve() for path in (args.source_doc or [])]
        )
        if not docs:
            raise CaptureError(
                "No source scope documents found. Expected names like '9. PhamviGMP.docx' "
                "or 'z3. PhamviGMP.docx'."
            )

        records = [inspect_document(path) for path in docs]
        blockers = []
        for record in records:
            if record["detail_bookmark_count"] == 0:
                blockers.append({"code": "NO_L_DETAIL_BOOKMARKS", "document": record["filename"]})
            if record["unsupported_bookmark_spans"]:
                blockers.append({
                    "code": "CROSS_CONTAINER_BOOKMARK_SPAN_UNSUPPORTED",
                    "document": record["filename"],
                    "bookmarks": record["unsupported_bookmark_spans"],
                })

        FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
        for record in records:
            safe = re.sub(r"[^A-Za-z0-9._-]+", "_", record["filename"])
            (FIXTURE_DIR / f"{safe}.fragments.json").write_text(
                json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

        report = {
            "schema_version": "c5e-certificate-detail-source-fragments/v1",
            "status": "SOURCE_FRAGMENTS_CAPTURED" if not blockers else "SOURCE_FRAGMENTS_PARTIAL",
            "documents": records,
            "blockers": blockers,
            "invariants": {
                "source_documents_modified": False,
                "unkeyed_entries_used": False,
                "compact_summary_used": False,
                "historical_prose_used": False,
                "fragment_formatting_preserved_as_xml": True,
            },
        }
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"STATUS={report['status']}")
        print(f"BLOCKERS={len(blockers)}")
        print(f"DOCUMENTS={len(records)}")
        print(f"DETAIL_BOOKMARKS={sum(r['detail_bookmark_count'] for r in records)}")
        print(f"OUTPUT={OUTPUT}")
        print(f"FIXTURE_DIR={FIXTURE_DIR}")
        return 0
    except (CaptureError, zipfile.BadZipFile, ET.ParseError) as exc:
        print("STATUS=SOURCE_FRAGMENT_CAPTURE_FAILED")
        print(f"ERROR={exc}")
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
