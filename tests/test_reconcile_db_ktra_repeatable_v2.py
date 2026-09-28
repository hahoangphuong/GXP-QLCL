from __future__ import annotations

from datetime import date, time
from hashlib import sha256
import json
from pathlib import Path

import pytest

from backend.app.domain.legacy_db_ktra_repeatable_v2 import (
    excel_serial_minutes_representation_equivalent,
    normalize_v2_minutes_representation,
    parse_v2_repeatable_rows,
)
from backend.app.domain.legacy_db_ktra_source_v2 import excel_serial_date
from backend.app.domain.legacy_db_ktra_reconciliation import (
    parse_legacy_inspection_decisions,
    parse_legacy_minutes_records,
)
from backend.app.domain.legacy_snapshot_v2 import SCHEMA_VERSION, snapshot_bytes
from tools import reconcile_db_ktra_repeatable_v2 as verifier


def _cell(column: int, value: object) -> dict[str, object]:
    return {"column_ordinal": column, "raw_value": value}


def _snapshot(*rows: tuple[object, object, object, object, object]) -> tuple[dict[str, object], str]:
    header = ["ID", "LOẠI KT", "ID CƠ SỞ", "Q. định", "B. bản"]
    raw_rows = [{"source_row_number": 4, "cells": [_cell(index, value) for index, value in enumerate(header, start=1)]}]
    for source_row_number, values in enumerate(rows, start=5):
        raw_rows.append({"source_row_number": source_row_number, "cells": [_cell(index, value) for index, value in enumerate(values, start=1)]})
    payload = {"schema_version": SCHEMA_VERSION, "sheets": [{"sheet_name": "db.ktra", "raw_rows": raw_rows}]}
    return payload, sha256(snapshot_bytes(payload)).hexdigest()


def _canonical() -> dict[int, dict[str, object]]:
    return {
        1: {
            "case_id": "case-1",
            "inspection_plan_id": "plan-1",
            "inspection_outcome_id": "outcome-1",
            "plan": {"decision_reference": None, "decision_date": None, "decision_legacy_raw": None},
            "outcome": {"minutes_recorded_on": None, "minutes_recorded_time": None, "minutes_legacy_raw": None},
        }
    }


def _matching_rows() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    decisions = [
        {"id": "decision-1", "legacy_inspection_id": 1, "case_id": "case-1", "inspection_plan_id": "plan-1", "ordinal": 1, "reference": "2/QD", "decision_on": date(2026, 2, 2), "legacy_raw": "2/QD ngày 02/02/2026", "relation_type": "REPLACES", "related_decision_id": "decision-2"},
        {"id": "decision-2", "legacy_inspection_id": 1, "case_id": "case-1", "inspection_plan_id": "plan-1", "ordinal": 2, "reference": "1/QD", "decision_on": date(2026, 2, 1), "legacy_raw": "thay the QD số 1/QD ngày 01/02/2026", "relation_type": None, "related_decision_id": None},
    ]
    minutes = [
        {"id": "minutes-1", "legacy_inspection_id": 1, "case_id": "case-1", "inspection_outcome_id": "outcome-1", "ordinal": 1, "recorded_on": date(2026, 2, 1), "recorded_time": None, "precision": "DATE_ONLY", "source_format": "DMY_DATE", "legacy_raw": "01/02/2026"},
        {"id": "minutes-2", "legacy_inspection_id": 1, "case_id": "case-1", "inspection_outcome_id": "outcome-1", "ordinal": 2, "recorded_on": date(2026, 2, 2), "recorded_time": None, "precision": "DATE_ONLY", "source_format": "DMY_DATE", "legacy_raw": "02/02/2026"},
    ]
    return decisions, minutes


def _reconcile(
    snapshot: dict[str, object],
    digest: str,
    canonical: dict[int, dict[str, object]],
    decisions: list[dict[str, object]],
    minutes: list[dict[str, object]],
    *,
    topology: dict[str, object] | None = None,
    owner_integrity: dict[str, object] | None = None,
) -> dict[str, object]:
    integrity = owner_integrity or verifier._clean_owner_integrity(canonical)
    return verifier.build_reconciliation(
        snapshot,
        canonical,
        decisions,
        minutes,
        expected_snapshot_sha256=digest,
        topology_evidence=topology or verifier.topology_evidence_for_canonical(canonical, owner_integrity=integrity),
        owner_integrity=integrity,
    )


def _owner_rows(
    *,
    cases: list[dict[str, object]],
    plans: list[dict[str, object]] | None = None,
    outcomes: list[dict[str, object]] | None = None,
) -> tuple[dict[int, dict[str, object]], dict[str, object]]:
    canonical, integrity = verifier._canonical_owner_state(cases, plans or [], outcomes or [])
    return canonical, integrity


def test_v2_minutes_representation_adapter_is_narrow_and_fail_closed():
    assert normalize_v2_minutes_representation(45000) == ("15/03/2023", "NUMERIC_CONVERTED_EXCEL_SERIAL_DATE")
    assert normalize_v2_minutes_representation("01/02/2026") == ("01/02/2026", "UNCHANGED")
    assert normalize_v2_minutes_representation("-") == ("-", "UNCHANGED")
    assert normalize_v2_minutes_representation(45000.5)[1] == "NUMERIC_UNRESOLVED"
    assert excel_serial_date(45000) == date(2023, 3, 15)


