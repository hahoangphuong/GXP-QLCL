from __future__ import annotations

"""Read-only source audit for INSPECTION_KE_HOACH_KT (legacy builder branch i=3).

This tool deliberately stops at source evidence. It does not assign modern
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
    _branch_context,
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
    "Fulldate",
)
REQUIRED_SECTION_SUPPRESSIONS = (
    "PVCepha",
    "PVPeni",
    "PVDuoclieu",
    "PVTiem",
    "PVNhomat",
    "PVNangmem",
    "PVSuibot",
)


def _read_sources(vba_zip: Path) -> dict[str, list[str]]:
    with zipfile.ZipFile(vba_zip) as archive:
        return {
            name: _decode(archive.read(name))
            .replace("\r\n", "\n")
            .replace("\r", "\n")
            .splitlines()
            for name in archive.namelist()
        }


def _find_active_lines(
    lines: list[str],
    *,
    pattern: str,
    filename: str,
) -> list[dict[str, object]]:
    compiled = re.compile(pattern, re.I)
    matches: list[dict[str, object]] = []
    for index, raw in enumerate(lines, 1):
        code = _active(raw)
        if code and compiled.search(code):
            matches.append({"file": filename, "line": index, "code": code})
    return matches


def _find_unique_active_line(
    lines: list[str],
    *,
    pattern: str,
    filename: str,
    label: str,
) -> dict[str, object]:
    matches = _find_active_lines(lines, pattern=pattern, filename=filename)
    if len(matches) != 1:
        raise RuntimeError(f"expected exactly one {label}, found {len(matches)}")
    return matches[0]


def _find_proc_lines(
    proc: dict[str, object],
    *,
    pattern: str,
) -> list[dict[str, object]]:
    matches: list[dict[str, object]] = []
    compiled = re.compile(pattern, re.I)
    for index, raw in enumerate(proc["lines"]):
        code = _active(raw)
        if code and compiled.search(code):
            matches.append(
                {
                    "line": int(proc["offset"]) + index + 1,
                    "code": code,
                }
            )
    return matches


def _require_proc_lines(
    proc: dict[str, object],
    *,
    pattern: str,
    label: str,
    minimum: int = 1,
    target_i: int | None = None,
) -> list[dict[str, object]]:
    compiled = re.compile(pattern, re.I)
    matches: list[dict[str, object]] = []
    for index, raw in enumerate(proc["lines"]):
        code = _active(raw)
        if not code or not compiled.search(code):
            continue
        if target_i is not None:
            _, reachability = _branch_context(
                proc["lines"],
                index,
                target_i=target_i,
            )
            if reachability == f"UNREACHABLE_I{target_i}":
                continue
        matches.append(
            {
                "line": int(proc["offset"]) + index + 1,
                "code": code,
            }
        )
    if len(matches) < minimum:
        raise RuntimeError(
            f"expected at least {minimum} active {label} source line(s), "
            f"found {len(matches)}"
        )
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
    operation_types: set[str],
) -> list[dict[str, object]]:
    return [
        item
        for item in operations
        if str(item.get("physical_bookmark", "")).lower() == bookmark.lower()
        and str(item.get("operation_type", "")) in operation_types
        and item.get(REACHABILITY_KEY) != "UNREACHABLE_I3"
    ]


def _require_write_sequence(
    operations: list[dict[str, object]],
    *,
    bookmark: str,
) -> dict[str, object]:
    matches = _active_operations_for(
        operations,
        bookmark=bookmark,
        operation_types={"WRITE"},
    )
    if not matches:
        raise RuntimeError(
            f"Expected at least one active i=3 WRITE operation for {bookmark}, found 0"
        )
    return {
        "write_sequence": matches,
        "effective_write": matches[-1],
    }


def _require_section_suppression(
    operations: list[dict[str, object]],
    *,
    bookmark: str,
) -> dict[str, object]:
    # Legacy source uses Delete_Bookmark for these sections. RANGE_DELETE is
    # accepted as the equivalent physical operation because the shared parser
    # also recognizes direct Word Range.Delete syntax.
    matches = _active_operations_for(
        operations,
        bookmark=bookmark,
        operation_types={"DELETE", "RANGE_DELETE"},
    )
    if len(matches) != 1:
        raise RuntimeError(
            "Expected exactly one active i=3 section suppression for "
            f"{bookmark}, found {len(matches)}"
        )
    return matches[0]


def _build_source_provenance(
    *,
    make_record: dict[str, object],
    prepare: dict[str, object],
    get_site: dict[str, object],
    get_inspection: dict[str, object],
    btn_file: dict[str, object],
) -> dict[str, object]:
    prepare_call = _find_unique(
        make_record,
        r"\bPrepareRecordForm\b",
        "Make_RecordKT PrepareRecordForm call",
    )
    site_call = _find_unique(
        prepare,
        r"\bGetTT_CsCty\b",
        "PrepareRecordForm GetTT_CsCty call",
    )
    inspection_call = _find_unique(
        prepare,
        r"\bGetTT_Ktra\b",
        "PrepareRecordForm GetTT_Ktra call",
    )

    site_fields = {
        "TenCtydd": _find_unique(
            get_site,
            r"\bTenCtydd\s*=",
            "GetTT_CsCty TenCtydd assignment",
        ),
        "DiachiDD": _find_unique(
            get_site,
            r"\bDiachiDD\s*=",
            "GetTT_CsCty DiachiDD assignment",
        ),
        "Tinhthanh": _find_unique(
            get_site,
            r"\bTinhthanh\s*=",
            "GetTT_CsCty Tinhthanh assignment",
        ),
    }
    inspection_fields = {
        "s_MaHsDk_and_s_NgaynopHsDk": _find_unique(
            get_inspection,
            r"\bs_MaHsDk\s*=.*\bs_NgaynopHsDk\s*=",
            "GetTT_Ktra dossier metadata assignment",
        ),
        "s_LoaiKT": _find_unique(
            get_inspection,
            r"\bs_LoaiKT\s*=",
            "GetTT_Ktra s_LoaiKT assignment",
        ),
        "DaychuyenRaw": _find_unique(
            get_inspection,
            r"\bDaychuyenRaw\s*=",
            "GetTT_Ktra DaychuyenRaw assignment",
        ),
        "DC_cu_and_GHanDC": _find_unique(
            get_inspection,
            r"\bGet_DCx\s*\(\s*DaychuyenRaw\s*,\s*DC_cu\s*,\s*DC_moi\s*,\s*GHanDC\s*\)",
            "GetTT_Ktra Get_DCx scope split",
        ),
        "QDKT_and_NgayQDKT": _require_proc_lines(
            get_inspection,
            pattern=r"\bQDKT\s*=.*\bNgayQDKT\s*=",
            label="GetTT_Ktra QDKT/NgayQDKT branch assignment",
            minimum=2,
        ),
        "TTV": _find_unique(
            get_inspection,
            r"\bIf\s+Len\(ss\)\s*>\s*1\s+Then\s+TTV\s*=",
            "GetTT_Ktra team source assignment",
        ),
    }

    team_transfers = _require_proc_lines(
        btn_file,
        pattern=(
            r"\bTTVForm\.Get_TTV2?\b.*\bTTVdd\s*=\s*TTVForm\.TTVdd"
            r".*\bTTV_VKNdd\s*=\s*TTVForm\.TTV_VKNdd"
            r".*\bTTV_SYTdd\s*=\s*TTVForm\.TTV_SYTdd"
        ),
        label="btnFile TTVForm team transfer",
        minimum=2,
        target_i=TARGET_I,
    )

    return {
        "preparation_chain": {
            "make_record_prepare_call": prepare_call,
            "prepare_site_call": site_call,
            "prepare_inspection_call": inspection_call,
        },
        "site_fields": site_fields,
        "inspection_fields": inspection_fields,
        "team_transfers": team_transfers,
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

    sources = _read_sources(vba_zip)
    if "RecordForm.frm" not in sources:
        raise RuntimeError("required source missing: RecordForm.frm")
    record_lines = sources["RecordForm.frm"]
    with zipfile.ZipFile(vba_zip) as archive:
        record = _decode(archive.read("RecordForm.frm"))
    record_procs = _procedures(record)

    make_record = _require(record_procs, "Make_RecordKT", "RecordForm.frm")
    prepare = _require(record_procs, "PrepareRecordForm", "RecordForm.frm")
    get_site = _require(record_procs, "GetTT_CsCty", "RecordForm.frm")
    get_inspection = _require(record_procs, "GetTT_Ktra", "RecordForm.frm")
    btn_file = _require(record_procs, "btnFile", "RecordForm.frm")
    create = _require(record_procs, "CreateFile", "RecordForm.frm")
    get_tpl = _require(record_procs, "Get_Tpl", "RecordForm.frm")
    builder = _require(
        record_procs,
        "Tao_QDKT_KHKT_BBKT",
        "RecordForm.frm",
    )

    # i=3 is generated by the RecordForm button path. It is not dispatched by
    # Module1.TaoQDKT_KHKT, which owns the i=2 inspection decision path.
    entry_call = _find_unique_active_line(
        record_lines,
        pattern=r"^Private\s+Sub\s+btn3_Click\(\)\s*:\s*btnFile\s+3\s*:",
        filename="RecordForm.frm",
        label="btn3_Click -> btnFile 3 entry call",
    )
    btnfile_create_call = _find_unique(
        btn_file,
        r"\bCreateFile\s*\(\s*s\s*,\s*i\s*,",
        "btnFile CreateFile dispatch",
    )
    get_tpl_call = _find_unique(create, r"\bGet_Tpl\s*\(", "Get_Tpl call")
    builder_call = _find_unique(
        create,
        r"\bTao_QDKT_KHKT_BBKT\b",
        "builder call",
    )
    template_assignment = _case_template_assignment(get_tpl, target_i=TARGET_I)

    source_provenance = _build_source_provenance(
        make_record=make_record,
        prepare=prepare,
        get_site=get_site,
        get_inspection=get_inspection,
        btn_file=btn_file,
    )

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
    required_section_suppressions = {
        name: _require_section_suppression(
            all_operations,
            bookmark=name,
        )
        for name in REQUIRED_SECTION_SUPPRESSIONS
    }

    return {
        "schema_version": "inspection-ke-hoach-kt-i3-source-audit/v2",
        "status": "SOURCE_INSPECTION_KE_HOACH_KT_I3_CAPTURED",
        "source_zip": "legacy/GXP-VBA code.zip",
        "source_zip_sha256": source_sha,
        "target_i": TARGET_I,
        "call_chain": {
            "recordform_entry_call": entry_call,
            "btnfile_create_call": btnfile_create_call,
            "create_get_tpl_call": get_tpl_call,
            "create_builder_call": builder_call,
            "template_assignment": template_assignment,
        },
        "source_provenance": source_provenance,
        "required_writes": required_writes,
        "required_section_suppressions": required_section_suppressions,
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
        "ENTRY_CALL="
        + str(report["call_chain"]["recordform_entry_call"]["code"])
    )
    print(
        "TEMPLATE_ASSIGNMENT="
        + str(report["call_chain"]["template_assignment"]["code"])
    )
    print(
        "SECTION_SUPPRESSION_OPERATIONS="
        + str(len(report["required_section_suppressions"]))
    )
    print(f"OUTPUT={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
