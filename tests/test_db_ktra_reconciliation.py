from __future__ import annotations

from datetime import date
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.app.domain.legacy_db_ktra_reconciliation import (
    parse_legacy_approval_submission,
    parse_legacy_date,
    parse_legacy_inspection_decisions,
    parse_legacy_inspection_decision,
    parse_legacy_minutes_records,
    parse_legacy_minutes_recorded,
    parse_legacy_team,
    scalar_compatibility_projection,
)
from tools import plan_db_ktra_reconciliation as planner
from tools import plan_db_ktra_repeatable_semantics as repeatable_planner
from backend.app.services.workflow import CaseWorkflowService
from backend.app.db.models.phase1 import InspectionDecision, InspectionMinutesRecord


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


def test_repeatable_decision_and_minutes_parsers_preserve_order_without_scalar_selection():
    decisions = parse_legacy_inspection_decisions("1/QD\nngày 01/02/2026; 2/QD ngày 02/02/2026")
    assert decisions["state"] == "KNOWN"
    assert [(item["ordinal"], item["reference"], item["decision_on"]) for item in decisions["occurrences"]] == [
        (1, "1/QD", date(2026, 2, 1)), (2, "2/QD", date(2026, 2, 2))
    ]
    assert scalar_compatibility_projection(decisions["occurrences"]) is None
    minutes = parse_legacy_minutes_records("01/02/2026 09:30 và 02/02/2026")
    assert [(item["ordinal"], item["recorded_on"], item["recorded_time"]) for item in minutes["occurrences"]] == [
        (1, date(2026, 2, 1), __import__("datetime").time(9, 30)), (2, date(2026, 2, 2), None)
    ]


def test_repeatable_parsers_fail_closed_and_preserve_explicit_replacement_only():
    replacement = parse_legacy_inspection_decisions("2/QD ngày 02/02/2026 (thay the QD số 1/QD ngày 01/02/2026)")
    assert [(item["ordinal"], item["reference"]) for item in replacement["occurrences"]] == [(1, "2/QD"), (2, "1/QD")]
    assert replacement["occurrences"][0]["relation_type"] == "REPLACES"
    assert replacement["occurrences"][0]["replaces_source_reference"] == "1/QD"
    assert parse_legacy_inspection_decisions("1/QD; 02/02/2026")["state"] == "UNRESOLVED"
    assert parse_legacy_minutes_records("Nguyễn Văn A")["state"] == "RAW_ONLY"
    assert scalar_compatibility_projection([]) is None


def test_real_snapshot_replacement_layouts_preserve_both_proven_decisions():
    replacement_rows = [
        row for row in planner.load_snapshot(planner.SNAPSHOT)
        if "thay" in str(row.get("decision_reference") or "").lower()
    ]
    parsed = [parse_legacy_inspection_decisions(row["decision_reference"]) for row in replacement_rows]
    assert len(replacement_rows) >= 2
    assert all(item["state"] == "KNOWN" and len(item["occurrences"]) == 2 for item in parsed)
    assert all(item["occurrences"][0]["relation_type"] == "REPLACES" for item in parsed)


def test_repeatable_source_planner_is_deterministic_and_never_proposes_apply():
    rows = [
        {"ID": "1", "decision_reference": "1/QD ngày 1/2/2026; 2/QD ngày 02/02/2026", "bbkt_reference": "01/02/2026 & 02/02/2026", "HẠN KT TUÂN THỦ": "3 năm"},
        {"ID": "2", "decision_reference": "-", "bbkt_reference": "Nguyễn Văn A"},
    ]
    report = repeatable_planner.build_plan(rows)
    assert report["decisions"]["rows_by_cardinality"] == {"MISSING": 1, "MULTIPLE": 1}
    assert report["minutes"]["rows_by_cardinality"] == {"MULTIPLE": 1, "RAW_ONLY": 1}
    assert report["compliance"]["NO_MIGRATION_USER_ENTERED"] == [1]
    assert report["write_candidates"] == "BLOCKED_PENDING_READ_ONLY_REHEARSAL_COMPARISON"
    assert report["guardrails"] == {"database_mutated": False, "fuzzy_matching_used": False, "importer_invoked": False, "apply_tool_present": False}


