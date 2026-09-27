"""Read-only, complete-sheet inventory for the authoritative legacy workbook."""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

from pyxlsb import open_workbook

from backend.app.domain.legacy_snapshot import CORE_SHEETS, safe_text
from backend.app.domain.legacy_snapshot_v2 import SCHEMA_VERSION


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "artifacts" / "legacy_audit" / "complete_legacy_workbook_inventory_v1.json"
SENTINELS = {"", "-", "???"}
# Keep Unicode letters intact. Header analysis is evidence discovery, not a
# license to erase Vietnamese semantics before they can be observed.
HEADER_WORDS = re.compile(r"(?i)(?:\bid\b|\btt\b|mã|tên|ngày|loại|địa|phạm|chứng|tình|ghi|người|số|công ty|cơ sở)")
AUTHORITATIVE_SHEETS = {"TTviên"}
REPORT_OR_DERIVED_ONLY_SHEETS = {"Lịch sử TTV", "DsCB", "DsCB GMP", "DsCBKT", "DsCBDDK"}
OBSOLETE_SHEETS = {"Nhóm 1c"}
REFERENCE_SHEETS = {"Địa danh", "Phạm vi CN", "Dịch-Viết tắt", "Loc"}


def _sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _value(value: Any) -> str:
    return safe_text(value).replace("\r\n", "\n")


def _is_number(value: str) -> bool:
    try:
        float(value)
        return True
    except ValueError:
        return False


def _header_score(row: list[str]) -> int:
    nonblank = [value for value in row if value]
    if not nonblank:
        return -1
    words = sum(bool(HEADER_WORDS.search(value)) for value in nonblank)
    text = sum(not _is_number(value) for value in nonblank)
    return words * 20 + text * 2 + len(nonblank)


def _header_terms(header: str) -> list[str]:
    """Return Unicode-preserving diagnostic header terms."""
    return re.findall(r"[^\W_]+", header.casefold(), flags=re.UNICODE)


def _column_profile(header: str, position: int, values: list[str]) -> dict[str, Any]:
    nonblank = [value for value in values if value not in SENTINELS]
    types = {"numeric" if _is_number(value) else "text" for value in nonblank}
    storage_type = "EMPTY" if not nonblank else next(iter(types)).upper() if len(types) == 1 else "MIXED"
    terms = _header_terms(header)
    identifier = any(term in {"id", "mã", "code", "initial"} for term in terms)
    importance = "REQUIRED" if identifier else "UNRESOLVED"
    return {
        "source_column": header or f"__UNLABELED_COLUMN_{position}",
        "header_terms_unicode_preserved": terms,
        "source_position": position,
        "nonblank_count": len(nonblank),
        "blank_or_sentinel_count": len(values) - len(nonblank),
        "distinct_count": len(set(nonblank)),
        "representatives": sorted(set(nonblank), key=lambda value: (len(value), value))[:3],
        "observed_storage_type": storage_type,
        "stable_identifier_potential": "CANDIDATE" if identifier and len(nonblank) == len(set(nonblank)) else "NONE_OR_NOT_UNIQUE",
        "candidate_semantic_meaning": "UNRESOLVED_BUSINESS_DECISION",
        "candidate_canonical_owner": "UNRESOLVED_BUSINESS_DECISION",
        "migration_importance": importance,
    }


def _sheet_kind(name: str) -> str:
    if name in AUTHORITATIVE_SHEETS:
        return "AUTHORITATIVE_SOURCE"
    if name in REPORT_OR_DERIVED_ONLY_SHEETS:
        return "REPORT_OR_DERIVED_ONLY"
    if name in OBSOLETE_SHEETS:
        return "OBSOLETE"
    if name in REFERENCE_SHEETS:
        return "REFERENCE"
    if name.startswith("db."):
        return "CANONICAL_SOURCE_TABLE_CANDIDATE"
    if name in {"GMP", "GLP", "GSP", "GMPbb", "GMPnn", "KHKT", "KH", "Ngừng CN"}:
        return "REFERENCE"
    return "UNKNOWN_REQUIRES_REVIEW"


