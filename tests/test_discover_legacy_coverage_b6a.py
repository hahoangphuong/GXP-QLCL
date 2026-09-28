from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json

import pytest

from backend.app.domain.legacy_snapshot_v2 import snapshot_bytes
from tools.discover_legacy_coverage_b6a import (
    CHAINS, ROOT, SNAPSHOT_SHA256, WORKBOOK_SHA256, _db_ktra_eligible_rows,
    _crosswalk_row, _minutes_numeric_conversion, _repeatable_crosswalk, _ttvien_evidence,
    _lineage, build_reports,
)


def _headers(name: str) -> list[str]:
    result: list[str] = []
    for chain in CHAINS:
        if chain["sheet"] == name:
            for label, _occurrence in chain["headers"]:
                if label not in result:
                    result.append(label)
    return result


def _snapshot() -> dict[str, object]:
    sheets = []
    for name in sorted({chain["sheet"] for chain in CHAINS}):
        if name == "TTviên":
            header = {4: "HỌ TÊN", 6: None, 7: "CHỨC DANH", 8: "ĐƠN VỊ", 14: "Ngừng hoạt động", 16: "Chuyên môn"}
            rows = [_row(number, {4: None, 6: None}) for number in range(1, 385)]
            rows[4] = _row(5, header)
            groups = [*range(6, 54), *range(59, 90), *range(95, 144), *range(148, 177), *range(182, 385)]
            for index, number in enumerate(groups):
                rows[number - 1] = _row(number, {3: index + 1, 4: None if number in {53, 384} else "Ông", 5: "DS", 6: f"Name {number}", 7: "Position", 8: "Unit", 14: None, 16: f"Specialty {index % 7}" if index < 38 else None})
            sheets.append({"sheet_name": name, "raw_rows": rows})
            continue
        labels = _headers(name)
        header_row = 5 if name == "TTviên" else 4
        header_cells = [{"column_ordinal": index, "raw_value": label} for index, label in enumerate(labels, 1)]
        values = [{"column_ordinal": index, "raw_value": f"{name}-{index}"} for index, _label in enumerate(labels, 1)]
        if name == "db.ktra":
            values[labels.index("ID")]["raw_value"] = 1
            values[labels.index("LOẠI KT")]["raw_value"] = "Tái"
            values[labels.index("ID CƠ SỞ")]["raw_value"] = 2
            values[labels.index("Q. định")]["raw_value"] = "QD-1"
            values[labels.index("B. bản")]["raw_value"] = None
            values[labels.index("T.tra viên")]["raw_value"] = "Team A\nTeam B"
        sheets.append({"sheet_name": name, "raw_rows": [{"source_row_number": header_row, "cells": header_cells}, {"source_row_number": header_row + 1, "cells": values}]})
    return {"schema_version": "legacy-workbook-snapshot/v2", "workbook": {"sha256": "w" * 64}, "sheets": sheets}


def _row(number: int, values: dict[int, object]) -> dict[str, object]:
    complete = {column: values.get(column) for column in range(3, 17)}
    return {"source_row_number": number, "cells": [{"column_ordinal": column, "raw_value": value} for column, value in complete.items()]}


def _reports(snapshot: dict[str, object]):
    return build_reports(snapshot, snapshot_sha256=sha256(snapshot_bytes(snapshot)).hexdigest(), workbook_sha256="w" * 64)


def _record(matrix, domain):
    return next(item for item in matrix["records"] if item["domain"] == domain)


def test_reports_are_deterministic_and_do_not_claim_database_inspection():
    snapshot = _snapshot()
    first = _reports(snapshot)
    assert first == _reports(deepcopy(snapshot))
    assert first[0]["provenance"]["database_mutated"] is False
    assert first[0]["provenance"]["database_inspection"] == "NOT_PERFORMED_NO_EXPLICIT_DATABASE_URL"
    assert all(record["state"]["current_rehearsal_verification"] == "NOT_CHECKED" for record in first[4]["records"])


def test_snapshot_and_workbook_lineage_fail_closed():
    snapshot = _snapshot(); digest = sha256(snapshot_bytes(snapshot)).hexdigest()
    with pytest.raises(ValueError, match="workbook lineage"):
        build_reports(snapshot, snapshot_sha256=digest, workbook_sha256="x" * 64)
    with pytest.raises(ValueError, match="provenance"):
        build_reports(snapshot, snapshot_sha256="0" * 64, workbook_sha256="w" * 64)


