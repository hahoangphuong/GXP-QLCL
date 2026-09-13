from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "c5e_certificate_detail" / "Input_DC_to_CC.active.bas"
OUTPUT_JSON = ROOT / "artifacts" / "legacy_audit" / "c5e_certificate_detail_contract_candidate.json"
OUTPUT_MD = ROOT / "artifacts" / "legacy_audit" / "c5e_certificate_detail_contract_candidate.md"

KEY2BM_RE = re.compile(r"Key2Bookmark\s*\((.+?)\)\)", re.I)
SOURCE_BM_COPY_RE = re.compile(
    r"Selection\.FormattedText\s*=\s*(?P<doc>[A-Za-z_][A-Za-z0-9_]*)"
    r"\.Bookmarks\(Key2Bookmark\((?P<key>.+?)\)\)\.Range\.FormattedText",
    re.I,
)

ACTION_PATTERNS = {
    "formatted_bookmark_copy": re.compile(r"\.FormattedText\s*=", re.I),
    "selection_text_write": re.compile(r"\bSelection\.(TypeText|InsertAfter|InsertBefore)\b", re.I),
    "selection_move": re.compile(r"\bSelection\.(Move|MoveRight|MoveLeft|Collapse|EndKey|HomeKey)\b", re.I),
    "bookmark_access": re.compile(r"\bBookmarks\s*\(", re.I),
    "split_lines": re.compile(r"\bSplitLines\s*\(", re.I),
    "translate_scope": re.compile(r"\bTranslate_VE_Daychuyen\s*\(", re.I),
    "translate_address": re.compile(r"\bTranslate_VE_Diachi\s*\(", re.I),
    "load_scope_nodes": re.compile(r"\bLoad_DC_Nodes\s*\(", re.I),
    "pv_map": re.compile(r"\bPV_map\s*\(", re.I),
    "pv_desc": re.compile(r"\bPV_Desc\s*\(", re.I),
    "main_topic": re.compile(r"\bPVCN_colMainTopic\b", re.I),
    "primary_secondary_pack": re.compile(r"\bPVCN_row(?:PriPack|SecPack)\b", re.I),
    "english_branch": re.compile(r"\bEngPart\b", re.I),
    "scope_note": re.compile(r"\bs_Note\b", re.I),
    "scope_name": re.compile(r"\bs_N\b", re.I),
    "scope_data": re.compile(r"\bs_D\b", re.I),
}

IF_START_RE = re.compile(r"^\s*If\b.*\bThen\b", re.I)
ELSEIF_RE = re.compile(r"^\s*ElseIf\b.*\bThen\b", re.I)
ELSE_RE = re.compile(r"^\s*Else\s*$", re.I)
END_IF_RE = re.compile(r"^\s*End\s+If\s*$", re.I)
FOR_RE = re.compile(r"^\s*For\b", re.I)
NEXT_RE = re.compile(r"^\s*Next\b", re.I)


def strip_comment(line: str) -> str:
    out: list[str] = []
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


def active_lines(text: str) -> list[dict[str, object]]:
    rows = []
    for number, raw in enumerate(text.replace("\r\n", "\n").replace("\r", "\n").splitlines(), start=1):
        code = strip_comment(raw)
        if not code.strip():
            continue
        rows.append({"line": number, "code": code.strip()})
    return rows


def classify(line: str) -> list[str]:
    return [name for name, pattern in ACTION_PATTERNS.items() if pattern.search(line)]


def build_control_context(lines: list[dict[str, object]]) -> list[dict[str, object]]:
    stack: list[dict[str, object]] = []
    enriched = []
    for row in lines:
        code = str(row["code"])
        line_no = int(row["line"])

        if END_IF_RE.match(code):
            if stack and stack[-1]["kind"] == "if":
                stack.pop()
        elif NEXT_RE.match(code):
            if stack and stack[-1]["kind"] == "for":
                stack.pop()
        elif ELSEIF_RE.match(code):
            if stack and stack[-1]["kind"] == "if":
                stack[-1] = {"kind": "if", "line": line_no, "condition": code}
        elif ELSE_RE.match(code):
            if stack and stack[-1]["kind"] == "if":
                stack[-1] = {"kind": "if", "line": line_no, "condition": "Else"}
        elif IF_START_RE.match(code) and not re.search(r":\s*(GoTo|Exit|MsgBox|[A-Za-z_].*=)", code, re.I):
            stack.append({"kind": "if", "line": line_no, "condition": code})
        elif FOR_RE.match(code):
            stack.append({"kind": "for", "line": line_no, "condition": code})

        enriched.append({
            **row,
            "actions": classify(code),
            "control_context": [dict(item) for item in stack],
        })
    return enriched


