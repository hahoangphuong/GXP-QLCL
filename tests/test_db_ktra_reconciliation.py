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
    assert timestamp["precision"] == "DATE_TIME_LOCAL" and timestamp["recorded_time"].isoformat() == "09:30:00"
    iso = parse_legacy_minutes_recorded("2016-08-27 23:30:00+07:00")
    assert (iso["state"], iso["recorded_on"], iso["recorded_time"], iso["precision"], iso["source_format"]) == (
        "KNOWN", date(2016, 8, 27), iso["recorded_time"], "DATE_TIME_LOCAL", "ISO_OFFSET_DATETIME"
    )
    assert iso["recorded_time"].isoformat() == "23:30:00"
    assert parse_legacy_minutes_recorded("24/08/2016; 25/08/2016")["state"] == "UNRESOLVED"
    assert "inspected_on" not in timestamp and "inspected_to_on" not in timestamp


def test_deadline_team_and_approval_parsers_fail_closed_without_identity_or_completion_inference():
    assert parse_legacy_date("24/08/2016")["value"] == date(2016, 8, 24)
    assert parse_legacy_date("24-25/08/2016")["state"] == "PARTIAL"
    team = parse_legacy_team("Nguyễn Văn A, Trần Thị B, Lê Văn C")
    assert [member["role_code"] for member in team["members"]] == ["LEADER", "SECRETARY", "MEMBER"]
    assert parse_legacy_team("A; B; C")["state"] == "UNRESOLVED"
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


def test_iso_deadline_and_full_fact_coverage_use_source_faithful_metadata():
    deadline = parse_legacy_date("2026-08-21 09:30:00+07:00")
    assert (deadline["state"], deadline["value"], deadline["precision"], deadline["source_format"]) == (
        "KNOWN", date(2026, 8, 21), "DATE_TIME_LOCAL", "ISO_OFFSET_DATETIME"
    )
    row = {
        "ID": "7", "assessment_result": "Dat", "decision_reference": "10/QD ngay 24/08/2016",
        "bbkt_reference": "2016-08-27 09:30:00+07:00", "ĐÁNH GIÁ CUỐI": "Dat",
        "HẠN KT TUÂN THỦ": "2026-08-21 09:30:00+07:00", "T.tra viên": "A, B",
        "PHIẾU TRÌNH PCT": "1/PCT ngay 24/08/2016", "PHIẾU TRÌNH CT": "2/CT ngay 24/08/2016", "ID CC GPs": "12",
    }
    report = planner.build_comparison_plan([row], {7: {"id": "case-7", "site_id": "site-7", "gxp_type": "GMP", "outcome": {}, "assessment": {}, "application": {}, "plan": {}, "submissions": {}, "team_resolution": {"resolved": 2, "unresolved": 0, "ambiguous": 0}, "certificate_by_legacy_id": {"legacy_certificate_id": 12, "case_id": None, "site_id": "site-7", "certificate_type": "GMP"}}})
    names = {fact["fact"] for fact in report["facts"]}
    assert {"outcome_result", "assessment_result_contamination", "decision_reference", "decision_date", "decision_legacy_raw", "application_dossier_reference_contamination", "outcome_decision_reference_contamination", "minutes_recorded_on", "minutes_recorded_time", "outcome_bbkt_reference_contamination", "final_evaluation", "compliance_due_on", "inspection_team", "pct_submission", "ct_submission", "certificate_link"} <= names
    assert report["facts"][-1]["classification"] == "SAFE_LINK"
    assert report["facts"][-2]["classification"] == "BLOCKED_PARENT_RELATION"
    assert all("current_canonical_value" in fact for fact in report["facts"])
    assert len(report["contamination"]) == 4


def test_full_snapshot_profile_proves_iso_and_comma_team_morphologies_are_not_misclassified():
    profile = planner.profile_rows(planner.load_snapshot(planner.SNAPSHOT))
    assert profile["fields"]["B. bản"]["state_counts"]["KNOWN"] >= 1150
    assert profile["fields"]["HẠN KT TUÂN THỦ"]["state_counts"]["KNOWN"] >= 405
    assert profile["team_segmentation"]["delimiter_counts"] == {"comma": 1290, "none": 3}
    assert profile["team_segmentation"]["candidate_member_count_distribution"].get(1, 0) == 3


def test_team_identity_and_certificate_compatibility_fail_closed():
    team = parse_legacy_team("A, B")
    case = {"id": "case-9", "site_id": "site-9", "gxp_type": "GMP", "team_resolution": {"resolved": 1, "unresolved": 0, "ambiguous": 1, "current_member_count": 0}, "certificate_by_legacy_id": {"legacy_certificate_id": 99, "case_id": None, "site_id": "site-9", "certificate_type": "GLP"}}
    team_fact = planner._team_fact(9, case, team)
    certificate_fact = planner._certificate_fact(9, case, planner.parse_legacy_certificate_id("99"))
    assert team_fact["classification"] == "BLOCKED_IDENTITY"
    assert certificate_fact["classification"] == "BLOCKED_TYPE_MISMATCH"
    pct = planner._approval_fact(9, case, "PCT", parse_legacy_approval_submission("1/PCT ngay 24/08/2016"))
    ct = planner._approval_fact(9, case, "CT", parse_legacy_approval_submission("2/CT ngay 24/08/2016"))
    assert pct["classification"] == "SAFE_SUBMISSION_FACT"
    assert ct["classification"] == "BLOCKED_PARENT_RELATION"


def test_readonly_guard_refuses_unsafe_target_and_contains_no_write_sql():
    with pytest.raises(RuntimeError):
        planner.validate_rehearsal_target("sqlite:///unsafe.db")
    with pytest.raises(RuntimeError):
        planner.validate_rehearsal_target("postgresql://user:password@host/other")
    source = inspect.getsource(planner.run_read_only_comparison).upper()
    assert "SET TRANSACTION READ ONLY" in source
    assert all(token not in source for token in ("INSERT ", "UPDATE ", "DELETE "))
