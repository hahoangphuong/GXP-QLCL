"""Regression: legacy DDK/GxP reverse references are evidence, not links."""
from __future__ import annotations

import json
from pathlib import Path

from backend.app.domain.legacy_ddk_gxp_source_audit import audit_ddk_gxp_source_links


ROOT = Path(__file__).resolve().parents[1]


def test_ddk_gxp_source_audit_keeps_reverse_links_separate_from_import_forward_refs():
    snapshot = {
        "db.dkkd": [
            {"ID": "10", "ID CƠ SỞ": "100", "ID CTY": "1", "ID CC": ""},
            {"ID": "11", "ID CƠ SỞ": "200", "ID CTY": "2", "ID CC": ""},
            {"ID": "12", "ID CƠ SỞ": "", "ID CTY": "", "ID CC": ""},
        ],
        "db.cc": [
            {"ID": "1", "ID CƠ SỞ": "100", "ID CTY": "1", "ID DDK": "10.00"},
            {"ID": "2", "ID CƠ SỞ": "100", "ID CTY": "1", "ID DDK": "11"},
            {"ID": "3", "ID CƠ SỞ": "100", "ID CTY": "1", "ID DDK": "12"},
            {"ID": "4", "ID CƠ SỞ": "100", "ID CTY": "1", "ID DDK": "999"},
            {"ID": "5", "ID CƠ SỞ": "100", "ID CTY": "1", "ID DDK": "-"},
            {"ID": "6", "ID CƠ SỞ": "100", "ID CTY": "1", "ID DDK": "10"},
        ],
    }
    before = json.loads(json.dumps(snapshot))
    report = audit_ddk_gxp_source_links(
        snapshot, confirmed_blanked_row_keys={("db.cc", "6")},
    )
    assert report["summary"] == {
        "ddk_source_rows": 3,
        "certificate_source_rows": 6,
        "forward_nonblank_ddk_id_cc": 0,
        "reverse_nonblank_cert_id_ddk": 6,
        "reverse_literal": 5,
        "reverse_nonliteral": 1,
        "reverse_missing_target": 1,
        "reverse_excluded_confirmed_blanked": 1,
        "reverse_effective_candidates": 3,
        "reverse_same_site": 1,
        "reverse_cross_site": 1,
        "reverse_missing_site_value": 1,
        "reverse_company_mismatch": 1,
        "reverse_unique_effective_ddk": 3,
    }
    assert [(x["legacy_certificate_id"], x["legacy_ddk_id"]) for x in report["cross_site_candidates"]] == [(2, 11)]
    assert report["excluded_confirmed_blanked"][0]["legacy_certificate_id"] == 6
    assert report["missing_targets"][0]["legacy_ddk_id"] == 999
    assert report["nonliteral_reference_values"] == ["-"]
    assert snapshot == before


def test_ddk_gxp_source_corpus_gate_matches_immutable_excel_snapshot():
    snapshot = json.loads(
        (ROOT / "artifacts/phase3c/legacy_snapshot.json").read_text(encoding="utf-8")
    )
    contract = json.loads(
        (ROOT / "artifacts/phase3q/confirmed_blanked_rows.json").read_text(encoding="utf-8")
    )
    confirmed = {
        (item["source_sheet"], item["source_row_key"])
        for item in contract["rows"]
    }
    report = audit_ddk_gxp_source_links(
        snapshot, confirmed_blanked_row_keys=confirmed,
    )
    summary = report["summary"]
    assert summary == {
        "ddk_source_rows": 830,
        "certificate_source_rows": 1628,
        "forward_nonblank_ddk_id_cc": 0,
        "reverse_nonblank_cert_id_ddk": 806,
        "reverse_literal": 639,
        "reverse_nonliteral": 167,
        "reverse_missing_target": 0,
        "reverse_excluded_confirmed_blanked": 9,
        "reverse_effective_candidates": 630,
        "reverse_same_site": 628,
        "reverse_cross_site": 2,
        "reverse_missing_site_value": 0,
        "reverse_company_mismatch": 1,
        "reverse_unique_effective_ddk": 495,
    }
    assert [
        (record["legacy_certificate_id"], record["legacy_ddk_id"])
        for record in report["cross_site_candidates"]
    ] == [(790, 160), (1500, 464)]
    assert len(report["excluded_confirmed_blanked"]) == 9
    # These are competing source claims, not authorization to produce 630 links.
