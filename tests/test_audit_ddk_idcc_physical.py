from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import pytest

from backend.app.domain.legacy_snapshot import _core_source_row
from tools.audit_ddk_idcc_physical import (
    AUDIT_SOURCE_SHEETS, MissingPhysicalEvidence, audit, excel_column_letter,
    find_ddk_header_row, find_id_header_row, require_literal_idcc_column,
    split_idcc_references, discover_ddk_group_layout, project_ddk_group_source,
    capture_ddk_source_row, source_value2_text,
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


def test_audit_only_reads_required_source_owner_sheets():
    assert set(AUDIT_SOURCE_SHEETS) == {"db.cty", "db.cso", "db.cc", "db.dkkd"}


def test_non_ddk_header_selected_by_literal_id_not_row_density():
    raw = [["Title"], ["ID", "ID CƠ SỞ", "LOẠI CC"], ["200", "10", "GMP", "lots", "of", "values"]]
    assert find_id_header_row(raw, "db.cc") == 1


@pytest.mark.parametrize("raw", [
    [["No ID header"]],
    [["ID", "name"], ["ID", "duplicate"]],
])
def test_non_ddk_ambiguous_header_fails_closed(raw):
    with pytest.raises(MissingPhysicalEvidence, match="source ID header"):
        find_id_header_row(raw, "db.cc")


def test_ambiguous_source_site_id_never_counts_as_same_site():
    data = fixture()
    data["db.cso"].append({"ID": "10", "ID Cty": "999"})
    result = audit(data)
    matched = next(
        c for c in result["candidates"]
        if c["source_row_number"] == 7 and c["certificate_legacy_id"] == 200
    )
    assert matched["classification"] == "SITE_UNRESOLVED"
    assert matched["ddk_site_lookup"] == "AMBIGUOUS"
    assert matched["certificate_site_lookup"] == "AMBIGUOUS"
    assert matched["ddk_company_vs_site"] == "UNRESOLVED"


def test_absent_site_owner_identity_is_unresolved_not_same_site():
    data = fixture()
    data["db.cso"] = [data["db.cso"][1]]
    matched = next(
        c for c in audit(data)["candidates"]
        if c["source_row_number"] == 7 and c["certificate_legacy_id"] == 200
    )
    assert matched["classification"] == "SITE_UNRESOLVED"
    assert matched["ddk_site_lookup"] == "MISSING"


def test_company_reference_missing_or_inconsistent_is_visible():
    data = fixture()
    data["db.cty"] = []
    result = audit(data)
    matched = next(c for c in result["candidates"] if c["certificate_legacy_id"] == 201)
    assert matched["ddk_company_lookup"] == "MISSING"
    assert matched["ddk_company_vs_site"] == "UNRESOLVED"

    data = fixture()
    data["db.cso"][0]["ID Cty"] = "2"
    result = audit(data)
    matched = next(c for c in result["candidates"] if c["certificate_legacy_id"] == 201)
    assert matched["ddk_company_vs_site"] == "MISMATCH"
    assert result["id_cc_columns"][1]["counts"]["ddk_company_vs_site_mismatch"] == 2


def test_reverse_field_missing_cannot_be_reported_as_blank_source_fk():
    data = fixture()
    del data["db.cc"][0]["ID DDK"]
    result = audit(data)
    matched = next(
        c for c in result["candidates"]
        if c["source_row_number"] == 7 and c["certificate_legacy_id"] == 200
    )
    assert matched["reverse_relation"] == "REVERSE_FIELD_UNAVAILABLE"
    assert result["id_cc_columns"][0]["counts"]["reverse_field_unavailable"] >= 1


def test_source_semicolon_cells_create_independent_candidate_tokens():
    data = fixture()
    data["db.dkkd"][0]["ID CC [excel_column=4]"] = "200; 201; 202"
    result = audit(data)
    assert result["candidate_count"] == 9
    tokens = [
        c for c in result["candidates"]
        if c["source_row_number"] == 7 and c["excel_column"] == 4
    ]
    assert [c["certificate_legacy_id"] for c in tokens] == [200, 201, 202]
    assert [c["raw_fk_token"] for c in tokens] == ["200", "201", "202"]
    assert [c["source_token_index"] for c in tokens] == [1, 2, 3]
    assert all(c["source_token_count"] == 3 for c in tokens)
    assert all(c["raw_fk"] == "200; 201; 202" for c in tokens)
    assert result["id_cc_columns"][0]["counts"]["multi_id_cells"] == 1
    assert result["id_cc_columns"][0]["counts"]["candidate_tokens"] == 4


def test_audit_does_not_drop_empty_or_malformed_semicolon_components():
    assert split_idcc_references("17; 29") == ["17", "29"]
    assert split_idcc_references("17;; 29;") == ["17", "", "29", ""]
    data = fixture()
    data["db.dkkd"][0]["ID CC [excel_column=4]"] = "200;; 201"
    result = audit(data)
    tokens = [
        c for c in result["candidates"]
        if c["source_row_number"] == 7 and c["excel_column"] == 4
    ]
    assert len(tokens) == 3
    assert tokens[1]["classification"] == "NONLITERAL_FK"
    assert tokens[1]["raw_fk_token"] == ""
    assert tokens[2]["certificate_legacy_id"] == 201


def test_source_header_group_is_recorded_without_business_role_approval():
    data = fixture()
    result = audit(data, header_evidence={"id_cc_columns": [
        {"ordinal": 4, "observed_group_header": "GMP"},
        {"ordinal": 5, "observed_group_header": "GLP"},
        {"ordinal": 6, "observed_group_header": "GSP"},
        {"ordinal": 7, "observed_group_header": "GDP"},
    ]})
    assert [x["observed_group_header"] for x in result["id_cc_columns"]] == [
        "GMP", "GLP", "GSP", "GDP"
    ]
    assert all(x["owner_role"] == "UNVERIFIED" for x in result["id_cc_columns"])
    assert result["approval_status"] == "NOT_APPROVED_NO_RELATIONSHIPS_CREATED"

    matched = next(
        c for c in result["candidates"]
        if c["source_row_number"] == 7 and c["excel_column"] == 5
    )
    assert matched["certificate_type_vs_source_header"] == "MATCH"
    mismatch = next(
        c for c in result["candidates"]
        if c["source_row_number"] == 8 and c["excel_column"] == 5
    )
    assert mismatch["certificate_type_vs_source_header"] == "MISMATCH"
    assert result["id_cc_columns"][1]["counts"]["source_type_mismatch"] == 1


def test_certificate_company_is_compared_independently_of_site_and_reverse_ddk():
    data = fixture()
    data["db.cty"].append({"ID": "2"})
    data["db.cc"][0]["ID CTY"] = "2"
    mismatch = next(
        c for c in audit(data)["candidates"]
        if c["source_row_number"] == 7 and c["certificate_legacy_id"] == 200
    )
    assert mismatch["classification"] == "SAME_SITE"
    assert mismatch["certificate_company_lookup"] == "UNIQUE"
    assert mismatch["certificate_company_vs_ddk"] == "MISMATCH"

    data["db.cc"][0]["ID CTY"] = "1"
    match = next(
        c for c in audit(data)["candidates"]
        if c["source_row_number"] == 7 and c["certificate_legacy_id"] == 200
    )
    assert match["certificate_company_vs_ddk"] == "MATCH"

    del data["db.cc"][0]["ID CTY"]
    unresolved = next(
        c for c in audit(data)["candidates"]
        if c["source_row_number"] == 7 and c["certificate_legacy_id"] == 200
    )
    assert unresolved["certificate_company_vs_ddk"] == "UNRESOLVED"


def grouped_ddk_source_fixture():
    group_fields = [
        "ID CC", "PHẠM VI CHỨNG NHẬN",
        "TIÊU CHUẨN ÁP DỤNG", "HOẠT ĐỘNG KINH DOANH",
    ]
    headers = ["ID", "ID CƠ SỞ", "ID CTY"] + group_fields * 4
    above = [""] * len(headers)
    for ordinal, role in [(4, "GMP"), (8, "GLP"), (12, "GSP"), (16, "GDP")]:
        above[ordinal - 1] = role
    # GLP and GDP contain independently populated fields despite empty ID CC.
    values = [
        "400", "10", "1",
        "200", "GMP physical scope", "WHO-GMP", "Sản xuất thuốc",
        "", "GLP standalone scope", "GLP", "",
        "202", "", "", "",
        "", "", "", "Bán buôn thuốc",
    ]
    rows = [_core_source_row(headers, values, 7)]
    plans = discover_ddk_group_layout(headers, above)
    return rows, plans


def test_grouped_source_preserves_all_four_fields_even_without_id_cc():
    rows, plans = grouped_ddk_source_fixture()
    projected, counts = project_ddk_group_source(rows, plans)
    assert len(projected) == 1
    row = projected[0]
    assert row["source_row_number"] == 7
    assert row["ddk_legacy_id"] == 400
    groups = {g["source_group"]: g for g in row["groups"]}
    assert groups["GMP"]["fields"]["certificate_scope"]["raw_value"] == "GMP physical scope"
    assert groups["GMP"]["fields"]["applicable_standard"]["raw_value"] == "WHO-GMP"
    assert groups["GLP"]["fields"]["id_cc"]["raw_value"] == ""
    assert groups["GLP"]["fields"]["certificate_scope"]["raw_value"] == "GLP standalone scope"
    assert groups["GLP"]["has_companion_without_id_cc"]
    assert groups["GDP"]["fields"]["id_cc"]["raw_value"] == ""
    assert groups["GDP"]["fields"]["business_activity"]["raw_value"] == "Bán buôn thuốc"
    assert groups["GDP"]["has_companion_without_id_cc"]
    assert groups["GDP"]["fields"]["business_activity"]["excel_column"] == 19
    totals = {item["source_group"]: item["counts"] for item in counts}
    assert totals["GMP"]["id_cc_populated"] == 1
    assert totals["GDP"]["business_activity_populated"] == 1
    assert totals["GDP"]["companion_without_id_cc"] == 1


def test_grouped_projection_is_preserved_in_readonly_audit_without_creating_links():
    rows, plans = grouped_ddk_source_fixture()
    data = fixture()
    data["db.dkkd"] = rows
    result = audit(data, header_evidence={"id_cc_columns": plans})
    assert result["schema"] == "GXP_DDK_IDCC_PHYSICAL_REVIEW_V3"
    assert result["grouped_source_status"] == "COMPLETE_SOURCE_GROUP_PROJECTION"
    assert len(result["grouped_source_rows"]) == 1
    assert result["candidate_count"] == 2
    assert result["approval_status"] == "NOT_APPROVED_NO_RELATIONSHIPS_CREATED"
    assert result["grouped_source_rows"][0]["groups"][3]["fields"]["business_activity"]["raw_value"]
    assert not any(c["excel_column"] == 16 for c in result["candidates"])


def test_group_layout_binds_explicit_heading_not_group_position():
    rows, plans = grouped_ddk_source_fixture()
    headers = ["ID", "ID CƠ SỞ", "ID CTY"] + [
        name for _ in range(4) for name in
        ["ID CC", "PHẠM VI CHỨNG NHẬN", "TIÊU CHUẨN ÁP DỤNG", "HOẠT ĐỘNG KINH DOANH"]
    ]
    above = [""] * len(headers)
    for ordinal, role in [(4, "GDP"), (8, "GSP"), (12, "GLP"), (16, "GMP")]:
        above[ordinal - 1] = role
    rearranged = discover_ddk_group_layout(headers, above)
    assert [(p["ordinal"], p["observed_group_header"]) for p in rearranged] == [
        (4, "GDP"), (8, "GSP"), (12, "GLP"), (16, "GMP")
    ]


def test_incomplete_group_or_missing_companion_cell_fails_closed():
    rows, plans = grouped_ddk_source_fixture()
    broken = copy.deepcopy(rows)
    del broken[0]["HOẠT ĐỘNG KINH DOANH [excel_column=19]"]
    with pytest.raises(MissingPhysicalEvidence, match="Missing preserved physical source field"):
        project_ddk_group_source(broken, plans)
    headers = ["ID", "ID CƠ SỞ", "ID CTY"] + [
        name for _ in range(4) for name in
        ["ID CC", "PHẠM VI CHỨNG NHẬN", "TIÊU CHUẨN ÁP DỤNG", "HOẠT ĐỘNG KINH DOANH"]
    ]
    headers[16] = "WRONG SCOPE FIELD"
    above = [""] * len(headers)
    for c, role in [(4, "GMP"), (8, "GLP"), (12, "GSP"), (16, "GDP")]:
        above[c-1] = role
    with pytest.raises(MissingPhysicalEvidence, match="Incomplete db.dkkd"):
        discover_ddk_group_layout(headers, above)


def test_grouped_source_is_unavailable_without_proven_header_layout():
    result = audit(fixture())
    assert result["grouped_source_status"] == "UNAVAILABLE_REQUIRES_PHYSICAL_HEADER_BAND"
    assert result["grouped_source_rows"] == []


def test_raw_value2_group_cells_preserve_source_whitespace_not_shared_normalization():
    assert source_value2_text("  Certificate scope\n") == "  Certificate scope\n"
    assert source_value2_text(17.0) == "17"
    fields = ["ID CC", "PHẠM VI CHỨNG NHẬN", "TIÊU CHUẨN ÁP DỤNG", "HOẠT ĐỘNG KINH DOANH"]
    headers = ["ID", "ID CƠ SỞ", "ID CTY"] + fields * 4
    band = [""] * len(headers)
    for col, label in [(4, "GMP"), (8, "GLP"), (12, "GSP"), (16, "GDP")]:
        band[col - 1] = label
    plans = discover_ddk_group_layout(headers, band)
    values = [
        "400", "10", "1",
        " 200 ; 201 ", "  GMP scope\n", " WHO-GMP ", " Sản xuất  ",
        "", "   ", " GLP ", "",
        "", "", "", "",
        "", "", "", " Bán buôn\n",
    ]
    from backend.app.domain.legacy_snapshot import _core_header_plan
    record = capture_ddk_source_row(headers, values, 7, _core_header_plan(headers), plans)
    assert record["ID CC [excel_column=4]"] == " 200 ; 201 "
    assert record["PHẠM VI CHỨNG NHẬN [excel_column=5]"] == "  GMP scope\n"
    assert record["TIÊU CHUẨN ÁP DỤNG [excel_column=6]"] == " WHO-GMP "
    assert record["HOẠT ĐỘNG KINH DOANH [excel_column=19]"] == " Bán buôn\n"
    rows, counts = project_ddk_group_source([record], plans)
    group = rows[0]["groups"][0]
    assert group["fields"]["certificate_scope"]["raw_value"] == "  GMP scope\n"
    assert counts[0]["counts"]["id_cc_populated"] == 1
    assert counts[1]["counts"].get("certificate_scope_populated", 0) == 0
    data = fixture()
    data["db.dkkd"] = [record]
    reviewed = audit(data, header_evidence={"id_cc_columns": plans})
    tokens = [c for c in reviewed["candidates"] if c["excel_column"] == 4]
    assert [t["raw_fk_token"] for t in tokens] == ["200", "201"]
    assert all(t["raw_fk"] == " 200 ; 201 " for t in tokens)
