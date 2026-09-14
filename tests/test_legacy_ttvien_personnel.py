from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest

from backend.app.domain.legacy_ttvien_personnel import _substantive, build_personnel_plan, preview_team_crosswalk, split_approved_name_markers
from backend.app.domain.legacy_snapshot_v2 import snapshot_bytes


CANONICAL_SNAPSHOT_SHA256 = "484cf37603aacc5ff01a7bde5ffab01ed444748d5c7b1a0b30e7fc3a04936caa"
CANONICAL_PLANNER_SHA256 = "f2a5ab81dd768aed45b4706167518b8c11378b1264ad82e3486eca54ef34a6a2"


@pytest.fixture(scope="module")
def canonical_payload() -> tuple[dict, dict, dict]:
    snapshot = json.loads(Path("artifacts/phase3c/legacy_snapshot_v2.json").read_text(encoding="utf-8"))
    plan = build_personnel_plan(snapshot, expected_snapshot_sha256=CANONICAL_SNAPSHOT_SHA256)
    return snapshot, plan, preview_team_crosswalk(snapshot, plan)


def _row(number: int, *, name: str | None, honorific: str | None = "Ông", inactive: str | None = None) -> dict:
    values = {3: 1, 4: honorific, 5: "Ds.", 6: name, 7: "Position", 8: "Unit", 9: None, 10: None, 11: None, 12: None, 13: None, 14: inactive, 15: None, 16: None}
    return {"source_row_number": number, "cells": [{"column_ordinal": column, "raw_value": value} for column, value in values.items()]}


def _snapshot(rows: list[dict]) -> dict:
    return {"schema_version": "legacy-workbook-snapshot/v2", "workbook": {"sha256": "a" * 64}, "sheets": [{"sheet_name": "TTviên", "raw_rows": rows}]}


def test_approved_markers_only_change_presentation():
    assert split_approved_name_markers("PCT. Nguyễn Văn A*") == ("Nguyễn Văn A", True, True)
    assert split_approved_name_markers("Nguyễn Văn A") == ("Nguyễn Văn A", False, False)


def test_plan_rejects_wrong_provenance():
    try:
        build_personnel_plan(_snapshot([]), expected_snapshot_sha256="not-a-digest")
    except ValueError as error:
        assert "provenance" in str(error)
    else:
        raise AssertionError("expected provenance failure")


def test_plan_rejects_incomplete_roster_instead_of_creating_partial_import():
    snapshot = _snapshot([_row(6, name="PCT. Nguyễn Văn A*")])
    try:
        build_personnel_plan(snapshot, expected_snapshot_sha256=sha256(snapshot_bytes(snapshot)).hexdigest())
    except ValueError as error:
        assert "eligible-person invariant" in str(error)
    else:
        raise AssertionError("expected roster invariant failure")


def test_canonical_snapshot_has_exactly_one_planned_record_for_each_person_row(canonical_payload):
    _, plan, _ = canonical_payload
    assert plan["database_accessed"] is False
    assert len(plan["records"]) == 358
    assert len({record["source_row_number"] for record in plan["records"]}) == 358
    assert sum(record["pct_marker"] for record in plan["records"]) == 5
    assert sum(record["star_marker"] for record in plan["records"]) == 4


def test_canonical_plan_contract_and_travel_vendor_region(canonical_payload):
    _, plan, _ = canonical_payload
    assert plan["classification_counts"] == {
        "IMPORT_CANDIDATE": 358,
        "SOURCE_CONFLICT": 0,
        "SOURCE_UNRESOLVED": 0,
        "NON_PERSONNEL_ROW": 2,
        "LAYOUT_ROW": 25,
    }
    assert plan["group_counts"] == {
        "DRUG_ADMINISTRATION_AND_TRADITIONAL_MEDICINE": 46,
        "NATIONAL_INSTITUTE_OF_DRUG_QUALITY_CONTROL": 31,
        "HO_CHI_MINH_CITY_DRUG_QUALITY_CONTROL_INSTITUTE": 49,
        "NATIONAL_INSTITUTE_FOR_VACCINE_AND_BIOLOGICALS_CONTROL": 29,
        "PROVINCIAL_HEALTH_DEPARTMENTS": 203,
    }
    assert plan["inactive_count"] == 71
    assert plan["separate_regions"]["travel_vendor"] == {
        "source_sheet": "TTviên",
        "columns": [18, 19, 20, 21, 22],
        "row_start": 6,
        "row_end": 14,
        "migration_status": "SEPARATE_DOMAIN",
    }


def test_c16_contract_and_source_value_are_preserved(canonical_payload):
    snapshot, plan, _ = canonical_payload
    assert plan["c16_contract"] == {
        "source_header": "Chuyên môn",
        "business_semantic": "inspector professional specialty",
        "nonblank_count": 38,
        "distinct_count": 7,
        "canonical_owner": "InspectorProfile",
        "canonical_field": "professional_specialty",
        "datatype": "String(255)",
        "migration_status": "IMPORT_TYPED",
        "filter_query_usage": "future inspector-specialty workflow filters",
        "raw_preservation": "preserve exact source value",
    }
    source_rows = {
        row["source_row_number"]: {cell["column_ordinal"]: cell["raw_value"] for cell in row["cells"]}
        for sheet in snapshot["sheets"] if sheet["sheet_name"] == "TTviên"
        for row in sheet["raw_rows"]
    }
    record = next(record for record in plan["records"] if _substantive(source_rows[record["source_row_number"]][16]))
    assert record["professional_specialty"] == source_rows[record["source_row_number"]][16]


