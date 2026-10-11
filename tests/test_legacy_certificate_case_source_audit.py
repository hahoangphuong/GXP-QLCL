"""Source-only coverage: detection is not permission to repair business links."""
from __future__ import annotations

import json
from pathlib import Path

from backend.app.domain.legacy_certificate_case_source_audit import audit_certificate_case_source_links
from backend.app.domain.phase2_import import load_confirmed_blanked_row_keys
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


def test_source_ids_must_be_literal_integers_not_truncated_floats():
    snapshot = _snapshot()
    snapshot["db.cc"][0]["ID ĐỢT KTRA"] = "100.5"
    snapshot["db.cc"][2]["ID CƠ SỞ"] = "10.5"
    report = audit_certificate_case_source_links(snapshot)
    classifications = {
        item["certificate_legacy_id"]: item["classification"]
        for item in report["anomalies"]
    }
    assert classifications[1] == "UNPARSEABLE_CASE_REFERENCE"
    assert classifications[3] == "SITE_CONTEXT_INCOMPLETE"

    snapshot["db.cc"][0]["ID ĐỢT KTRA"] = "100.0"
    snapshot["db.cc"][2]["ID CƠ SỞ"] = "10.0"
    restored = audit_certificate_case_source_links(snapshot)
    assert restored["classification_counts"]["EXACT_SOURCE_CONTEXT"] == 1
    assert restored["classification_counts"]["SITE_MISMATCH"] == 1


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

    excluded_keys = {
        key for sheet, key in load_confirmed_blanked_row_keys() if sheet == "db.cc"
    }
    effective = audit_certificate_case_source_links(
        snapshot.get("sheets", snapshot), excluded_certificate_row_keys=excluded_keys
    )
    assert effective["excluded_confirmed_blanked_certificate_count"] == 27
    assert effective["effective_certificate_source_rows"] == 1601
    assert effective["effective_classification_counts"] == {
        "ADMINISTRATIVE_NO_CASE_REFERENCE": 143,
        "EXACT_SOURCE_CONTEXT": 1455,
        "SITE_MISMATCH": 3,
    }
    assert [item["certificate_legacy_id"] for item in effective["effective_anomalies"]] == [
        376, 1037, 1180
    ]
    evidence_by_id = {
        item["certificate_legacy_id"]: item["reverse_case_reference_evidence"]
        for item in effective["effective_anomalies"]
    }
    assert evidence_by_id[376] == [
        {
            "case_legacy_id": 380,
            "site_legacy_id": 73,
            "gxp_type": "GMP",
            "same_certificate_site_and_type": True,
            "same_nonblank_certificate_number": True,
        }
    ]
    assert evidence_by_id[1037][0]["case_legacy_id"] == 1023
    assert evidence_by_id[1037][0]["same_certificate_site_and_type"] is False
    assert evidence_by_id[1037][0]["same_nonblank_certificate_number"] is True
    assert evidence_by_id[1180] == []
    assert all(item["remediation_authorized"] is False for item in effective["effective_anomalies"])


def test_confirmed_blanked_filter_changes_only_effective_counts():
    snapshot = _snapshot()
    raw = audit_certificate_case_source_links(snapshot)
    filtered = audit_certificate_case_source_links(
        snapshot, excluded_certificate_row_keys={"3"}
    )
    assert raw["classification_counts"] == filtered["classification_counts"]
    assert len(raw["anomalies"]) == 7
    assert len(filtered["anomalies"]) == 7
    assert len(filtered["effective_anomalies"]) == 6
    assert filtered["excluded_confirmed_blanked_certificate_count"] == 1
    assert filtered["effective_certificate_source_rows"] == 8
    assert filtered["effective_anomalies"][0]["certificate_legacy_id"] == 4


def test_cli_strict_is_fail_closed_but_never_writes_database(tmp_path):
    snapshot_path = tmp_path / "snapshot.json"
    output_path = tmp_path / "audit.json"
    snapshot_path.write_text(json.dumps(_snapshot(), ensure_ascii=False), encoding="utf-8")
    assert main(["--snapshot", str(snapshot_path), "--output", str(output_path)]) == 0
    assert main(["--snapshot", str(snapshot_path), "--strict"]) == 2
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["database_mutated"] is False
    assert len(payload["anomalies"]) == 7



def test_duplicate_certificate_source_identity_fails_cli_strict_even_with_valid_links(tmp_path):
    # Import rejects duplicate db.cc source row keys before schema creation.
    # The standalone read-only audit must not report a false-clean source.
    snapshot = {
        "db.ktra": [{"ID": "700", "ID CƠ SỞ": "50", "LOẠI KT": "GMP"}],
        "db.cc": [
            {"ID": "900", "ID ĐỢT KTRA": "700", "ID CƠ SỞ": "50", "LOẠI CC": "GMP"},
            {"ID": "900", "ID ĐỢT KTRA": "700", "ID CƠ SỞ": "50", "LOẠI CC": "GMP"},
        ],
    }
    report = audit_certificate_case_source_links(snapshot)
    assert report["effective_anomalies"] == []
    assert report["classification_counts"] == {"EXACT_SOURCE_CONTEXT": 2}
    assert report["source_identity_anomalies"] == [{
        "classification": "DUPLICATE_CERTIFICATE_SOURCE_ROW_KEY",
        "source_sheet": "db.cc",
        "source_row_key": "900",
        "occurrences": 2,
    }]

    # Approved exclusions must not hide a structural duplicate that would
    # still be rejected by _validate_snapshot_source_keys in the importer.
    excluded = audit_certificate_case_source_links(
        snapshot, excluded_certificate_row_keys={"900"}
    )
    assert excluded["effective_certificate_source_rows"] == 0
    assert excluded["source_identity_anomalies"] == report["source_identity_anomalies"]

    snapshot_path = tmp_path / "duplicate-source.json"
    output_path = tmp_path / "source-audit.json"
    snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
    assert main(["--snapshot", str(snapshot_path), "--output", str(output_path), "--strict"]) == 2
    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert saved["source_identity_anomalies"] == report["source_identity_anomalies"]
