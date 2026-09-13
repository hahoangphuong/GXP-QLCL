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
OUTPUT = ROOT / "artifacts" / "legacy_audit" / "c5e_certificate_detail_cross_container_extraction.json"
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "c5e_certificate_detail" / "cross_container_fragments"

WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": WORD_NS}

ALLOWED_SHAPES = {
    "parent=False|p=False|tc=False|tr=False|tbl=True|lca=tbl|sp=p|ep=p",
    "parent=False|p=False|tc=False|tr=False|tbl=True|lca=tbl|sp=p|ep=tbl",
}


class ExtractionError(RuntimeError):
    pass


def w(tag: str) -> str:
    return f"{{{WORD_NS}}}{tag}"


def local(tag: str) -> str:
    return tag.split("}", 1)[1] if tag.startswith("{") else tag


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def build_parent_map(root: ET.Element) -> dict[ET.Element, ET.Element]:
    return {
        child: parent
        for parent in root.iter()
        for child in list(parent)
    }


def ancestors(node: ET.Element, parent_map: dict[ET.Element, ET.Element]) -> list[ET.Element]:
    result = [node]
    current = node
    while current in parent_map:
        current = parent_map[current]
        result.append(current)
    return result


def lowest_common_ancestor(
    a: ET.Element,
    b: ET.Element,
    parent_map: dict[ET.Element, ET.Element],
) -> ET.Element | None:
    a_chain = list(reversed(ancestors(a, parent_map)))
    b_chain = list(reversed(ancestors(b, parent_map)))
    result = None
    for left, right in zip(a_chain, b_chain):
        if left is not right:
            break
        result = left
    return result


def nearest_ancestor(
    node: ET.Element,
    parent_map: dict[ET.Element, ET.Element],
    tag: str,
) -> ET.Element | None:
    qualified = w(tag)
    current = node
    while True:
        if current.tag == qualified:
            return current
        if current not in parent_map:
            return None
        current = parent_map[current]


def find_bookmark_end(root: ET.Element, bookmark_id: str | None) -> ET.Element | None:
    if bookmark_id is None:
        return None
    for node in root.findall(".//w:bookmarkEnd", NS):
        if node.attrib.get(w("id")) == bookmark_id:
            return node
    return None


def shape_key(
    start: ET.Element,
    end: ET.Element,
    parent_map: dict[ET.Element, ET.Element],
) -> str:
    sp = parent_map.get(start)
    ep = parent_map.get(end)
    lca = lowest_common_ancestor(start, end, parent_map)
    start_p = nearest_ancestor(start, parent_map, "p")
    end_p = nearest_ancestor(end, parent_map, "p")
    start_tc = nearest_ancestor(start, parent_map, "tc")
    end_tc = nearest_ancestor(end, parent_map, "tc")
    start_tr = nearest_ancestor(start, parent_map, "tr")
    end_tr = nearest_ancestor(end, parent_map, "tr")
    start_tbl = nearest_ancestor(start, parent_map, "tbl")
    end_tbl = nearest_ancestor(end, parent_map, "tbl")
    return "|".join(
        [
            f"parent={sp is ep}",
            f"p={start_p is not None and start_p is end_p}",
            f"tc={start_tc is not None and start_tc is end_tc}",
            f"tr={start_tr is not None and start_tr is end_tr}",
            f"tbl={start_tbl is not None and start_tbl is end_tbl}",
            f"lca={None if lca is None else local(lca.tag)}",
            f"sp={None if sp is None else local(sp.tag)}",
            f"ep={None if ep is None else local(ep.tag)}",
        ]
    )


def build_preorder(root: ET.Element) -> tuple[list[ET.Element], dict[ET.Element, int], dict[ET.Element, int]]:
    nodes = list(root.iter())
    index = {node: i for i, node in enumerate(nodes)}
    subtree_end: dict[ET.Element, int] = {}

    def visit(node: ET.Element) -> int:
        end = index[node]
        for child in list(node):
            end = max(end, visit(child))
        subtree_end[node] = end
        return end

    visit(root)
    return nodes, index, subtree_end


def clone_intersection(
    node: ET.Element,
    *,
    start_index: int,
    end_index: int,
    index: dict[ET.Element, int],
    subtree_end: dict[ET.Element, int],
) -> ET.Element | None:
    node_start = index[node]
    node_end = subtree_end[node]

    if node_end <= start_index or node_start >= end_index:
        return None

    if node.tag in {w("bookmarkStart"), w("bookmarkEnd")}:
        return None

    clone = ET.Element(node.tag, dict(node.attrib))
    clone.text = node.text
    clone.tail = node.tail

    for child in list(node):
        child_clone = clone_intersection(
            child,
            start_index=start_index,
            end_index=end_index,
            index=index,
            subtree_end=subtree_end,
        )
        if child_clone is not None:
            clone.append(child_clone)

    # Keep leaf content only when the leaf itself lies strictly inside the range.
    if not list(node):
        if not (start_index < node_start < end_index):
            return None

    # Structural containers can remain even without direct children only when they
    # are part of an ancestor chain needed to preserve the Word table hierarchy.
    if list(node) and len(clone) == 0:
        return None

    return clone


def strip_bookmark_markup(element: ET.Element) -> None:
    for parent in list(element.iter()):
        for child in list(parent):
            if child.tag in {w("bookmarkStart"), w("bookmarkEnd")}:
                parent.remove(child)


def visible_text(element: ET.Element) -> str:
    return "".join(node.text or "" for node in element.findall(".//w:t", NS))


