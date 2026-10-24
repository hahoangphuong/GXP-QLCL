"""Verify coordinate-preserving Snapshot V2 sheet bytes before a QĐKT audit.

A claimed workbook digest in JSON is not independently sufficient to certify
raw cell coordinates: rehash the deterministic sheet payload from the extractor.
This detects post-extraction edits, not malicious reconstruction or forged
workbook provenance; original workbook attestation remains a separate gate.
"""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Mapping

from backend.app.domain.legacy_snapshot_v2 import (
    AUTHORITATIVE_WORKBOOK_SHA256, SCHEMA_VERSION,
)


class QdKtSnapshotContentBlocked(ValueError):
    pass


def verify_dbktra_snapshot_content(snapshot: Any) -> dict[str, int | str]:
    if not isinstance(snapshot, Mapping) or snapshot.get("schema_version") != SCHEMA_VERSION:
        raise QdKtSnapshotContentBlocked("SNAPSHOT_SCHEMA_INVALID")
    workbook = snapshot.get("workbook")
    if not isinstance(workbook, Mapping) or workbook.get("sha256") != AUTHORITATIVE_WORKBOOK_SHA256:
        raise QdKtSnapshotContentBlocked("SNAPSHOT_WORKBOOK_UNVERIFIED")
    sheets = snapshot.get("sheets")
    if not isinstance(sheets, list):
        raise QdKtSnapshotContentBlocked("SNAPSHOT_SHEETS_INVALID")
    matching = [s for s in sheets if isinstance(s, Mapping) and s.get("sheet_name") == "db.ktra"]
    if len(matching) != 1:
        raise QdKtSnapshotContentBlocked("DBKTRA_SHEET_NOT_UNIQUE")
    sheet = matching[0]
    rows = sheet.get("raw_rows")
    if not isinstance(rows, list) or not rows:
        raise QdKtSnapshotContentBlocked("DBKTRA_ROWS_INVALID")
    if any(not isinstance(row, Mapping) or not isinstance(row.get("cells"), list)
           for row in rows):
        raise QdKtSnapshotContentBlocked("DBKTRA_ROW_SHAPE_INVALID")
    canonical = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    actual = sha256(canonical).hexdigest()
    if sheet.get("content_sha256") != actual:
        raise QdKtSnapshotContentBlocked("DBKTRA_SHEET_CONTENT_DIGEST_MISMATCH")
    inventory = sheet.get("raw_coordinate_inventory")
    if not isinstance(inventory, Mapping):
        raise QdKtSnapshotContentBlocked("DBKTRA_COORDINATE_INVENTORY_MISSING")
    num_cells = sum(len(row["cells"]) for row in rows)
    num_cols = max((cell.get("column_ordinal") for row in rows
                    for cell in row["cells"] if isinstance(cell, Mapping)
                    and type(cell.get("column_ordinal")) is int), default=0)
    if (type(inventory.get("row_count")) is not int
            or inventory["row_count"] != len(rows)
            or type(inventory.get("cell_coordinate_count")) is not int
            or inventory["cell_coordinate_count"] != num_cells
            or type(inventory.get("column_count")) is not int
            or inventory["column_count"] != num_cols):
        raise QdKtSnapshotContentBlocked("DBKTRA_COORDINATE_INVENTORY_MISMATCH")
    if (type(sheet.get("raw_row_count")) is not int or sheet["raw_row_count"] != len(rows)
            or type(sheet.get("used_row_count")) is not int or sheet["used_row_count"] != len(rows)
            or type(sheet.get("used_column_count")) is not int or sheet["used_column_count"] != num_cols):
        raise QdKtSnapshotContentBlocked("DBKTRA_SHEET_COUNTS_MISMATCH")
    return {
        "dbktra_content_sha256": actual,
        "dbktra_source_row_count": len(rows),
        "dbktra_observed_cell_count": num_cells,
    }
