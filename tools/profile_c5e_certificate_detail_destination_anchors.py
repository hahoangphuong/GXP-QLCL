from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts" / "legacy_audit" / "c5e_certificate_detail_destination_anchor_profile.json"

WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": WORD_NS}

class ProfileError(RuntimeError):
    pass

def w(tag: str) -> str:
    return f"{{{WORD_NS}}}{tag}"

def local(tag: str) -> str:
    return tag.split("}", 1)[1] if tag.startswith("{") else tag

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def build_parent_map(root: ET.Element):
    return {child: parent for parent in root.iter() for child in list(parent)}

def ancestors(node: ET.Element, parent_map):
    result = [node]
    current = node
    while current in parent_map:
        current = parent_map[current]
        result.append(current)
    return result

def nearest(node: ET.Element, parent_map, tag: str):
    q = w(tag)
    current = node
    while True:
        if current.tag == q:
            return current
        if current not in parent_map:
            return None
        current = parent_map[current]

def find_end(root: ET.Element, bookmark_id: str | None):
    if bookmark_id is None:
        return None
    for node in root.findall(".//w:bookmarkEnd", NS):
        if node.attrib.get(w("id")) == bookmark_id:
            return node
    return None

def ordinal(node: ET.Element, parent_map):
    parent = parent_map.get(node)
    if parent is None:
        return None
    for i, child in enumerate(list(parent)):
        if child is node:
            return i
    return None

def text_between_same_parent(start: ET.Element, end: ET.Element, parent_map) -> str | None:
    parent = parent_map.get(start)
    if parent is None or parent is not parent_map.get(end):
        return None
    children = list(parent)
    si = children.index(start)
    ei = children.index(end)
    if ei <= si:
        return None
    parts = []
    for child in children[si+1:ei]:
        for t in child.findall(".//w:t", NS):
            parts.append(t.text or "")
    return "".join(parts)

def inspect_anchor(root: ET.Element, name: str) -> dict[str, object]:
    starts = [
        node for node in root.findall(".//w:bookmarkStart", NS)
        if node.attrib.get(w("name")) == name
    ]
    if len(starts) != 1:
        return {
            "bookmark": name,
            "status": "START_CARDINALITY_ERROR",
            "start_count": len(starts),
        }
    start = starts[0]
    end = find_end(root, start.attrib.get(w("id")))
    if end is None:
        return {"bookmark": name, "status": "END_NOT_FOUND"}

    parent_map = build_parent_map(root)
    sp = parent_map.get(start)
    ep = parent_map.get(end)
    start_p = nearest(start, parent_map, "p")
    end_p = nearest(end, parent_map, "p")
    start_tc = nearest(start, parent_map, "tc")
    end_tc = nearest(end, parent_map, "tc")
    start_tbl = nearest(start, parent_map, "tbl")
    end_tbl = nearest(end, parent_map, "tbl")
    same_parent = sp is ep

    return {
        "bookmark": name,
        "status": "OK",
        "start_parent": None if sp is None else local(sp.tag),
        "end_parent": None if ep is None else local(ep.tag),
        "same_parent": same_parent,
        "same_paragraph": start_p is not None and start_p is end_p,
        "same_cell": start_tc is not None and start_tc is end_tc,
        "same_table": start_tbl is not None and start_tbl is end_tbl,
        "start_parent_ordinal": ordinal(start, parent_map),
        "end_parent_ordinal": ordinal(end, parent_map),
        "between_text_same_parent": text_between_same_parent(start, end, parent_map),
        "start_ancestor_path": [local(x.tag) for x in reversed(ancestors(start, parent_map))],
        "end_ancestor_path": [local(x.tag) for x in reversed(ancestors(end, parent_map))],
    }

def inspect_document(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise ProfileError(f"Template not found: {path}")
    with zipfile.ZipFile(path, "r") as archive:
        if "word/document.xml" not in archive.namelist():
            raise ProfileError(f"{path.name} has no word/document.xml")
        root = ET.fromstring(archive.read("word/document.xml"))

    names = sorted({
        node.attrib.get(w("name"))
        for node in root.findall(".//w:bookmarkStart", NS)
        if (node.attrib.get(w("name")) or "").lower().startswith("pvi")
    })
    anchors = [inspect_anchor(root, name) for name in names]

    return {
        "filename": path.name,
        "sha256": sha256_bytes(path.read_bytes()),
        "anchor_count": len(anchors),
        "anchors": anchors,
    }

def discover(root: Path) -> list[Path]:
    matches = []
    for path in root.rglob("*"):
        if path.suffix.lower() not in {".docx", ".dotx"}:
            continue
        name = path.name.lower()
        if "chung chi" in name or "giay" in name or "quyet dinh" in name or "qd" in name:
            matches.append(path)
    return sorted(matches)

def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--template-root", type=Path)
    group.add_argument("--template", action="append", type=Path)
    args = parser.parse_args()

    try:
        paths = (
            discover(args.template_root.resolve())
            if args.template_root is not None
            else [p.resolve() for p in (args.template or [])]
        )
        if not paths:
            raise ProfileError("No candidate destination templates found.")

        records = [inspect_document(path) for path in paths]
        records = [r for r in records if r["anchor_count"] > 0]
        if not records:
            raise ProfileError("No Pvi* destination bookmarks found in candidate templates.")

        shape_counts = collections.Counter()
        unresolved = 0
        total = 0
        for record in records:
            for a in record["anchors"]:
                total += 1
                if a["status"] != "OK":
                    unresolved += 1
                    shape_counts["STATUS:" + a["status"]] += 1
                    continue
                key = "|".join([
                    f"sp={a['start_parent']}",
                    f"ep={a['end_parent']}",
                    f"same_parent={a['same_parent']}",
                    f"same_p={a['same_paragraph']}",
                    f"same_tc={a['same_cell']}",
                    f"same_tbl={a['same_table']}",
                    f"empty={a['between_text_same_parent'] == '' if a['between_text_same_parent'] is not None else None}",
                ])
                shape_counts[key] += 1

        report = {
            "schema_version": "c5e-certificate-detail-destination-anchor-profile/v1",
            "status": "DESTINATION_ANCHORS_PROFILED" if unresolved == 0 else "DESTINATION_ANCHORS_PARTIAL",
            "documents": records,
            "summary": {
                "document_count": len(records),
                "anchor_count": total,
                "unresolved_anchors": unresolved,
                "distinct_shape_count": len(shape_counts),
                "shape_counts": dict(shape_counts.most_common()),
            },
            "invariants": {
                "templates_modified": False,
                "renderer_modified": False,
                "unkeyed_entries_used": False,
                "compact_summary_used": False,
            },
        }
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"STATUS={report['status']}")
        print(f"DOCUMENTS={len(records)}")
        print(f"ANCHORS={total}")
        print(f"UNRESOLVED={unresolved}")
        print(f"DISTINCT_SHAPES={len(shape_counts)}")
        print(f"OUTPUT={OUTPUT}")
        return 0
    except (ProfileError, zipfile.BadZipFile, ET.ParseError) as exc:
        print("STATUS=DESTINATION_ANCHOR_PROFILE_FAILED")
        print(f"ERROR={exc}")
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
