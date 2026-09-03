from __future__ import annotations

from backend.app.domain.evaluation_scope_vba_renderer import (
    compile_vba_node,
    compile_vba_scope_core,
)


def _taxonomy(*rows):
    return [
        {"key": key, "short_render": short_render, "source_order": index}
        for index, (key, short_render) in enumerate(rows, start=1)
    ]


def test_compile_node_ports_vba_template_and_terminator_semantics():
    # DCForm.frm :: Compile_Node — substitute first visible $$, then append '; '.
    result = compile_vba_node(
        short_render="Thuốc $$",
        custom_description="viên nén",
        contribution_id="selected:1:1",
    )
    assert result.text == "Thuốc viên nén; "
    assert [span.kind for span in result.spans] == [
        "SOURCE_TAXONOMY",
        "SOURCE_CUSTOM_DESCRIPTION",
        "VBA_RENDERER_TERMINATOR",
    ]
    assert result.continuation_marker is False


def test_compile_node_ports_vba_ampersand_suppression_exactly():
    # DCForm.frm :: Compile_Node — '&' taxonomy text is suppressed when sDesc is nonblank.
    blank = compile_vba_node(
        short_render="&Nội dung chuẩn",
        custom_description="",
        contribution_id="selected:1:1",
    )
    custom = compile_vba_node(
        short_render="&Nội dung chuẩn",
        custom_description="Nội dung riêng",
        contribution_id="selected:1:1",
    )
    assert blank.text == "Nội dung chuẩn; "
    assert custom.text == ": Nội dung riêng; "
    assert "Nội dung chuẩn" not in custom.text



def test_compile_node_ports_vba_colon_cleanup_and_blank_short_render():
    # Compile_Node always appends ": " for non-template custom text; its later
    # "::" cleanup collapses a source colon plus the generated colon.
    colon = compile_vba_node(
        short_render="Chủ đề:",
        custom_description="Nội dung",
        contribution_id="selected:1:1",
    )
    blank = compile_vba_node(
        short_render="",
        custom_description="Metadata only",
        contribution_id="selected:1:2",
    )
    assert colon.text == "Chủ đề: Nội dung; "
    assert blank.text == ""
    assert blank.spans == ()


def test_compile_node_ports_vba_ampersand_template_suppression_without_inventing_custom_text():
    # In VBA j is computed before '&' suppression.  With nonblank sDesc the
    # template is suppressed, Replace finds no visible '$$', and only the
    # compiler terminator survives.  Odd but source-faithful.
    result = compile_vba_node(
        short_render="&Ẩn $$",
        custom_description="Không được tự cứu",
        contribution_id="selected:1:1",
    )
    assert result.text == "; "
    assert all(span.kind != "SOURCE_CUSTOM_DESCRIPTION" for span in result.spans)

def test_compile_node_ports_vba_continuation_marker_as_intermediate_control_text():
    # DCForm.frm :: Compile_Node emits '<'; Compile_PVCN later removes vbCr + '<'.
    result = compile_vba_node(
        short_render="<Mục con $$",
        custom_description="A",
        contribution_id="selected:1:1.1",
    )
    assert result.text == "<Mục con A; "
    assert result.continuation_marker is True
    assert result.spans[0].kind == "SOURCE_CONTROL_CONTINUATION"


def test_compile_node_ports_vba_open_group_without_semicolon():
    result = compile_vba_node(
        short_render="Nhóm (",
        custom_description="",
        contribution_id="selected:1:1",
    )
    assert result.text == "Nhóm ("
    assert result.opens_group is True


def test_compile_scope_core_restores_required_ancestor_and_joins_continuation():
    # DCForm.frm :: Compile_Node_Full + Compile_PVCN.
    taxonomy = _taxonomy(
        ("1", "* Chủ đề:"),
        ("1.1", "<Mục con $$"),
    )
    result = compile_vba_scope_core(
        taxonomy_nodes=taxonomy,
        selections=[{"key": "1.1", "source_order": 1, "custom_description": "A"}],
        gxp_type="GLP",
    )
    assert result.text == "* Chủ đề:Mục con A."
    assert [item["role"] for item in result.contributions] == ["required_ancestor", "selected_node"]
    assert result.deferred_rules == ()


