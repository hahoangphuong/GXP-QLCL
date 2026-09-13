from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts" / "legacy_audit" / "c5e_certificate_detail_source_document_trace.json"
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "c5e_certificate_detail" / "source_document_trace"

PROC_START = re.compile(
    r"^\s*(?:Public\s+|Private\s+|Friend\s+)?(?:Sub|Function)\s+([A-Za-z_][A-Za-z0-9_]*)\b",
    re.I,
)
PROC_END = re.compile(r"^\s*End\s+(?:Sub|Function)\s*$", re.I)
TARGET_CALL = re.compile(r"\bInput_DC_to_CC\s*(?:\(|\s)", re.I)
OPEN_RE = re.compile(r"\bDocuments\.Open\b|\bOpenDocument\b|\bGetObject\b", re.I)
SET_DOC_RE = re.compile(r"\bSet\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+)", re.I)
STRING_RE = re.compile(r'"((?:""|[^"])*)"')


class TraceError(RuntimeError):
    pass


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def normalize(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def strip_comment(line: str) -> str:
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


def decode_vba(raw: bytes) -> tuple[str, str]:
    try:
        return raw.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return raw.decode("cp1252"), "cp1252"


def procedures(text: str, member: str) -> list[dict[str, object]]:
    lines = normalize(text).splitlines()
    result = []
    i = 0
    while i < len(lines):
        code = strip_comment(lines[i])
        m = PROC_START.match(code)
        if not m:
            i += 1
            continue
        name = m.group(1)
        start = i
        j = i + 1
        while j < len(lines) and not PROC_END.match(strip_comment(lines[j])):
            j += 1
        if j >= len(lines):
            break
        proc_lines = []
        for n in range(start, j + 1):
            active = strip_comment(lines[n])
            proc_lines.append({
                "line": n + 1,
                "raw": lines[n],
                "active": active,
            })
        result.append({
            "member": member,
            "name": name,
            "start_line": start + 1,
            "end_line": j + 1,
            "lines": proc_lines,
        })
        i = j + 1
    return result


def analyze_proc(proc: dict[str, object]) -> dict[str, object] | None:
    lines = proc["lines"]
    call_indices = [
        idx for idx, row in enumerate(lines)
        if row["active"].strip() and TARGET_CALL.search(row["active"])
        and not re.search(r"(?:Sub|Function)\s+Input_DC_to_CC\b", row["active"], re.I)
    ]
    if not call_indices:
        return None

    windows = []
    for idx in call_indices:
        lo = max(0, idx - 35)
        hi = min(len(lines), idx + 16)
        context = lines[lo:hi]
        assignments = []
        opens = []
        string_literals = set()
        for row in context:
            active = row["active"]
            if not active.strip():
                continue
            m = SET_DOC_RE.search(active)
            if m:
                assignments.append({
                    "line": row["line"],
                    "variable": m.group(1),
                    "expression": m.group(2).strip(),
                })
            if OPEN_RE.search(active):
                opens.append({"line": row["line"], "code": active.strip()})
            for value in STRING_RE.findall(active):
                string_literals.add(value.replace('""', '"'))
        windows.append({
            "call_line": lines[idx]["line"],
            "call_code": lines[idx]["active"].strip(),
            "context": [
                {"line": row["line"], "code": row["active"].strip()}
                for row in context if row["active"].strip()
            ],
            "object_assignments": assignments,
            "document_open_actions": opens,
            "string_literals": sorted(string_literals),
        })
    return {
        "member": proc["member"],
        "procedure": proc["name"],
        "start_line": proc["start_line"],
        "end_line": proc["end_line"],
        "call_windows": windows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Trace active callers of Input_DC_to_CC and the wdDoc2 source document."
    )
    parser.add_argument("--vba-zip", required=True, type=Path)
    args = parser.parse_args()
    vba_zip = args.vba_zip.resolve()

    if not vba_zip.is_file():
        print("STATUS=SOURCE_DOCUMENT_TRACE_FAILED")
        print(f"ERROR=VBA ZIP not found: {vba_zip}")
        return 2

    callers = []
    member_hashes = []
    with zipfile.ZipFile(vba_zip, "r") as archive:
        for member in archive.namelist():
            if Path(member).suffix.lower() not in {".frm", ".bas", ".cls"}:
                continue
            raw = archive.read(member)
            text, encoding = decode_vba(raw)
            member_hashes.append({
                "member": member,
                "sha256": sha256_bytes(raw),
                "encoding": encoding,
            })
            for proc in procedures(text, member):
                finding = analyze_proc(proc)
                if finding:
                    callers.append(finding)

    blockers = []
    if not callers:
        blockers.append({
            "code": "NO_ACTIVE_INPUT_DC_TO_CC_CALLER_FOUND",
            "message": "No active caller was found in the supplied VBA ZIP.",
        })

    wdDoc2_mentions = []
    for caller in callers:
        for window in caller["call_windows"]:
            call_code = window["call_code"]
            if "wdDoc2" in call_code:
                wdDoc2_mentions.append({
                    "member": caller["member"],
                    "procedure": caller["procedure"],
                    "call_line": window["call_line"],
                    "call_code": call_code,
                    "nearby_document_open_actions": window["document_open_actions"],
                    "nearby_object_assignments": window["object_assignments"],
                    "nearby_string_literals": window["string_literals"],
                })

    if callers and not wdDoc2_mentions:
        blockers.append({
            "code": "CALLER_FOUND_BUT_SOURCE_DOCUMENT_ARGUMENT_NOT_IDENTIFIED",
            "message": (
                "Input_DC_to_CC caller(s) exist, but the captured call window does not identify "
                "wdDoc2 directly. Review argument position and nearby object assignments."
            ),
        })

    report = {
        "schema_version": "c5e-certificate-detail-source-document-trace/v1",
        "status": "SOURCE_DOCUMENT_CALL_PATH_CAPTURED" if not blockers else "SOURCE_DOCUMENT_TRACE_INCOMPLETE",
        "source_zip": str(vba_zip),
        "source_zip_sha256": sha256_bytes(vba_zip.read_bytes()),
        "callers": callers,
        "wdDoc2_mentions": wdDoc2_mentions,
        "blockers": blockers,
        "invariants": {
            "commented_calls_used": False,
            "source_files_modified": False,
            "unkeyed_entries_used": False,
            "compact_summary_used": False,
        },
        "next_step": (
            "Identify the exact Word file opened/assigned as the second Input_DC_to_CC document "
            "argument. Capture that file's bookmark fragments and SHA256 before implementing "
            "formatted-fragment rendering."
        ),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    for index, caller in enumerate(callers, start=1):
        fixture = FIXTURE_DIR / f"{index:02d}_{Path(caller['member']).stem}_{caller['procedure']}.json"
        fixture.write_text(json.dumps(caller, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"STATUS={report['status']}")
    print(f"BLOCKERS={len(blockers)}")
    print(f"CALLERS={len(callers)}")
    print(f"WDDOC2_MENTIONS={len(wdDoc2_mentions)}")
    print(f"OUTPUT={OUTPUT}")
    print(f"FIXTURE_DIR={FIXTURE_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
