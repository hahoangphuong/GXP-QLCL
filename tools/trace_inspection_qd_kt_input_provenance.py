from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path

from tools.trace_inspection_qd_kt_vba import EXPECTED_SHA256, _active, _decode, build_trace

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ZIP = ROOT / "legacy" / "GXP-VBA code.zip"
DEFAULT_TRACE = ROOT / "artifacts" / "legacy_audit" / "inspection_qd_kt_vba_trace.json"
DEFAULT_OUTPUT = ROOT / "artifacts" / "legacy_audit" / "inspection_qd_kt_input_provenance.json"


TARGETS = {
    "Fulldate": {
        "variables": ["Date"], "owner": "deterministic generated value", "classification": "OWNER_BLOCKED",
        "blocker": "legacy uses workstation Date; no persisted QĐKT generation-date contract is proven",
        "source": "deterministic generated value: current VBA workstation date",
    },
    "Tencoso": {
        "variables": ["TenCtydd"], "owner": "Site.site_name", "classification": "OWNER_PARTIAL",
        "blocker": "selected planning row and db_cso both feed the variable; exact modern selection provenance is not proven",
        "source": "planning row cell 4; fallback/alternate db_cso site row",
    },
    "Diadiem": {
        "variables": ["Tinhthanh"], "owner": "Site.province_name", "classification": "OWNER_BLOCKED",
        "blocker": "active i=2 path uses the selected planning row cell 10 and applies province cleanup; no exact modern source is proven",
        "source": "selected planning row cell 10, with province-name normalization",
    },
    "Diadiemx": {
        "variables": ["Tinhthanhx"], "owner": "Site.province_name", "classification": "OWNER_BLOCKED",
        "blocker": "Dia_danh/Dia_danh_x lookup and fallback semantics have no proven modern owner",
        "source": "Tinhthanh plus Dia_danh/Dia_danh_x named-range lookup",
    },
    "Diachicoso": {
        "variables": ["DiachiDD"], "owner": "Site.site_address", "classification": "OWNER_BLOCKED",
        "blocker": "active i=2 source is planning row cell 11; site-address equivalence is not proven",
        "source": "selected planning row cell 11, then CRLF-to-semicolon and final-period normalization",
    },
    "HsDK": {
        "variables": ["s_MaHsDk"], "owner": "CaseApplication.dossier_code", "classification": "OWNER_PARTIAL",
        "blocker": "db.ktra column identity is source-proven, but the modern dossier-code equivalence is not fully reconciled",
        "source": "db.ktra row, ColDB_HSDK_Ktra + 1",
    },
    "NgaynopHsDK": {
        "variables": ["s_NgaynopHsDk"], "owner": "CaseApplication.submitted_on", "classification": "OWNER_PARTIAL",
        "blocker": "db.ktra source date is proven, but exact submitted/received semantic equivalence is not closed",
        "source": "db.ktra row, ColDB_HSDK_Ktra",
    },
    "QDKT": {
        "variables": ["QDKT"], "owner": "explicit decision reference atom", "classification": "OWNER_BLOCKED",
        "blocker": "source derives QDKT by splitting one db.ktra decision cell; no authoritative structured decision reference owner is proven",
        "source": "db.ktra row, ColDB_NgayKtra + 1, first token before space/line break",
    },
    "NgayQDKT": {
        "variables": ["NgayQDKT"], "owner": "explicit decision date atom", "classification": "OWNER_BLOCKED",
        "blocker": "source derives date from the same combined decision cell; no structured decision-date owner exists",
        "source": "db.ktra row, ColDB_NgayKtra + 1, trailing token after space/line break",
    },
    "VKNx": {
        "variables": ["Vkn1", "DaychuyenDD", "TinhthanhId"], "owner": "dedicated VKN authority atom", "classification": "OWNER_BLOCKED",
        "blocker": "Get_VKN generates organization prose from vaccine text/province threshold; it is not an inspector/team value",
        "source": "Get_VKN: DaychuyenDD vaccine detection, else TinhthanhId <= 32",
    },
    "VKN": {
        "variables": ["Vkn2", "DaychuyenDD", "TinhthanhId"], "owner": "dedicated VKN authority atom", "classification": "OWNER_BLOCKED",
        "blocker": "Get_VKN generates abbreviated organization prose; no structured authority owner is proven",
        "source": "Get_VKN: vaccine/province branch, used for Sel_GPs 1 or 2 and i=2",
    },
    "TT3x": {
        "variables": ["Ds_TTV", "TVss", "TTVdd", "TT_ext"], "owner": "InspectionTeam ordered members", "classification": "OWNER_PARTIAL",
        "blocker": "structured members exist, but legacy third-member/separator and title augmentation equivalence is not proven",
        "source": "Split(TTVdd, '|'), third entry plus TT_ext and CRLF for later entries",
    },
    "TT3Del": {
        "variables": ["Ds_TTV", "TTVdd"], "owner": "InspectionTeam ordered members", "classification": "OWNER_PARTIAL",
        "blocker": "member-count predicate is proven, but complete modern deletion instruction contract is not",
        "source": "Delete_Bookmark when UBound(Split(TTVdd, '|')) <= 1",
    },
    "TTx": {
        "variables": ["Ds_TTV", "TTVdd", "TT_ext"], "owner": "InspectionTeam ordered members", "classification": "OWNER_PARTIAL",
        "blocker": "dynamic TTx family is source-proven, but logical TT1/TT2 mapping and rendered role format remain unresolved",
        "source": "first two Split(TTVdd, '|') entries written to TT1x/TT2x; later entries feed TT3x",
    },
}


