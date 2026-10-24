"""Source cell edits cannot hide behind workbook.sha256 metadata."""
import copy
from hashlib import sha256
import json

import pytest

from backend.app.domain.legacy_snapshot_v2 import AUTHORITATIVE_WORKBOOK_SHA256, SCHEMA_VERSION
from backend.app.document.inspection_qd_kt_snapshot_content_integrity import (
    QdKtSnapshotContentBlocked, verify_dbktra_snapshot_content,
)


def _valid():
    rows = [
        {"source_row_number": 1, "cells": [{"column_ordinal": 1, "raw_value": "ID"}]},
        {"source_row_number": 2, "cells": [{"column_ordinal": 1, "raw_value": 101}]},
    ]
    digest = sha256(json.dumps(rows, sort_keys=True, ensure_ascii=False,
                               separators=(",", ":")).encode("utf-8")).hexdigest()
    return {
        "schema_version": SCHEMA_VERSION,
        "workbook": {"sha256": AUTHORITATIVE_WORKBOOK_SHA256},
        "sheets": [{"sheet_name": "db.ktra", "raw_rows": rows,
                    "content_sha256": digest,
                    "raw_row_count": 2, "used_row_count": 2,
                    "used_column_count": 1,
                    "raw_coordinate_inventory": {"row_count": 2, "column_count": 1,
                                                 "cell_coordinate_count": 2}}],
    }


def test_extract_style_content_digest_verified():
    proof = verify_dbktra_snapshot_content(_valid())
    assert proof["dbktra_source_row_count"] == 2
    assert proof["dbktra_observed_cell_count"] == 2


def test_modified_id_with_same_claimed_workbook_hash_rejected():
    source = _valid()
    source["sheets"][0]["raw_rows"][1]["cells"][0]["raw_value"] = 999
    with pytest.raises(QdKtSnapshotContentBlocked, match="CONTENT_DIGEST_MISMATCH"):
        verify_dbktra_snapshot_content(source)


@pytest.mark.parametrize("change,error", [
    ("missing_digest", "CONTENT_DIGEST_MISMATCH"),
    ("wrong_count", "COORDINATE_INVENTORY_MISMATCH"),
    ("wrong_width", "COORDINATE_INVENTORY_MISMATCH"),
    ("wrong_row_count", "SHEET_COUNTS_MISMATCH"),
    ("duplicate_sheet", "SHEET_NOT_UNIQUE"),
])
def test_structure_mutation_rejected(change, error):
    source = _valid()
    sheet = source["sheets"][0]
    if change == "missing_digest":
        sheet.pop("content_sha256")
    elif change == "wrong_count":
        sheet["raw_coordinate_inventory"]["cell_coordinate_count"] = 3
    elif change == "wrong_width":
        sheet["raw_coordinate_inventory"]["column_count"] = 9
    elif change == "wrong_row_count":
        sheet["raw_row_count"] = 10
    else:
        source["sheets"].append(copy.deepcopy(sheet))
    with pytest.raises(QdKtSnapshotContentBlocked, match=error):
        verify_dbktra_snapshot_content(source)