def _numeric_minutes_expected() -> dict[str, object]:
    return {
        "recorded_on": date(2023, 3, 15),
        "recorded_time": None,
        "precision": "DATE_ONLY",
        "source_format": "DMY_DATE",
        "legacy_raw": "15/03/2023",
    }


def _historical_midnight_minutes() -> dict[str, object]:
    return {
        "recorded_on": date(2023, 3, 15),
        "recorded_time": time(0, 0),
        "precision": "DATE_TIME_LOCAL",
        "source_format": "ISO_OFFSET_DATETIME",
        "legacy_raw": "2023-03-15T00:00:00+00:00",
    }


def test_excel_serial_minutes_bridge_requires_proven_numeric_and_historical_midnight_lineage():
    expected = _numeric_minutes_expected()
    historical = _historical_midnight_minutes()
    assert excel_serial_minutes_representation_equivalent(
        source_representation="NUMERIC_CONVERTED_EXCEL_SERIAL_DATE",
        expected=expected,
        historical=historical,
    )
    for source_representation in ("UNCHANGED", "NUMERIC_UNRESOLVED"):
        assert not excel_serial_minutes_representation_equivalent(
            source_representation=source_representation,
            expected=expected,
            historical=historical,
        )
    for changed in (
        {**historical, "recorded_on": date(2023, 3, 16)},
        {**historical, "recorded_time": time(0, 1)},
        {**historical, "precision": "DATE_ONLY"},
        {**historical, "source_format": "DMY_DATE_TIME"},
        {**historical, "legacy_raw": "15/03/2023"},
    ):
        assert not excel_serial_minutes_representation_equivalent(
            source_representation="NUMERIC_CONVERTED_EXCEL_SERIAL_DATE",
            expected=expected,
            historical=changed,
        )


def test_reconciliation_reports_excel_serial_equivalence_without_suppressing_other_mismatches():
    snapshot, digest = _snapshot((1, "GMP", 1, "-", 45000))
    canonical = _canonical()
    minutes = [{
        "id": "minutes-1", "legacy_inspection_id": 1, "case_id": "case-1", "inspection_outcome_id": "outcome-1",
        "ordinal": 1, **_historical_midnight_minutes(),
    }]
    canonical[1]["outcome"] = {
        "minutes_recorded_on": date(2023, 3, 15),
        "minutes_recorded_time": time(0, 0),
        "minutes_legacy_raw": "2023-03-15T00:00:00+00:00",
    }
    report = _reconcile(snapshot, digest, canonical, [], minutes)
    assert report["minutes"]["classification_counts"]["EXCEL_SERIAL_DATE_REPRESENTATION_EQUIVALENT"] == 1
    assert report["compatibility_projection"]["minutes"] == {
        "EXCEL_SERIAL_DATE_REPRESENTATION_EQUIVALENT": 1
    }
    assert report["audit_result"] == "PASS"
    minutes[0]["recorded_time"] = time(0, 1)
    report = _reconcile(snapshot, digest, canonical, [], minutes)
    assert report["minutes"]["classification_counts"]["FIELD_MISMATCH"] == 1
    assert report["audit_result"] == "FAIL"


def test_repeatable_parser_accepts_only_one_proven_terminal_semicolon():
    base = parse_legacy_inspection_decisions("376/QD-QLD ngày 29/08/2016")
    terminal = parse_legacy_inspection_decisions("376/QD-QLD ngày 29/08/2016;")
    assert base["state"] == terminal["state"] == "KNOWN"
    assert base["occurrences"] == terminal["occurrences"]
    assert terminal["raw"] == "376/QD-QLD ngày 29/08/2016;"
    malformed = (
        ";376/QD-QLD ngày 29/08/2016",
        "376/QD-QLD ngày 29/08/2016;;",
        "376/QD-QLD ngày 29/08/2016; ;",
        "376/QD-QLD ngày 29/08/2016 &",
        "& 376/QD-QLD ngày 29/08/2016",
        "376/QD-QLD ngày 29/08/2016 và",
        "và 376/QD-QLD ngày 29/08/2016",
        "376/QD-QLD ngày 29/08/2016;; 377/QD-QLD ngày 30/08/2016",
    )
    assert all(parse_legacy_inspection_decisions(value)["state"] != "KNOWN" for value in malformed)


def test_repeatable_parser_preserves_substantive_separator_and_replacement_grammar():
    for value in (
        "376/QD-QLD ngày 29/08/2016; 377/QD-QLD ngày 30/08/2016",
        "376/QD-QLD ngày 29/08/2016 & 377/QD-QLD ngày 30/08/2016",
        "376/QD-QLD ngày 29/08/2016 và 377/QD-QLD ngày 30/08/2016",
    ):
        parsed = parse_legacy_inspection_decisions(value)
        assert parsed["state"] == "KNOWN"
        assert [item["ordinal"] for item in parsed["occurrences"]] == [1, 2]
    replacement = parse_legacy_inspection_decisions(
        "2/QD ngày 02/02/2026 (thay the QD số 1/QD ngày 01/02/2026)"
    )
    assert replacement["occurrences"][0]["relation_type"] == "REPLACES"


