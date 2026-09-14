from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from shutil import copyfile
from types import SimpleNamespace

import pytest
from pyxlsb import open_workbook

from backend.app.domain.legacy_snapshot_v2 import (
    AUTHORITATIVE_WORKBOOK_SHA256,
    CANONICAL_WORKBOOK_FILENAME,
    EXPECTED_SHEET_INVENTORY,
    PROVEN_RELATIONSHIPS,
    _cell,
    _raw_row_payload,
    _verify_sheet_inventory,
    build_snapshot,
    snapshot_bytes,
)
from tools.export_legacy_snapshot_v2 import V1_PATH, validate_output_path


WORKBOOK = Path("legacy/Danh sách Kiểm tra GPs.xlsb")
WORKBOOK_SHA = "c12537ea5a5c9f470e42fb5bdbe214f36983e310fceac7c560ad38885209fe3d"
SNAPSHOT_SHA = "484cf37603aacc5ff01a7bde5ffab01ed444748d5c7b1a0b30e7fc3a04936caa"


@pytest.fixture(scope="session")
def snapshot_v2():
    assert sha256(WORKBOOK.read_bytes()).hexdigest() == WORKBOOK_SHA
    return build_snapshot(WORKBOOK)


@pytest.fixture(scope="session")
def workbook_populated_cells():
    with open_workbook(WORKBOOK) as workbook:
        return sum(cell.v is not None and cell.v != "" for name in workbook.sheets for row in workbook.get_sheet(name).rows() for cell in row)


@pytest.fixture(scope="session")
def workbook_reader_coordinates():
    with open_workbook(WORKBOOK) as workbook:
        return {
            (name, cell.r + 1, cell.c + 1)
            for name in workbook.sheets
            for row in workbook.get_sheet(name).rows()
            for cell in row
        }


def test_authoritative_workbook_is_fenced_and_complete(snapshot_v2):
    snapshot = snapshot_v2
    assert AUTHORITATIVE_WORKBOOK_SHA256 == WORKBOOK_SHA
    assert snapshot["workbook"]["canonical_filename"] == CANONICAL_WORKBOOK_FILENAME
    assert "filename" not in snapshot["workbook"]
    assert tuple(snapshot["workbook"]["sheet_inventory"]) == EXPECTED_SHEET_INVENTORY
    assert tuple(item["sheet_name"] for item in snapshot["sheets"]) == EXPECTED_SHEET_INVENTORY
    assert len(snapshot["sheets"]) == 32
    ttvien = next(item for item in snapshot["sheets"] if item["sheet_name"] == "TTviên")
    assert ttvien["raw_row_count"] == 385
    assert ttvien["populated_cell_count"] == 2720
    assert snapshot["field_registry"] == []
    assert len(snapshot["unresolved_field_header_candidates"]) == 1374
    assert PROVEN_RELATIONSHIPS == (
        ("db.ktra", "ID CƠ SỞ", "db.cso", "ID"),
        ("db.cc", "ID ĐỢT KTRA", "db.ktra", "ID"),
        ("db.dkkd", "ID CƠ SỞ", "db.cso", "ID"),
        ("db.dkkd", "ID CTY", "db.cty", "ID"),
        ("db.dkkd", "ID CC", "db.cc", "ID"),
        ("db.Tdoi2", "ID Gốc", "db.Tdoi", "ID"),
    )


def test_non_authoritative_workbook_fails_closed(tmp_path):
    different_workbook = tmp_path / "different.xlsb"
    different_workbook.write_bytes(b"not the authoritative workbook")
    with pytest.raises(ValueError, match="provenance"):
        build_snapshot(different_workbook)


def test_authoritative_workbook_copy_is_path_independent(tmp_path):
    copied_workbook = tmp_path / "authoritative-copy.xlsb"
    copyfile(WORKBOOK, copied_workbook)
    original = build_snapshot(WORKBOOK)
    copied = build_snapshot(copied_workbook)
    assert copied["workbook"]["sha256"] == AUTHORITATIVE_WORKBOOK_SHA256
    assert snapshot_bytes(copied) == snapshot_bytes(original)
    assert sha256(snapshot_bytes(copied)).hexdigest() == sha256(snapshot_bytes(original)).hexdigest()


