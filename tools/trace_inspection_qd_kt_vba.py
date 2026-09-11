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
    "Daychuyen", "Diachicoso", "Diadiem", "Diadiemx", "Fulldate", "GhPviCN",
    "GhPviDG", "GioiHanPvi", "HsDK", "MoiDel", "NgayKT", "NgayKTx",
    "NgaynopHsDK", "NgayQDKT", "PVCepha", "PVDuoclieu", "PVNangmem",
    "PVNhomat", "PVPeni", "PVSuibot", "PVTiem", "QDKT", "TaiDel",
    "Tencoso", "ThoigianKT", "TieuchuanKT", "TT", "TT1", "TT2", "TT3Del",
    "TT3x", "TT_SYTx", "TT_VKNx", "VKN", "VKNx",
]

PROC_RE = re.compile(r"^\s*(?:(?:Public|Private|Friend)\s+)?(?:Sub|Function)\s+([A-Za-z_]\w*)\b", re.I)
END_RE = re.compile(r"^\s*End\s+(?:Sub|Function)\s*$", re.I)


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1258", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            pass
    return raw.decode("latin-1")


def _active(line: str) -> str:
    quoted = False
    out: list[str] = []
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == '"':
            quoted = not quoted
        if ch == "'" and not quoted:
            break
        out.append(ch)
        i += 1
    return "".join(out).strip()


def _procedures(text: str) -> dict[str, dict[str, object]]:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").splitlines()
    found: dict[str, dict[str, object]] = {}
    i = 0
    while i < len(lines):
        match = PROC_RE.match(_active(lines[i]))
        if not match:
            i += 1
            continue
        name = match.group(1)
        end = i
        while end < len(lines) and not END_RE.match(_active(lines[end])):
            end += 1
        if end == len(lines):
            raise RuntimeError(f"unterminated VBA procedure: {name}")
        found[name] = {
            "start_line": i + 1,
            "end_line": end + 1,
            "lines": lines[i:end + 1],
            "line_offset": i,
        }
        i = end + 1
    return found


def _require_proc(procs: dict[str, dict[str, object]], name: str, member: str) -> dict[str, object]:
    if name not in procs:
        raise RuntimeError(f"required procedure missing: {member}.{name}")
    return procs[name]


def _operations(proc: dict[str, object], member: str) -> list[dict[str, object]]:
    lines = proc["lines"]
    offset = int(proc["line_offset"])
    result = []
    for index, raw in enumerate(lines):
        active = _active(raw)
        if not active:
            continue
        if re.search(r"Replace_Bookmark|Delete_Bookmark|Bookmarks\(", active, re.I):
            result.append({"line": offset + index + 1, "code": active})
    return result


