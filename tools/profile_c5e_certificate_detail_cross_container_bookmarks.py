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
OUTPUT = ROOT / "artifacts" / "legacy_audit" / "c5e_certificate_detail_cross_container_profile.json"

WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": WORD_NS}

class ProfileError(RuntimeError):
    pass

def w(tag: str) -> str:
    return f"{{{WORD_NS}}}{tag}"

def local(tag: str) -> str:
    if tag.startswith("{"):
        return tag.split("}", 1)[1]
    return tag

def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()

def build_parent_map(root: ET.Element) -> dict[ET.Element, ET.Element]:
    result = {}
    for parent in root.iter():
        for child in list(parent):
            result[child] = parent
    return result

def ancestors(node: ET.Element, parent_map: dict[ET.Element, ET.Element]) -> list[ET.Element]:
    result = [node]
    cur = node
    while cur in parent_map:
        cur = parent_map[cur]
        result.append(cur)
    return result

def path_labels(node: ET.Element, parent_map: dict[ET.Element, ET.Element]) -> list[str]:
    return [local(item.tag) for item in reversed(ancestors(node, parent_map))]

def lowest_common_ancestor(
    a: ET.Element,
    b: ET.Element,
    parent_map: dict[ET.Element, ET.Element],
) -> ET.Element | None:
    a_chain = list(reversed(ancestors(a, parent_map)))
    b_chain = list(reversed(ancestors(b, parent_map)))
    lca = None
    for left, right in zip(a_chain, b_chain):
        if left is right:
            lca = left
        else:
            break
    return lca

def nearest_ancestor(
    node: ET.Element,
    parent_map: dict[ET.Element, ET.Element],
    tag: str,
) -> ET.Element | None:
    qualified = w(tag)
    cur = node
    while True:
        if cur.tag == qualified:
            return cur
        if cur not in parent_map:
            return None
        cur = parent_map[cur]

def ordinal_within_parent(node: ET.Element, parent_map: dict[ET.Element, ET.Element]) -> int | None:
    parent = parent_map.get(node)
    if parent is None:
        return None
    for idx, child in enumerate(list(parent)):
        if child is node:
            return idx
    return None

def document_order(root: ET.Element) -> dict[ET.Element, int]:
    return {node: idx for idx, node in enumerate(root.iter())}

def find_end_by_id(root: ET.Element, bookmark_id: str | None) -> ET.Element | None:
    if bookmark_id is None:
        return None
    for node in root.findall(".//w:bookmarkEnd", NS):
        if node.attrib.get(w("id")) == bookmark_id:
            return node
    return None

def inspect_bookmark(
    start: ET.Element,
    root: ET.Element,
    parent_map: dict[ET.Element, ET.Element],
    order: dict[ET.Element, int],
) -> dict[str, object]:
    name = start.attrib.get(w("name"))
    bookmark_id = start.attrib.get(w("id"))
    end = find_end_by_id(root, bookmark_id)
    if end is None:
        return {
            "bookmark": name,
            "bookmark_id": bookmark_id,
            "status": "END_NOT_FOUND",
        }

    start_parent = parent_map.get(start)
    end_parent = parent_map.get(end)
    lca = lowest_common_ancestor(start, end, parent_map)

    start_p = nearest_ancestor(start, parent_map, "p")
    end_p = nearest_ancestor(end, parent_map, "p")
    start_tc = nearest_ancestor(start, parent_map, "tc")
    end_tc = nearest_ancestor(end, parent_map, "tc")
    start_tr = nearest_ancestor(start, parent_map, "tr")
    end_tr = nearest_ancestor(end, parent_map, "tr")
    start_tbl = nearest_ancestor(start, parent_map, "tbl")
    end_tbl = nearest_ancestor(end, parent_map, "tbl")

    start_idx = order[start]
    end_idx = order[end]
    lo, hi = sorted((start_idx, end_idx))
    between = [node for node, idx in order.items() if lo < idx < hi]

    between_counts = collections.Counter(local(node.tag) for node in between)
    same_parent = start_parent is end_parent
    same_paragraph = start_p is not None and start_p is end_p
    same_cell = start_tc is not None and start_tc is end_tc
    same_row = start_tr is not None and start_tr is end_tr
    same_table = start_tbl is not None and start_tbl is end_tbl

    shape = {
        "same_parent": same_parent,
        "same_paragraph": same_paragraph,
        "same_cell": same_cell,
        "same_row": same_row,
        "same_table": same_table,
        "lca": None if lca is None else local(lca.tag),
        "start_parent": None if start_parent is None else local(start_parent.tag),
        "end_parent": None if end_parent is None else local(end_parent.tag),
    }

    return {
        "bookmark": name,
        "bookmark_id": bookmark_id,
        "status": "OK",
        "shape": shape,
        "start_path": path_labels(start, parent_map),
        "end_path": path_labels(end, parent_map),
        "start_parent_ordinal": ordinal_within_parent(start, parent_map),
        "end_parent_ordinal": ordinal_within_parent(end, parent_map),
        "document_order_distance": abs(end_idx - start_idx),
        "between_node_count": len(between),
        "between_tag_counts": dict(sorted(between_counts.items())),
    }

