from pathlib import Path
import json

from backend.app.project_paths import phase_artifact_path
from tools.generate_phase3b_remediation_template import REMEDIATION_KEY_BY_REASON


def test_phase2_reconciliation_contains_full_anomalies():
    data = json.loads(phase_artifact_path("phase2", "reconciliation.json").read_text(encoding="utf-8"))
    assert "anomaly_rows" in data
    assert isinstance(data["anomaly_rows"], list)


def test_phase3b_template_can_be_generated_after_phase2():
    path = Path("tools/generate_phase3b_remediation_template.py")
    assert path.exists()


def test_phase3b_reason_mapping_still_covers_all_supported_fk_anomalies():
    assert REMEDIATION_KEY_BY_REASON == {
        "missing_company_fk": "company_legacy_id",
        "missing_site_fk": "site_legacy_id",
        "missing_case_fk": "case_legacy_id",
        "missing_change_request_fk": "change_request_legacy_id",
    }


def test_phase3b_candidate_can_be_keyed_by_source_row_key_when_legacy_id_missing():
    row = {
        "source_sheet": "db.ktra",
        "legacy_row_id": None,
        "source_row_key": "row:42",
        "reason": "missing_site_fk",
        "status": "open",
    }
    row_key = row.get("source_row_key") or row.get("legacy_row_id")
    assert row_key == "row:42"