def test_textual_minutes_remain_raw_only():
    assert parse_legacy_minutes_records("Nguyễn Đức Toàn")["state"] == "RAW_ONLY"


def test_reconciliation_exactly_preserves_relation_and_repeated_minutes():
    snapshot, digest = _snapshot((1, "GMP", 1, "2/QD ngày 02/02/2026; thay the QD số 1/QD ngày 01/02/2026", "01/02/2026 & 02/02/2026"))
    decisions, minutes = _matching_rows()
    report = _reconcile(snapshot, digest, _canonical(), decisions, minutes)
    assert report["audit_result"] == "PASS"
    assert report["decisions"]["classification_counts"]["EXACT_MATCH"] == 2
    assert report["minutes"]["classification_counts"]["EXACT_MATCH"] == 2
    assert report["minutes"]["repeated_occurrence_ids"] == [{"legacy_inspection_id": 1, "ordinals": [1, 2]}]


def test_relation_target_with_same_reference_in_another_plan_is_not_equivalent():
    snapshot, digest = _snapshot((1, "GMP", 1, "2/QD ngày 02/02/2026; thay the QD số 1/QD ngày 01/02/2026", "-"))
    decisions, _minutes = _matching_rows()
    decisions[0]["related_decision_id"] = "other-plan-target"
    decisions.append({**decisions[1], "id": "other-plan-target", "inspection_plan_id": "other-plan"})
    report = _reconcile(snapshot, digest, _canonical(), decisions, [])
    assert report["decisions"]["classification_counts"]["RELATION_MISMATCH"] == 1


@pytest.mark.parametrize(
    ("mutator", "classification"),
    [
        (lambda decisions, minutes: decisions.pop(), "MISSING_IN_DB"),
        (lambda decisions, minutes: decisions.append({**decisions[0], "id": "extra", "ordinal": 3}), "EXTRA_IN_DB"),
        (lambda decisions, minutes: decisions[0].__setitem__("reference", "wrong"), "FIELD_MISMATCH"),
        (lambda decisions, minutes: decisions[0].__setitem__("inspection_plan_id", "wrong-plan"), "OWNER_MISMATCH"),
        (lambda decisions, minutes: decisions[0].__setitem__("related_decision_id", None), "RELATION_MISMATCH"),
    ],
)
def test_reconciliation_detects_each_structured_mismatch(mutator, classification):
    snapshot, digest = _snapshot((1, "GMP", 1, "2/QD ngày 02/02/2026; thay the QD số 1/QD ngày 01/02/2026", "01/02/2026 & 02/02/2026"))
    decisions, minutes = _matching_rows()
    mutator(decisions, minutes)
    report = _reconcile(snapshot, digest, _canonical(), decisions, minutes)
    assert report["audit_result"] == "FAIL"
    assert report["decisions"]["classification_counts"][classification] == 1


def test_owner_gap_and_source_unresolved_are_reported_without_auto_creation():
    snapshot, digest = _snapshot(
        (1, "GMP", 1, "1/QD ngày 01/02/2026", "01/02/2026"),
        (2, "GMP", 1, "unstructured", "unstructured"),
    )
    report = _reconcile(snapshot, digest, {}, [], [])
    assert report["decisions"]["classification_counts"]["CANONICAL_CASE_MISSING"] == 1
    assert report["decisions"]["classification_counts"]["SOURCE_UNRESOLVED"] == 1
    assert report["owners"]["canonical_owner_gaps"] == [1, 2]
    assert report["audit_result"] == "FAIL"


def test_missing_source_is_a_valid_zero_occurrence_but_existing_row_is_extra():
    snapshot, digest = _snapshot((1, "GMP", 1, "-", "-"))
    report = _reconcile(snapshot, digest, _canonical(), [], [])
    assert report["audit_result"] == "PASS"
    assert report["decisions"]["classification_counts"]["SOURCE_MISSING"] == 1
    assert report["minutes"]["classification_counts"]["SOURCE_MISSING"] == 1
    assert report["compatibility_projection"]["decisions"]["SOURCE_MISSING_NULL_EXACT"] == 1
    assert report["compatibility_projection"]["minutes"]["SOURCE_MISSING_NULL_EXACT"] == 1
    assert report["compatibility_projection"]["status"] == "PASS"
    decisions, minutes = _matching_rows()
    report = _reconcile(snapshot, digest, _canonical(), decisions[:1], minutes[:1])
    assert report["audit_result"] == "FAIL"
    assert report["decisions"]["classification_counts"]["EXTRA_IN_DB"] == 1
    assert report["minutes"]["classification_counts"]["EXTRA_IN_DB"] == 1