def inspect_document(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise ProfileError(f"Document not found: {path}")
    with zipfile.ZipFile(path, "r") as archive:
        if "word/document.xml" not in archive.namelist():
            raise ProfileError(f"{path.name} has no word/document.xml")
        root = ET.fromstring(archive.read("word/document.xml"))

    parent_map = build_parent_map(root)
    order = document_order(root)
    starts = [
        node for node in root.findall(".//w:bookmarkStart", NS)
        if (node.attrib.get(w("name")) or "").startswith("L")
    ]
    bookmarks = [inspect_bookmark(node, root, parent_map, order) for node in starts]

    shape_counts = collections.Counter()
    for item in bookmarks:
        if item.get("status") != "OK":
            shape_counts["STATUS:" + str(item.get("status"))] += 1
            continue
        shape = item["shape"]
        key = "|".join(
            [
                f"parent={shape['same_parent']}",
                f"p={shape['same_paragraph']}",
                f"tc={shape['same_cell']}",
                f"tr={shape['same_row']}",
                f"tbl={shape['same_table']}",
                f"lca={shape['lca']}",
                f"sp={shape['start_parent']}",
                f"ep={shape['end_parent']}",
            ]
        )
        shape_counts[key] += 1

    return {
        "filename": path.name,
        "sha256": sha256_bytes(path.read_bytes()),
        "bookmark_count": len(bookmarks),
        "shape_counts": dict(shape_counts.most_common()),
        "bookmarks": bookmarks,
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
            raise ProfileError("No matching source documents found.")

        records = [inspect_document(path) for path in docs]
        global_shapes = collections.Counter()
        total = 0
        unresolved = 0
        for record in records:
            total += record["bookmark_count"]
            for key, count in record["shape_counts"].items():
                global_shapes[key] += count
                if key.startswith("STATUS:"):
                    unresolved += count

        report = {
            "schema_version": "c5e-certificate-detail-cross-container-profile/v1",
            "status": "CROSS_CONTAINER_GEOMETRY_PROFILED" if unresolved == 0 else "CROSS_CONTAINER_GEOMETRY_PARTIAL",
            "documents": records,
            "summary": {
                "document_count": len(records),
                "bookmark_count": total,
                "unresolved_bookmarks": unresolved,
                "distinct_shape_count": len(global_shapes),
                "global_shape_counts": dict(global_shapes.most_common()),
            },
            "invariants": {
                "source_documents_modified": False,
                "unkeyed_entries_used": False,
                "compact_summary_used": False,
                "historical_prose_used": False,
                "renderer_implementation_changed": False,
            },
        }
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"STATUS={report['status']}")
        print(f"DOCUMENTS={len(records)}")
        print(f"BOOKMARKS={total}")
        print(f"UNRESOLVED={unresolved}")
        print(f"DISTINCT_SHAPES={len(global_shapes)}")
        print(f"OUTPUT={OUTPUT}")
        return 0
    except (ProfileError, zipfile.BadZipFile, ET.ParseError) as exc:
        print("STATUS=CROSS_CONTAINER_PROFILE_FAILED")
        print(f"ERROR={exc}")
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
