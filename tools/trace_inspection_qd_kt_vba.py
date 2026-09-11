from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ZIP = ROOT / "legacy" / "GXP-VBA code.zip"
DEFAULT_OUTPUT = ROOT / "artifacts" / "legacy_audit" / "inspection_qd_kt_vba_trace.json"
EXPECTED_SHA256 = "6227fb0a6b3d74fa0f4cc655b94b021a40d65a508c2f2eefc62f1724c7b89ff7"
FIELDS = [
    "Daychuyen", "Diachicoso", "Diadiem", "Diadiemx", "Fulldate", "GhPviCN", "GhPviDG",
    "GioiHanPvi", "HsDK", "MoiDel", "NgayKT", "NgayKTx", "NgaynopHsDK", "NgayQDKT",
    "PVCepha", "PVDuoclieu", "PVNangmem", "PVNhomat", "PVPeni", "PVSuibot", "PVTiem",
    "QDKT", "TaiDel", "Tencoso", "ThoigianKT", "TieuchuanKT", "TT", "TT1", "TT2",
    "TT3Del", "TT3x", "TT_SYTx", "TT_VKNx", "VKN", "VKNx",
]
PROC_RE = re.compile(r"^\s*(?:(?:Public|Private|Friend)\s+)?(?:Sub|Function)\s+([A-Za-z_]\w*)\b", re.I)
END_RE = re.compile(r"^\s*End\s+(?:Sub|Function)\s*$", re.I)
OP_START_RE = re.compile(r"(?i)(Replace_Bookmark|Delete_Bookmark)\b")
RANGE_DELETE_RE = re.compile(r'(?i)(\w+)\.Bookmarks\(\"([^\"]+)\"\)\.Range.*?\.Delete\b')


def _active(line: str) -> str:
    quoted = False
    out: list[str] = []
    for char in line:
        if char == '"':
            quoted = not quoted
        if char == "'" and not quoted:
            break
        out.append(char)
    return "".join(out).strip()


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1258", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


def _procedures(text: str) -> dict[str, dict[str, object]]:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").splitlines()
    result: dict[str, list[dict[str, object]]] = {}
    index = 0
    while index < len(lines):
        match = PROC_RE.match(_active(lines[index]))
        if not match:
            index += 1
            continue
        name = match.group(1)
        end = index + 1
        while end < len(lines) and not END_RE.match(_active(lines[end])):
            end += 1
        if end >= len(lines):
            raise RuntimeError(f"unterminated procedure: {name}")
        result.setdefault(name.lower(), []).append({"name": name, "start_line": index + 1, "end_line": end + 1, "lines": lines[index:end + 1], "offset": index})
        index = end + 1
    duplicates = {name: rows for name, rows in result.items() if len(rows) > 1}
    if duplicates:
        details = "; ".join(
            f"{rows[0]['name']} ranges=" + ",".join(f"{row['start_line']}-{row['end_line']}" for row in rows) + f" count={len(rows)}"
            for rows in duplicates.values()
        )
        raise RuntimeError(f"duplicate procedure in module: {details}")
    return {name: rows[0] for name, rows in result.items()}


def _condition_status(condition: str) -> str:
    normalized = re.sub(r"\s+", " ", condition.strip()).lower()
    match = re.fullmatch(r"(?:not\s*\(\s*)?i\s*(=|<>|<|<=|>|>=)\s*(\d+)(?:\s*\))?", normalized)
    if not match:
        return "CONDITIONAL_I2"
    operator, value = match.group(1), int(match.group(2))
    actual = 2
    result = {"=": actual == value, "<>": actual != value, "<": actual < value, "<=": actual <= value, ">": actual > value, ">=": actual >= value}[operator]
    if normalized.startswith("not"):
        result = not result
    return "TRUE_I2" if result else "FALSE_I2"


def _split_argument(text: str) -> tuple[str, str]:
    quoted = False
    depth = 0
    for index, char in enumerate(text):
        if char == '"':
            quoted = not quoted
        elif not quoted and char == "(":
            depth += 1
        elif not quoted and char == ")":
            depth -= 1
        elif not quoted and depth == 0 and char == ",":
            return text[:index].strip(), text[index + 1:].strip()
    return text.strip(), ""


def _branch_context(lines: list[str], index: int) -> tuple[str, str]:
    stack: list[dict[str, object]] = []
    for row in lines[:index + 1]:
        code = _active(row)
        if not code:
            continue
        if re.match(r"(?i)^if\b.*\bthen\s*$", code):
            predicate = code[2:-4].strip()
            stack.append({"alternatives": [predicate], "effective": predicate})
        elif re.match(r"(?i)^elseif\b.*\bthen\s*$", code):
            if stack:
                frame = stack[-1]
                predicate = code[6:-4].strip()
                frame["effective"] = " AND ".join([*(f"NOT({item})" for item in frame["alternatives"]), predicate])
                frame["alternatives"].append(predicate)
        elif re.match(r"(?i)^else\s*(?::.*)?$", code):
            if stack:
                frame = stack[-1]
                frame["effective"] = " AND ".join(f"NOT({item})" for item in frame["alternatives"])
        elif re.match(r"(?i)^end\s+if\b", code):
            if stack:
                stack.pop()
    predicates = " AND ".join(str(frame["effective"]) for frame in stack) if stack else "COMMON"
    statuses = []
    for frame in stack:
        for atom in str(frame["effective"]).split(" AND "):
            statuses.append(_condition_status(atom))
    if any(item == "FALSE_I2" for item in statuses):
        return predicates, "UNREACHABLE_I2"
    if any(item == "CONDITIONAL_I2" for item in statuses):
        return predicates, "CONDITIONAL_I2"
    return predicates, "REACHABLE_I2"