def test_case_universe_exactly_matches_effective_snapshot_ids():
    snapshot, digest = _snapshot((1, "GMP", 1, "-", "-"))
    report = _reconcile(snapshot, digest, _canonical(), [], [])
    universe = report["owners"]["case_universe"]
    assert universe["case_universe_status"] == "PASS"
    assert universe["source_case_count"] == universe["canonical_case_count"] == 1
    assert universe["source_case_legacy_id_set_sha256"] == universe["canonical_case_legacy_id_set_sha256"]
    assert universe["missing_canonical_case_ids"] == []
    assert universe["extra_canonical_case_ids"] == []


def test_duplicate_case_legacy_id_fails_closed_without_owner_overwrite():
    snapshot, digest = _snapshot((1, "GMP", 1, "-", "-"))
    canonical, integrity = _owner_rows(
        cases=[
            {"id": "case-1a", "legacy_inspection_id": 1},
            {"id": "case-1b", "legacy_inspection_id": 1},
        ]
    )
    report = _reconcile(snapshot, digest, canonical, [], [], owner_integrity=integrity)
    assert canonical == {}
    assert report["owners"]["owner_integrity"] == {
        "case_rows_with_legacy_id": 2,
        "distinct_case_legacy_ids": 1,
        "plan_rows_for_canonical_cases": 0,
        "outcome_rows_for_canonical_cases": 0,
        "duplicate_case_legacy_ids": [1],
        "duplicate_plan_case_ids": [],
        "duplicate_outcome_case_ids": [],
        "status": "FAIL",
    }
    assert report["owners"]["case_universe"]["case_universe_status"] == "PASS"
    assert report["audit_result"] == "FAIL"


def test_duplicate_physical_case_fails_when_distinct_legacy_id_universe_matches_source():
    snapshot, digest = _snapshot((1, "GMP", 1, "-", "-"), (2, "GMP", 1, "-", "-"))
    canonical, integrity = _owner_rows(
        cases=[
            {"id": "case-1a", "legacy_inspection_id": 1},
            {"id": "case-1b", "legacy_inspection_id": 1},
            {"id": "case-2", "legacy_inspection_id": 2},
        ]
    )
    report = _reconcile(snapshot, digest, canonical, [], [], owner_integrity=integrity)
    universe = report["owners"]["case_universe"]
    assert universe["source_case_count"] == universe["canonical_case_count"] == 2
    assert universe["case_universe_status"] == "PASS"
    assert report["owners"]["topology"]["case_count"] == 3
    assert report["owners"]["owner_integrity"]["duplicate_case_legacy_ids"] == [1]
    assert report["audit_result"] == "FAIL"


@pytest.mark.parametrize(
    ("owner_kind", "rows_key", "duplicate_key"),
    [
        ("plan", "plans", "duplicate_plan_case_ids"),
        ("outcome", "outcomes", "duplicate_outcome_case_ids"),
    ],
)
def test_multiple_physical_owner_rows_fail_closed_without_last_row_wins(owner_kind, rows_key, duplicate_key):
    snapshot, digest = _snapshot((1, "GMP", 1, "-", "-"))
    rows = [
        {"id": f"{owner_kind}-1a", "case_id": "case-1"},
        {"id": f"{owner_kind}-1b", "case_id": "case-1"},
    ]
    canonical, integrity = _owner_rows(
        cases=[{"id": "case-1", "legacy_inspection_id": 1}],
        **{rows_key: rows},
    )
    report = _reconcile(snapshot, digest, canonical, [], [], owner_integrity=integrity)
    assert f"inspection_{owner_kind}_id" not in canonical[1]
    assert report["owners"]["owner_integrity"][duplicate_key] == ["case-1"]
    assert report["audit_result"] == "FAIL"


def test_clean_raw_owner_topology_preserves_single_owner_behavior():
    canonical, integrity = _owner_rows(
        cases=[{"id": "case-1", "legacy_inspection_id": 1}],
        plans=[{"id": "plan-1", "case_id": "case-1"}],
        outcomes=[{"id": "outcome-1", "case_id": "case-1"}],
    )
    assert canonical[1]["inspection_plan_id"] == "plan-1"
    assert canonical[1]["inspection_outcome_id"] == "outcome-1"
    assert integrity["status"] == "PASS"
    assert verifier.topology_evidence_for_canonical(canonical, owner_integrity=integrity)["case_count"] == 1


def test_case_universe_missing_case_fails_even_when_both_repeatable_sources_are_missing():
    snapshot, digest = _snapshot((1, "GMP", 1, "-", "-"), (2, "GMP", 1, "-", "-"))
    report = _reconcile(snapshot, digest, _canonical(), [], [])
    universe = report["owners"]["case_universe"]
    assert universe["missing_canonical_case_ids"] == [2]
    assert universe["case_universe_status"] == "FAIL"
    assert report["audit_result"] == "FAIL"


def test_case_universe_reports_missing_case_with_known_repeatable_source():
    snapshot, digest = _snapshot((1, "GMP", 1, "1/QD ngày 01/02/2026", "-"), (2, "GMP", 1, "2/QD ngày 02/02/2026", "-"))
    report = _reconcile(snapshot, digest, _canonical(), [], [])
    assert report["owners"]["case_universe"]["missing_canonical_case_ids"] == [2]
    assert report["decisions"]["classification_counts"]["CANONICAL_CASE_MISSING"] == 1
    assert report["audit_result"] == "FAIL"


