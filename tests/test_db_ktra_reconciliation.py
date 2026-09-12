from __future__ import annotations

from datetime import date
import inspect
import json

import pytest

from backend.app.domain.legacy_db_ktra_reconciliation import (
    parse_legacy_approval_submission,
    parse_legacy_date,
    parse_legacy_inspection_decision,
    parse_legacy_minutes_recorded,
    parse_legacy_team,
)
from tools import plan_db_ktra_reconciliation as planner


def test_snapshot_guard_fails_before_outputs(tmp_path):
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(json.dumps({"db.ktra": []}), encoding="utf-8")
    with pytest.raises(RuntimeError, match="SHA256"):
        planner.load_snapshot(snapshot)


def test_canonical_snapshot_passes_provenance_guard():
    rows = planner.load_snapshot(planner.SNAPSHOT)
    assert len(rows) == 1543


def test_decision_parser_requires_one_reference_and_one_date():
    known = parse_legacy_inspection_decision("368/QD-QLD ngày 24/08/2016")
    assert (known["state"], known["decision_reference"], known["decision_date"]) == ("KNOWN", "368/QD-QLD", date(2016, 8, 24))
    assert parse_legacy_inspection_decision("QD 01 01/02/2026; 03/02/2026")["state"] == "UNRESOLVED"
    assert parse_legacy_inspection_decision("QD 01")["state"] == "PARTIAL"
    assert parse_legacy_inspection_decision("-")["decision_date"] is None


def test_minutes_parser_never_fabricates_period_midnight_or_timezone():
    date_only = parse_legacy_minutes_recorded("24/08/2016")
    assert (date_only["state"], date_only["recorded_on"], date_only["recorded_time"], date_only["precision"]) == ("KNOWN", date(2016, 8, 24), None, "DATE_ONLY")
    timestamp = parse_legacy_minutes_recorded("24/08/2016 09:30")
    assert timestamp["precision"] == "DATE_TIME" and timestamp["recorded_time"].isoformat() == "09:30:00"
    assert parse_legacy_minutes_recorded("24/08/2016; 25/08/2016")["state"] == "UNRESOLVED"
    assert "inspected_on" not in timestamp and "inspected_to_on" not in timestamp


def test_deadline_team_and_approval_parsers_fail_closed_without_identity_or_completion_inference():
    assert parse_legacy_date("24/08/2016")["value"] == date(2016, 8, 24)
    assert parse_legacy_date("24-25/08/2016")["state"] == "PARTIAL"
    team = parse_legacy_team("A; B; C")
    assert [member["role_code"] for member in team["members"]] == ["LEADER", "SECRETARY", "MEMBER"]
    pct = parse_legacy_approval_submission("PCT-01 24/08/2016")
    assert pct["state"] == "KNOWN" and "completed_on" not in pct and "pct_submission_id" not in pct


def test_result_contamination_classification_is_exact_and_never_clears_assessment():
    report = planner.build_comparison_plan(
        [{"ID": "1", "assessment_result": "Dat"}],
        {1: {"id": "case-1", "outcome": {"outcome_result": None}, "assessment": {"assessment_result": "Dat"}}},
    )
    facts = {fact["fact"]: fact for fact in report["facts"]}
    assert facts["outcome_result"]["classification"] == "SAFE_DIRECT"
    assert facts["assessment_result_contamination"]["classification"] == "CONTAMINATED_EXACT_COPY"
    assert facts["assessment_result_contamination"]["future_action"] == "review_only"


def test_readonly_guard_refuses_unsafe_target_and_contains_no_write_sql():
    with pytest.raises(RuntimeError):
        planner.validate_rehearsal_target("sqlite:///unsafe.db")
    with pytest.raises(RuntimeError):
        planner.validate_rehearsal_target("postgresql://user:password@host/other")
    source = inspect.getsource(planner.run_read_only_comparison).upper()
    assert "SET TRANSACTION READ ONLY" in source
    assert all(token not in source for token in ("INSERT ", "UPDATE ", "DELETE "))
