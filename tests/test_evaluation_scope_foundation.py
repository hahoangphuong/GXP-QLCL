from __future__ import annotations

from backend.app.domain.evaluation_scope import (
    build_taxonomy_artifact,
    classify_scope_corpus,
    parse_legacy_evaluation_scope,
    taxonomy_content_hash,
    validate_taxonomy_artifact,
)


def source_ranges() -> dict[str, dict[str, object]]:
    return {
        "PVCN_GMP": {"sheet_name": "Danh muc", "start_row": 10, "values": [["2", "Thuốc không vô trùng", "", "", "", "Chủ đề", "", ""], ["2.1", "Penicillin", "", "Gợi ý", "", "", "Penicillin", ""], ["2.1.13", "Viên nén", "", "", "", "", "", "x"]]},
        "PVCN_GLP": {"sheet_name": "Danh muc", "start_row": 30, "values": [["1", "Phép thử vật lý", "", "", "", "Chủ đề", "", ""], ["1.1", "Quang phổ", "", "", "", "", "Quang phổ", ""]]},
        "PVCN_GSP": {"sheet_name": "Danh muc", "start_row": 50, "values": [["1", "Kho", "", "", "", "", "Kho", ""]]},
        "PVCN_GDP": {"sheet_name": "Danh muc", "start_row": 70, "values": [["1", "Phân phối", "", "", "", "", "Phân phối", ""]]},
    }


def taxonomy():
    return build_taxonomy_artifact(workbook_name="GPs.xlsb", workbook_sha256="a" * 64, ranges=source_ranges())


def test_taxonomy_export_preserves_vba_columns_order_and_deterministic_hash():
    artifact = taxonomy()
    gmp = artifact["named_ranges"]["PVCN_GMP"]
    assert gmp["gxp_type"] == "GMP"
    assert [row["key"] for row in gmp["rows"]] == ["2", "2.1", "2.1.13"]
    assert gmp["rows"][1]["hint"] == "Gợi ý"
    assert gmp["rows"][2]["no_expand"] == "x"
    assert artifact["taxonomy_content_sha256"] == taxonomy_content_hash(artifact["named_ranges"])
    assert taxonomy()["taxonomy_content_sha256"] == artifact["taxonomy_content_sha256"]


def test_taxonomy_validation_reports_duplicates_malformed_and_synthetic_parents():
    ranges = source_ranges()
    ranges["PVCN_GMP"]["values"] = [["2.1.13", "Leaf"], ["2.1.13", "Duplicate"], ["bad.key", "Bad"]]
    report = validate_taxonomy_artifact(build_taxonomy_artifact(workbook_name="GPs.xlsb", workbook_sha256=None, ranges=ranges))
    anomalies = report["ranges"]["PVCN_GMP"]["anomalies"]
    assert {row["kind"] for row in anomalies} == {"duplicate_key", "malformed_key"}
    assert report["ranges"]["PVCN_GMP"]["synthetic_structural_parent_keys"] == ["2", "2.1"]


def test_parser_preserves_structured_payload_limitations_multiscope_and_custom_text():
    raw = "Rendered scope\r\n(*Giới hạn đánh giá*)\r\n{Line A¶2.1: Custom Penicillin\r2.1.13:\r- Ghi chú tự do¿Note A§Line B¶1.1: UV-VIS}*"
    parsed = parse_legacy_evaluation_scope(raw, gxp_type="GMP", taxonomy=taxonomy())
    assert parsed["classification"] == "STRUCTURED_PARTIAL"
    assert parsed["rendered_prose"] == "Rendered scope"
    assert parsed["limitation_text"] == "Giới hạn đánh giá"
    assert parsed["scopes"][0]["selected_nodes"][0]["description"] == "Custom Penicillin"
    assert parsed["scopes"][0]["selected_nodes"][1]["description"] == ""
    assert parsed["scopes"][0]["unkeyed_entries"] == [{"source_order": 3, "text": "- Ghi chú tự do"}]
    assert parsed["scopes"][1]["selected_nodes"][0]["taxonomy_status"] == "UNKNOWN_NODE"


def test_parser_never_recovers_nodes_from_prose_and_classifies_failures_without_repair():
    prose = "* Penicillin: Viên nén; thuốc bột."
    assert parse_legacy_evaluation_scope(prose, gxp_type="GMP", taxonomy=taxonomy())["classification"] == "PROSE_ONLY"
    malformed = parse_legacy_evaluation_scope("Rendered (*missing {2.1: x}*", gxp_type="GMP")
    assert malformed["classification"] == "STRUCTURED_MALFORMED"
    truncated = parse_legacy_evaluation_scope("Rendered {2.1: x", gxp_type="GMP")
    assert truncated["classification"] == "STRUCTURED_MALFORMED"
    assert truncated["diagnostics"] == [{"kind": "truncated_or_invalid_structured_suffix"}]
    duplicate = parse_legacy_evaluation_scope("R{2.1: A\r2.1: B}*", gxp_type="GMP", taxonomy=taxonomy())
    assert duplicate["classification"] == "STRUCTURED_PARTIAL"
    assert any(item["kind"] == "duplicate_selected_key" for item in duplicate["diagnostics"])


def test_corpus_report_reconciles_blank_prose_and_structured_classes_without_taxonomy():
    report = classify_scope_corpus(
        [
            {"ID": "1", "LOẠI KT": "GMP", "PHẠM VI KIỂM TRA": "R{2.1: A}*"},
            {"ID": "2", "LOẠI KT": "GLP", "PHẠM VI KIỂM TRA": "Prose only"},
            {"ID": "3", "LOẠI KT": "GSP", "PHẠM VI KIỂM TRA": ""},
        ]
    )
    assert report["taxonomy_validation_available"] is False
    assert report["counts"] == {"BLANK": 1, "PROSE_ONLY": 1, "STRUCTURED_VALID": 1}