def test_canonical_active_and_inactive_markers(canonical_payload):
    _, plan, _ = canonical_payload
    inactive = next(record for record in plan["records"] if record["inactive_marker_raw"] == "x")
    active = next(record for record in plan["records"] if record["inactive_marker_raw"] in (None, ""))
    assert inactive["is_active"] is False
    assert active["is_active"] is True


def test_valid_snapshot_with_wrong_digest_fails_closed_in_domain_owner():
    snapshot = _snapshot([])
    try:
        build_personnel_plan(snapshot, expected_snapshot_sha256="a" * 64)
    except ValueError as error:
        assert "provenance" in str(error)
    else:
        raise AssertionError("expected canonical snapshot mismatch")


def test_sensitive_presence_excludes_blank_and_sentinel_source_values():
    assert all(not _substantive(value) for value in (None, "", "  ", "-", "???"))
    assert _substantive("observed") is True


def test_crosswalk_refuses_cleaned_name_collision_without_raw_marker_evidence():
    plan = {"records": [
        {"legacy_raw_full_name": "PCT. Nguyễn Văn A", "cleaned_full_name": "Nguyễn Văn A", "pct_marker": True, "star_marker": False, "source_provenance_hash": "one"},
        {"legacy_raw_full_name": "Nguyễn Văn A*", "cleaned_full_name": "Nguyễn Văn A", "pct_marker": False, "star_marker": True, "source_provenance_hash": "two"},
    ]}
    snapshot = {"sheets": [{"sheet_name": "db.ktra", "raw_rows": [
        {"source_row_number": 4, "cells": [{"column_ordinal": 16, "raw_value": "T.tra viên"}]},
        {"source_row_number": 5, "cells": [{"column_ordinal": 16, "raw_value": "Nguyễn Văn A"}]},
    ]}]}
    preview = preview_team_crosswalk(snapshot, plan)
    assert preview["records"][0]["classification"] == "AMBIGUOUS"


def test_canonical_crosswalk_contract(canonical_payload):
    _, _, preview = canonical_payload
    assert preview["classification_counts"] == {
        "EXACT_RAW_MATCH": 5037,
        "EXACT_AFTER_PCT_MARKER_HANDLING": 0,
        "EXACT_AFTER_STAR_MARKER_HANDLING": 0,
        "ZERO_MATCH": 121,
        "AMBIGUOUS": 0,
        "DUPLICATE_SOURCE_OCCURRENCE": 4,
    }
    assert preview["distinct_planned_person_records_referenced"] == 337


def test_selected_canonical_team_rows_preserve_raw_token_identity(canonical_payload):
    _, plan, preview = canonical_payload
    raw_personnel = {record["legacy_raw_full_name"]: record["source_provenance_hash"] for record in plan["records"]}
    rows = {row: [record for record in preview["records"] if record["source_row_number"] == row] for row in (451, 605, 676)}
    assert rows[451][0]["classification"] == "ZERO_MATCH"
    assert rows[451][0]["raw_team_token"] not in raw_personnel
    for row_records in rows.values():
        for record in row_records:
            if record["classification"] == "EXACT_RAW_MATCH":
                assert record["raw_team_token"] in raw_personnel
                assert record["person_source_provenance_hash"] == raw_personnel[record["raw_team_token"]]


def test_duplicate_canonical_team_occurrences_retain_exact_raw_targets(canonical_payload):
    _, _, preview = canonical_payload
    for source_row_number in (915, 990):
        duplicates = [
            record
            for record in preview["records"]
            if record["source_row_number"] == source_row_number
            and record["classification"] == "DUPLICATE_SOURCE_OCCURRENCE"
        ]
        assert len(duplicates) == 2
        assert {record["member_ordinal"] for record in duplicates} == {3, 5}
        assert len({record["raw_team_token"] for record in duplicates}) == 1
        assert {record["match_basis"] for record in duplicates} == {"EXACT_RAW_MATCH"}
        assert len({record["person_source_provenance_hash"] for record in duplicates}) == 1
        assert duplicates[0]["person_source_provenance_hash"] is not None


def test_canonical_planner_payload_sha_and_sensitive_output_contract(canonical_payload):
    snapshot, plan, preview = canonical_payload
    payload = {**plan, "team_crosswalk_preview": preview}
    content = (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    assert sha256(content).hexdigest() == CANONICAL_PLANNER_SHA256
    assert sha256(snapshot_bytes(snapshot)).hexdigest() == CANONICAL_SNAPSHOT_SHA256
    prohibited_fields = {
        "citizen_identity",
        "citizen_identity_issue_date",
        "citizen_identity_issuing_place",
        "payment",
        "airline_contact_like",
    }
    for record in plan["records"]:
        assert prohibited_fields.isdisjoint(record)
        assert set(record["sensitive_field_presence"]) == prohibited_fields
