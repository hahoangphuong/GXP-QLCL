from __future__ import annotations

from tools.audit_evaluation_scope_vba_shadow_corpus import audit


def _taxonomy() -> dict:
    return {
        "named_ranges": {
            "PVCN_GLP": {
                "gxp_type": "GLP",
                "rows": [
                    {
                        "key": "1",
                        "description": "Mục một",
                        "short_render": "&Mục",
                        "source_order": 1,
                    }
                ],
            }
        },
        "taxonomy_availability": {"GLP": {"status": "available"}},
    }


def test_shadow_corpus_audit_keeps_three_projections_diagnostic_not_failure_gate():
    snapshot = {
        "db.ktra": [
            {
                "ID": "K1",
                "LOẠI KT": "GLP",
                "PHẠM VI KIỂM TRA": "Prose lịch sử khác\r\n{1: tùy chỉnh}*",
            }
        ]
    }
    result = audit(snapshot, _taxonomy())

    assert result["counts"]["structured_records"] == 1
    assert result["counts"]["historical_vs_vba_exact_mismatch"] == 1
    assert result["counts"]["python_vs_vba_exact_mismatch"] == 1
    assert result["hard_failures"] == {
        "taxonomy_unavailable": 0,
        "compile_exceptions": 0,
        "deferred_rule_records": 0,
        "span_integrity_failures": 0,
    }
    assert result["contract"]["historical_prose_role"] == "history_diagnostic_not_oracle"
    assert result["contract"]["current_python_renderer_role"] == "compatibility_reference_not_oracle"


def test_shadow_corpus_audit_reports_unavailable_taxonomy_as_hard_failure():
    taxonomy = _taxonomy()
    taxonomy["taxonomy_availability"]["GDP"] = {
        "status": "unavailable",
        "reason": "not_defined_in_legacy_workbook",
    }
    snapshot = {
        "db.ktra": [
            {
                "ID": "K2",
                "LOẠI KT": "GDP",
                "PHẠM VI KIỂM TRA": "History\r\n{1: tùy chỉnh}*",
            }
        ]
    }
    result = audit(snapshot, taxonomy)

    assert result["counts"]["structured_records"] == 1
    assert result["hard_failures"]["taxonomy_unavailable"] == 1
    assert result["bounded_examples"]["taxonomy_unavailable"][0]["legacy_inspection_id"] == "K2"
