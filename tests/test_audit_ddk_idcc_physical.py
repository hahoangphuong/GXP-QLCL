from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import pytest

from backend.app.domain.legacy_snapshot import _core_source_row
from tools.audit_ddk_idcc_physical import (
    MissingPhysicalEvidence, audit, excel_column_letter, find_ddk_header_row,
    require_literal_idcc_column,
)


def fixture():
    headers = ["ID", "ID CƠ SỞ", "ID CTY", "ID CC", "ID CC", "ID CC", "ID CC"]
    rows = [
        _core_source_row(headers, ["400", "10", "1", "200", "201", "202", "203"], 7),
        _core_source_row(headers, ["401", "10", "1", "200", "200", "", "not-a-number"], 8),
    ]
    return {
        "db.cty": [{"ID": "1"}],
        "db.cso": [{"ID": "10", "ID Cty": "1"}, {"ID": "11", "ID Cty": "1"}],
        "db.ktra": [],
        "db.cc": [
            {"ID": "200", "ID CƠ SỞ": "10", "LOẠI CC": "GMP", "ID DDK": "400"},
            {"ID": "201", "ID CƠ SỞ": "10", "LOẠI CC": "GLP", "ID DDK": "999"},
            {"ID": "202", "ID CƠ SỞ": "11", "LOẠI CC": "GSP", "ID DDK": "400"},
        ],
        "db.dkkd": rows,
    }


def test_lossless_source_audit_preserves_all_four_independent_columns():
    snapshot = fixture()
    untouched = copy.deepcopy(snapshot)
    result = audit(snapshot, source_sha256="test-hash")
    assert result["ddk_source_rows"] == 2
    assert result["id_cc_column_count"] == 4
    assert result["candidate_count"] == 7
    assert [col["excel_column"] for col in result["id_cc_columns"]] == [4, 5, 6, 7]
    assert all(col["owner_role"] == "UNVERIFIED" for col in result["id_cc_columns"])
    assert result["id_cc_columns"][0]["certificate_type_distribution"] == {"GMP": 2}
    assert result["id_cc_columns"][2]["counts"]["cross_site"] == 1
    assert result["id_cc_columns"][3]["counts"]["nonliteral_fk"] == 1
    assert result["id_cc_columns"][0]["counts"]["duplicate_within_ddk"] == 1
    assert sorted(c["classification"] for c in result["candidates"]) == sorted(
        ["SAME_SITE", "SAME_SITE", "SAME_SITE", "SAME_SITE",
         "CROSS_SITE", "MISSING_CERTIFICATE", "NONLITERAL_FK"]
    )
    assert next(c for c in result["candidates"] if c["certificate_legacy_id"] == 201)["reverse_relation"] == "REVERSE_CONFLICTS"
    assert snapshot == untouched
    assert "linked_certificate_ids" not in snapshot["db.dkkd"][0]


def test_flattened_v1_cannot_be_audited_as_four_column_source():
    data = fixture()
    data["db.dkkd"] = [{"ID": "400", "ID CC": ""}]
    with pytest.raises(MissingPhysicalEvidence, match="flattened V1 snapshot"):
        audit(data)


def test_missing_duplicate_cell_fails_closed():
    data = fixture()
    del data["db.dkkd"][1]["ID CC [excel_column=7]"]
    with pytest.raises(MissingPhysicalEvidence, match="Missing one or more"):
        audit(data)


def test_excel_column_letter_boundaries():
    assert [excel_column_letter(i) for i in (1, 26, 27, 52, 53)] == [
        "A", "Z", "AA", "AZ", "BA"
    ]


def test_varying_physical_header_ordinals_block_source_review():
    data = fixture()
    row = data["db.dkkd"][1]
    row["__excel_duplicate_headers"] = json.dumps([
        {"header": "ID CC", "column_ordinals": [4, 5, 6, 8]},
    ])
    with pytest.raises(MissingPhysicalEvidence, match="vary across rows"):
        audit(data)


def test_ddk_header_source_identity_wins_over_denser_data_row():
    raw = [
        ["Legacy source workbook"],
        ["ID", "ID CƠ SỞ", "ID CTY", "ID CC", "ID CC", "ID CC", "ID CC", "", ""],
        ["400", "10", "1", "200", "201", "202", "203", "a", "b"],
    ]
    assert find_ddk_header_row(raw) == 1


@pytest.mark.parametrize("raw", [
    [["ID", "ID CC", "ID CC", "ID CC"]],
    [["ID", "ID CC", "ID CC", "ID CC", "ID CC"]] * 2,
])
def test_ddk_header_source_identity_ambiguous_or_incomplete_fails_closed(raw):
    with pytest.raises(MissingPhysicalEvidence, match="Cannot uniquely identify"):
        find_ddk_header_row(raw)


@pytest.mark.parametrize("columns", [
    [4, 5, 6],
    [4, 5, 5, 7],
    [4, 5, "6", 7],
    [4, 5, 6, 0],
    [4, 6, 5, 7],
])
def test_audit_refuses_invalid_four_column_physical_metadata(columns):
    data = fixture()
    for row in data["db.dkkd"]:
        row["__excel_duplicate_headers"] = json.dumps([
            {"header": "ID CC", "column_ordinals": columns},
        ])
    with pytest.raises(MissingPhysicalEvidence, match="four-column ID CC"):
        audit(data)


def test_duplicate_ddk_legacy_id_does_not_conflate_distinct_source_rows():
    data = fixture()
    data["db.dkkd"][1]["ID"] = "400"
    data["db.dkkd"][1]["ID CC [excel_column=5]"] = "201"
    result = audit(data)
    candidates = [
        c for c in result["candidates"]
        if c["certificate_legacy_id"] == 200
    ]
    assert len(candidates) == 2
    assert {c["source_row_number"] for c in candidates} == {7, 8}
    assert all(not c["duplicate_within_ddk"] for c in candidates)
    assert all(c["duplicate_across_ddk_rows"] for c in candidates)


def test_each_raw_fk_including_nonliteral_is_preserved_for_source_review():
    result = audit(fixture())
    assert next(c for c in result["candidates"]
                if c["classification"] == "NONLITERAL_FK")["raw_fk"] == "not-a-number"
    assert next(c for c in result["candidates"]
                if c["certificate_legacy_id"] == 201)["raw_fk"] == "201"


def test_missing_or_repeated_physical_rows_rejected():
    data = fixture()
    data["db.dkkd"][1]["__excel_row_number"] = "7"
    with pytest.raises(MissingPhysicalEvidence, match="physical db.dkkd row"):
        audit(data)
    data["db.dkkd"][1]["__excel_row_number"] = ""
    with pytest.raises(MissingPhysicalEvidence, match="physical db.dkkd row"):
        audit(data)


def test_owner_tool_module_entrypoint_imports_from_repo_root():
    result = subprocess.run(
        [sys.executable, "-m", "tools.audit_ddk_idcc_physical", "--help"],
        cwd=Path(__file__).resolve().parents[1],
        text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "--workbook" in result.stdout


@pytest.mark.parametrize("formula_state", [True, None, "UNVERIFIABLE"])
def test_computed_or_unknown_excel_idcc_formula_status_fails_closed(formula_state):
    with pytest.raises(MissingPhysicalEvidence, match="computed FKs"):
        require_literal_idcc_column(formula_state, 14)


@pytest.mark.parametrize("formula_state", [False, 0])
def test_literal_excel_idcc_column_formula_status_is_accepted(formula_state):
    assert require_literal_idcc_column(formula_state, 14) is None
