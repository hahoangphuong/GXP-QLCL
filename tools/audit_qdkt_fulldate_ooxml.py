"""Offline, read-only OOXML inspection of QĐKT issuance-date bookmarks.

Reports structural evidence only; cannot prove rendered page appearance.
Never modifies template bytes or supplies a date for any bookmark.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
PARTS = ("word/document.xml",)


def inspect_qdkt_fulldate(path: Path) -> dict[str, object]:
    result: dict[str, object] = {
        "filename": path.name,
        "physical_bookmark": "Fulldate",
        "status": "UNPROVEN",
        "matches": [],
        "limitations": [
            "Bookmark XML structure does not prove visual blank issuance date.",
            "No issuance date may be generated from clock or decision date.",
        ],
    }
    try:
        with ZipFile(path) as archive:
            parts = sorted(
                name for name in archive.namelist()
                if name in PARTS or (
                    name.startswith("word/header") and name.endswith(".xml")
                ) or (
                    name.startswith("word/footer") and name.endswith(".xml")
                )
            )
            for name in parts:
                root = ET.fromstring(archive.read(name))
                starts = [
                    elem for elem in root.iter(W + "bookmarkStart")
                    if elem.get(W + "name") == "Fulldate"
                ]
                for start in starts:
                    bid = start.get(W + "id")
                    ends = [
                        elem for elem in root.iter(W + "bookmarkEnd")
                        if elem.get(W + "id") == bid
                    ]
                    result["matches"].append({
                        "part": name,
                        "bookmark_id": bid,
                        "matching_end_count": len(ends),
                    })
    except (OSError, BadZipFile, ET.ParseError, KeyError) as exc:
        result["status"] = "UNREADABLE_TEMPLATE"
        result["error_type"] = type(exc).__name__
        return result
    if len(result["matches"]) == 1 and result["matches"][0]["matching_end_count"] == 1:
        result["status"] = "STRUCTURAL_BOOKMARK_FOUND"
    elif not result["matches"]:
        result["status"] = "BOOKMARK_NOT_FOUND"
    else:
        result["status"] = "BOOKMARK_AMBIGUOUS"
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("templates", type=Path, nargs="+")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    findings = [inspect_qdkt_fulldate(path) for path in args.templates]
    report = {"schema_version": "qdkt-fulldate-physical-audit/v1", "findings": findings}
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out is not None:
        args.out.write_text(serialized + "\n", encoding="utf-8")
    else:
        print(serialized)
    return 0 if all(x["status"] == "STRUCTURAL_BOOKMARK_FOUND" for x in findings) else 2


if __name__ == "__main__":
    raise SystemExit(main())