def test_field_region_evidence_is_column_specific_and_multifield_is_explicit():
    matrix, *_ = _reports(_snapshot())
    decision = _record(matrix, "inspection_decisions")["source_evidence"]
    minutes = _record(matrix, "inspection_minutes")["source_evidence"]
    team = _record(matrix, "inspection_teams")["source_evidence"]
    assert decision["fields"][0]["source_header"]["header"] == "Q. định"
    assert decision["fields"][0]["nonblank_count"] == 1
    assert minutes["fields"][0]["nonblank_count"] == 0
    assert team["fields"][0]["source_state_counts"] == {"TEXT_MULTILINE": 1}
    outcome = _record(matrix, "inspection_outcomes")["source_evidence"]
    assert outcome["region_kind"] == "MULTI_FIELD_REGION"
    assert len(outcome["fields"]) == 3


def test_ttvien_semantic_coordinates_use_c6_not_layout_header_c4():
    snapshot = _snapshot(); digest = sha256(snapshot_bytes(snapshot)).hexdigest()
    evidence = _ttvien_evidence(snapshot, digest)
    full_name = next(item for item in evidence["fields"] if item["semantic_field"] == "full_name")
    specialty = next(item for item in evidence["fields"] if item["semantic_field"] == "professional_specialty")
    assert full_name["semantic_column_ordinal"] == 6
    assert full_name["layout_header_evidence"]["column_ordinal"] == 4
    assert evidence["aggregate"]["migration_eligible_rows"] == 358
    assert specialty["nonblank_count"] == 38
    assert specialty["distinct_count"] == 7


def test_db_ktra_population_excludes_invalid_id_and_missing_required_context():
    snapshot = _snapshot()
    sheet = next(item for item in snapshot["sheets"] if item["sheet_name"] == "db.ktra")
    header = sheet["raw_rows"][0]["cells"]
    columns = {cell["raw_value"]: cell["column_ordinal"] for cell in header}
    sheet["raw_rows"].extend([
        _row(6, {columns["ID"]: "not-an-id", columns["LOẠI KT"]: "Tái", columns["ID CƠ SỞ"]: 2}),
        _row(7, {columns["ID"]: 2, columns["LOẠI KT"]: "-", columns["ID CƠ SỞ"]: 2}),
        _row(8, {columns["ID"]: 3, columns["LOẠI KT"]: "Tái", columns["ID CƠ SỞ"]: ""}),
    ])
    assert len(_db_ktra_eligible_rows(snapshot)) == 1


def test_b6a_uses_only_public_snapshot_v2_coordinate_and_excel_helpers():
    source = (ROOT / "tools/discover_legacy_coverage_b6a.py").read_text(encoding="utf-8")
    assert "legacy_inspection_team import" not in source
    for helper in ("snapshot_columns", "snapshot_cell_value", "substantive_source_value", "excel_serial_date"):
        assert helper in source


def test_b6a_numeric_contract_is_date_only_without_invented_time_or_timezone():
    _matrix, _summary, _questions, _lineage, _state, crosswalk = _reports(_snapshot())
    contract = crosswalk["numeric_conversion_contract"]
    rendered = json.dumps(contract, ensure_ascii=False).lower()
    assert contract["owner"] == "backend.app.domain.legacy_db_ktra_source_v2.excel_serial_date"
    assert contract["canonical_precision"] == "DATE_ONLY"
    assert contract["recorded_time"] is None
    assert "utc" not in rendered
    assert "midnight" not in rendered
    assert "no clock time or timezone is invented" in contract["output"]
    assert _minutes_numeric_conversion(45000) == ("15/03/2023", "NUMERIC_CONVERTED_EXCEL_SERIAL_DATE")


def test_roles_lineage_state_and_count_denominations_are_explicit():
    matrix, _summary, questions, lineage, state, _crosswalk = _reports(_snapshot())
    decision = _record(matrix, "inspection_decisions")
    team = _record(matrix, "inspection_teams")
    personnel = _record(matrix, "personnel")
    assert decision["semantic_parser_owner"] != decision["planner_owner"]
    assert decision["planner_owner"] != decision["writer_owner"]
    assert decision["candidate_count_evidence"]["evidence_type"] == "CODE_FENCE_EXPECTATION"
    assert decision["candidate_count_evidence"]["old_v1_rehearsal_write_candidate_fence"] == 1219
    assert "v2_source_occurrences" in decision["candidate_count_evidence"]
    assert team["state_vector"]["migration_status"] == "IMPLEMENTATION_VERIFIED_REHEARSAL_NOT_APPLIED"
    assert personnel["state_vector"]["migration_status"] == "HISTORICALLY_VERIFIED_NOT_RECHECKED"
    assert any(item["tool"] == "tools/apply_db_ktra_repeatable_semantics.py" and item["snapshot_format"] == "V1" for item in lineage["tools"])
    assert questions["defects_or_architecture_drift"][0]["classification"] == "BLOCKS_B6B"
    assert matrix["sheet_classification_counts"] != matrix["field_region_classification_counts"]
    assert len(state["records"]) == len(matrix["records"])


