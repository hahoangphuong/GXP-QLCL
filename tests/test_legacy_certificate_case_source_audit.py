"""Source-only coverage: detection is not permission to repair business links."""
from __future__ import annotations

import json
from pathlib import Path

from backend.app.domain.legacy_certificate_case_source_audit import audit_certificate_case_source_links
from tools.audit_legacy_certificate_case_sources import main


def _snapshot():
    return {
        "db.ktra": [
            {"ID": "100", "ID CƠ SỞ": "10", "LOẠI KT": "GMP"},
            {"ID": "101", "ID CƠ SỞ": "11", "LOẠI KT": "GMP"},
            {"ID": "102", "ID CƠ SỞ": "10", "LOẠI KT": "GLP"},
            {"ID": "103", "ID CƠ SỞ": "", "LOẠI KT": "GMP"},
            {"ID": "104", "ID CƠ SỞ": "11", "LOẠI KT": "GLP"},
            {"ID": "105", "ID CƠ SỞ": "10", "LOẠI KT": "GMP"},
            {"ID": "105", "ID CƠ SỞ": "10", "LOẠI KT": "GMP"},
        ],
        "db.cc": [
            {"ID": "1", "ID ĐỢT KTRA": "100", "ID CƠ SỞ": "10", "LOẠI CC": "GMP"},
            {"ID": "2", "ID ĐỢT KTRA": "", "ID CƠ SỞ": "10", "LOẠI CC": "GMP"},
            {"ID": "3", "ID ĐỢT KTRA": "101", "ID CƠ SỞ": "10", "LOẠI CC": "GMP"},
            {"ID": "4", "ID ĐỢT KTRA": "102", "ID CƠ SỞ": "10", "LOẠI CC": "GMP"},
            {"ID": "5", "ID ĐỢT KTRA": "999", "ID CƠ SỞ": "10", "LOẠI CC": "GMP"},
            {"ID": "6", "ID ĐỢT KTRA": "unknown", "ID CƠ SỞ": "10", "LOẠI CC": "GMP"},
            {"ID": "7", "ID ĐỢT KTRA": "103", "ID CƠ SỞ": "10", "LOẠI CC": "GMP"},
            {"ID": "8", "ID ĐỢT KTRA": "104", "ID CƠ SỞ": "10", "LOẠI CC": "GMP"},
            {"ID": "9", "ID ĐỢT KTRA": "105", "ID CƠ SỞ": "10", "LOẠI CC": "GMP"},
        ],
    }


def test_audit_distinguishes_all_evidence_states_without_rescuing_conflicts():
    report = audit_certificate_case_source_links(_snapshot())
    assert report["classification_counts"] == {
        "ADMINISTRATIVE_NO_CASE_REFERENCE": 1,
        "CASE_SOURCE_NOT_FOUND": 1,
        "DUPLICATE_CASE_SOURCE_ID": 1,
        "EXACT_SOURCE_CONTEXT": 1,
        "GXP_MISMATCH": 1,
        "SITE_AND_GXP_MISMATCH": 1,
        "SITE_CONTEXT_INCOMPLETE": 1,
        "SITE_MISMATCH": 1,
        "UNPARSEABLE_CASE_REFERENCE": 1,
    }
    assert [item["certificate_legacy_id"] for item in report["anomalies"]] == [3, 4, 5, 6, 7, 8, 9]
    site_mismatch = report["anomalies"][0]
    assert (site_mismatch["certificate_site_legacy_id"], site_mismatch["linked_case_site_legacy_id"]) == (10, 11)
    assert report["database_mutated"] is False
    assert report["source_modified"] is False


def test_real_source_snapshot_exposes_all_site_conflicts_without_inventing_remediation():
    snapshot = json.loads(Path("artifacts/phase3c/legacy_snapshot.json").read_text(encoding="utf-8"))
    report = audit_certificate_case_source_links(snapshot.get("sheets", snapshot))
    assert report["total_certificate_source_rows"] == 1628
    assert report["classification_counts"] == {
        "ADMINISTRATIVE_NO_CASE_REFERENCE": 169,
        "EXACT_SOURCE_CONTEXT": 1455,
        "SITE_CONTEXT_INCOMPLETE": 1,
        "SITE_MISMATCH": 3,
    }
    assert {
        (item["certificate_legacy_id"], item["linked_case_legacy_id"])
        for item in report["anomalies"]
        if item["classification"] == "SITE_MISMATCH"
    } == {(376, 378), (1037, 1023), (1180, 1023)}
    assert report["database_mutated"] is False


def test_cli_strict_is_fail_closed_but_never_writes_database(tmp_path):
    snapshot_path = tmp_path / "snapshot.json"
    output_path = tmp_path / "audit.json"
    snapshot_path.write_text(json.dumps(_snapshot(), ensure_ascii=False), encoding="utf-8")
    assert main(["--snapshot", str(snapshot_path), "--output", str(output_path)]) == 0
    assert main(["--snapshot", str(snapshot_path), "--strict"]) == 2
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["database_mutated"] is False
    assert len(payload["anomalies"]) == 7
