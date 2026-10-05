from __future__ import annotations

"""Read-only source audit for INSPECTION_KE_HOACH_KT (legacy builder branch i=3).

This tool deliberately stops at source evidence.  It does not assign modern
business owners and it never accesses or mutates the database.
"""

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path

from tools.trace_inspection_qd_kt_vba import (
    EXPECTED_SHA256,
    _active,
    _decode,
    _find_unique,
    _operations,
    _procedures,
    _require,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ZIP = ROOT / "legacy" / "GXP-VBA code.zip"
DEFAULT_OUTPUT = (
    ROOT
    / "artifacts"
    / "legacy_audit"
    / "inspection_ke_hoach_kt_i3_source_audit.json"
)

TARGET_I = 3
REACHABILITY_KEY = "reachability_i3"
REQUIRED_WRITES = (
    "Daychuyen",
    "GioiHanPvi",
    "Diachicoso",
    "TieuchuanKT",
)
REQUIRED_SECTION_DELETES = (
    "PVCepha",
    "PVPeni",
    "PVDuoclieu",
    "PVTiem",
    "PVNhomat",
    "PVNangmem",
    "PVSuibot",
)
SOURCE_VARIABLE_PATTERNS = {
    "s_LoaiKT": r"\bs_LoaiKT\s*=",
    "DC_cu": r"\bDC_cu\s*=",
    "GHanDC": r"\bGHanDC\s*=",
    "TTVdd": r"\bTTVdd\s*=",
    "TTV_VKNdd": r"\bTTV_VKNdd\s*=",
    "TTV_SYTdd": r"\bTTV_SYTdd\s*=",
    "TenCtydd": r"\bTenCtydd\s*=",
    "Tinhthanh": r"\bTinhthanh\s*=",
    "DiachiDD": r"\bDiachiDD\s*=",
}


def _read_sources(vba_zip: Path) -> dict[str, list[str]]:
    with zipfile.ZipFile(vba_zip) as archive:
        return {
            name: _decode(archive.read(name))
            .replace("\r\n", "\n")
            .replace("\r", "\n")
            .splitlines()
            for name in archive.namelist()
        }


def _find_active_assignments(
    sources: dict[str, list[str]],
    *,
    pattern: str,
) -> list[dict[str, object]]:
    matches: list[dict[str, object]] = []
    compiled = re.compile(pattern, re.I)
    for filename, lines in sources.items():
        for index, raw in enumerate(lines, 1):
            code = _active(raw)
            if code and compiled.search(code):
                matches.append({"file": filename, "line": index, "code": code})
    return matches


def _case_template_assignment(
    get_tpl: dict[str, object],
    *,
    target_i: int,
) -> dict[str, object]:
    lines = get_tpl["lines"]
    case_index = next(
        (
            i
            for i, row in enumerate(lines)
            if re.search(
                rf"^\s*Case\s+{target_i}(?:\s|$)",
                _active(row),
                re.I,
            )
        ),
        None,
    )
    if case_index is None:
        raise RuntimeError(f"Get_Tpl Case {target_i} branch missing")
    case_end = next(
        (
            i
            for i, row in enumerate(lines[case_index + 1 :], case_index + 1)
            if re.match(r"^\s*(?:Case\b|End\s+Select\b)", _active(row), re.I)
        ),
        len(lines),
    )
    assignments = [
        {
            "line": int(get_tpl["offset"]) + i + 1,
            "code": _active(row),
        }
        for i, row in enumerate(lines[case_index + 1 : case_end], case_index + 1)
        if re.search(r"^\s*tpl\s*=", _active(row), re.I)
    ]
    if len(assignments) != 1:
        raise RuntimeError(
            f"Get_Tpl Case {target_i} requires exactly one tpl assignment, "
            f"found {len(assignments)}"
        )
    return assignments[0]


def _active_operations_for(
    operations: list[dict[str, object]],
    *,
    bookmark: str,
    operation_type: str,
) -> list[dict[str, object]]:
    return [
        item
        for item in operations
        if str(item.get("physical_bookmark", "")).lower() == bookmark.lower()
        and item.get("operation_type") == operation_type
        and item.get(REACHABILITY_KEY) != "UNREACHABLE_I3"
    ]


def _require_operation(
    operations: list[dict[str, object]],
    *,
    bookmark: str,
    operation_type: str,
) -> dict[str, object]:
    matches = _active_operations_for(
        operations,
        bookmark=bookmark,
        operation_type=operation_type,
    )
    if len(matches) != 1:
        raise RuntimeError(
            f"Expected exactly one active i=3 {operation_type} operation for "
            f"{bookmark}, found {len(matches)}"
        )
    return matches[0]


def _require_write_sequence(
    operations: list[dict[str, object]],
    *,
    bookmark: str,
) -> dict[str, object]:
    matches = _active_operations_for(
        operations,
        bookmark=bookmark,
        operation_type="WRITE",
    )
    if not matches:
        raise RuntimeError(
            f"Expected at least one active i=3 WRITE operation for {bookmark}, found 0"
        )
    return {
        "write_sequence": matches,
        "effective_write": matches[-1],
    }


def build_i3_source_audit(
    vba_zip: Path,
    *,
    expected_sha256: str | None = EXPECTED_SHA256,
) -> dict[str, object]:
    if not vba_zip.is_file():
        raise FileNotFoundError(f"VBA ZIP not found: {vba_zip}")
    source_sha = hashlib.sha256(vba_zip.read_bytes()).hexdigest()
    if expected_sha256 and source_sha.lower() != expected_sha256.lower():
        raise RuntimeError(
            f"VBA ZIP SHA256 mismatch: expected {expected_sha256}, got {source_sha}"
        )

    with zipfile.ZipFile(vba_zip) as archive:
        module = _decode(archive.read("Module1.bas"))
        record = _decode(archive.read("RecordForm.frm"))
    module_procs = _procedures(module)
    record_procs = _procedures(record)

    tao = _require(module_procs, "TaoQDKT_KHKT", "Module1.bas")
    create = _require(record_procs, "CreateFile", "RecordForm.frm")
    get_tpl = _require(record_procs, "Get_Tpl", "RecordForm.frm")
    builder = _require(
        record_procs,
        "Tao_QDKT_KHKT_BBKT",
        "RecordForm.frm",
    )

    create_call = _find_unique(
        tao,
        r"\.CreateFile\s*\(?.*,\s*3\s*,",
        "i=3 CreateFile call",
    )
    get_tpl_call = _find_unique(create, r"\bGet_Tpl\s*\(", "Get_Tpl call")
    builder_call = _find_unique(
        create,
        r"\bTao_QDKT_KHKT_BBKT\b",
        "builder call",
    )
    template_assignment = _case_template_assignment(get_tpl, target_i=TARGET_I)

    all_operations = _operations(builder, target_i=TARGET_I)
    active_operations = [
        item
        for item in all_operations
        if item.get(REACHABILITY_KEY) != "UNREACHABLE_I3"
    ]
    required_writes = {
        name: _require_write_sequence(
            all_operations,
            bookmark=name,
        )
        for name in REQUIRED_WRITES
    }
    required_section_deletes = {
        name: _require_operation(
            all_operations,
            bookmark=name,
            operation_type="RANGE_DELETE",
        )
        for name in REQUIRED_SECTION_DELETES
    }

    sources = _read_sources(vba_zip)
    assignments = {
        variable: _find_active_assignments(sources, pattern=pattern)
        for variable, pattern in SOURCE_VARIABLE_PATTERNS.items()
    }
    if not assignments["s_LoaiKT"]:
        raise RuntimeError(
            "Active source assignment for s_LoaiKT was not found; "
            "TieuchuanKT ownership remains untraceable."
        )

    return {
        "schema_version": "inspection-ke-hoach-kt-i3-source-audit/v1",
        "status": "SOURCE_INSPECTION_KE_HOACH_KT_I3_CAPTURED",
        "source_zip": "legacy/GXP-VBA code.zip",
        "source_zip_sha256": source_sha,
        "target_i": TARGET_I,
        "call_chain": {
            "module_create_call": create_call,
            "create_get_tpl_call": get_tpl_call,
            "create_builder_call": builder_call,
            "template_assignment": template_assignment,
        },
        "required_writes": required_writes,
        "required_section_deletes": required_section_deletes,
        "source_assignments": assignments,
        "active_physical_operations": active_operations,
        "invariants": {
            "database_accessed": False,
            "database_mutated": False,
            "source_modified": False,
            "template_modified": False,
            "modern_owner_inferred": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Capture source-derived i=3 evidence for INSPECTION_KE_HOACH_KT."
        )
    )
    parser.add_argument("--vba-zip", type=Path, default=DEFAULT_ZIP)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--expected-sha256", default=EXPECTED_SHA256)
    args = parser.parse_args()
    try:
        report = build_i3_source_audit(
            args.vba_zip.resolve(),
            expected_sha256=args.expected_sha256,
        )
        output = args.output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except (
        FileNotFoundError,
        KeyError,
        RuntimeError,
        zipfile.BadZipFile,
    ) as exc:
        print("STATUS=INSPECTION_KE_HOACH_KT_I3_SOURCE_AUDIT_FAILED")
        print(f"ERROR={exc}")
        return 2

    print(f"STATUS={report['status']}")
    print(f"SOURCE_SHA256={report['source_zip_sha256']}")
    print(
        "TEMPLATE_ASSIGNMENT="
        + str(report["call_chain"]["template_assignment"]["code"])
    )
    print(
        "S_LOAIKT_ASSIGNMENTS="
        + str(len(report["source_assignments"]["s_LoaiKT"]))
    )
    print(
        "SECTION_DELETE_OPERATIONS="
        + str(len(report["required_section_deletes"]))
    )
    print(f"OUTPUT={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
