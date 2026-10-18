"""No source code or runtime writes when examining same-MÃ-DC GMP lineage."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from backend.app.domain.legacy_gmp_replacement_source_audit import (
    audit_gmp_replacement_sources,
)


def _snapshot():
    return {
        "db.cso": [
            {"ID": "10", "ID Cty": "50"},
            {"ID": "11", "ID Cty": "50"},
            {"ID": "12", "ID Cty": "60"},
        ],
        "db.cc": [
            {"ID": "100", "ID CƠ SỞ": "10", "LOẠI CC": "GMP", "MÃ DC": "LINE-A",
             "Ngày cấp CC": "01/01/2020", "MỚI NHẤT": "o"},
            {"ID": "101", "ID CƠ SỞ": "11", "LOẠI CC": "GMP", "MÃ DC": "LINE-A",
             "Ngày cấp CC": "01/02/2021"},
            {"ID": "102", "ID CƠ SỞ": "10", "LOẠI CC": "GMP", "MÃ DC": "LINE-A",
             "Ngày cấp CC": "01/03/2022"},
            {"ID": "200", "ID CƠ SỞ": "12", "LOẠI CC": "GMP", "MÃ DC": "LINE-B",
             "Ngày cấp CC": "01/01/2021"},
            {"ID": "201", "ID CƠ SỞ": "12", "LOẠI CC": "GLP", "MÃ DC": "LINE-A",
             "Ngày cấp CC": "01/03/2023"},
            {"ID": "202", "ID CƠ SỞ": "12", "LOẠI CC": "GMPbb", "MÃ DC": "LINE-A",
             "Ngày cấp CC": "01/03/2023"},
            {"ID": "203", "ID CƠ SỞ": "12", "LOẠI CC": "GMP", "MÃ DC": "",
             "Ngày cấp CC": "01/03/2023"},
        ],
    }


def test_same_exact_ma_dc_order_is_review_only_and_preserves_source():
    data = _snapshot()
    before = deepcopy(data)
    report = audit_gmp_replacement_sources(data)
    assert data == before
    assert report["group_count"] == 1
    assert report["counts"]["GMP_WITH_MA_DC"] == 4
    assert report["counts"]["GMP_MISSING_MA_DC"] == 1
    group = report["groups"][0]
    assert group["source_state"] == "SOURCE_CHRONOLOGY_FOR_REVIEW"
    assert [item["legacy_certificate_id"] for item in group["certificates"]] == [100, 101, 102]
    assert group["chronological_adjacent_pairs_for_review"] == [
        {"older_legacy_certificate_id": 100, "newer_legacy_certificate_id": 101, "authorization": "REVIEW_ONLY"},
        {"older_legacy_certificate_id": 101, "newer_legacy_certificate_id": 102, "authorization": "REVIEW_ONLY"},
    ]
    assert group["replacement_authorized"] is False
    assert report["database_mutated"] is False
    assert report["source_modified"] is False
    assert report["replacement_authorized"] is False
    # No original MÃ DC values or certificate numbers are duplicated in the report.
    assert "LINE-A" not in json.dumps(report)
    assert "LINE-B" not in json.dumps(report)


def test_shared_ma_dc_across_different_companies_blocks_all_edges():
    source = _snapshot()
    source["db.cc"][2]["ID CƠ SỞ"] = "12"
    report = audit_gmp_replacement_sources(source)
    group = report["groups"][0]
    assert group["source_state"] == "BLOCKED_CROSS_COMPANY_MA_DC"
    assert group["chronological_adjacent_pairs_for_review"] == []


def test_missing_or_ambiguous_site_company_owner_blocks_inference():
    source = _snapshot()
    source["db.cso"] = source["db.cso"][:1]
    assert audit_gmp_replacement_sources(source)["groups"][0]["source_state"] == "BLOCKED_SITE_COMPANY_OWNER"
    source = _snapshot()
    source["db.cso"].append({"ID": "10", "ID Cty": "50"})
    assert audit_gmp_replacement_sources(source)["groups"][0]["source_state"] == "BLOCKED_SITE_COMPANY_OWNER"


def test_missing_or_tied_issuance_dates_block_order_and_do_not_use_latest_flag():
    source = _snapshot()
    source["db.cc"][1]["Ngày cấp CC"] = "01/01/2020"
    group = audit_gmp_replacement_sources(source)["groups"][0]
    assert group["source_state"] == "BLOCKED_MISSING_OR_EQUAL_ISSUE_DATE"
    assert group["chronological_adjacent_pairs_for_review"] == []
    source["db.cc"][1]["Ngày cấp CC"] = ""
    assert audit_gmp_replacement_sources(source)["groups"][0]["source_state"] == "BLOCKED_MISSING_OR_EQUAL_ISSUE_DATE"


def test_duplicate_or_unparseable_certificate_identity_never_creates_edges():
    source = _snapshot()
    source["db.cc"][1]["ID"] = "100"
    assert audit_gmp_replacement_sources(source)["groups"][0]["source_state"] == "BLOCKED_SOURCE_CERTIFICATE_IDENTITY"
    source["db.cc"][1]["ID"] = "100.5"
    assert audit_gmp_replacement_sources(source)["groups"][0]["source_state"] == "BLOCKED_SOURCE_CERTIFICATE_IDENTITY"


def test_approved_exclusion_is_not_guessed_and_does_not_modify_originals():
    source = _snapshot()
    report = audit_gmp_replacement_sources(source, excluded_certificate_row_keys={"101"})
    assert report["counts"]["EXCLUDED_APPROVED_SOURCE_ROW"] == 1
    assert [r["legacy_certificate_id"] for r in report["groups"][0]["certificates"]] == [100, 102]
    assert report["groups"][0]["chronological_adjacent_pairs_for_review"] == [
        {"older_legacy_certificate_id": 100, "newer_legacy_certificate_id": 102, "authorization": "REVIEW_ONLY"},
    ]
    assert source["db.cc"][1]["ID"] == "101"


def test_real_snapshot_is_read_only_and_all_source_groups_remain_unapproved():
    payload = json.loads(Path("artifacts/phase3c/legacy_snapshot.json").read_text(encoding="utf-8"))
    data = payload.get("sheets", payload)
    report = audit_gmp_replacement_sources(data)
    assert report["source_key"] == "MÃ DC"
    assert report["database_mutated"] is False
    assert report["source_modified"] is False
    assert all(group["replacement_authorized"] is False for group in report["groups"])
    assert all(
        edge["authorization"] == "REVIEW_ONLY"
        for group in report["groups"]
        for edge in group["chronological_adjacent_pairs_for_review"]
    )


def test_cli_emits_sanitized_read_only_report(monkeypatch, tmp_path, capsys):
    from tools.audit_gmp_replacement_sources import main
    from backend.app.domain import phase2_import

    source = tmp_path / "snapshot.json"
    source.write_text(json.dumps(_snapshot(), ensure_ascii=False), encoding="utf-8")
    output = tmp_path / "result.json"
    monkeypatch.setattr(phase2_import, "CONFIRMED_BLANKED_ROWS_PATH", tmp_path / "none.json")
    # The source contract loader expects its approved file to exist.
    (tmp_path / "none.json").write_text('{"rows": []}', encoding="utf-8")
    assert main(["--snapshot", str(source), "--output", str(output)]) == 0
    summary = json.loads(capsys.readouterr().out)
    detail = json.loads(output.read_text(encoding="utf-8"))
    assert summary["replacement_authorized"] is False
    assert summary["database_mutated"] is False
    assert detail["group_count"] == 1
    assert "LINE-A" not in output.read_text(encoding="utf-8")
