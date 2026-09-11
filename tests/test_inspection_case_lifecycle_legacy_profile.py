from __future__ import annotations

from tools.audit_inspection_case_lifecycle_legacy import (
    _classify_decision_composite,
    _discover_headers,
    _profile_values,
    _shape,
)


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