def test_case_universe_rejects_extra_canonical_case_without_structured_rows():
    snapshot, digest = _snapshot((1, "GMP", 1, "-", "-"))
    canonical = _canonical()
    canonical[2] = {
        "case_id": "case-2",
        "inspection_plan_id": "plan-2",
        "inspection_outcome_id": "outcome-2",
        "plan": {"decision_reference": None, "decision_date": None, "decision_legacy_raw": None},
        "outcome": {"minutes_recorded_on": None, "minutes_recorded_time": None, "minutes_legacy_raw": None},
    }
    report = _reconcile(snapshot, digest, canonical, [], [])
    assert report["owners"]["case_universe"]["extra_canonical_case_ids"] == [2]
    assert report["audit_result"] == "FAIL"


def test_case_universe_rejects_same_count_with_different_legacy_id_sets():
    snapshot, digest = _snapshot(
        (1, "GMP", 1, "-", "-"),
        (2, "GMP", 1, "-", "-"),
        (3, "GMP", 1, "-", "-"),
    )
    canonical = _canonical()
    for legacy_id in (2, 4):
        canonical[legacy_id] = {
            "case_id": f"case-{legacy_id}",
            "inspection_plan_id": f"plan-{legacy_id}",
            "inspection_outcome_id": f"outcome-{legacy_id}",
            "plan": {"decision_reference": None, "decision_date": None, "decision_legacy_raw": None},
            "outcome": {"minutes_recorded_on": None, "minutes_recorded_time": None, "minutes_legacy_raw": None},
        }
    report = _reconcile(snapshot, digest, canonical, [], [])
    universe = report["owners"]["case_universe"]
    assert universe["source_case_count"] == universe["canonical_case_count"] == 3
    assert universe["source_case_legacy_id_set_sha256"] != universe["canonical_case_legacy_id_set_sha256"]
    assert universe["missing_canonical_case_ids"] == [3]
    assert universe["extra_canonical_case_ids"] == [4]
    assert report["audit_result"] == "FAIL"


@pytest.mark.parametrize(
    ("target", "field", "value"),
    [
        ("plan", "decision_reference", "123/QD"),
        ("plan", "decision_date", date(2026, 2, 1)),
        ("plan", "decision_legacy_raw", "123/QD ngày 01/02/2026"),
        ("outcome", "minutes_recorded_on", date(2026, 2, 1)),
        ("outcome", "minutes_recorded_time", time(9, 30)),
        ("outcome", "minutes_legacy_raw", "01/02/2026"),
    ],
)
def test_missing_source_rejects_each_stale_scalar_compatibility_value(target, field, value):
    snapshot, digest = _snapshot((1, "GMP", 1, "-", "-"))
    canonical = _canonical()
    canonical[1][target][field] = value
    report = _reconcile(snapshot, digest, canonical, [], [])
    projection = report["compatibility_projection"]
    section = "decisions" if target == "plan" else "minutes"
    assert projection[section]["SOURCE_MISSING_SCALAR_PRESENT"] == 1
    assert projection["status"] == "FAIL"
    assert report["audit_result"] == "FAIL"


def test_unresolved_source_is_incomplete_without_structured_mismatch():
    snapshot, digest = _snapshot((1, "GMP", 1, "unstructured", "unstructured"))
    report = _reconcile(snapshot, digest, _canonical(), [], [])
    assert report["audit_result"] == "INCOMPLETE_EVIDENCE"
    assert report["decisions"]["classification_counts"]["SOURCE_UNRESOLVED"] == 1
    assert report["minutes"]["classification_counts"]["SOURCE_RAW_ONLY"] == 1


def test_source_raw_only_alone_blocks_pass_as_incomplete_evidence():
    snapshot, digest = _snapshot((1, "GMP", 1, "-", "unstructured"))
    report = _reconcile(snapshot, digest, _canonical(), [], [])
    assert report["audit_result"] == "INCOMPLETE_EVIDENCE"
    assert report["decisions"]["classification_counts"]["SOURCE_MISSING"] == 1
    assert report["minutes"]["classification_counts"]["SOURCE_RAW_ONLY"] == 1


def test_decision_without_plan_requires_exact_topology_evidence_before_not_writable_classification():
    snapshot, digest = _snapshot((1, "GMP", 1, "1/QD ngày 01/02/2026", "-"))
    canonical = _canonical()
    canonical[1].pop("inspection_plan_id")
    canonical[1].pop("plan")
    expected_topology = verifier.topology_evidence_for_canonical(_canonical())
    with pytest.raises(verifier.ReconciliationFenceError, match="topology"):
        _reconcile(snapshot, digest, canonical, [], [], topology=expected_topology)
    report = _reconcile(snapshot, digest, canonical, [], [])
    assert report["audit_result"] == "PASS"
    assert report["decisions"]["expected_structured_count"] == 0
    assert report["decisions"]["expected_not_writable_count"] == 1
    assert report["decisions"]["classification_counts"]["EXPECTED_NOT_WRITABLE_NO_PLAN"] == 1


