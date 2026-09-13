from __future__ import annotations

from backend.app.domain.legacy_db_ktra_reconciliation import parse_legacy_inspection_decision
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
    rows = [{"ID": "1", "T.tra viên": "A, B", "pct_submission": "PCT-1 ngay 01/02/2026", "ct_submission": "CT-1 ngay 02/02/2026"}]
    report = audit.build_audit(rows, {1: {"id": "case-1", "team_member_states": {"A": "UNRESOLVED", "B": "UNRESOLVED"}, "certificate_anomaly": None}}, cases_by_site_and_type={}, person_count=0, profile_count=0)
    assert report["team_identity_source_matrix"]["conclusion"] == "PERSONNEL_MIGRATION_REQUIRED"
    assert report["approval_source_semantics"]["PCT"]["SINGLE_UNORDERED_SUBMISSION"] == 1
    assert report["approval_source_semantics"]["CT"]["EXPLICIT_PARENT_REFERENCE_ABSENT"] == 1


def test_post_batch4_integrity_reports_only_deterministic_source_mismatches():
    row = {"ID": "1", "assessment_result": "Dat", "decision_reference": "12/QD ngay 01/02/2026", "bbkt_reference": "03/02/2026", "final_evaluation": "A", "compliance_due_on": "04/02/2026"}
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