def test_compile_scope_core_closes_vba_parent_group():
    taxonomy = _taxonomy(
        ("1", "* Nhóm ("),
        ("1.1", "<Lá"),
    )
    result = compile_vba_scope_core(
        taxonomy_nodes=taxonomy,
        selections=[{"key": "1.1", "source_order": 1, "custom_description": ""}],
        gxp_type="GLP",
    )
    assert result.text == "* Nhóm (Lá)."


def test_compile_scope_core_preserves_vba_source_order_and_deduplicates_ancestor():
    taxonomy = _taxonomy(
        ("1", "* Chủ đề:"),
        ("1.1", "<Một"),
        ("1.2", "<Hai"),
    )
    result = compile_vba_scope_core(
        taxonomy_nodes=taxonomy,
        selections=[
            {"key": "1.2", "source_order": 2, "custom_description": ""},
            {"key": "1.1", "source_order": 1, "custom_description": ""},
        ],
        gxp_type="GLP",
    )
    assert result.text == "* Chủ đề:Một; Hai."
    assert sum(item["role"] == "required_ancestor" for item in result.contributions) == 1


def test_compile_scope_core_defers_gmp_detail_postprocessing_explicitly():
    taxonomy = _taxonomy(("1", "Nội dung"))
    result = compile_vba_scope_core(
        taxonomy_nodes=taxonomy,
        selections=[{"key": "1", "source_order": 1, "custom_description": ""}],
        gxp_type="GMP",
    )
    assert result.text == "Nội dung."
    assert result.deferred_rules == ("VietChitiet_PVDG_GMP", "VietChitiet_PVXX_GMP")


def test_compile_scope_core_fails_closed_when_required_taxonomy_ancestor_is_missing():
    taxonomy = _taxonomy(("1.1", "<Mục con"))
    try:
        compile_vba_scope_core(
            taxonomy_nodes=taxonomy,
            selections=[{"key": "1.1", "source_order": 1, "custom_description": ""}],
            gxp_type="GLP",
        )
    except ValueError as exc:
        assert "Missing VBA taxonomy ancestor" in str(exc)
    else:
        raise AssertionError("VBA shadow compiler must fail closed on missing ancestors")


def test_compile_vba_block_ports_name_note_header_and_get_dc_name_desc_linebreak():
    from backend.app.domain.evaluation_scope_vba_renderer import compile_vba_block

    taxonomy = _taxonomy(("1", "Nội dung"))
    result = compile_vba_block(
        ordinal=1,
        name="Dây chuyền 1",
        note="Ghi chú",
        selections=[{"key": "1", "source_order": 1, "custom_description": ""}],
        taxonomy_nodes=taxonomy,
        gxp_type="GLP",
    )
    assert result.text == "« Dây chuyền 1 » (Ghi chú)\r\nNội dung."
    assert any(span.kind == "SOURCE_BLOCK_NAME" and span.text == "Dây chuyền 1" for span in result.spans)
    assert any(span.kind == "SOURCE_BLOCK_NOTE" and span.text == "Ghi chú" for span in result.spans)


def test_compile_vba_block_preserves_vba_note_without_name_leading_space():
    from backend.app.domain.evaluation_scope_vba_renderer import compile_vba_block

    taxonomy = _taxonomy(("1", "Nội dung"))
    result = compile_vba_block(
        ordinal=1,
        name="",
        note="Ghi chú",
        selections=[{"key": "1", "source_order": 1, "custom_description": ""}],
        taxonomy_nodes=taxonomy,
        gxp_type="GLP",
    )
    # Directly mirrors IIf(note <> "", " (" & note & ")", "") in VBA.
    assert result.text == " (Ghi chú)\r\nNội dung."