def test_scalar_compatibility_projection_distinguishes_singleton_and_multiple():
    snapshot, digest = _snapshot(
        (1, "GMP", 1, "1/QD ngày 01/02/2026", "01/02/2026"),
        (2, "GMP", 1, "2/QD ngày 02/02/2026; 3/QD ngày 03/02/2026", "02/02/2026 & 03/02/2026"),
    )
    canonical = _canonical()
    canonical[1]["plan"] = {"decision_reference": "1/QD", "decision_date": date(2026, 2, 1), "decision_legacy_raw": "1/QD ngày 01/02/2026"}
    canonical[1]["outcome"] = {"minutes_recorded_on": date(2026, 2, 1), "minutes_recorded_time": None, "minutes_legacy_raw": "01/02/2026"}
    canonical[2] = {"case_id": "case-2", "inspection_plan_id": "plan-2", "inspection_outcome_id": "outcome-2", "plan": {"decision_reference": None, "decision_date": None, "decision_legacy_raw": None}, "outcome": {"minutes_recorded_on": None, "minutes_recorded_time": None, "minutes_legacy_raw": None}}
    report = _reconcile(snapshot, digest, canonical, [], [])
    assert report["compatibility_projection"] == {"decisions": {"MULTIPLE_NULL_EXACT": 1, "SINGLETON_EXACT": 1}, "minutes": {"MULTIPLE_NULL_EXACT": 1, "SINGLETON_EXACT": 1}, "status": "PASS"}


def test_compatibility_scalar_drift_is_a_hard_reconciliation_failure():
    snapshot, digest = _snapshot((1, "GMP", 1, "2/QD ngày 02/02/2026; thay the QD số 1/QD ngày 01/02/2026", "-"))
    canonical = _canonical()
    canonical[1]["plan"] = {"decision_reference": "wrong", "decision_date": None, "decision_legacy_raw": None}
    decisions, _minutes = _matching_rows()
    report = _reconcile(snapshot, digest, canonical, decisions, [])
    assert report["decisions"]["classification_counts"]["EXACT_MATCH"] == 2
    assert report["compatibility_projection"]["decisions"]["MULTIPLE_SCALAR_PRESENT"] == 1
    assert report["compatibility_projection"]["status"] == "FAIL"
    assert report["audit_result"] == "FAIL"


def test_compatibility_singleton_exact_is_pass_when_structured_rows_match():
    snapshot, digest = _snapshot((1, "GMP", 1, "1/QD ngày 01/02/2026", "-"))
    canonical = _canonical()
    canonical[1]["plan"] = {"decision_reference": "1/QD", "decision_date": date(2026, 2, 1), "decision_legacy_raw": "1/QD ngày 01/02/2026"}
    decisions = [{"id": "decision-1", "legacy_inspection_id": 1, "case_id": "case-1", "inspection_plan_id": "plan-1", "ordinal": 1, "reference": "1/QD", "decision_on": date(2026, 2, 1), "legacy_raw": "1/QD ngày 01/02/2026", "relation_type": None, "related_decision_id": None}]
    report = _reconcile(snapshot, digest, canonical, decisions, [])
    assert report["compatibility_projection"]["decisions"]["SINGLETON_EXACT"] == 1
    assert report["compatibility_projection"]["status"] == "PASS"
    assert report["audit_result"] == "PASS"


def test_terminal_semicolon_decision_raw_is_proven_source_lineage_equivalent():
    snapshot, digest = _snapshot((1, "GMP", 1, "376/QD-QLD ngày 29/08/2016;", "-"))
    canonical = _canonical()
    canonical[1]["plan"] = {
        "decision_reference": "376/QD-QLD",
        "decision_date": date(2016, 8, 29),
        "decision_legacy_raw": "376/QD-QLD ngày 29/08/2016;",
    }
    report = _reconcile(snapshot, digest, canonical, [], [])
    assert report["compatibility_projection"]["decisions"] == {
        "TERMINAL_SEPARATOR_REPRESENTATION_EQUIVALENT": 1
    }
    assert report["compatibility_projection"]["status"] == "PASS"


@pytest.mark.parametrize("historical_raw", ["376/QD-QLD ngày 29/08/2016;;", "376/QD-QLD ngày 29/08/2016."])
def test_decision_raw_punctuation_other_than_one_proven_terminal_semicolon_is_not_equivalent(historical_raw):
    snapshot, digest = _snapshot((1, "GMP", 1, "376/QD-QLD ngày 29/08/2016;", "-"))
    canonical = _canonical()
    canonical[1]["plan"] = {
        "decision_reference": "376/QD-QLD",
        "decision_date": date(2016, 8, 29),
        "decision_legacy_raw": historical_raw,
    }
    report = _reconcile(snapshot, digest, canonical, [], [])
    assert report["compatibility_projection"]["decisions"]["SINGLETON_FIELD_MISMATCH"] == 1


