from pathlib import Path
import json
import sqlite3

from backend.app.project_paths import phase_artifact_path
from tools.analyze_phase3_anomalies import build_summary


def test_phase2_artifacts_exist_for_phase3(fixture_artifacts_root):
    assert (fixture_artifacts_root / "phase2" / "reconciliation.json").exists()
    assert (fixture_artifacts_root / "phase2" / "staging_readonly.sql").exists()


def test_phase2_database_contains_core_tables(materialized_phase2_db):
    db_path = materialized_phase2_db
    con = sqlite3.connect(str(db_path))
    try:
        cur = con.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cur.fetchall()}
    finally:
        con.close()
    assert {"company", "site", "case", "certificate", "legacy_id_map"}.issubset(tables)


def test_reconciliation_json_has_skipped_rows():
    data = json.loads(phase_artifact_path("phase2", "reconciliation.json").read_text(encoding="utf-8"))
    assert "skipped_rows" in data
    assert isinstance(data["skipped_rows"], dict)


def test_build_summary_uses_full_anomaly_rows_not_sample_rows():
    reconciliation = {
        "skipped_rows": {"db.cc": 2},
        "skipped_row_samples": {
            "db.cc": [
                {"legacy_id": 1, "reason": "missing_case_fk", "raw_fk": ""},
            ]
        },
        "anomaly_rows": [
            {
                "source_sheet": "db.cc",
                "legacy_row_id": "1",
                "reason": "missing_site_fk",
                "required_field": "ID CƠ SỞ",
                "raw_fk_value": "",
                "status": "open",
            },
            {
                "source_sheet": "db.cc",
                "legacy_row_id": "2",
                "reason": "missing_case_fk",
                "required_field": "ID ĐỢT KTRA",
                "raw_fk_value": "999",
                "status": "overridden",
            },
        ],
    }

    summary = build_summary(reconciliation)

    assert summary["total_anomalies"] == 2
    assert summary["open_anomalies"] == 1
    assert summary["overridden_anomalies"] == 1
    assert summary["by_reason"] == {"missing_site_fk": 1, "missing_case_fk": 1}
    assert summary["by_sheet"]["db.cc"]["reason_breakdown"] == {"missing_site_fk": 1, "missing_case_fk": 1}
    assert summary["by_sheet"]["db.cc"]["status_breakdown"] == {"open": 1, "overridden": 1}
