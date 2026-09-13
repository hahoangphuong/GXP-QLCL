from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "c5e_certificate_detail"
ACTIVE_VBA = FIXTURE_DIR / "Input_DC_to_CC.active.bas"
HELPER_DIR = FIXTURE_DIR / "helpers"
OUTPUT = ROOT / "artifacts" / "legacy_audit" / "c5e_certificate_detail_semantic_extraction.json"

STRING_RE = re.compile(r'"((?:""|[^"])*)"')
BOOKMARK_LITERAL_RE = re.compile(r'Bookmarks\s*\(\s*"([^"]+)"\s*\)', re.I)
KEY2BM_RE = re.compile(r'\bKey2Bookmark\s*\((.*?)\)', re.I)
COPY_RE = re.compile(r'\.(Copy|Paste(?:AndFormat)?|FormattedText)\b', re.I)
ROW_RE = re.compile(r'\b(?:Rows?|Cells?)\s*\(', re.I)
IF_RE = re.compile(r'^\s*(If|ElseIf|Else\b)', re.I)
FOR_RE = re.compile(r'^\s*(For\b|Do\b|While\b)', re.I)
CALL_NAME_RE = re.compile(r'\b([A-Za-z_][A-Za-z0-9_]*)\s*(?:\(|$)')


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _strip_comment(line: str) -> str:
    # VBA comments start at apostrophe outside a string.
    out = []
    in_string = False
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == '"':
            if in_string and i + 1 < len(line) and line[i + 1] == '"':
                out.extend(['"', '"'])
                i += 2
                continue
            in_string = not in_string
            out.append(ch)
            i += 1
            continue
        if ch == "'" and not in_string:
            break
        out.append(ch)
        i += 1
    return "".join(out).rstrip()


def _active_lines(text: str) -> list[tuple[int, str]]:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").splitlines()
    result = []
    for idx, raw in enumerate(lines, start=1):
        code = _strip_comment(raw)
        if code.strip():
            result.append((idx, code))
    return result


def _extract_helper_contract(name: str, text: str) -> dict[str, object]:
    active = _active_lines(text)
    return {
        "name": name,
        "line_count": len(active),
        "string_literals": sorted({
            s.replace('""', '"')
            for _, line in active
            for s in STRING_RE.findall(line)
        }),
        "contains_bookmark_access": any("Bookmarks" in line for _, line in active),
        "contains_copy_semantics": any(COPY_RE.search(line) for _, line in active),
        "contains_row_cell_semantics": any(ROW_RE.search(line) for _, line in active),
        "active_lines": [{"line": n, "code": line.strip()} for n, line in active],
    }