def test_missing_writable_decision_has_deterministic_dry_run_action_and_is_data_apply_required():
    snapshot, digest = _snapshot((1, "GMP", 1, "376/QD-QLD ngày 29/08/2016;", "-"))
    canonical = _canonical()
    canonical[1]["plan"] = {
        "decision_reference": "376/QD-QLD",
        "decision_date": date(2016, 8, 29),
        "decision_legacy_raw": "376/QD-QLD ngày 29/08/2016;",
    }
    report = _reconcile(snapshot, digest, canonical, [], [])
    action_plan = report["dry_run_apply_plan"]
    assert report["reconciliation_outcome"]["status"] == "DATA_APPLY_REQUIRED"
    assert action_plan["write_authorized"] is False
    assert action_plan["writer_invoked"] is False
    assert action_plan["actions"] == [{
        "kind": "decisions",
        "classification": "DATA_APPLY_REQUIRED",
        "legacy_inspection_id": 1,
        "canonical_case_id": "case-1",
        "inspection_plan_id": "plan-1",
        "source_ordinal": 1,
        "expected": {
            # Safe occurrence evidence intentionally does not serialize a
            # primitive ordinal; the action's source_ordinal is authoritative.
            "ordinal": None,
            "reference": "376/QD-QLD",
            "decision_on": "2016-08-29",
            "relation_type": None,
            "replaces_source_reference": None,
            **verifier.safe_evidence("376/QD-QLD ngày 29/08/2016"),
        },
    }]
    assert verifier.build_dry_run_apply_plan(report) == action_plan


def test_dry_run_is_idempotent_after_missing_decision_exists_and_conflicts_never_overwrite():
    snapshot, digest = _snapshot((1, "GMP", 1, "376/QD-QLD ngày 29/08/2016;", "-"))
    canonical = _canonical()
    canonical[1]["plan"] = {
        "decision_reference": "376/QD-QLD",
        "decision_date": date(2016, 8, 29),
        "decision_legacy_raw": "376/QD-QLD ngày 29/08/2016;",
    }
    decision = {
        "id": "decision-1",
        "legacy_inspection_id": 1,
        "case_id": "case-1",
        "inspection_plan_id": "plan-1",
        "ordinal": 1,
        "reference": "376/QD-QLD",
        "decision_on": date(2016, 8, 29),
        "legacy_raw": "376/QD-QLD ngày 29/08/2016",
        "relation_type": None,
        "related_decision_id": None,
    }
    report = _reconcile(snapshot, digest, canonical, [decision], [])
    assert report["dry_run_apply_plan"]["actions"] == []
    assert report["reconciliation_outcome"]["status"] == "PASS_EXACT"
    decision["reference"] = "conflict"
    report = _reconcile(snapshot, digest, canonical, [decision], [])
    assert report["decisions"]["classification_counts"]["FIELD_MISMATCH"] == 1
    assert report["dry_run_apply_plan"]["actions"] == []
    assert report["reconciliation_outcome"]["hard_semantic_conflicts"]["count"] == 1


def test_unresolved_decision_without_plan_is_incomplete_not_a_missing_row_action():
    snapshot, digest = _snapshot((1, "GMP", 1, "376/QD-QLD", "-"))
    canonical = _canonical()
    canonical[1].pop("inspection_plan_id")
    canonical[1].pop("plan")
    report = _reconcile(snapshot, digest, canonical, [], [])
    record = report["decisions"]["records"][0]
    assert record["classification"] == "SOURCE_UNRESOLVED"
    assert record["owner_availability"] == "NO_INSPECTION_PLAN"
    assert report["reconciliation_outcome"]["incomplete_evidence"]["count"] == 1
    assert report["dry_run_apply_plan"]["actions"] == []


def test_raw_only_minutes_and_excel_serial_equivalents_never_produce_dry_run_actions():
    raw_snapshot, raw_digest = _snapshot((1, "GMP", 1, "-", "Nguyễn Đức Toàn"))
    raw_report = _reconcile(raw_snapshot, raw_digest, _canonical(), [], [])
    assert raw_report["minutes"]["classification_counts"]["SOURCE_RAW_ONLY"] == 1
    assert raw_report["dry_run_apply_plan"]["actions"] == []

    serial_snapshot, serial_digest = _snapshot((1, "GMP", 1, "-", 45000))
    canonical = _canonical()
    canonical[1]["outcome"] = {
        "minutes_recorded_on": date(2023, 3, 15),
        "minutes_recorded_time": time(0, 0),
        "minutes_legacy_raw": "2023-03-15T00:00:00+00:00",
    }
    minutes = [{
        "id": "minutes-1", "legacy_inspection_id": 1, "case_id": "case-1", "inspection_outcome_id": "outcome-1",
        "ordinal": 1, **_historical_midnight_minutes(),
    }]
    serial_report = _reconcile(serial_snapshot, serial_digest, canonical, [], minutes)
    assert serial_report["minutes"]["classification_counts"]["EXCEL_SERIAL_DATE_REPRESENTATION_EQUIVALENT"] == 1
    assert serial_report["dry_run_apply_plan"]["actions"] == []