def derive_contract(lines: list[dict[str, object]]) -> dict[str, object]:
    dynamic_copies = []
    for row in lines:
        code = str(row["code"])
        m = SOURCE_BM_COPY_RE.search(code)
        if m:
            dynamic_copies.append({
                "line": row["line"],
                "source_document_expression": m.group("doc"),
                "source_bookmark_key_expression": m.group("key").strip(),
                "bookmark_transform": "Key2Bookmark: trim; remove trailing '.'; prefix 'L'; replace '.' with '_'",
                "copy_mode": "Range.FormattedText -> Selection.FormattedText",
                "control_context": row["control_context"],
            })

    action_index: dict[str, list[dict[str, object]]] = {}
    for row in lines:
        for action in row["actions"]:
            action_index.setdefault(action, []).append({
                "line": row["line"],
                "code": row["code"],
                "control_context": row["control_context"],
            })

    return {
        "semantic_owner": "active VBA Input_DC_to_CC fixture",
        "render_primitive_candidate": "formatted_bookmark_fragment_copy_plus_text_append",
        "table_row_clone_is_primary_primitive": False,
        "dynamic_formatted_bookmark_copies": dynamic_copies,
        "actions": action_index,
        "explicit_invariants": {
            "unkeyed_entries_allowed": False,
            "compact_summary_allowed": False,
            "historical_prose_allowed": False,
            "commented_vba_allowed": False,
            "source_bookmark_formatting_must_be_preserved": bool(dynamic_copies),
        },
    }


def main() -> int:
    if not FIXTURE.is_file():
        print("STATUS=CONTRACT_CANDIDATE_FAILED")
        print(f"ERROR=Missing active VBA fixture: {FIXTURE}")
        return 2

    text = FIXTURE.read_text(encoding="utf-8")
    lines = build_control_context(active_lines(text))
    contract = derive_contract(lines)

    blockers = []
    if len(contract["dynamic_formatted_bookmark_copies"]) != 1:
        blockers.append({
            "code": "FORMATTED_BOOKMARK_COPY_CARDINALITY_UNEXPECTED",
            "observed": len(contract["dynamic_formatted_bookmark_copies"]),
            "expected": 1,
        })
    if not contract["actions"].get("load_scope_nodes"):
        blockers.append({"code": "LOAD_DC_NODES_NOT_OBSERVED"})
    if not contract["actions"].get("pv_map"):
        blockers.append({"code": "PV_MAP_NOT_OBSERVED"})
    if not contract["actions"].get("pv_desc"):
        blockers.append({"code": "PV_DESC_NOT_OBSERVED"})
    if not contract["actions"].get("english_branch"):
        blockers.append({"code": "ENGPART_BRANCH_NOT_OBSERVED"})

    report = {
        "schema_version": "c5e-certificate-detail-contract-candidate/v1",
        "status": "CONTRACT_CANDIDATE_READY_FOR_REVIEW" if not blockers else "CONTRACT_CANDIDATE_INCOMPLETE",
        "fixture": FIXTURE.relative_to(ROOT).as_posix(),
        "active_line_count": len(lines),
        "contract": contract,
        "active_lines": lines,
        "blockers": blockers,
        "next_step": (
            "Review this exact line-provenance contract. Then implement a certificate-detail projection "
            "and a DOCX formatted-fragment insertion primitive only if source bookmark fragments are "
            "available as durable source-template assets at generation time."
        ),
    }

    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    md = [
        "# C.5e Input_DC_to_CC contract candidate",
        "",
        f"Status: `{report['status']}`",
        "",
        "## Derived primitive",
        "",
        f"- `{contract['render_primitive_candidate']}`",
        "- table-row cloning is **not** the primary primitive.",
        "",
        "## Dynamic formatted bookmark copy",
        "",
    ]
    for item in contract["dynamic_formatted_bookmark_copies"]:
        md += [
            f"- line {item['line']}: source document `{item['source_document_expression']}`",
            f"  - key expression: `{item['source_bookmark_key_expression']}`",
            f"  - transform: {item['bookmark_transform']}",
            f"  - copy: `{item['copy_mode']}`",
        ]
    md += ["", "## Active line provenance", ""]
    for row in lines:
        acts = ", ".join(row["actions"]) or "-"
        md.append(f"- L{row['line']}: `{row['code']}` — {acts}")
    OUTPUT_MD.write_text("\n".join(md) + "\n", encoding="utf-8")

    print(f"STATUS={report['status']}")
    print(f"BLOCKERS={len(blockers)}")
    print(f"ACTIVE_LINES={len(lines)}")
    print(f"FORMATTED_BOOKMARK_COPIES={len(contract['dynamic_formatted_bookmark_copies'])}")
    print(f"OUTPUT={OUTPUT_JSON}")
    print(f"MARKDOWN={OUTPUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