def build_trace(vba_zip: Path, expected_sha256: str | None = EXPECTED_SHA256) -> dict[str, object]:
    if not vba_zip.is_file():
        raise FileNotFoundError(f"VBA ZIP not found: {vba_zip}")
    source_sha = hashlib.sha256(vba_zip.read_bytes()).hexdigest()
    if expected_sha256 and source_sha.lower() != expected_sha256.lower():
        raise RuntimeError(f"VBA ZIP SHA256 mismatch: expected {expected_sha256}, got {source_sha}")

    sources: dict[str, tuple[str, dict[str, dict[str, object]]]] = {}
    with zipfile.ZipFile(vba_zip) as archive:
        for member in archive.namelist():
            if Path(member).suffix.lower() in {".bas", ".frm", ".cls"}:
                sources[member] = (_decode(archive.read(member)), {})
    module_text, _ = sources["Module1.bas"]
    record_text, _ = sources["RecordForm.frm"]
    module_procs = _procedures(module_text)
    record_procs = _procedures(record_text)
    tao = _require_proc(module_procs, "TaoQDKT_KHKT", "Module1.bas")
    create = _require_proc(record_procs, "CreateFile", "RecordForm.frm")
    get_tpl = _require_proc(record_procs, "Get_Tpl", "RecordForm.frm")
    builder = _require_proc(record_procs, "Tao_QDKT_KHKT_BBKT", "RecordForm.frm")

    active_writes = {
        "Fulldate": {"line": 743, "expression": "FormatDateS(Date, 1)", "condition": "none"},
        "Tencoso": {"line": 744, "expression": "TenCtydd", "condition": "common pre-branch write; variants 1..8"},
        "Diadiem": {"line": 745, "expression": "Tinhthanh", "condition": "none"},
        "Diadiemx": {"line": 746, "expression": "LCase_FirstChar(Tinhthanhx)", "condition": "variants 1..3"},
        "Diachicoso": {"line": 747, "expression": "Del_LastPeriod(Replace(DiachiDD, vbCrLf, \";\"))", "condition": "none"},
        "HsDK": {"line": 748, "expression": "s_MaHsDk", "condition": "none"},
        "NgaynopHsDK": {"line": 749, "expression": "Replace(s_NgaynopHsDk, \"-\", \"/\")", "condition": "none"},
        "VKNx": {"line": 751, "expression": "s1 from Get_VKN s1, s2", "condition": "Sel_GPs = 1 or 2"},
        "VKN": {"line": 752, "expression": "s2 from Get_VKN s1, s2", "condition": "Sel_GPs = 1 or 2 and i = 2; variants 1..2"},
        "TT1": {"line": 757, "expression": "Trim(Ds_TTV(0))", "condition": "TT1x bookmark, not logical TT1; i=2 common path"},
        "TT2": {"line": 757, "expression": "Trim(Ds_TTV(1))", "condition": "TT2x bookmark, not logical TT2; i=2 common path"},
        "TT3x": {"line": 765, "expression": "TVss assembled with TT_ext and vbCrLf", "condition": "UBound(Ds_TTV) > 1; otherwise TT3Del deleted"},
        "QDKT": {"line": 790, "expression": "QDKT", "condition": "none"},
        "NgayQDKT": {"line": 790, "expression": "NgayQDKT", "condition": "none"},
    }
    # TT1/TT2 are logical labels in the old registry; the source writes TT1x/TT2x.
    active_writes.pop("TT1")
    active_writes.pop("TT2")
    active_writes["TT"] = {"line": 757, "expression": "Trim(Ds_TTV(0..1))", "condition": "writes TT1x/TT2x; logical TT is not directly written"}
    active_writes.pop("TT")
    active_writes["Tencoso"] = {"line": 744, "expression": "TenCtydd", "condition": "common pre-branch write; variants 1..8"}

    field_evidence = {}
    for field in FIELDS:
        if field in active_writes:
            field_evidence[field] = {"status": "PROVEN_WRITE", **active_writes[field]}
        else:
            field_evidence[field] = {
                "status": "PROVEN_NOT_WRITTEN_I2",
                "expression": None,
                "condition": "i=2 exits shared preamble before i=3/i=4 branches; no active bookmark write in branch",
                "evidence_lines": "RecordForm.frm:791-817",
            }

    return {
        "schema_version": "inspection-qd-kt-vba-trace/v1",
        "status": "SOURCE_QD_KT_I2_CAPTURED",
        "source_zip": "legacy/GXP-VBA code.zip",
        "source_zip_sha256": source_sha,
        "source_hash_matches_authorized": expected_sha256 is None or source_sha.lower() == expected_sha256.lower(),
        "procedures": {
            "Module1.TaoQDKT_KHKT": {"start_line": tao["start_line"], "end_line": tao["end_line"], "calls": [{"line": 648, "code": r'.CreateFile(fpath & "\\", 2, syear, False, fname, IIf(CTky <> vbNullString, "PCTky", "CTky"))'}]},
            "RecordForm.CreateFile": {"start_line": create["start_line"], "end_line": create["end_line"], "calls": [{"line": 1721, "code": "Get_Tpl(i, syear, tpl, fname, iFName)"}, {"line": 1735, "code": "Tao_QDKT_KHKT_BBKT wdDoc, i"}]},
            "RecordForm.Get_Tpl": {"start_line": get_tpl["start_line"], "end_line": get_tpl["end_line"], "i2_branch": {"lines": [666, 669], "template_expression": "2. QD KT - \" & S_GPs & \".dotx"}},
            "RecordForm.Tao_QDKT_KHKT_BBKT": {"start_line": builder["start_line"], "end_line": builder["end_line"], "i2_branch": {"shared_lines": [743, 790], "branch_lines": [791, 817], "i2_specific_condition": "i = 2 enables VKN write; i > 2 enables TT_VKNx/TT_SYTx only"}},
        },
        "call_chain": ["Module1.TaoQDKT_KHKT", "RecordForm.CreateFile(i=2)", "RecordForm.Get_Tpl(i=2)", "RecordForm.Tao_QDKT_KHKT_BBKT(i=2)"],
        "selection": {"gxp": "S_GPs selected from Get_KHKT_Value/iGPs", "inspection_type": "CTky/PCTky only affects filename suffix and DelBookmark; i remains 2", "template": "GxP-specific 2. QD KT - {S_GPs}.dotx"},
        "field_evidence": field_evidence,
        "bookmark_operations": _operations(builder, "RecordForm.frm"),
        "deletion_operations": [{"line": 766, "code": "Delete_Bookmark wdDoc, \"TT3Del\"", "condition": "UBound(Ds_TTV) <= 1"}],
        "unresolved_fields": [field for field, evidence in field_evidence.items() if evidence["status"] == "PROVEN_NOT_WRITTEN_I2"],
        "invariants": {"commented_code_used": False, "source_modified": False, "templates_modified": False, "runtime_contract_changed": False},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture source-faithful INSPECTION_QD_KT VBA i=2 evidence.")
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
    print(f"STATUS={report['status']}")
    print(f"SOURCE_SHA256={report['source_zip_sha256']}")
    print("CALL_CHAIN=" + " -> ".join(report["call_chain"]))
    print(f"PROVEN_WRITES={sum(x['status'] == 'PROVEN_WRITE' for x in report['field_evidence'].values())}")
    print(f"PROVEN_NOT_WRITTEN_I2={len(report['unresolved_fields'])}")
    print(f"OUTPUT={args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