def _operations(proc: dict[str, object]) -> list[dict[str, object]]:
    lines = proc["lines"]
    offset = int(proc["offset"])
    result: list[dict[str, object]] = []
    for index, raw in enumerate(lines):
        code = _active(raw)
        if not code:
            continue
        inline = re.match(r"(?i)^if\b(.+?)\bthen\s+(.+)$", code)
        candidates = [code]
        inline_condition = None
        if inline:
            inline_condition, candidates = inline.group(1).strip(), [inline.group(2).strip()]
        for candidate in candidates:
            starts = list(OP_START_RE.finditer(candidate))
            for start_index, start in enumerate(starts):
                end = starts[start_index + 1].start() if start_index + 1 < len(starts) else len(candidate)
                statement = candidate[start.end():end].strip()
                argument = re.match(r"\w+\s*,\s*(.+)$", statement)
                if not argument:
                    continue
                bookmark_expression, value_expression = _split_argument(argument.group(1))
                quoted = re.findall(r'\"([^\"]+)\"', bookmark_expression)
                physical = quoted[0] if quoted else bookmark_expression.split(",", 1)[0].strip()
                if len(quoted) > 1 and "&" in bookmark_expression:
                    physical = "".join(quoted)
                condition, reachability = _branch_context(lines, index)
                if inline_condition:
                    condition = inline_condition if condition == "COMMON" else condition + " AND " + inline_condition
                    inline_status = _condition_status(inline_condition)
                    if inline_status == "FALSE_I2":
                        reachability = "UNREACHABLE_I2"
                    elif reachability != "UNREACHABLE_I2" and reachability != "CONDITIONAL_I2":
                        reachability = inline_status.replace("TRUE", "REACHABLE")
                result.append({
                    "physical_bookmark": physical,
                    "physical_bookmark_expression": bookmark_expression,
                    "operation_type": "WRITE" if start.group(1).lower().startswith("replace") else "DELETE",
                    "line": offset + index + 1,
                    "expression": value_expression,
                    "branch_predicates": condition,
                    "reachability_i2": reachability,
                })
            range_match = RANGE_DELETE_RE.search(candidate)
            if range_match:
                condition, reachability = _branch_context(lines, index)
                result.append({
                    "physical_bookmark": range_match.group(2), "operation_type": "RANGE_DELETE",
                    "line": offset + index + 1, "expression": candidate,
                    "branch_predicates": condition, "reachability_i2": reachability,
                })
    return result


def _require(procs: dict[str, dict[str, object]], name: str, member: str) -> dict[str, object]:
    key = name.lower()
    if key not in procs:
        raise RuntimeError(f"required procedure missing: {member}.{name}")
    return procs[key]


def _find_unique(proc: dict[str, object], pattern: str, label: str) -> dict[str, object]:
    matches = []
    for index, raw in enumerate(proc["lines"]):
        code = _active(raw)
        if re.search(pattern, code, re.I):
            matches.append({"line": int(proc["offset"]) + index + 1, "code": code})
    if len(matches) != 1:
        raise RuntimeError(f"expected exactly one {label}, found {len(matches)}")
    return matches[0]