def test_repeatable_model_indexes_match_migration_intent():
    assert {index.name for index in InspectionDecision.__table__.indexes} == {"ix_inspection_decision_related_decision_id"}
    assert not InspectionMinutesRecord.__table__.indexes
    migration = Path("migrations/versions/20260913_0013_repeatable_inspection_semantics.py").read_text(encoding="utf-8")
    assert migration.count("op.create_index(") == 1
    assert migration.count("op.drop_index(") == 1
    assert 'op.create_index("ix_inspection_decision_related_decision_id", "inspection_decision", ["related_decision_id"])' in migration
    assert 'op.drop_index("ix_inspection_decision_related_decision_id", table_name="inspection_decision")' in migration


def test_repeatable_rehearsal_comparison_requires_exact_existing_owners_without_writes():
    rows = [
        {"ID": "1", "decision_reference": "1/QD ngày 01/02/2026", "bbkt_reference": "01/02/2026"},
        {"ID": "2", "decision_reference": "2/QD ngày 01/02/2026", "bbkt_reference": "01/02/2026"},
        {"ID": "3", "decision_reference": "3/QD ngày 01/02/2026", "bbkt_reference": "Nguyễn Văn A", "HẠN KT TUÂN THỦ": "03 năm"},
    ]
    report = repeatable_planner.build_rehearsal_comparison(rows, {1: {"case_id": "case-1", "inspection_plan_id": "plan-1", "inspection_outcome_id": "outcome-1"}, 2: {"case_id": "case-2", "inspection_plan_id": None, "inspection_outcome_id": None}})
    assert report["decisions"]["rehearsal_classification_counts"] == {"BLOCKED_NO_CANONICAL_CASE": 1, "BLOCKED_NO_INSPECTION_PLAN": 1, "WRITE_CANDIDATE": 1}
    assert report["minutes"]["rehearsal_classification_counts"] == {"BLOCKED_NO_INSPECTION_OUTCOME": 1, "RAW_ONLY": 1, "WRITE_CANDIDATE": 1}
    assert report["canonical_gaps"] == {"classification": "NO_AUTO_CREATE", "legacy_inspection_ids": [3], "count": 1, "write_candidates": 0}
    assert report["compliance"]["write_candidates"] == 0
    assert report["guardrails"]["database_mutated"] is False
    assert isinstance(report["write_candidates"], dict)
    assert report["write_candidates"]["decisions"] == [
        item for item in report["decisions"]["classification_records"] if item["classification"] == "WRITE_CANDIDATE"
    ]
    assert report["write_candidates"]["decisions"][0]["inspection_plan_id"] == "plan-1"
    assert report["write_candidates"]["minutes"][0]["inspection_outcome_id"] == "outcome-1"
    assert all(item["classification"] != "WRITE_CANDIDATE" for item in report["decisions"]["classification_records"] if item["legacy_inspection_id"] == 3)


def test_repeatable_rehearsal_comparison_excludes_invalid_source_ids_from_all_ownership_paths():
    rows = [
        {"ID": "1", "decision_reference": "1/QD ngày 01/02/2026", "bbkt_reference": "01/02/2026"},
        {"ID": "", "decision_reference": "2/QD ngày 01/02/2026", "bbkt_reference": "01/02/2026"},
        {"ID": "not-an-id", "decision_reference": "3/QD ngày 01/02/2026", "bbkt_reference": "01/02/2026"},
    ]
    report = repeatable_planner.build_rehearsal_comparison(rows, {1: {"case_id": "case-1", "inspection_plan_id": "plan-1", "inspection_outcome_id": "outcome-1"}})
    assert report["canonical_gaps"]["legacy_inspection_ids"] == []
    assert [item["legacy_inspection_id"] for item in report["decisions"]["candidates"]] == [1]
    assert [item["legacy_inspection_id"] for item in report["minutes"]["candidates"]] == [1]


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
    for field in ("PHIẾU TRÌNH PCT", "PHIẾU TRÌNH CT"):
        for example in profile["fields"][field]["representative_safe_examples"].get("KNOWN", []):
            assert not example["parsed"]["reference"].lower().endswith(("ngày", "ngay"))


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


