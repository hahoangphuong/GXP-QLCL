from __future__ import annotations

import argparse
import collections
import json
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts" / "legacy_audit" / "c5e_certificate_detail_destination_anchor_child_profile.json"

WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": WORD_NS}


class ProfileError(RuntimeError):
    pass


def w(tag: str) -> str:
    return f"{{{WORD_NS}}}{tag}"


def local(tag: str) -> str:
    return tag.split("}", 1)[1] if tag.startswith("{") else tag


def build_parent_map(root: ET.Element):
    return {child: parent for parent in root.iter() for child in list(parent)}


def nearest(node: ET.Element, parent_map, tag: str):
    q = w(tag)
    cur = node
    while True:
        if cur.tag == q:
            return cur
        if cur not in parent_map:
            return None
        cur = parent_map[cur]


def find_end(root: ET.Element, bookmark_id: str | None):
    if bookmark_id is None:
        return None
    for node in root.findall(".//w:bookmarkEnd", NS):
        if node.attrib.get(w("id")) == bookmark_id:
            return node
    return None


def summarize_run(run: ET.Element) -> dict[str, object]:
    children = []
    for child in list(run):
        entry = {"tag": local(child.tag)}
        if child.tag == w("t"):
            entry["text"] = child.text or ""
        if child.attrib:
            entry["attrib"] = {local(k): v for k, v in child.attrib.items()}
        children.append(entry)
    return {
        "tag": "r",
        "text": "".join(t.text or "" for t in run.findall(".//w:t", NS)),
        "children": children,
    }


def summarize_child(child: ET.Element) -> dict[str, object]:
    tag = local(child.tag)
    item: dict[str, object] = {"tag": tag}
    if child.attrib:
        item["attrib"] = {local(k): v for k, v in child.attrib.items()}
    if child.tag == w("r"):
        item.update(summarize_run(child))
    else:
        text = "".join(t.text or "" for t in child.findall(".//w:t", NS))
        if text:
            item["text"] = text
        descendants = [local(n.tag) for n in child.iter() if n is not child]
        if descendants:
            item["descendant_tags"] = descendants
    return item


def inspect_anchor(root: ET.Element, name: str) -> dict[str, object]:
    starts = [
        node for node in root.findall(".//w:bookmarkStart", NS)
        if node.attrib.get(w("name")) == name
    ]
    if len(starts) != 1:
        return {"bookmark": name, "status": "START_CARDINALITY_ERROR", "start_count": len(starts)}

    start = starts[0]
    end = find_end(root, start.attrib.get(w("id")))
    if end is None:
        return {"bookmark": name, "status": "END_NOT_FOUND"}

    pm = build_parent_map(root)
    p = nearest(start, pm, "p")
    end_p = nearest(end, pm, "p")
    if p is None or p is not end_p:
        return {"bookmark": name, "status": "NOT_SAME_PARAGRAPH"}

    children = [summarize_child(child) for child in list(p)]
    tag_sequence = [child["tag"] for child in children]
    visible_text = "".join(t.text or "" for t in p.findall(".//w:t", NS))

    return {
        "bookmark": name,
        "status": "OK",
        "visible_text": visible_text,
        "tag_sequence": tag_sequence,
        "children": children,
    }


def inspect_template(path: Path) -> dict[str, object]:
    with zipfile.ZipFile(path, "r") as archive:
        root = ET.fromstring(archive.read("word/document.xml"))

    names = sorted({
        node.attrib.get(w("name"))
        for node in root.findall(".//w:bookmarkStart", NS)
        if (node.attrib.get(w("name")) or "").lower().startswith("pvi")
    })
    return {
        "filename": path.name,
        "anchors": [inspect_anchor(root, name) for name in names],
    }


def is_candidate(path: Path) -> bool:
    if path.suffix.lower() not in {".docx", ".dotx"}:
        return False
    name = path.name.lower()
    return (
        "chung chi" in name
        or "giay" in name
        or "quyet dinh" in name
        or "qd" in name
    )


def discover(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*") if is_candidate(path))


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

        records = [inspect_template(path) for path in paths]
        records = [record for record in records if record["anchors"]]
        if not records:
            raise ProfileError("No Pvi* anchors found.")

        sequence_counts = collections.Counter()
        total = 0
        for record in records:
            for anchor in record["anchors"]:
                total += 1
                if anchor["status"] == "OK":
                    sequence_counts[" > ".join(anchor["tag_sequence"])] += 1
                else:
                    sequence_counts["STATUS:" + anchor["status"]] += 1

        report = {
            "schema_version": "c5e-certificate-detail-destination-anchor-child-profile/v1",
            "status": "DESTINATION_ANCHOR_CHILDREN_PROFILED",
            "documents": records,
            "summary": {
                "document_count": len(records),
                "anchor_count": total,
                "distinct_child_sequences": len(sequence_counts),
                "child_sequence_counts": dict(sequence_counts.most_common()),
            },
            "invariants": {
                "templates_modified": False,
                "renderer_modified": False,
                "scope_matches_destination_anchor_profile": True,
            },
        }
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"STATUS={report['status']}")
        print(f"DOCUMENTS={len(records)}")
        print(f"ANCHORS={total}")
        print(f"DISTINCT_CHILD_SEQUENCES={len(sequence_counts)}")
        print(f"OUTPUT={OUTPUT}")
        return 0
    except Exception as exc:
        print("STATUS=DESTINATION_ANCHOR_CHILD_PROFILE_FAILED")
        print(f"ERROR={exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
