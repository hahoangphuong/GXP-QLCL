from __future__ import annotations

from tools.audit_evaluation_scope_vba_taxonomy_coverage import audit


def _taxonomy() -> dict:
    return {
        "named_ranges": {
            "PVCN_GLP": {
                "source_name": "PVCN_GLP",
                "gxp_type": "GLP",
                "rows": [
                    {
                        "key": "1",
                        "description": "Mục 1",
                        "short_render": "1. Mục ($$):",
                        "source_order": 1,
                    },
                    {
                        "key": "1.1",
                        "description": "Mục 1.1",
                        "short_render": "<Chi tiết $$",
                        "source_order": 2,
                    },
                ],
            },
            "PVCN_GSP": {
                "source_name": "PVCN_GSP",
                "gxp_type": "GSP",
                "rows": [
                    {
                        "key": "1",
                        "description": "Kho",
                        "short_render": "",
                        "source_order": 1,
                    },
                    {
                        "key": "1.1",
                        "description": "Bảo quản",
                        "short_render": "<Bảo quản",
                        "source_order": 2,
                    },
                ],
            },
        },
        "taxonomy_availability": {
            "GLP": {"status": "available", "source_name": "PVCN_GLP"},
            "GSP": {"status": "available", "source_name": "PVCN_GSP"},
            "GDP": {"status": "unavailable", "reason": "not_defined_in_legacy_workbook"},
        },
    }


def _snapshot() -> dict:
    return {
        "db.ktra": [
            {"LOẠI KT": "GLP"},
            {"LOẠI KT": "GMPbb"},
            {"LOẠI KT": "GMPbb"},
        ]
    }


def test_taxonomy_coverage_exercises_unseen_available_family_synthetically():
    result = audit(_taxonomy(), _snapshot())

    assert result["hard_failures"] == {
        "node_compile_failures": 0,
        "family_sequence_failures": 0,
    }
    assert result["families"]["GLP"]["historical_corpus_exercised"] is True
    assert result["families"]["GLP"]["coverage_role"] == "historical_plus_exhaustive_taxonomy"
    assert result["families"]["GSP"]["historical_corpus_exercised"] is False
    assert result["families"]["GSP"]["coverage_role"] == "exhaustive_taxonomy_synthetic_only"
    assert result["families"]["GSP"]["counts"]["blank_custom_pass"] == 2
    assert result["families"]["GSP"]["counts"]["nonblank_custom_pass"] == 2


def test_taxonomy_coverage_keeps_gdp_and_gmpbb_fail_closed_and_distinct():
    result = audit(_taxonomy(), _snapshot())

    assert result["taxonomy_unavailable"]["GDP"]["status"] == "unavailable"
    assert result["contract"]["gdp_policy"] == "fail_closed_when_taxonomy_unavailable"
    assert result["non_taxonomy_legacy_types"] == {"GMPbb": 2}
    assert result["contract"]["gmpbb_policy"] == "distinct_legacy_prose_family_never_alias_to_gmp"
