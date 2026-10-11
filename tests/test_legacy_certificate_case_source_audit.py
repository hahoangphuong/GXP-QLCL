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
    # All source-parent orphans are among the 27 previously approved blanked
    # certificates, not among the 1,455 exact links or 3 unresolved conflicts.
    assert effective["source_parent_check_available"] is True
    assert len(effective["source_parent_anomalies"]) == 27
    assert effective["effective_parent_anomalies"] == []
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
            "inspection_period_source": "07-08/12/2017",
            "same_certificate_site_and_type": True,
            "same_nonblank_certificate_number": True,
            "same_nonblank_scope_text": True,
        }
    ]
    assert evidence_by_id[1037][0]["case_legacy_id"] == 1023
    assert evidence_by_id[1037][0]["same_certificate_site_and_type"] is False
    assert evidence_by_id[1037][0]["same_nonblank_certificate_number"] is True
    assert evidence_by_id[1037][0]["same_nonblank_scope_text"] is False
    assert report["effective_anomalies"][0]["certificate_issued_at_source"] == "2018-03-12 00:00:00+00:00"
    assert report["effective_anomalies"][0]["linked_case_inspection_period_source"] == "04-05/03/2008"
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


def test_strict_audit_detects_duplicate_parent_sheet_key_with_only_administrative_certificate(tmp_path):
    # The importer validates all sheets, even when no certificate links to a
    # duplicated Case. A db.cc-only check would incorrectly report a clean input.
    snapshot = {
        "db.ktra": [
            {"ID": "700", "ID CƠ SỞ": "50", "LOẠI KT": "GMP"},
            {"ID": "700", "ID CƠ SỞ": "50", "LOẠI KT": "GMP"},
        ],
        "db.cc": [
            {"ID": "900", "ID ĐỢT KTRA": "", "ID CƠ SỞ": "50", "LOẠI CC": "GMP"},
        ],
    }
    report = audit_certificate_case_source_links(snapshot)
    assert report["effective_anomalies"] == []
    assert report["classification_counts"] == {"ADMINISTRATIVE_NO_CASE_REFERENCE": 1}
    assert report["source_identity_anomalies"] == [{
        "classification": "DUPLICATE_SOURCE_ROW_KEY",
        "source_sheet": "db.ktra",
        "source_row_key": "700",
        "occurrences": 2,
    }]
    path = tmp_path / "parent-duplicate.json"
    output = tmp_path / "parent-report.json"
    path.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
    assert main(["--snapshot", str(path), "--output", str(output), "--strict"]) == 2
    assert json.loads(output.read_text(encoding="utf-8"))["source_identity_anomalies"] == report["source_identity_anomalies"]


def test_source_identity_detection_matches_importer_for_all_sheets():
    # A certificate-only audit must not suppress structural collisions in
    # db.cty/db.cso or any other sheet known to the importer.
    for sheet in ("db.cty", "db.cso", "db.ktra", "db.Tdoi"):
        snapshot = {
            "db.ktra": [],
            "db.cc": [{"ID": "800", "ID ĐỢT KTRA": "", "ID CƠ SỞ": "50", "LOẠI CC": "GMP"}],
        }
        snapshot[sheet] = [{"ID": "42"}, {"ID": "42"}]
        report = audit_certificate_case_source_links(snapshot)
        assert report["source_identity_anomalies"] == [{
            "classification": "DUPLICATE_SOURCE_ROW_KEY",
            "source_sheet": sheet,
            "source_row_key": "42",
            "occurrences": 2,
        }], sheet
        assert report["effective_anomalies"] == [], sheet


def test_source_parent_importability_fails_closed_without_reclassifying_links(tmp_path):
    snapshot = {
        "db.cty": [{"ID": "1"}],
        "db.cso": [{"ID": "10", "ID Cty": "1"}],
        "db.ktra": [{"ID": "100", "ID CƠ SỞ": "99", "LOẠI KT": "GMP"}],
        "db.cc": [
            {"ID": "200", "ID ĐỢT KTRA": "100", "ID CƠ SỞ": "99", "LOẠI CC": "GMP"},
            {"ID": "201", "ID ĐỢT KTRA": "", "ID CƠ SỞ": "10", "LOẠI CC": "GMP"},
        ],
    }
    report = audit_certificate_case_source_links(snapshot)
    assert report["source_parent_check_available"] is True
    assert report["effective_anomalies"] == []
    assert report["classification_counts"] == {
        "ADMINISTRATIVE_NO_CASE_REFERENCE": 1,
        "EXACT_SOURCE_CONTEXT": 1,
    }
    assert [
        (item["certificate_legacy_id"], item["classification"], item["parent_source_sheet"])
        for item in report["effective_parent_anomalies"]
    ] == [
        (200, "CERTIFICATE_SITE_PARENT_NOT_IMPORTABLE", "db.cso"),
        (200, "LINKED_CASE_PARENT_NOT_IMPORTABLE", "db.ktra"),
    ]
    excluded = audit_certificate_case_source_links(
        snapshot, excluded_certificate_row_keys={"200"}
    )
    assert len(excluded["source_parent_anomalies"]) == 2
    assert excluded["effective_parent_anomalies"] == []
    path = tmp_path / "orphan-source.json"
    path.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
    assert main(["--snapshot", str(path), "--strict"]) == 2


