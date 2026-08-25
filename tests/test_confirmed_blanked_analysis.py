import json
from pathlib import Path

from tools.build_unresolved_fk_analysis import build_unresolved_fk_analysis


def test_real_artifacts_fully_reconcile_with_confirmed_blanked_contract():
    anomaly_rows = json.loads(Path("artifacts/phase3_review/anomaly_review_report.json").read_text(encoding="utf-8"))
    confirmed_payload = json.loads(Path("artifacts/phase3q/confirmed_blanked_rows.json").read_text(encoding="utf-8"))

    report = build_unresolved_fk_analysis(anomaly_rows, confirmed_payload["rows"])

    assert report["raw_anomaly_count"] == 151
    assert report["confirmed_blanked_match_count"] == 151
    assert report["confirmed_blanked_match_failure_count"] == 0
    assert report["remaining_root_anomaly_count"] == 0
    assert report["cascade_anomaly_count"] == 2
    assert report["blank_fk_total"] == 149
    assert report["blank_fk_breakdown"]["already_owner_confirmed_blanked"] == 149
    assert report["blank_fk_breakdown"]["not_in_confirmed_blanked"] == 0


def test_real_artifacts_mark_known_cascades_from_confirmed_blanked_parent():
    anomaly_rows = json.loads(Path("artifacts/phase3_review/anomaly_review_report.json").read_text(encoding="utf-8"))
    confirmed_payload = json.loads(Path("artifacts/phase3q/confirmed_blanked_rows.json").read_text(encoding="utf-8"))

    report = build_unresolved_fk_analysis(anomaly_rows, confirmed_payload["rows"])
    row_index = {(row["source_sheet"], row["source_row_key"]): row for row in report["row_analyses"]}

    assert row_index[("db.Tdoi2", "155")]["classification"] == "cascade_from_confirmed_blanked_parent"
    assert row_index[("db.Tdoi2", "155")]["parent_source_sheet"] == "db.Tdoi"
    assert row_index[("db.Tdoi2", "155")]["parent_source_row_key"] == "187"

    assert row_index[("db.cc", "268")]["classification"] == "cascade_from_confirmed_blanked_parent"
    assert row_index[("db.cc", "268")]["parent_source_sheet"] == "db.ktra"
    assert row_index[("db.cc", "268")]["parent_source_row_key"] == "257"