def test_decision_contamination_uses_full_composite_not_split_reference():
    raw = "368/QĐ-QLD ngày 24/08/2016"
    report = planner.build_comparison_plan([{"ID": "1", "decision_reference": raw}], {1: {"id": "case-1", "outcome": {"decision_reference": raw}, "application": {"dossier_reference": raw}, "assessment": {}, "plan": {}}})
    facts = {fact["fact"]: fact for fact in report["facts"]}
    assert facts["application_dossier_reference_contamination"]["classification"] == "CONTAMINATED_EXACT_COPY"
    assert facts["outcome_decision_reference_contamination"]["classification"] == "CONTAMINATED_EXACT_COPY"
    report = planner.build_comparison_plan([{"ID": "1", "decision_reference": raw}], {1: {"id": "case-1", "outcome": {"decision_reference": "368/QĐ-QLD"}, "application": {}, "assessment": {}, "plan": {}}})
    assert {fact["fact"]: fact for fact in report["facts"]}["outcome_decision_reference_contamination"]["classification"] == "TARGET_DIFFERENT"


def test_approval_reference_connector_and_rounds_are_preserved_without_inference():
    parsed = parse_legacy_approval_submission("418/CL ngày 17/8/2019")
    assert parsed["reference"] == "418/CL" and parsed["raw"] == "418/CL ngày 17/8/2019"
    case = {"id": "case-1", "submissions": {"PCT": [{"stage": "PCT", "round_no": 1, "reference": "418/CL", "submitted_on": date(2019, 8, 17), "submitted_time": None}, {"stage": "PCT", "round_no": 2, "reference": "418/CL", "submitted_on": date(2019, 8, 17), "submitted_time": None}]}}
    fact = planner._approval_fact(1, case, "PCT", parsed)
    assert fact["classification"] == "MANUAL_REVIEW"
    assert [item["round_no"] for item in fact["canonical_submission_rounds"]] == [1, 2]


def test_write_grade_team_mapping_and_contamination_denominators():
    parsed = parse_legacy_team("Person, Profile")
    index = {"Person": {("person", "person-id")}, "Profile": {("inspector_profile", "profile-id")}}
    resolution = planner._team_resolution(parsed, index, 0)
    assert [item["resolution_state"] for item in resolution["members"]] == ["RESOLVED_PERSON", "RESOLVED_INSPECTOR_PROFILE"]
    assert resolution["members"][0]["person_id"] == "person-id"
    assert resolution["members"][1]["inspector_profile_id"] == "profile-id"
    ambiguous = planner._team_resolution(parse_legacy_team("Name"), {"Name": {("person", "a"), ("inspector_profile", "b")}}, 0)
    assert ambiguous["ambiguous"] == 1
    report = planner.build_comparison_plan([{"ID": "1", "assessment_result": "-"}], {1: {"id": "case-1", "outcome": {}, "assessment": {}, "application": {}, "plan": {}}})
    summary = report["contamination"]["assessment_result_contamination"]
    assert summary["source_known_rows"] == 0 and summary["safe_to_clean_later_count"] == 0


def test_certificate_planner_uses_runtime_case_site_and_type_invariants():
    runtime = object.__new__(CaseWorkflowService)
    case_model = SimpleNamespace(site_id="site-1", gxp_type="GMP")
    runtime._validate_certificate_case_link(site_id="site-1", case=case_model, certificate_type="GMP", issuance_basis="inspection_case")
    case = {"id": "case-1", "site_id": "site-1", "gxp_type": "GMP", "certificate_by_legacy_id": {"legacy_certificate_id": 1, "case_id": None, "site_id": "site-1", "certificate_type": "GMP"}}
    assert planner._certificate_fact(1, case, planner.parse_legacy_certificate_id("1"))["classification"] == "SAFE_LINK"
    with pytest.raises(HTTPException, match="certificate_type"):
        runtime._validate_certificate_case_link(site_id="site-1", case=case_model, certificate_type="GLP", issuance_basis="inspection_case")
    case["certificate_by_legacy_id"]["certificate_type"] = "GLP"
    assert planner._certificate_fact(1, case, planner.parse_legacy_certificate_id("1"))["classification"] == "BLOCKED_TYPE_MISMATCH"


def test_readonly_guard_refuses_unsafe_target_and_contains_no_write_sql():
    with pytest.raises(RuntimeError):
        planner.validate_rehearsal_target("sqlite:///unsafe.db")
    with pytest.raises(RuntimeError):
        planner.validate_rehearsal_target("postgresql://user:password@host/other")
    source = inspect.getsource(planner.run_read_only_comparison).upper()
    assert "SET TRANSACTION READ ONLY" in source
    assert all(token not in source for token in ("INSERT ", "UPDATE ", "DELETE "))
