"""Deterministic, read-only full-workbook legacy snapshot extraction."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from pyxlsb import open_workbook


SCHEMA_VERSION = "legacy-workbook-snapshot/v2"
EXTRACTOR_VERSION = "1"
AUTHORITATIVE_WORKBOOK_SHA256 = "c12537ea5a5c9f470e42fb5bdbe214f36983e310fceac7c560ad38885209fe3d"
CANONICAL_WORKBOOK_FILENAME = "Danh sách Kiểm tra GPs.xlsb"
EXPECTED_SHEET_INVENTORY = (
    "GSP", "GMP", "GLP", "GMPbb", "GMPnn", "DsCB", "DsCB GMP", "Nhóm 1c",
    "DsCBKT", "DsCBDDK", "DsCs", "DsCty", "Loc", "KHKT", "Liên hệ", "KH",
    "Lịch sử TTV", "TTviên", "Địa danh", "Thống kê", "Phạm vi CN", "Ngừng CN",
    "db.cc", "db.ktra", "db.Tdoi", "db.Tdoi2", "db.DC", "db.cso", "db.cty",
    "db.dkkd", "Dịch-Viết tắt", "SXVX",
)
SENTINELS = {"", "-", "???"}
PROVEN_RELATIONSHIPS = (
    ("db.ktra", "ID CƠ SỞ", "db.cso", "ID"),
    ("db.cc", "ID ĐỢT KTRA", "db.ktra", "ID"),
    ("db.dkkd", "ID CƠ SỞ", "db.cso", "ID"),
    ("db.dkkd", "ID CTY", "db.cty", "ID"),
    ("db.dkkd", "ID CC", "db.cc", "ID"),
    ("db.Tdoi2", "ID Gốc", "db.Tdoi", "ID"),
)


def _sha_bytes(value: bytes) -> str:
    return sha256(value).hexdigest()


def _cell(value: Any) -> tuple[object | None, str, str]:
    if value is None:
        return None, "NULL", "null"
    if isinstance(value, str):
        if value == "":
            return value, "BLANK_STRING", "str"
        if value.strip() == "":
            return value, "WHITESPACE_ONLY", "str"
        if value.strip() in {"-", "???"}:
            return value, "SENTINEL", "str"
        return value, "TEXT", "str"
    if isinstance(value, bool):
        return value, "BOOLEAN", "bool"
    if isinstance(value, (int, float)):
        return value, "NUMBER", type(value).__name__
    return str(value), "TEXT", type(value).__name__


def _sheet_classification(name: str) -> str:
    if name in {"TTviên", "Địa danh", "Phạm vi CN", "Dịch-Viết tắt", "Loc", "db.DC"}:
        return "MASTER_REFERENCE"
    if name.startswith("db.") or name in {"GMP", "GLP", "GSP", "GMPbb", "GMPnn", "KHKT", "KH", "Lịch sử TTV", "Ngừng CN"}:
        return "TRANSACTION_HISTORY"
    if name in {"Thống kê", "DsCB", "DsCB GMP", "DsCBKT", "DsCBDDK", "DsCs", "DsCty", "Nhóm 1c", "Liên hệ", "SXVX"}:
        return "REPORT_DISPLAY"
    return "UNRESOLVED"


def _verify_sheet_inventory(names: list[str]) -> None:
    if tuple(names) != EXPECTED_SHEET_INVENTORY:
        raise ValueError("workbook sheet inventory provenance guard failed")


def _raw_row_payload(source_cells: list[Any]) -> dict[str, Any]:
    if not source_cells:
        raise ValueError("reader returned a row without observable cells")
    source_row_number = source_cells[0].r + 1
    if any(cell.r + 1 != source_row_number for cell in source_cells):
        raise ValueError("reader returned cells from multiple source rows")
    cells = []
    for cell in source_cells:
        raw, state, observed_type = _cell(cell.v)
        cells.append({"column_ordinal": cell.c + 1, "raw_value": raw, "raw_state": state, "observed_type": observed_type})
    return {"source_row_number": source_row_number, "cells": cells}


def _sheet_payload(workbook: Any, name: str, ordinal: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    with workbook.get_sheet(name) as sheet:
        raw_rows = [_raw_row_payload(list(row)) for row in sheet.rows()]
    width = max((cell["column_ordinal"] for row in raw_rows for cell in row["cells"]), default=0)
    canonical = json.dumps(raw_rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    populated = sum(cell["raw_state"] != "NULL" and cell["raw_value"] != "" for row in raw_rows for cell in row["cells"])
    candidates = [{"source_sheet": name, "source_column_ordinal": column, "candidate": "UNRESOLVED_HEADER_OR_LAYOUT", "notes": "Raw coordinate is authoritative; Batch A does not infer semantic headers."} for column in range(1, width + 1)]
    return ({"sheet_name": name, "sheet_ordinal": ordinal, "classification": _sheet_classification(name), "used_row_count": len(raw_rows), "used_column_count": width, "raw_row_count": len(raw_rows), "populated_cell_count": populated, "content_sha256": _sha_bytes(canonical), "raw_coordinate_inventory": {"row_count": len(raw_rows), "column_count": width, "cell_coordinate_count": sum(len(row["cells"]) for row in raw_rows)}, "raw_rows": raw_rows}, candidates)


def build_snapshot(workbook_path: Path) -> dict[str, Any]:
    workbook_sha = _sha_bytes(workbook_path.read_bytes())
    if workbook_sha != AUTHORITATIVE_WORKBOOK_SHA256:
        raise ValueError("workbook SHA256 provenance guard failed")
    with open_workbook(workbook_path) as workbook:
        names = list(workbook.sheets)
        _verify_sheet_inventory(names)
        sheets, registry = zip(*(_sheet_payload(workbook, name, ordinal) for ordinal, name in enumerate(names, start=1)), strict=True)
    relationships = [{"source_sheet": source_sheet, "source_field": source_field, "target_sheet": target_sheet, "target_field": target_field, "cardinality": "UNRESOLVED", "evidence": "EXACT_AUTHORITATIVE_WORKBOOK_FIELD_NAMES", "status": "PROVEN_FIELD_REFERENCE"} for source_sheet, source_field, target_sheet, target_field in PROVEN_RELATIONSHIPS]
    return {"schema_version": SCHEMA_VERSION, "workbook": {"canonical_filename": CANONICAL_WORKBOOK_FILENAME, "sha256": workbook_sha, "extractor_version": EXTRACTOR_VERSION, "extraction_timestamp": None, "total_sheet_count": len(names), "sheet_inventory": names, "semantic_output_deterministic": True}, "sheets": list(sheets), "relationships": relationships, "field_registry": [], "unresolved_field_header_candidates": [item for group in registry for item in group], "contract": {"raw_source_view": "AUTHORITATIVE_READER_OBSERVED_COORDINATES_ONLY", "semantic_tabular_view": "NOT_CREATED_IN_BATCH_A", "no_inference_rule": "AUTHORITATIVE_WORKBOOK_DATA_MUST_BE_USED;_FALLBACK_REQUIRES_SOURCE_ABSENCE,_EXPLICIT_APPROVAL,_AND_FIELD_REGISTRY_RECORD."}}


def snapshot_bytes(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
