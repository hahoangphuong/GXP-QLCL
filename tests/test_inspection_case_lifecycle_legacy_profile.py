from __future__ import annotations

from pathlib import Path
import subprocess
import sys

from tools.audit_inspection_case_lifecycle_legacy import (
    _classify_decision_composite,
    _date_morphology,
    _discover_headers,
    _fold,
    _profile_values,
    _shape,
)


ROOT = Path(__file__).resolve().parents[1]


def test_decision_composite_classifier_is_fail_closed():
    assert _classify_decision_composite("") == "empty"
    assert _classify_decision_composite("123/QĐ-KT 10/09/2026") == "reference_plus_trailing_date"
    assert _classify_decision_composite("123/QĐ-KT\n10-09-2026") == "reference_plus_trailing_date"
    assert _classify_decision_composite("10/09/2026") == "date_only"
    assert _classify_decision_composite("123/QĐ-KT") == "no_trailing_date"
    assert _classify_decision_composite("123/QĐ-KT date unknown") == "no_trailing_date"


def test_profile_persists_shapes_not_raw_business_values():
    values = ["123/QĐ-KT 10/09/2026", "", "456/QĐ-KT 11/09/2026"]
    profile = _profile_values(values, decision_composite=True)
    assert profile["total_rows"] == 3
    assert profile["nonempty"] == 2
    assert profile["empty"] == 1
    assert profile["raw_values_persisted"] is False
    rendered = repr(profile)
    assert "123/QĐ-KT" not in rendered
    assert "456/QĐ-KT" not in rendered
    assert profile["composite_classification"]["reference_plus_trailing_date"] == 2
    assert profile["trailing_date_separator_counts"] == {"/": 2}
    assert profile["duplicate_normalized_reference_count"] == 0
    assert profile["invalid_trailing_date_count"] == 0


def test_morphology_profile_counts_sentinels_and_multiple_values():
    profile = _profile_values(["-", "???", "A, B", ""], field="certificate_expiry_date")
    assert profile["sentinel_counts"] == {"-": 1, "???": 1}
    assert profile["multi_value_count"] == 1
    assert profile["date_like_count"] == 0
    assert profile["invalid_or_non_date_count"] == 1


def test_vietnamese_folding_normalizes_d_and_preserves_ct_pct_tokens():
    assert _fold("Đánh giá") == "danh gia"
    assert _fold("đổi tên") == "doi ten"
    assert _fold("PHIẾU TRÌNH PCT") == "phieu trinh pct"

    discovered = _discover_headers({"db.ktra": [{"Đánh giá cuối": "x", "Phiếu trình PCT": "y"}]})
    assert discovered["final_evaluation"] == [{"sheet": "db.ktra", "header": "Đánh giá cuối"}]
    assert discovered["approval_vice_chair"] == [{"sheet": "db.ktra", "header": "Phiếu trình PCT"}]


def test_date_morphology_distinguishes_supported_legacy_shapes():
    cases = {
        "": "EMPTY",
        "-": "SENTINEL_DASH",
        "???": "SENTINEL_UNKNOWN",
        "2026-07-21 00:00:00+00:00": "ISO_TIMESTAMP",
        "21-07-2026": "SINGLE_DATE",
        "1-12/12/2017": "DATE_RANGE",
        "01/12-12/12/2017": "DATE_RANGE",
        "01/01/2020, 02/01/2020": "MULTI_DATE",
        "9-9": "PARTIAL_DATE",
        "2026-07-21 (dự kiến 2027)": "ANNOTATED_DATE",
        "not a date": "INVALID_OR_OTHER",
    }
    for value, expected in cases.items():
        assert _date_morphology(value) == expected