def build_trace(vba_zip: Path, expected_sha256: str | None = EXPECTED_SHA256) -> dict[str, object]:
    if not vba_zip.is_file():
        raise FileNotFoundError(f"VBA ZIP not found: {vba_zip}")
    source_sha = hashlib.sha256(vba_zip.read_bytes()).hexdigest()
    if expected_sha256 and source_sha.lower() != expected_sha256.lower():
        raise RuntimeError(f"VBA ZIP SHA256 mismatch: expected {expected_sha256}, got {source_sha}")
    with zipfile.ZipFile(vba_zip) as archive:
        module = _decode(archive.read("Module1.bas"))
        record = _decode(archive.read("RecordForm.frm"))
    module_procs, record_procs = _procedures(module), _procedures(record)
    tao = _require(module_procs, "TaoQDKT_KHKT", "Module1.bas")
    create = _require(record_procs, "CreateFile", "RecordForm.frm")
    get_tpl = _require(record_procs, "Get_Tpl", "RecordForm.frm")
    builder = _require(record_procs, "Tao_QDKT_KHKT_BBKT", "RecordForm.frm")
    create_call = _find_unique(tao, r"\.CreateFile\s*\(?.*,\s*2\s*,", "i=2 CreateFile call")
    get_tpl_call = _find_unique(create, r"\bGet_Tpl\s*\(", "Get_Tpl call")
    builder_call = _find_unique(create, r"\bTao_QDKT_KHKT_BBKT\b", "builder call")
    tpl_lines = get_tpl["lines"]
    case_index = next((i for i, row in enumerate(tpl_lines) if re.search(r"^\s*Case\s+2(?:\s|$)", _active(row), re.I)), None)
    if case_index is None:
        raise RuntimeError("Get_Tpl Case 2 branch missing")
    case_end = next((
        i for i, row in enumerate(tpl_lines[case_index + 1:], case_index + 1)
        if re.match(r"^\s*(?:Case\b|End\s+Select\b)", _active(row), re.I)
    ), len(tpl_lines))
    tpl_assignments = [
        {"line": int(get_tpl["offset"]) + i + 1, "code": _active(row)}
        for i, row in enumerate(tpl_lines[case_index + 1:case_end], case_index + 1)
        if re.search(r"^\s*tpl\s*=", _active(row), re.I)
    ]
    if len(tpl_assignments) != 1:
        raise RuntimeError(f"Get_Tpl Case 2 requires exactly one tpl assignment, found {len(tpl_assignments)}")
    tpl_assignment = tpl_assignments[0]
    physical = _operations(builder)
    reachable = [op for op in physical if op["reachability_i2"] != "UNREACHABLE_I2"]
    dispositions: dict[str, dict[str, object]] = {}
    for field in FIELDS:
        exact = [op for op in reachable if op["physical_bookmark"].lower() == field.lower()]
        related = [op for op in reachable if op["physical_bookmark"].lower().startswith(field.lower())]
        if exact:
            all_delete = all(op["operation_type"] in {"DELETE", "RANGE_DELETE"} for op in exact)
            conditional = any(op["reachability_i2"] != "REACHABLE_I2" for op in exact)
            if all_delete:
                status = "PROVEN_CONDITIONAL_DELETE_I2" if conditional else "PROVEN_DELETE_I2"
            else:
                status = "PROVEN_CONDITIONAL_WRITE_I2" if conditional else "PROVEN_WRITE_I2"
            dispositions[field] = {"status": status, "physical_operations": exact}
        elif related or (field in {"TT1", "TT2"} and any(op["physical_bookmark"].lower() == "ttx" for op in reachable)):
            dispositions[field] = {"status": "UNRESOLVED_MAPPING", "physical_operations": related}
        else:
            dispositions[field] = {"status": "PROVEN_NO_ACTIVE_OPERATION_I2", "physical_operations": []}
    return {
        "schema_version": "inspection-qd-kt-vba-trace/v2", "status": "SOURCE_QD_KT_I2_CAPTURED",
        "source_zip": "legacy/GXP-VBA code.zip", "source_zip_sha256": source_sha,
        "procedures": {
            "Module1.TaoQDKT_KHKT": {"start_line": tao["start_line"], "end_line": tao["end_line"], "i2_create_file_call": create_call},
            "RecordForm.CreateFile": {"start_line": create["start_line"], "end_line": create["end_line"], "get_tpl_call": get_tpl_call, "builder_call": builder_call},
            "RecordForm.Get_Tpl": {"start_line": get_tpl["start_line"], "end_line": get_tpl["end_line"], "i2_case": tpl_assignment},
            "RecordForm.Tao_QDKT_KHKT_BBKT": {"start_line": builder["start_line"], "end_line": builder["end_line"]},
        },
        "call_chain": ["Module1.TaoQDKT_KHKT", "RecordForm.CreateFile(i=2)", "RecordForm.Get_Tpl(i=2)", "RecordForm.Tao_QDKT_KHKT_BBKT(i=2)"],
        "physical_bookmark_operations": physical,
        "logical_field_disposition": dispositions,
        "invariants": {"commented_code_used": False, "source_modified": False, "templates_modified": False, "runtime_contract_changed": False},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture source-derived INSPECTION_QD_KT VBA i=2 evidence.")
    parser.add_argument("--vba-zip", type=Path, default=DEFAULT_ZIP)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--expected-sha256", default=EXPECTED_SHA256)
    args = parser.parse_args()
    try:
        report = build_trace(args.vba_zip.resolve(), args.expected_sha256)
    except (FileNotFoundError, KeyError, RuntimeError, zipfile.BadZipFile) as exc:
        print("STATUS=INSPECTION_QD_KT_VBA_TRACE_FAILED")
        print(f"ERROR={exc}")
        return 2
    args.output.resolve().parent.mkdir(parents=True, exist_ok=True)
    args.output.resolve().write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    counts: dict[str, int] = {}
    for value in report["logical_field_disposition"].values():
        counts[value["status"]] = counts.get(value["status"], 0) + 1
    print(f"STATUS={report['status']}")
    print(f"SOURCE_SHA256={report['source_zip_sha256']}")
    print("CALL_CHAIN=" + " -> ".join(report["call_chain"]))
    print(f"PHYSICAL_OPERATIONS={len(report['physical_bookmark_operations'])}")
    print("CLASSIFICATION_COUNTS=" + json.dumps(counts, sort_keys=True))
    print(f"OUTPUT={args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
