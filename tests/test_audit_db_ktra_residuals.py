from __future__ import annotations

from backend.app.domain.legacy_db_ktra_reconciliation import parse_legacy_inspection_decision
from tools.plan_db_ktra_reconciliation import SNAPSHOT, load_snapshot
from tools import audit_db_ktra_residuals as audit


def test_residual_classification_requires_exact_source_copy_proof():
    parsed = parse_legacy_inspection_decision("12/QD ngay 01/02/2026")
    assert audit.classify_residual(parsed=parsed, current=parsed["raw"], canonical=None) == "TRANSFORMED_CONTAMINATION_PROVEN"
    assert audit.classify_residual(parsed=parsed, current="12/QD", canonical=None) == "CURRENT_VALUE_UNEXPLAINED"
    assert audit.classify_residual(parsed=parsed, current="owner", canonical="owner") == "OWNER_DUPLICATE"


def test_blocked_parser_morphology_does_not_select_a_date():
    parsed = parse_legacy_inspection_decision("QD 1 01/02/2026; 02/02/2026")
    assert audit.parser_morphology("decision", parsed) == "MULTIPLE_REFERENCES_OR_DATES"
    assert audit.parser_morphology("minutes", {"state": "RAW_ONLY", "raw": "ghi chu"}) == "TEXTUAL_ANNOTATION_OR_REFERENCE_ONLY"


def test_unmatched_identity_stays_fail_closed_without_exact_alternate_id():
    row = {"ID": "7", "site_legacy_id_ref": "11", "inspection_gxp_type": "GMP"}
    item = audit._identity_row(row, {}, {(11, "GMP"): [{"id": "case-a"}, {"id": "case-b"}]})
    assert item and item["classification"] == "MULTIPLE_CANDIDATES"


def test_team_and_approval_audit_never_synthesizes_identity_round_or_parent():
    rows = [{"ID": "1", "T.tra viên": "A, B", "PHIẾU TRÌNH PCT": "PCT-1 ngay 01/02/2026", "PHIẾU TRÌNH CT": "CT-1 ngay 02/02/2026"}]
    report = audit.build_audit(rows, {1: {"id": "case-1", "team_member_states": {"A": "UNRESOLVED", "B": "UNRESOLVED"}, "certificate_anomaly": None}}, cases_by_site_and_type={}, person_count=0, profile_count=0)
    assert report["team_identity_source_matrix"]["conclusion"] == "PERSONNEL_MIGRATION_REQUIRED"
    assert report["approval_source_semantics"]["PCT"]["SINGLE_UNORDERED_SUBMISSION"] == 1
    assert report["approval_source_semantics"]["CT"]["EXPLICIT_PARENT_REFERENCE_ABSENT"] == 1


def test_post_batch4_integrity_reports_only_deterministic_source_mismatches():
    row = {"ID": "1", "assessment_result": "Dat", "decision_reference": "12/QD ngay 01/02/2026", "bbkt_reference": "03/02/2026", "ĐÁNH GIÁ CUỐI": "A", "HẠN KT TUÂN THỦ": "04/02/2026"}
    decision = parse_legacy_inspection_decision(row["decision_reference"])
    live = {1: {
        "plan_decision_reference": decision["decision_reference"], "plan_decision_date": decision["decision_date"], "plan_decision_legacy_raw": decision["raw"],
        "application_dossier_reference": None, "outcome_decision_reference": None,
        "minutes_recorded_on": __import__("datetime").date(2026, 2, 3), "minutes_recorded_time": None, "minutes_legacy_raw": "03/02/2026", "outcome_bbkt_reference": None,
        "outcome_result": "Dat", "assessment_result": None, "final_evaluation": "A", "compliance_due_on": __import__("datetime").date(2026, 2, 4),
    }}
    assert audit._integrity([row], live)["mismatch_count"] == 0
    live[1]["outcome_bbkt_reference"] = "03/02/2026"
    assert audit._integrity([row], live)["mismatch_count"] == 1


def test_compare_mode_fails_before_writing_db_derived_artifacts_without_url(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with __import__("pytest").raises(RuntimeError, match="DATABASE_URL"):
        audit.main(["--compare-rehearsal", "--residual-output", str(tmp_path / "residual.json")])
    assert not (tmp_path / "residual.json").exists()


def test_real_snapshot_uses_shared_vietnamese_source_keys():
    rows = load_snapshot(SNAPSHOT)
    report = audit.build_audit(rows, {}, cases_by_site_and_type={}, person_count=0, profile_count=0)
    approvals = report["approval_source_semantics"]
    assert approvals["PCT"]["SOURCE_KNOWN"] == 371
    assert approvals["CT"]["SOURCE_KNOWN"] == 315
    profile = report["blocked_parser"]
    assert profile["HẠN KT TUÂN THỦ"]["morphology_counts"]["KNOWN"] == 405
    assert sum(1 for row in rows if audit._parse_snapshot_field("ĐÁNH GIÁ CUỐI", row)["state"] == "KNOWN") == 1294


def test_real_normalized_snapshot_rows_reach_final_and_deadline_integrity_paths():
    rows = load_snapshot(SNAPSHOT)
    final_row = next(row for row in rows if audit._parse_snapshot_field("ĐÁNH GIÁ CUỐI", row)["state"] == "KNOWN")
    deadline_row = next(row for row in rows if audit._parse_snapshot_field("HẠN KT TUÂN THỦ", row)["state"] == "KNOWN")
    base = {"plan_decision_reference": None, "plan_decision_date": None, "plan_decision_legacy_raw": None, "application_dossier_reference": None, "outcome_decision_reference": None, "minutes_recorded_on": None, "minutes_recorded_time": None, "minutes_legacy_raw": None, "outcome_bbkt_reference": None, "outcome_result": None, "assessment_result": None, "final_evaluation": None, "compliance_due_on": None}
    final_checks = {item["check"] for item in audit._integrity([final_row], {int(final_row["ID"]): base})["mismatches"]}
    deadline_checks = {item["check"] for item in audit._integrity([deadline_row], {int(deadline_row["ID"]): base})["mismatches"]}
    assert "final_evaluation_source_value" in final_checks
    assert "compliance_due_on_source_value" in deadline_checks


def test_certificate_anomaly_classifications_are_exact_and_complete():
    case = {"id": "case-1", "site_id": "site-1", "gxp_type": "GMP"}
    assert audit._certificate_anomaly(case, [{}, {}], 7)["classification"] == "BLOCKED_IDENTITY"
    assert audit._certificate_anomaly(case, [{"case_id": "case-2", "site_id": "site-1", "certificate_type": "GMP"}], 7)["classification"] == "BLOCKED_CASE_MISMATCH"
    assert audit._certificate_anomaly(case, [{"case_id": None, "site_id": "site-2", "certificate_type": "GMP"}], 7)["classification"] == "BLOCKED_SITE_MISMATCH"
    assert audit._certificate_anomaly(case, [{"case_id": None, "site_id": "site-1", "certificate_type": "GLP"}], 7)["classification"] == "BLOCKED_TYPE_MISMATCH"
    assert audit._certificate_anomaly(case, [{"case_id": "case-1", "site_id": "site-1", "certificate_type": "GMP"}], 7) is None