def test_canonical_snapshot_population_and_v1_v2_drift_when_available():
    path = ROOT / "artifacts/phase3c/legacy_snapshot_v2.json"
    if not path.exists():
        pytest.skip("local canonical Snapshot V2 is intentionally not tracked")
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    assert len(_db_ktra_eligible_rows(snapshot)) == 1496
    crosswalk = _repeatable_crosswalk(snapshot)
    assert crosswalk["provenance"]["shared_legacy_ids"] == 1533
    assert crosswalk["fields"]["decisions"]["v1_source_occurrences"] == 1295
    assert crosswalk["fields"]["decisions"]["v2_source_occurrences"] == 1295
    assert crosswalk["fields"]["minutes"]["v1_source_occurrences"] == 1162
    assert crosswalk["fields"]["minutes"]["v2_source_occurrences"] == 1162
    assert crosswalk["fields"]["minutes"]["conversion_classification_counts"]["NUMERIC_DATE_EQUIVALENT"] == 1149
    for field in ("decisions", "minutes"):
        assert sum(crosswalk["fields"][field]["classification_counts"].values()) == 1533
    lineage = _lineage(crosswalk)
    repeatable = next(item for item in lineage["tools"] if item["tool"] == "tools/plan_db_ktra_repeatable_semantics.py")
    assert repeatable["source_semantics_status"] == ["SOURCE_SEMANTICS_EQUIVALENT", "REPRESENTATION_EQUIVALENT_AFTER_PROVEN_CONVERSION"]
    assert repeatable["current_rehearsal_candidate_counts"] == "NOT_CHECKED_NO_EXPLICIT_DATABASE_URL"
    assert _minutes_numeric_conversion(45000) == ("15/03/2023", "NUMERIC_CONVERTED_EXCEL_SERIAL_DATE")
    assert _minutes_numeric_conversion(45000.5)[1] == "NUMERIC_UNRESOLVED"


def test_crosswalk_keeps_source_parity_separate_from_write_candidate_fences():
    same = _crosswalk_row(1, "2023-03-15T00:00:00Z", 45000, kind="minutes")
    mismatch = _crosswalk_row(2, "2023-03-16T00:00:00Z", 45000, kind="minutes")
    decision = _crosswalk_row(3, "1/QĐ ngày 01/01/2024", "1/QĐ ngày 01/01/2024", kind="decisions")
    assert same["classification"] == "REPRESENTATION_ONLY_DIFFERENCE"
    assert same["conversion_classification"] == "NUMERIC_DATE_EQUIVALENT"
    assert mismatch["classification"] == "PARSER_SEMANTIC_DIFFERENCE"
    assert mismatch["conversion_classification"] == "NUMERIC_DATE_MISMATCH"
    assert decision["classification"] == "EXACT_SEMANTIC_MATCH"


def test_excel_serial_bridge_is_limited_to_proven_numeric_v2_minutes():
    v1_midnight = "2023-03-15T00:00:00Z"

    numeric = _crosswalk_row(1, v1_midnight, 45000, kind="minutes")
    textual_date = _crosswalk_row(2, v1_midnight, "15/03/2023", kind="minutes")
    explicit_datetime = _crosswalk_row(3, v1_midnight, "2023-03-15T00:00:00Z", kind="minutes")
    fractional = _crosswalk_row(4, v1_midnight, 45000.5, kind="minutes")

    assert numeric["classification"] == "REPRESENTATION_ONLY_DIFFERENCE"
    assert numeric["conversion_classification"] == "NUMERIC_DATE_EQUIVALENT"
    assert textual_date["classification"] == "PARSER_SEMANTIC_DIFFERENCE"
    assert textual_date["conversion_classification"] == "SOURCE_DIFFERENCE"
    assert explicit_datetime["conversion_classification"] != "NUMERIC_DATE_EQUIVALENT"
    assert explicit_datetime["classification"] == "EXACT_SEMANTIC_MATCH"
    assert fractional["conversion_classification"] == "NUMERIC_UNRESOLVED"


def test_snapshot_tracking_status_is_explicit_when_no_repository_probe_was_requested():
    matrix, *_ = _reports(_snapshot())
    assert matrix["provenance"]["git_tracking_status"] == "NOT_CHECKED"


def test_local_canonical_snapshot_tracking_is_explicit_when_available():
    path = ROOT / "artifacts/phase3c/legacy_snapshot_v2.json"
    if not path.exists():
        pytest.skip("local canonical Snapshot V2 is intentionally not tracked")
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    matrix, *_ = build_reports(snapshot, snapshot_sha256=SNAPSHOT_SHA256, workbook_sha256=WORKBOOK_SHA256, snapshot_path=path)
    assert matrix["provenance"]["git_tracking_status"] == "LOCAL_UNTRACKED_CANONICAL_ARTIFACT"