def test_topology_fence_rejects_same_count_but_different_legacy_owner_set():
    snapshot, digest = _snapshot((1, "GMP", 1, "-", "-"))
    expected = verifier.topology_evidence_for_canonical(_canonical())
    replacement = {
        2: {
            "case_id": "case-2",
            "inspection_plan_id": "plan-2",
            "inspection_outcome_id": "outcome-2",
            "plan": {"decision_reference": None, "decision_date": None, "decision_legacy_raw": None},
            "outcome": {"minutes_recorded_on": None, "minutes_recorded_time": None, "minutes_legacy_raw": None},
        }
    }
    with pytest.raises(verifier.ReconciliationFenceError, match="topology"):
        _reconcile(snapshot, digest, replacement, [], [], topology=expected)


def test_duplicate_required_db_ktra_header_fails_closed():
    snapshot, digest = _snapshot((1, "GMP", 1, "-", "-"))
    snapshot["sheets"][0]["raw_rows"][0]["cells"].append(_cell(6, "Q. định"))  # type: ignore[index]
    digest = sha256(snapshot_bytes(snapshot)).hexdigest()
    with pytest.raises(ValueError, match="duplicate required source headers"):
        parse_v2_repeatable_rows(snapshot, expected_snapshot_sha256=digest)


def test_target_fences_are_exact_and_fail_closed():
    verifier.validate_target_url("postgresql://user:password@host/gxp_legacy_rehearsal")
    with pytest.raises(verifier.ReconciliationFenceError, match="PostgreSQL"):
        verifier.validate_target_url("sqlite:///unsafe.db")
    with pytest.raises(verifier.ReconciliationFenceError, match="other than"):
        verifier.validate_target_url("postgresql://user:password@host/gxp_qlcl")

    class Scalar:
        def __init__(self, value): self.value = value
        def scalar_one(self): return self.value

    class Connection:
        def __init__(self, database, read_only, revision): self.values = (database, read_only, revision)
        def execute(self, statement):
            sql = str(statement)
            if "current_database" in sql: return Scalar(self.values[0])
            if "transaction_read_only" in sql: return Scalar(self.values[1])
            if "version_num" in sql: return Scalar(self.values[2])
            raise AssertionError(sql)

    verifier.verify_read_only_target(Connection("gxp_legacy_rehearsal", "on", "20260914_0015"))
    for values in (("wrong", "on", "20260914_0015"), ("gxp_legacy_rehearsal", "off", "20260914_0015"), ("gxp_legacy_rehearsal", "on", "20260913_0015")):
        with pytest.raises(verifier.ReconciliationFenceError):
            verifier.verify_read_only_target(Connection(*values))


def test_cli_result_codes_and_exact_file_byte_provenance(tmp_path, monkeypatch):
    assert verifier.exit_code_for_result("PASS") == 0
    assert verifier.exit_code_for_result("INCOMPLETE_EVIDENCE") != 0
    assert verifier.exit_code_for_result("FAIL") != 0
    snapshot, digest = _snapshot((1, "GMP", 1, "-", "-"))
    path = tmp_path / "snapshot.json"
    path.write_bytes(snapshot_bytes(snapshot))
    monkeypatch.setattr(verifier, "CANONICAL_SNAPSHOT_SHA256", digest)
    assert verifier.load_verified_snapshot_file(path) == snapshot
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(verifier.ReconciliationFenceError, match="file SHA256"):
        verifier.load_verified_snapshot_file(path)


def test_database_error_summary_redacts_credential_bearing_urls():
    summary = verifier.safe_error_summary(RuntimeError("postgresql+psycopg://operator:secret@host/gxp_legacy_rehearsal?password=query-secret"))
    assert "secret" not in summary
    assert "[REDACTED]" in summary


def test_source_adapter_uses_canonical_parser_without_changing_decision_semantics():
    snapshot, digest = _snapshot((1, "GMP", 1, "1/QD ngày 01/02/2026", 45000))
    row = parse_v2_repeatable_rows(snapshot, expected_snapshot_sha256=digest)[0]
    assert row["decisions"]["occurrences"][0]["reference"] == "1/QD"
    assert row["minutes"]["occurrences"][0]["recorded_on"] == date(2023, 3, 15)
    assert row["minutes"]["occurrences"][0]["recorded_time"] is None
    assert row["minutes"]["occurrences"][0]["precision"] == "DATE_ONLY"
    assert row["minutes"]["occurrences"][0]["source_format"] == "DMY_DATE"


def test_canonical_snapshot_v2_adapter_preserves_proven_repeatable_population():
    path = Path("artifacts/phase3c/legacy_snapshot_v2.json")
    if not path.exists():
        pytest.skip("local canonical Snapshot V2 is intentionally not tracked")
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    rows = parse_v2_repeatable_rows(snapshot, expected_snapshot_sha256=verifier.CANONICAL_SNAPSHOT_SHA256)
    assert len(rows) == 1496
    assert sum(len(row["decisions"]["occurrences"]) for row in rows) == 1295
    assert sum(len(row["minutes"]["occurrences"]) for row in rows) == 1162
    assert sum(row["minutes_representation"] == "NUMERIC_CONVERTED_EXCEL_SERIAL_DATE" for row in rows) == 1149
