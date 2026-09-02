from __future__ import annotations

from backend.app.domain.evaluation_scope import (
    build_taxonomy_artifact,
    classify_scope_corpus,
    parse_legacy_evaluation_scope,
    render_evaluation_scope_summary,
    taxonomy_content_hash,
    validate_taxonomy_artifact,
)


def test_canonical_projection_composes_parent_child_groups_blocks_and_limitation_cleanly():
    nodes = [
        {"id": "parent", "key": "1", "short_render": "* Chủ đề ($$):", "source_order": 1},
        {"id": "child", "key": "1.1", "short_render": "<Mục con ($$)", "source_order": 2},
        {"id": "group", "key": "1.2", "short_render": "<Nhóm ($$) (", "source_order": 3},
        {"id": "leaf", "key": "1.2.1", "short_render": "<Lá ($$)", "source_order": 4},
    ]
    result = render_evaluation_scope_summary(
        taxonomy_nodes=nodes,
        blocks=[
            {"id": "second", "ordinal": 2, "name": "Khối hai", "note": None, "selections": [{"taxonomy_node_id": "parent", "source_order": 9, "custom_description": ""}], "unkeyed_entries": []},
            {"id": "first", "ordinal": 1, "name": "Khối một", "note": "Ghi chú", "selections": [{"taxonomy_node_id": "leaf", "source_order": 9, "custom_description": "Nội dung riêng"}, {"taxonomy_node_id": "child", "source_order": 1, "custom_description": ""}], "unkeyed_entries": []},
        ],
        limitation_text="Giới hạn",
    )
    assert result == "« Khối một » (Ghi chú)\n* Chủ đề: Mục con; Nhóm (Lá (Nội dung riêng)).\n\n« Khối hai »\n* Chủ đề.\n(*Giới hạn*)"
    assert all(token not in result for token in (":;", ";;", "()", "\n\n\n"))


def source_ranges() -> dict[str, dict[str, object]]:
    return {
        "PVCN_GMP": {"sheet_name": "Danh muc", "start_row": 10, "values": [["2", "Thuốc không vô trùng", "", "", "", "Chủ đề", "", ""], ["2.1", "Penicillin", "", "Gợi ý", "", "", "Penicillin", ""], ["2.1.13", "Viên nén", "", "", "", "", "", "x"]]},
        "PVCN_GLP": {"sheet_name": "Danh muc", "start_row": 30, "values": [["1", "Phép thử vật lý", "", "", "", "Chủ đề", "", ""], ["1.1", "Quang phổ", "", "", "", "", "Quang phổ", ""]]},
        "PVCN_GSP": {"sheet_name": "Danh muc", "start_row": 50, "values": [["1", "Kho", "", "", "", "", "Kho", ""]]},
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
    assert "PVCN_GDP" not in artifact["named_ranges"]
    assert artifact["taxonomy_availability"]["GDP"] == {"status": "unavailable", "reason": "not_defined_in_legacy_workbook"}
    assert artifact["taxonomy_content_sha256"] == taxonomy_content_hash(artifact["named_ranges"])
    assert taxonomy()["taxonomy_content_sha256"] == artifact["taxonomy_content_sha256"]


def test_taxonomy_validation_reports_duplicates_malformed_and_synthetic_parents():
    ranges = source_ranges()
    ranges["PVCN_GMP"]["values"] = [["2.1.13", "Leaf"], ["2.1.13", "Duplicate"], ["bad.key", "Bad"]]
    report = validate_taxonomy_artifact(build_taxonomy_artifact(workbook_name="GPs.xlsb", workbook_sha256=None, ranges=ranges))
    anomalies = report["ranges"]["PVCN_GMP"]["anomalies"]
    assert {row["kind"] for row in anomalies} == {"duplicate_key", "malformed_key"}
    assert report["ranges"]["PVCN_GMP"]["synthetic_structural_parent_keys"] == ["2", "2.1"]


def test_missing_each_vba_required_range_fails_closed():
    for required_range in ("PVCN_GMP", "PVCN_GLP", "PVCN_GSP"):
        ranges = source_ranges()
        del ranges[required_range]
        try:
            build_taxonomy_artifact(workbook_name="GPs.xlsb", workbook_sha256=None, ranges=ranges)
        except ValueError as exc:
            assert required_range in str(exc)
        else:
            raise AssertionError(f"{required_range} must be required")


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


def test_parser_distinguishes_unavailable_taxonomy_from_unknown_node_key():
    unavailable = parse_legacy_evaluation_scope("R{1: Distribution}*", gxp_type="GDP", taxonomy=taxonomy())
    assert unavailable["classification"] == "STRUCTURED_VALID"
    assert unavailable["taxonomy_validation"] == {"status": "unavailable", "reason": "not_defined_in_legacy_workbook"}
    assert unavailable["scopes"][0]["selected_nodes"][0]["taxonomy_status"] == "TAXONOMY_UNAVAILABLE"
    assert not unavailable["diagnostics"]

    unknown = parse_legacy_evaluation_scope("R{9.9: Unknown}*", gxp_type="GMP", taxonomy=taxonomy())
    assert unknown["classification"] == "STRUCTURED_PARTIAL"
    assert unknown["scopes"][0]["selected_nodes"][0]["taxonomy_status"] == "UNKNOWN_NODE"