def audit() -> dict[str, object]:
    blockers: list[dict[str, object]] = []
    if not ACTIVE_VBA.is_file():
        raise SystemExit(f"Missing captured active VBA fixture: {ACTIVE_VBA}")

    active_text = _read(ACTIVE_VBA)
    active = _active_lines(active_text)
    bookmark_literals = []
    key2bookmark_calls = []
    copy_lines = []
    row_lines = []
    branch_lines = []
    loop_lines = []
    strings = set()

    for line_no, line in active:
        for value in STRING_RE.findall(line):
            strings.add(value.replace('""', '"'))
        for bm in BOOKMARK_LITERAL_RE.findall(line):
            bookmark_literals.append({"line": line_no, "bookmark": bm})
        for m in KEY2BM_RE.finditer(line):
            key2bookmark_calls.append({"line": line_no, "expression": m.group(1).strip()})
        if COPY_RE.search(line):
            copy_lines.append({"line": line_no, "code": line.strip()})
        if ROW_RE.search(line):
            row_lines.append({"line": line_no, "code": line.strip()})
        if IF_RE.search(line):
            branch_lines.append({"line": line_no, "code": line.strip()})
        if FOR_RE.search(line):
            loop_lines.append({"line": line_no, "code": line.strip()})

    helpers = []
    if HELPER_DIR.is_dir():
        for path in sorted(HELPER_DIR.glob("*.bas")):
            helpers.append(_extract_helper_contract(path.stem, _read(path)))

    structure_files = sorted(FIXTURE_DIR.glob("*.structure.json"))
    template_structures = []
    for path in structure_files:
        payload = json.loads(_read(path))
        all_bookmarks = []
        rows_with_bookmarks = []
        for part in payload.get("parts", []):
            all_bookmarks.extend(
                bm.get("name") for bm in part.get("bookmarks", []) if bm.get("name")
            )
            for table in part.get("tables", []):
                for row in table.get("rows", []):
                    if row.get("bookmarks"):
                        rows_with_bookmarks.append({
                            "part": part.get("part"),
                            "table_index": table.get("table_index"),
                            "row_index": row.get("row_index"),
                            "bookmarks": row.get("bookmarks"),
                            "cell_text_preview": row.get("cell_text_preview"),
                        })
        template_structures.append({
            "fixture": path.relative_to(ROOT).as_posix(),
            "template_filename": payload.get("template_filename"),
            "template_sha256": payload.get("template_sha256"),
            "all_bookmarks": all_bookmarks,
            "rows_with_bookmarks": rows_with_bookmarks,
        })

    # The detail path is considered mechanically evidenced only if the active body exposes
    # dynamic Key2Bookmark mapping and at least one copy/row operation. Otherwise a human
    # semantic review is still required before implementation.
    has_dynamic_key_mapping = bool(key2bookmark_calls)
    has_copy_or_row_behavior = bool(copy_lines or row_lines)
    if not has_dynamic_key_mapping:
        blockers.append({
            "code": "NO_DYNAMIC_KEY_TO_BOOKMARK_MAPPING_OBSERVED",
            "message": "Active Input_DC_to_CC fixture exposes no Key2Bookmark(...) call; row-level taxonomy ownership cannot be inferred safely.",
        })
    if not has_copy_or_row_behavior:
        blockers.append({
            "code": "NO_ROW_OR_COPY_BEHAVIOR_OBSERVED",
            "message": "Active Input_DC_to_CC fixture exposes no row/cell/copy behavior; template insertion semantics remain unproven.",
        })
    if not template_structures:
        blockers.append({
            "code": "NO_CAPTURED_CERTIFICATE_TEMPLATE_STRUCTURE",
            "message": "No captured certificate *.structure.json fixture is present.",
        })

    report = {
        "schema_version": "c5e-certificate-detail-semantic-extraction/v1",
        "status": "SEMANTIC_EVIDENCE_EXTRACTED" if not blockers else "SEMANTIC_EVIDENCE_INCOMPLETE",
        "active_procedure_fixture": ACTIVE_VBA.relative_to(ROOT).as_posix(),
        "active_line_count": len(active),
        "bookmark_literals": bookmark_literals,
        "key2bookmark_calls": key2bookmark_calls,
        "copy_semantics": copy_lines,
        "row_cell_semantics": row_lines,
        "branch_semantics": branch_lines,
        "loop_semantics": loop_lines,
        "string_literals": sorted(strings),
        "helpers": helpers,
        "templates": template_structures,
        "blockers": blockers,
        "invariants": {
            "commented_code_used": False,
            "compact_summary_used": False,
            "historical_prose_used": False,
            "unkeyed_entries_used": False,
            "production_code_modified": False,
        },
        "next_step": (
            "Use the extracted active-line evidence to author the exact Input_DC_to_CC row-level contract. "
            "Do not implement renderer integration until each dynamic bookmark/key and copy/row action has an explicit deterministic mapping."
        ),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    report = audit()
    print(f"STATUS={report['status']}")
    print(f"BLOCKERS={len(report['blockers'])}")
    print(f"KEY2BOOKMARK_CALLS={len(report['key2bookmark_calls'])}")
    print(f"COPY_ACTIONS={len(report['copy_semantics'])}")
    print(f"ROW_CELL_ACTIONS={len(report['row_cell_semantics'])}")
    print(f"TEMPLATES={len(report['templates'])}")
    print(f"OUTPUT={OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