def _read_sheet(workbook: Any, name: str) -> dict[str, Any]:
    with workbook.get_sheet(name) as sheet:
        rows = [[_value(cell.v) for cell in row] for row in sheet.rows()]
    width = max((len(row) for row in rows), default=0)
    rows = [row + [""] * (width - len(row)) for row in rows]
    header_index = max(range(min(20, len(rows))), key=lambda index: _header_score(rows[index]), default=0)
    headers = rows[header_index] if rows else []
    data_rows = rows[header_index + 1 :]
    columns = [_column_profile(headers[index], index + 1, [row[index] for row in data_rows]) for index in range(width)]
    return {
        "sheet_name": name,
        "visibility": "UNAVAILABLE_PYXLSB_READER",
        "used_row_count": len(rows),
        "used_column_count": width,
        "approximate_populated_cell_count": sum(bool(value) for row in rows for value in row),
        "header_row": header_index + 1,
        "header_detection": "HEURISTIC_REQUIRES_BUSINESS_REVIEW_FOR_COMPLEX_OR_MERGED_LAYOUTS",
        "headers": [column["source_column"] for column in columns],
        "columns": columns,
        "apparent_domain": _sheet_kind(name),
        "configured_import_plan_expectation": "CORE_SHEET_ALLOWLIST_MEMBER" if name in CORE_SHEETS else "NOT_DECLARED_BY_CORE_SHEET_ALLOWLIST",
        "observed_ingestion_coverage": "UNAVAILABLE_WITHOUT_EXPLICIT_EXECUTION_EVIDENCE",
    }


def build_inventory(workbook_path: Path, snapshot_path: Path, *, expected_workbook_sha256: str, expected_snapshot_sha256: str) -> dict[str, Any]:
    workbook_sha256 = _sha(workbook_path)
    snapshot_sha256 = _sha(snapshot_path)
    if workbook_sha256 != expected_workbook_sha256.lower():
        raise ValueError("workbook SHA256 provenance guard failed")
    if snapshot_sha256 != expected_snapshot_sha256.lower():
        raise ValueError("snapshot SHA256 provenance guard failed")
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    if snapshot.get("schema_version") != SCHEMA_VERSION or not isinstance(snapshot.get("sheets"), list):
        raise ValueError("Snapshot V2 schema provenance guard failed")
    workbook_metadata = snapshot.get("workbook")
    if not isinstance(workbook_metadata, dict):
        raise ValueError("Snapshot V2 workbook lineage is malformed")
    inventory = workbook_metadata.get("sheet_inventory")
    if (
        workbook_metadata.get("sha256") != workbook_sha256
        or type(workbook_metadata.get("total_sheet_count")) is not int
        or not isinstance(inventory, list)
        or not all(isinstance(name, str) and name for name in inventory)
        or len(inventory) != len(set(inventory))
    ):
        raise ValueError("Snapshot V2 workbook lineage or inventory is malformed")
    snapshot_sheet_names = []
    for sheet in snapshot["sheets"]:
        if not isinstance(sheet, dict) or not isinstance(sheet.get("sheet_name"), str) or not sheet["sheet_name"]:
            raise ValueError("Snapshot V2 sheet inventory is malformed")
        snapshot_sheet_names.append(sheet["sheet_name"])
    if len(snapshot_sheet_names) != len(set(snapshot_sheet_names)):
        raise ValueError("Snapshot V2 sheet inventory is duplicated")
    with open_workbook(workbook_path) as workbook:
        actual_sheet_names = list(workbook.sheets)
        sheets = [_read_sheet(workbook, name) for name in actual_sheet_names]
    if workbook_metadata["total_sheet_count"] != len(inventory) or snapshot_sheet_names != inventory:
        raise ValueError("Snapshot V2 internal sheet inventory is inconsistent")
    if actual_sheet_names != inventory:
        raise ValueError("workbook sheet inventory does not match Snapshot V2")
    return {
        "schema_version": "complete-legacy-workbook-inventory/v1",
        "provenance": {"workbook_path": str(workbook_path), "workbook_sha256": workbook_sha256, "snapshot_sha256": snapshot_sha256, "snapshot_workbook_sha256": workbook_metadata["sha256"], "read_only": True},
        "summary": {"sheet_count": len(sheets), "snapshot_sheet_count": len(inventory), "sheets_absent_from_snapshot": []},
        "sheets": sheets,
        "configured_import_plan": {"core_sheet_allowlist": CORE_SHEETS, "basis": "STATIC_CONFIGURATION_ONLY;_NOT_OBSERVED_INGESTION_COVERAGE"},
        "observed_ingestion_coverage": {"status": "UNAVAILABLE_WITHOUT_EXECUTION_EVIDENCE", "source": None},
        "no_inference_proposed_rule": "WHEN_AUTHORITATIVE_WORKBOOK_FIELD_OR_MASTER_SHEET_EXISTS,_DOWNSTREAM_MIGRATION_MUST_USE_IT;_FALLBACK_REQUIRES_DOCUMENTED_SOURCE_ABSENCE_AND_EXPLICIT_BUSINESS_APPROVAL.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only complete inventory of the legacy .xlsb workbook.")
    parser.add_argument("--workbook", type=Path, required=True)
    parser.add_argument("--expected-workbook-sha256", required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--expected-snapshot-sha256", required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    report = build_inventory(args.workbook.resolve(), args.snapshot.resolve(), expected_workbook_sha256=args.expected_workbook_sha256, expected_snapshot_sha256=args.expected_snapshot_sha256)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(f"SHA256={_sha(args.output)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