def _read_sources(vba_zip: Path) -> dict[str, list[str]]:
    with zipfile.ZipFile(vba_zip) as archive:
        return {name: _decode(archive.read(name)).replace("\r\n", "\n").replace("\r", "\n").splitlines() for name in archive.namelist()}


def _find_lines(sources: dict[str, list[str]], patterns: list[str]) -> list[dict[str, object]]:
    found: list[dict[str, object]] = []
    for filename, lines in sources.items():
        for index, raw in enumerate(lines, 1):
            code = _active(raw)
            if code and any(re.search(pattern, code, re.I) for pattern in patterns):
                found.append({"file": filename, "line": index, "code": code})
    return found


def _find_declarations(sources: dict[str, list[str]], variable: str) -> list[dict[str, object]]:
    if variable in {"Date", "TT_ext"}:
        return [{"kind": "intrinsic" if variable == "Date" else "physical_bookmark", "symbol": variable}]
    escaped = re.escape(variable)
    return _find_lines(sources, [rf"^\s*(?:Public|Private|Friend|Dim|Static|Const)\b.*\b{escaped}\b"])


def _operation_by_bookmark(trace: dict[str, object], bookmark: str) -> list[dict[str, object]]:
    return [item for item in trace["physical_bookmark_operations"] if item.get("physical_bookmark", "").lower() == bookmark.lower()]