def test_compile_vba_readable_scope_joins_blocks_and_limitation_like_getdata():
    from backend.app.domain.evaluation_scope_vba_renderer import compile_vba_readable_scope

    taxonomy = _taxonomy(("1", "Một"), ("2", "Hai"))
    result = compile_vba_readable_scope(
        blocks=[
            {"ordinal": 2, "name": "B", "note": "", "selections": [{"key": "2", "source_order": 1, "custom_description": ""}]},
            {"ordinal": 1, "name": "A", "note": "N", "selections": [{"key": "1", "source_order": 1, "custom_description": ""}]},
        ],
        taxonomy_nodes=taxonomy,
        limitation_text="Giới hạn",
        gxp_type="GLP",
    )
    assert result.text == "« A » (N)\r\nMột.\r\n« B »\r\nHai.\r\n(*Giới hạn*)"
    assert result.deferred_rules == ()
    assert [block.core.text for block in result.blocks] == ["Một.", "Hai."]
    assert any(span.kind == "SOURCE_LIMITATION" and span.text == "Giới hạn" for span in result.spans)


def test_compile_vba_readable_scope_uses_raw_nonblank_limitation_after_trim_gate():
    from backend.app.domain.evaluation_scope_vba_renderer import compile_vba_readable_scope

    taxonomy = _taxonomy(("1", "Một"))
    blank = compile_vba_readable_scope(
        blocks=[{"ordinal": 1, "selections": [{"key": "1", "source_order": 1, "custom_description": ""}]}],
        taxonomy_nodes=taxonomy,
        limitation_text="   ",
        gxp_type="GLP",
    )
    raw = compile_vba_readable_scope(
        blocks=[{"ordinal": 1, "selections": [{"key": "1", "source_order": 1, "custom_description": ""}]}],
        taxonomy_nodes=taxonomy,
        limitation_text="  giữ khoảng trắng  ",
        gxp_type="GLP",
    )
    assert blank.text == "Một."
    assert raw.text == "Một.\r\n(*  giữ khoảng trắng  *)"


def test_compile_vba_new_format_envelope_ports_structured_suffix_and_getdata_normalization():
    from backend.app.domain.evaluation_scope_vba_renderer import compile_vba_new_format_envelope

    taxonomy = _taxonomy(("1", "beta lactam"))
    result = compile_vba_new_format_envelope(
        blocks=[
            {
                "ordinal": 1,
                "name": "",
                "note": "",
                "raw_block_value": "1: beta lactam",
                "selections": [{"key": "1", "source_order": 1, "custom_description": ""}],
            }
        ],
        taxonomy_nodes=taxonomy,
        limitation_text=None,
        gxp_type="GLP",
    )
    assert result.structured_payload == "1: beta lactam"
    assert result.text == "β-Lactam.\r\n{1: β-Lactam}*"


def test_compile_vba_new_format_envelope_preserves_section_delimiter_source_order():
    from backend.app.domain.evaluation_scope_vba_renderer import compile_vba_new_format_envelope

    taxonomy = _taxonomy(("1", "Một"), ("2", "Hai"))
    result = compile_vba_new_format_envelope(
        blocks=[
            {"ordinal": 2, "raw_block_value": "B¶2: x¿n2", "selections": [{"key": "2", "source_order": 1, "custom_description": ""}]},
            {"ordinal": 1, "raw_block_value": "A¶1: x¿n1", "selections": [{"key": "1", "source_order": 1, "custom_description": ""}]},
        ],
        taxonomy_nodes=taxonomy,
        limitation_text="G",
        gxp_type="GLP",
    )
    assert result.structured_payload == "A¶1: x¿n1§B¶2: x¿n2"
    assert result.text.endswith("\r\n{A¶1: x¿n1§B¶2: x¿n2}*")


def test_compile_vba_new_format_envelope_fails_closed_without_raw_block_value():
    from backend.app.domain.evaluation_scope_vba_renderer import compile_vba_new_format_envelope

    taxonomy = _taxonomy(("1", "Một"))
    try:
        compile_vba_new_format_envelope(
            blocks=[{"ordinal": 1, "selections": [{"key": "1", "source_order": 1, "custom_description": ""}]}],
            taxonomy_nodes=taxonomy,
            gxp_type="GLP",
        )
    except ValueError as exc:
        assert "raw_block_value" in str(exc)
    else:
        raise AssertionError("Envelope reconstruction must fail closed without original structured block data")
