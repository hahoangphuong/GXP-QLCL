import json
from hashlib import sha256
from pathlib import Path

from backend.app.domain.phase2_import import CONFIRMED_BLANKED_ROWS_PATH
from tools.build_unresolved_fk_analysis import build_unresolved_fk_analysis


def test_confirmed_blanked_contract_is_tracked_in_repository_checkout():
    assert CONFIRMED_BLANKED_ROWS_PATH.exists()


def test_real_artifacts_fully_reconcile_with_confirmed_blanked_contract():
    source_snapshot_path = Path("artifacts/phase3c/legacy_snapshot.json")
    anomaly_report_path = Path("artifacts/phase3_review/anomaly_review_report.json")
    anomaly_rows = json.loads(anomaly_report_path.read_text(encoding="utf-8"))
    confirmed_payload = json.loads(CONFIRMED_BLANKED_ROWS_PATH.read_text(encoding="utf-8"))
    snapshot_sha256 = sha256(source_snapshot_path.read_bytes()).hexdigest()
    anomaly_report_sha256 = sha256(anomaly_report_path.read_bytes()).hexdigest()
    confirmed_sha256 = sha256(CONFIRMED_BLANKED_ROWS_PATH.read_bytes()).hexdigest()

    report = build_unresolved_fk_analysis(
        anomaly_rows,
        confirmed_payload["rows"],
        snapshot_sha256=snapshot_sha256,
        confirmed_contract_sha256=confirmed_sha256,
        anomaly_report_sha256=anomaly_report_sha256,
    )

    assert report["confirmed_blank_contract_path"] == "artifacts/phase3q/confirmed_blanked_rows.json"
    assert report["confirmed_blank_contract_sha256"] == confirmed_sha256
    assert report["snapshot_path"] == "artifacts/phase3c/legacy_snapshot.json"
    assert report["snapshot_sha256"] == snapshot_sha256
    assert report["anomaly_report_path"] == "artifacts/phase3_review/anomaly_review_report.json"
    assert report["anomaly_report_sha256"] == anomaly_report_sha256
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
    confirmed_payload = json.loads(CONFIRMED_BLANKED_ROWS_PATH.read_text(encoding="utf-8"))

    report = build_unresolved_fk_analysis(anomaly_rows, confirmed_payload["rows"])
    row_index = {(row["source_sheet"], row["source_row_key"]): row for row in report["row_analyses"]}

    assert row_index[("db.Tdoi2", "155")]["classification"] == "cascade_from_confirmed_blanked_parent"
    assert row_index[("db.Tdoi2", "155")]["parent_source_sheet"] == "db.Tdoi"
    assert row_index[("db.Tdoi2", "155")]["parent_source_row_key"] == "187"

    assert row_index[("db.cc", "268")]["classification"] == "cascade_from_confirmed_blanked_parent"
    assert row_index[("db.cc", "268")]["parent_source_sheet"] == "db.ktra"
    assert row_index[("db.cc", "268")]["parent_source_row_key"] == "257"