def extract_bookmark_table_fragment(root: ET.Element, bookmark_name: str) -> dict[str, object]:
    starts = [
        node
        for node in root.findall(".//w:bookmarkStart", NS)
        if node.attrib.get(w("name")) == bookmark_name
    ]
    if len(starts) != 1:
        raise ExtractionError(
            f"Expected exactly one bookmarkStart for {bookmark_name!r}; found {len(starts)}."
        )

    start = starts[0]
    end = find_bookmark_end(root, start.attrib.get(w("id")))
    if end is None:
        raise ExtractionError(f"bookmarkEnd not found for {bookmark_name!r}.")

    parent_map = build_parent_map(root)
    shape = shape_key(start, end, parent_map)
    if shape not in ALLOWED_SHAPES:
        raise ExtractionError(
            f"Unsupported bookmark geometry for {bookmark_name!r}: {shape}"
        )

    lca = lowest_common_ancestor(start, end, parent_map)
    if lca is None or lca.tag != w("tbl"):
        raise ExtractionError(
            f"Bookmark {bookmark_name!r} does not have w:tbl as lowest common ancestor."
        )

    _, index, subtree_end = build_preorder(root)
    start_index = index[start]
    end_index = index[end]
    if end_index <= start_index:
        raise ExtractionError(f"Bookmark {bookmark_name!r} has reversed document order.")

    fragment = clone_intersection(
        lca,
        start_index=start_index,
        end_index=end_index,
        index=index,
        subtree_end=subtree_end,
    )
    if fragment is None:
        raise ExtractionError(f"Bookmark {bookmark_name!r} produced an empty fragment.")

    strip_bookmark_markup(fragment)
    fragment_xml = ET.tostring(fragment, encoding="unicode")
    return {
        "bookmark": bookmark_name,
        "shape": shape,
        "visible_text": visible_text(fragment),
        "fragment_xml": fragment_xml,
        "fragment_sha256": sha256_bytes(fragment_xml.encode("utf-8")),
        "root_tag": local(fragment.tag),
        "row_count": len(fragment.findall("./w:tr", NS)),
        "cell_count": len(fragment.findall(".//w:tc", NS)),
        "paragraph_count": len(fragment.findall(".//w:p", NS)),
        "contains_bookmark_markup": bool(
            fragment.findall(".//w:bookmarkStart", NS)
            or fragment.findall(".//w:bookmarkEnd", NS)
        ),
    }


def inspect_document(path: Path) -> dict[str, object]:
    with zipfile.ZipFile(path, "r") as archive:
        if "word/document.xml" not in archive.namelist():
            raise ExtractionError(f"{path.name} has no word/document.xml.")
        root = ET.fromstring(archive.read("word/document.xml"))

    names = sorted(
        {
            node.attrib.get(w("name"))
            for node in root.findall(".//w:bookmarkStart", NS)
            if (node.attrib.get(w("name")) or "").startswith("L")
        }
    )

    fragments = []
    errors = []
    for name in names:
        try:
            fragments.append(extract_bookmark_table_fragment(root, name))
        except ExtractionError as exc:
            errors.append({"bookmark": name, "error": str(exc)})

    return {
        "filename": path.name,
        "sha256": sha256_bytes(path.read_bytes()),
        "bookmark_count": len(names),
        "extracted_count": len(fragments),
        "error_count": len(errors),
        "shape_counts": dict(
            __import__("collections").Counter(item["shape"] for item in fragments).most_common()
        ),
        "fragments": fragments,
        "errors": errors,
    }


def discover(root: Path) -> list[Path]:
    patterns = (
        re.compile(r"^9\.?\s*Phamvi.*\.docx$", re.I),
        re.compile(r"^z3\.?\s*Phamvi.*\.docx$", re.I),
    )
    return sorted(
        path
        for path in root.rglob("*.docx")
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
            raise ExtractionError("No matching source documents found.")

        records = [inspect_document(path) for path in docs]
        total = sum(r["bookmark_count"] for r in records)
        extracted = sum(r["extracted_count"] for r in records)
        errors = sum(r["error_count"] for r in records)

        FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
        for record in records:
            safe = re.sub(r"[^A-Za-z0-9._-]+", "_", record["filename"])
            (FIXTURE_DIR / f"{safe}.cross-container.json").write_text(
                json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

        report = {
            "schema_version": "c5e-certificate-detail-cross-container-extraction/v1",
            "status": (
                "CROSS_CONTAINER_FRAGMENTS_EXTRACTED"
                if errors == 0 and extracted == total
                else "CROSS_CONTAINER_EXTRACTION_PARTIAL"
            ),
            "allowed_shapes": sorted(ALLOWED_SHAPES),
            "documents": records,
            "summary": {
                "document_count": len(records),
                "bookmark_count": total,
                "extracted_count": extracted,
                "error_count": errors,
            },
            "invariants": {
                "source_documents_modified": False,
                "production_renderer_modified": False,
                "bookmark_markup_copied": False,
                "unkeyed_entries_used": False,
                "compact_summary_used": False,
                "historical_prose_used": False,
                "unsupported_geometry_fails_closed": True,
            },
        }
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"STATUS={report['status']}")
        print(f"DOCUMENTS={len(records)}")
        print(f"BOOKMARKS={total}")
        print(f"EXTRACTED={extracted}")
        print(f"ERRORS={errors}")
        print(f"OUTPUT={OUTPUT}")
        print(f"FIXTURE_DIR={FIXTURE_DIR}")
        return 0
    except (ExtractionError, zipfile.BadZipFile, ET.ParseError) as exc:
        print("STATUS=CROSS_CONTAINER_EXTRACTION_FAILED")
        print(f"ERROR={exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