def test_administrative_certificate_requires_materializable_site_parent(tmp_path):
    snapshot = {
        "db.cty": [{"ID": "1"}],
        "db.cso": [{"ID": "10", "ID Cty": "999"}],
        "db.ktra": [],
        "db.cc": [{"ID": "200", "ID ĐỢT KTRA": "", "ID CƠ SỞ": "10", "LOẠI CC": "GMP"}],
    }
    report = audit_certificate_case_source_links(snapshot)
    assert report["effective_anomalies"] == []
    assert report["source_parent_check_available"] is True
    assert len(report["effective_parent_anomalies"]) == 1
    assert report["effective_parent_anomalies"][0]["classification"] == "CERTIFICATE_SITE_PARENT_NOT_IMPORTABLE"
    source = tmp_path / "orphan-admin.json"
    source.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
    assert main(["--snapshot", str(source), "--strict"]) == 2


def test_cli_strict_cannot_certify_partial_source_without_parent_sheets(tmp_path):
    # Link-only analysis is allowed, but its clean result must not be mistaken
    # for an importer-compatible source-integrity acceptance decision.
    snapshot = {
        "db.ktra": [{"ID": "100", "ID CƠ SỞ": "10", "LOẠI KT": "GMP"}],
        "db.cc": [{"ID": "200", "ID ĐỢT KTRA": "100", "ID CƠ SỞ": "10", "LOẠI CC": "GMP"}],
    }
    report = audit_certificate_case_source_links(snapshot)
    assert report["effective_anomalies"] == []
    assert report["source_identity_anomalies"] == []
    assert report["effective_parent_anomalies"] == []
    assert report["source_parent_check_available"] is False
    source = tmp_path / "partial-source.json"
    source.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
    assert main(["--snapshot", str(source)]) == 0
    assert main(["--snapshot", str(source), "--strict"]) == 2


def test_reverse_case_scope_evidence_is_exact_not_a_remediation_decision():
    snapshot = {
        "db.ktra": [
            {"ID": "100", "ID CƠ SỞ": "11", "LOẠI KT": "GMP", "Ngày K.tra": "01/01/2008"},
            {"ID": "101", "ID CƠ SỞ": "10", "LOẠI KT": "GMP", "ID CC GPs": "200",
             "Mã số CC": "CERT-200", "Ngày K.tra": "01/01/2019", "PHẠM VI KIỂM TRA": "  Scope exact  "},
        ],
        "db.cc": [
            {"ID": "200", "ID ĐỢT KTRA": "100", "ID CƠ SỞ": "10", "LOẠI CC": "GMP",
             "Mã số CC": "CERT-200", "Ngày cấp CC": "2019-03-01", "PHẠM VI CHỨNG NHẬN": "Scope exact"},
        ],
    }
    report = audit_certificate_case_source_links(snapshot)
    assert report["effective_anomalies"][0]["classification"] == "SITE_MISMATCH"
    alternate = report["effective_anomalies"][0]["reverse_case_reference_evidence"][0]
    assert alternate["case_legacy_id"] == 101
    assert alternate["same_nonblank_scope_text"] is True
    assert alternate["inspection_period_source"] == "01/01/2019"
    assert report["effective_anomalies"][0]["certificate_issued_at_source"] == "2019-03-01"
    assert report["effective_anomalies"][0]["linked_case_inspection_period_source"] == "01/01/2008"
    assert report["effective_anomalies"][0]["remediation_authorized"] is False

    snapshot["db.ktra"][1]["PHẠM VI KIỂM TRA"] = "Scope extra"
    changed = audit_certificate_case_source_links(snapshot)
    assert changed["effective_anomalies"][0]["reverse_case_reference_evidence"][0]["same_nonblank_scope_text"] is False

    snapshot["db.ktra"][1]["PHẠM VI KIỂM TRA"] = ""
    snapshot["db.cc"][0]["PHẠM VI CHỨNG NHẬN"] = ""
    blanks = audit_certificate_case_source_links(snapshot)
    assert blanks["effective_anomalies"][0]["reverse_case_reference_evidence"][0]["same_nonblank_scope_text"] is False