def build_provenance(vba_zip: Path, trace_path: Path = DEFAULT_TRACE, expected_sha256: str | None = EXPECTED_SHA256) -> dict[str, object]:
    if not vba_zip.is_file():
        raise FileNotFoundError(f"VBA ZIP not found: {vba_zip}")
    source_sha = hashlib.sha256(vba_zip.read_bytes()).hexdigest()
    if expected_sha256 and source_sha.lower() != expected_sha256.lower():
        raise RuntimeError(f"VBA ZIP SHA256 mismatch: expected {expected_sha256}, got {source_sha}")
    trace = build_trace(vba_zip, expected_sha256)
    if not trace_path.is_file():
        raise FileNotFoundError(f"source trace artifact not found: {trace_path}")
    sources = _read_sources(vba_zip)
    operation_specs = {
        "Fulldate": [r'Replace_Bookmark\s+wdDoc,\s*"Fulldate"'],
        "Tencoso": [r'Replace_Bookmark\s+wdDoc,\s*"Tencoso"'],
        "Diadiem": [r'Replace_Bookmark\s+wdDoc,\s*"Diadiem"'],
        "Diadiemx": [r'Replace_Bookmark\s+wdDoc,\s*"Diadiemx"'],
        "Diachicoso": [r'Replace_Bookmark\s+wdDoc,\s*"Diachicoso"'],
        "HsDK": [r'Replace_Bookmark\s+wdDoc,\s*"HsDK"'],
        "NgaynopHsDK": [r'Replace_Bookmark\s+wdDoc,\s*"NgaynopHsDK"'],
        "QDKT": [r'Replace_Bookmark\s+wdDoc,\s*"QDKT"'],
        "NgayQDKT": [r'Replace_Bookmark\s+wdDoc,\s*"NgayQDKT"'],
        "VKNx": [r'Replace_Bookmark\s+wdDoc,\s*"VKNx"'],
        "VKN": [r'Replace_Bookmark\s+wdDoc,\s*"VKN"'],
        "TT3x": [r'Replace_Bookmark\s+wdDoc,\s*"TT3x"'],
        "TT3Del": [r'Delete_Bookmark\s+wdDoc,\s*"TT3Del"'],
        "TTx": [r'Replace_Bookmark\s+wdDoc,\s*"TT"'],
    }
    source_patterns = {
        "Date": [r'FormatDateS\(Date, 1\)'], "TenCtydd": [r'\.TenCtydd\s*='],
        "Tinhthanh": [r'\.Tinhthanh\s*='], "Tinhthanhx": [r'\.Tinhthanhx\s*='],
        "DiachiDD": [r'\.DiachiDD\s*='], "s_MaHsDk": [r'\bs_MaHsDk\s*='],
        "s_NgaynopHsDk": [r'\bs_NgaynopHsDk\s*='], "QDKT": [r'\bQDKT\s*='],
        "NgayQDKT": [r'\bNgayQDKT\s*='], "Vkn1": [r'\bVkn1\s*='], "Vkn2": [r'\bVkn2\s*='],
        "DaychuyenDD": [r'\bDaychuyenDD\s*='], "TinhthanhId": [r'\bTinhthanhId\s*='],
        "Ds_TTV": [r'\bDs_TTV\s*='], "TVss": [r'\bTVss\s*='], "TTVdd": [r'\bTTVdd\s*='],
        "TT_ext": [r'\bTText\s*=|Get_Bookmark\(wdDoc,\s*"TT_ext"'],
    }
    fields: dict[str, object] = {}
    for bookmark, spec in TARGETS.items():
        operations = _operation_by_bookmark(trace, bookmark)
        if bookmark == "TTx":
            operations = [item for item in trace["physical_bookmark_operations"] if str(item.get("physical_bookmark", "")).lower() == "ttx"]
        if not operations:
            raise RuntimeError(f"active source operation missing for {bookmark}")
        chains = []
        for variable in spec["variables"]:
            refs = _find_lines(sources, source_patterns[variable])
            if not refs:
                raise RuntimeError(f"source assignment missing for {bookmark}: {variable}")
            declarations = _find_declarations(sources, variable)
            if not declarations:
                raise RuntimeError(f"source declaration missing for {bookmark}: {variable}")
            chains.append({"variable": variable, "declarations": declarations, "steps": refs})
        fields[bookmark] = {
            "physical_bookmark": bookmark,
            "vba_rendered_operations": operations,
            "source_variables": spec["variables"],
            "provenance_chain": chains,
            "source_semantic_endpoint": spec["source"],
            "normalization_or_formatting": {
                "Fulldate": "FormatDateS(Date, 1)", "Diadiemx": "LCase_FirstChar(Tinhthanhx)",
                "Diachicoso": "Replace(DiachiDD, vbCrLf, ';') then Del_LastPeriod",
                "NgaynopHsDK": "Replace(s_NgaynopHsDk, '-', '/')",
                "TT3x": "Trim entries; TT_ext and vbCrLf between later members",
            }.get(bookmark, "none beyond the expression recorded in vba_rendered_operations"),
            "conditions": sorted({str(item.get("branch_predicates", "COMMON")) for item in operations}),
            "modern_owner_candidate": spec["owner"],
            "owner_classification": spec["classification"],
            "blocker": spec["blocker"],
        }
    counts = {key: sum(1 for value in fields.values() if value["owner_classification"] == key) for key in ("OWNER_PROVEN", "OWNER_PARTIAL", "OWNER_BLOCKED")}
    return {
        "schema_version": "inspection-qd-kt-input-provenance/v1",
        "status": "SOURCE_QD_KT_I2_PROVENANCE_CAPTURED",
        "source_zip": "legacy/GXP-VBA code.zip", "source_zip_sha256": source_sha,
        "trace_artifact": "artifacts/legacy_audit/inspection_qd_kt_vba_trace.json",
        "call_chain": trace["call_chain"], "fields": fields,
        "classification_counts": counts,
        "decision": {"typed_qd_kt_input_contract": "BUSINESS_INPUT_CONTRACT_MISSING", "reason": "required active inputs remain OWNER_BLOCKED"},
        "invariants": {"source_modified": False, "runtime_contract_changed": False, "models_modified": False, "display_prose_parsed_as_truth": False},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture source-derived provenance for active INSPECTION_QD_KT VBA i=2 inputs.")
    parser.add_argument("--vba-zip", type=Path, default=DEFAULT_ZIP)
    parser.add_argument("--trace", type=Path, default=DEFAULT_TRACE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--expected-sha256", default=EXPECTED_SHA256)
    args = parser.parse_args()
    try:
        report = build_provenance(args.vba_zip.resolve(), args.trace.resolve(), args.expected_sha256)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (FileNotFoundError, RuntimeError, KeyError, zipfile.BadZipFile) as exc:
        print("STATUS=INSPECTION_QD_KT_INPUT_PROVENANCE_FAILED")
        print(f"ERROR={exc}")
        return 2
    print("STATUS=SOURCE_QD_KT_I2_PROVENANCE_CAPTURED")
    print(f"SOURCE_SHA256={report['source_zip_sha256']}")
    print(f"FIELDS={len(report['fields'])}")
    print(f"CLASSIFICATION_COUNTS={json.dumps(report['classification_counts'], sort_keys=True)}")
    print(f"OUTPUT={args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