def test_date_profile_invalid_count_excludes_non_scalar_date_shapes():
    profile = _profile_values(
        ["21-07-2026", "17-19/07/2026", "01/01/2020, 02/01/2020", "9-9", "2026-07-21 (dự kiến 2027)", "???", "bad"],
        field="certificate_expiry_date",
    )
    assert profile["morphology_counts"] == {
        "SINGLE_DATE": 1,
        "DATE_RANGE": 1,
        "MULTI_DATE": 1,
        "PARTIAL_DATE": 1,
        "ANNOTATED_DATE": 1,
        "SENTINEL_UNKNOWN": 1,
        "INVALID_OR_OTHER": 1,
    }
    assert profile["date_like_count"] == 5
    assert profile["invalid_or_non_date_count"] == 1


def test_domain_normalization_merges_d_variants():
    profile = _profile_values(["Đổi tên", "doi ten"], field="inspection_type")
    assert profile["normalized_domain_counts"] == {"doi ten": 2}


def test_shape_collapses_business_content_to_morphology():
    first = _shape("123/QĐ-KT 10/09/2026")
    second = _shape("456/AB-CD 11/12/2025")
    assert "123" not in first
    assert "456" not in second
    assert "2026" not in first
    assert "2025" not in second


def test_header_discovery_is_diagnostic_and_cross_sheet():
    snapshot = {
        "db.ktra": [
            {
                "Ngày báo cáo": "x",
                "Số CV khắc phục": "y",
                "Phiếu trình PCT": "z",
                "__excel_row_number": "10",
            }
        ],
        "db.cc": [{"Phiếu trình CT": "q", "__excel_row_number": "4"}],
    }
    discovered = _discover_headers(snapshot)
    assert {item["header"] for item in discovered["report_written_on"]} == {"Ngày báo cáo"}
    assert {item["header"] for item in discovered["capa_incoming_reference"]} == {"Số CV khắc phục"}
    assert {item["header"] for item in discovered["approval_vice_chair"]} == {"Phiếu trình PCT"}
    assert "Phiếu trình CT" in {item["header"] for item in discovered["approval_chair"]}


def test_generic_ct_does_not_match_unrelated_words():
    snapshot = {"db.ktra": [{"Công tác kiểm tra": "x", "__excel_row_number": "2"}]}
    discovered = _discover_headers(snapshot)
    assert discovered["approval_chair"] == []


def test_chair_and_vice_chair_abbreviations_are_token_safe():
    snapshot = {
        "db.cc": [
            {"Phiếu trình CT": "x", "Phiếu trình PCT": "y", "Công tác": "z", "__excel_row_number": "1"}
        ]
    }
    discovered = _discover_headers(snapshot)
    assert {item["header"] for item in discovered["approval_chair"]} == {"Phiếu trình CT"}
    assert {item["header"] for item in discovered["approval_vice_chair"]} == {"Phiếu trình PCT"}


def test_multi_word_header_matching_remains_token_aware():
    snapshot = {"db.ktra": [{"Hạn kiểm tra tuân thủ": "x", "Báo cáo": "y", "__excel_row_number": "1"}]}
    discovered = _discover_headers(snapshot)
    assert discovered["compliance_due_on"] == [{"sheet": "db.ktra", "header": "Hạn kiểm tra tuân thủ"}]
    assert {item["header"] for item in discovered["report_written_on"]} == {"Báo cáo"}


def test_profile_exposes_source_headers_domains_and_migration_safety():
    standard = _profile_values(["WHO-GMP", "PIC/S", ""], field="applicable_standard")
    inspection = _profile_values(["Tái", "Tái + Mới", ""], field="inspection_type")
    assert standard["normalized_domain_counts"] == {"who-gmp": 1, "pic/s": 1}
    assert inspection["normalized_domain_counts"] == {"tai": 1, "tai + moi": 1}


def test_direct_script_entrypoint_can_import_backend_without_pythonpath():
    script = ROOT / "tools" / "audit_inspection_case_lifecycle_legacy.py"
    completed = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "Read-only legacy morphology/null-rate audit" in completed.stdout