def test_sheet_inventory_fails_closed():
    with pytest.raises(ValueError, match="sheet inventory"):
        _verify_sheet_inventory(["GSP"])


def test_v2_exporter_refuses_v1_path_and_allows_v2_path(tmp_path):
    with pytest.raises(ValueError, match="V1"):
        validate_output_path(V1_PATH)
    output = tmp_path / "legacy_snapshot_v2.json"
    assert validate_output_path(output) == output.resolve()


def test_raw_cell_states_preserve_evidence_without_normalization():
    assert _cell(None)[1:] == ("NULL", "null")
    assert _cell("")[1:] == ("BLANK_STRING", "str")
    assert _cell("  ")[1:] == ("WHITESPACE_ONLY", "str")
    assert _cell("-")[1:] == ("SENTINEL", "str")
    assert _cell(" raw ") == (" raw ", "TEXT", "str")


def test_raw_row_preserves_observed_null_without_synthesizing_absent_coordinates():
    row = _raw_row_payload([
        SimpleNamespace(r=4, c=0, v=None),
        SimpleNamespace(r=4, c=2, v="observed"),
    ])
    assert row["source_row_number"] == 5
    assert row["cells"] == [
        {"column_ordinal": 1, "raw_value": None, "raw_state": "NULL", "observed_type": "null"},
        {"column_ordinal": 3, "raw_value": "observed", "raw_state": "TEXT", "observed_type": "str"},
    ]


def test_raw_coordinates_hashes_and_complex_sheet_are_deterministic(snapshot_v2, workbook_populated_cells, workbook_reader_coordinates):
    first = snapshot_v2
    second = build_snapshot(WORKBOOK)
    assert snapshot_bytes(first) == snapshot_bytes(second)
    assert sha256(snapshot_bytes(first)).hexdigest() == SNAPSHOT_SHA
    assert [item["content_sha256"] for item in first["sheets"]] == [item["content_sha256"] for item in second["sheets"]]
    gmp = next(item for item in first["sheets"] if item["sheet_name"] == "GMP")
    source_coordinates = ((1, 1), (5, 3), (8, 7), (8, 13), (8, 21), (8, 22), (8, 24), (8, 34))
    with open_workbook(WORKBOOK) as workbook:
        with workbook.get_sheet("GMP") as sheet:
            source_rows = [[cell.v for cell in row] for row in sheet.rows()]
    snapshot_values = {
        (row["source_row_number"], cell["column_ordinal"]): cell["raw_value"]
        for row in gmp["raw_rows"]
        for cell in row["cells"]
    }
    assert {coordinate: source_rows[coordinate[0] - 1][coordinate[1] - 1] for coordinate in source_coordinates} == {
        coordinate: snapshot_values[coordinate] for coordinate in source_coordinates
    }
    assert workbook_populated_cells == 236786
    assert workbook_populated_cells == sum(sheet["populated_cell_count"] for sheet in first["sheets"])
    snapshot_coordinates = {
        (sheet["sheet_name"], row["source_row_number"], cell["column_ordinal"])
        for sheet in first["sheets"]
        for row in sheet["raw_rows"]
        for cell in row["cells"]
    }
    assert snapshot_coordinates == workbook_reader_coordinates
    assert sum(sheet["raw_coordinate_inventory"]["cell_coordinate_count"] for sheet in first["sheets"]) == len(workbook_reader_coordinates)
    for ordinal, sheet in enumerate(first["sheets"], start=1):
        assert sheet["sheet_ordinal"] == ordinal
        coordinates = [(row["source_row_number"], cell["column_ordinal"]) for row in sheet["raw_rows"] for cell in row["cells"]]
        assert coordinates == sorted(coordinates)
        assert len(coordinates) == len(set(coordinates))
