from __future__ import annotations

import pytest

from backend.app.document.c5e_certificate_detail_semantic_projection import (
    CertificateDetailSemanticProjectionError,
    PACKAGING_SPECIAL_KEYS,
    key2bookmark,
    project_certificate_detail_semantic_operations,
)


def _taxonomy():
    return [
        {
            "id": "n1",
            "key": "1",
            "main_topic": "x",
        },
        {
            "id": "n611",
            "key": "6.1.1",
            "main_topic": "",
        },
        {
            "id": "n621",
            "key": "6.2.1",
            "main_topic": "",
        },
        {
            "id": "n7",
            "key": "7.1",
            "main_topic": "",
        },
    ]


def test_packaging_identity_is_locked():
    assert PACKAGING_SPECIAL_KEYS == frozenset(
        {
            "6.1.1",
            "6.2.1",
        }
    )

    assert key2bookmark("6.1.1") == "L6_1_1"
    assert key2bookmark("6.2.1") == "L6_2_1"


def test_key2bookmark_exact_legacy_contract():
    assert key2bookmark("1") == "L1"
    assert key2bookmark(" 1. ") == "L1"
    assert key2bookmark("1.1") == "L1_1"
    assert key2bookmark("6.1.1") == "L6_1_1"
    assert key2bookmark("6.2.1") == "L6_2_1"


def test_key2bookmark_removes_only_one_final_period():
    assert key2bookmark("1..") == "L1_"


def test_projection_order():
    result = project_certificate_detail_semantic_operations(
        family_code="CERTIFICATE_ISSUANCE_WORD",
        gxp_type="GMP",
        eng_part=True,
        taxonomy_nodes=_taxonomy(),
        blocks=[
            {
                "id": "b1",
                "ordinal": 1,
                "name": "Phạm vi 1¶",
                "note": "Ghi chú 1",
                "selections": [
                    {
                        "taxonomy_node_id": "n1",
                        "source_order": 1,
                        "custom_description": "Main description",
                    },
                    {
                        "taxonomy_node_id": "n7",
                        "source_order": 2,
                        "custom_description": "A; B",
                    },
                ],
            }
        ],
    )

    assert result.source_variant == "certificate_9"
    assert result.destination_bookmark == "Pvi"

    assert [
        op.kind
        for op in result.operations
    ] == [
        "scope_heading_vi",
        "scope_heading_en",
        "formatted_fragment_copy",
        "append_custom_description_vi",
        "append_custom_description_en",
        "formatted_fragment_copy",
        "append_custom_description_vi",
        "append_custom_description_en",
        "append_scope_note_vi",
        "append_scope_note_en",
    ]

    assert result.operations[0].raw_text == "Phạm vi 1"

    assert result.operations[0].text_prefix == "* "
    assert result.operations[0].text_suffix == " - "

    assert (
        result.operations[1].translation_intent
        == "legacy_translate_ve_diachi"
    )
    assert result.operations[1].text_suffix == "\r\n"

    assert result.operations[2].source_bookmark == "L1"
    assert result.operations[5].source_bookmark == "L7_1"

    assert result.operations[3].branch == "main_topic"
    assert result.operations[6].branch == "normal"

    assert result.operations[3].text_prefix == " ("
    assert result.operations[3].text_suffix == ")"

    assert result.operations[6].text_prefix == ":\r\n\t"
    assert result.operations[6].split_separator == ";"

    assert result.operations[8].text_prefix == "\t"
    assert result.operations[8].text_suffix == "\r\n"

    assert (
        result.operations[9].translation_intent
        == "legacy_translate_ve_daychuyen_double_pass"
    )


@pytest.mark.parametrize(
    (
        "node_id",
        "bookmark",
    ),
    [
        (
            "n611",
            "L6_1_1",
        ),
        (
            "n621",
            "L6_2_1",
        ),
    ],
)
def test_packaging_special_branch(
    node_id,
    bookmark,
):
    result = project_certificate_detail_semantic_operations(
        family_code="CERTIFICATE_ISSUANCE_WORD",
        gxp_type="GMP",
        eng_part=True,
        taxonomy_nodes=_taxonomy(),
        blocks=[
            {
                "id": "b1",
                "ordinal": 1,
                "name": "",
                "note": "",
                "selections": [
                    {
                        "taxonomy_node_id": node_id,
                        "source_order": 1,
                        "custom_description": "A; B",
                    }
                ],
            }
        ],
    )

    fragment = next(
        op
        for op in result.operations
        if op.kind == "formatted_fragment_copy"
    )

    custom_vi = next(
        op
        for op in result.operations
        if op.kind == "append_custom_description_vi"
    )

    custom_en = next(
        op
        for op in result.operations
        if op.kind == "append_custom_description_en"
    )

    assert fragment.source_bookmark == bookmark

    assert custom_vi.branch == "packaging_special"
    assert custom_vi.split_separator == "; "
    assert custom_vi.text_prefix == ":\r\n\t"
    assert custom_vi.text_suffix == ""

    assert custom_en.branch == "packaging_special"
    assert custom_en.split_separator == "; "
    assert (
        custom_en.translation_intent
        == "legacy_translate_ve_daychuyen"
    )


def test_main_topic_has_priority_over_packaging_special():
    result = project_certificate_detail_semantic_operations(
        family_code="CERTIFICATE_ISSUANCE_WORD",
        gxp_type="GMP",
        eng_part=False,
        taxonomy_nodes=[
            {
                "id": "n",
                "key": "6.1.1",
                "main_topic": "x",
            }
        ],
        blocks=[
            {
                "id": "b1",
                "ordinal": 1,
                "name": "",
                "note": "",
                "selections": [
                    {
                        "taxonomy_node_id": "n",
                        "source_order": 1,
                        "custom_description": "A;",
                    }
                ],
            }
        ],
    )

    custom_vi = next(
        op
        for op in result.operations
        if op.kind == "append_custom_description_vi"
    )

    assert custom_vi.branch == "main_topic"
    assert custom_vi.split_separator is None
    assert custom_vi.text_prefix == " ("
    assert custom_vi.text_suffix == ")"


def test_packaging_special_is_gmp_only():
    result = project_certificate_detail_semantic_operations(
        family_code="CERTIFICATE_ISSUANCE_WORD",
        gxp_type="GLP",
        eng_part=False,
        taxonomy_nodes=[
            {
                "id": "n",
                "key": "6.1.1",
                "main_topic": "",
            }
        ],
        blocks=[
            {
                "id": "b1",
                "ordinal": 1,
                "name": "",
                "note": "",
                "selections": [
                    {
                        "taxonomy_node_id": "n",
                        "source_order": 1,
                        "custom_description": "A; B",
                    }
                ],
            }
        ],
    )

    custom_vi = next(
        op
        for op in result.operations
        if op.kind == "append_custom_description_vi"
    )

    assert custom_vi.branch == "normal"
    assert custom_vi.split_separator == ";"
    assert custom_vi.text_prefix == ":\r\n\t"


def test_eng_part_false_only_suppresses_custom_description_english():
    result = project_certificate_detail_semantic_operations(
        family_code="CERTIFICATE_ISSUANCE_WORD",
        gxp_type="GSP",
        eng_part=False,
        taxonomy_nodes=[
            {
                "id": "n",
                "key": "1.1",
                "main_topic": "",
            }
        ],
        blocks=[
            {
                "id": "b1",
                "ordinal": 1,
                "name": "Scope",
                "note": "Note",
                "selections": [
                    {
                        "taxonomy_node_id": "n",
                        "source_order": 1,
                        "custom_description": "Description",
                    }
                ],
            }
        ],
    )

    kinds = [
        op.kind
        for op in result.operations
    ]

    # Scope heading bilingual pair is NOT gated by EngPart.
    assert "scope_heading_vi" in kinds
    assert "scope_heading_en" in kinds

    # Only English custom-description append is gated by EngPart.
    assert "append_custom_description_vi" in kinds
    assert "append_custom_description_en" not in kinds

    # Scope notes are also bilingual regardless of EngPart.
    assert "append_scope_note_vi" in kinds
    assert "append_scope_note_en" in kinds


def test_scope_heading_exact_legacy_pair():
    result = project_certificate_detail_semantic_operations(
        family_code="CERTIFICATE_ISSUANCE_WORD",
        gxp_type="GMP",
        eng_part=False,
        taxonomy_nodes=[],
        blocks=[
            {
                "id": "b1",
                "ordinal": 1,
                "name": "Tên phạm vi¶",
                "note": "",
                "selections": [],
            }
        ],
    )

    assert [
        op.kind
        for op in result.operations
    ] == [
        "scope_heading_vi",
        "scope_heading_en",
    ]

    vi, en = result.operations

    assert vi.raw_text == "Tên phạm vi"
    assert vi.text_prefix == "* "
    assert vi.text_suffix == " - "
    assert vi.translation_intent is None

    assert en.raw_text == "Tên phạm vi"
    assert en.text_prefix == ""
    assert en.text_suffix == "\r\n"

    assert (
        en.translation_intent
        == "legacy_translate_ve_diachi"
    )


def test_scope_note_double_translation_is_unconditional():
    result = project_certificate_detail_semantic_operations(
        family_code="CERTIFICATE_ISSUANCE_WORD",
        gxp_type="GMP",
        eng_part=False,
        taxonomy_nodes=[],
        blocks=[
            {
                "id": "b1",
                "ordinal": 1,
                "name": "",
                "note": "Ghi chú",
                "selections": [],
            }
        ],
    )

    assert [
        op.kind
        for op in result.operations
    ] == [
        "append_scope_note_vi",
        "append_scope_note_en",
    ]

    vi, en = result.operations

    assert vi.raw_text == "Ghi chú"
    assert vi.text_prefix == "\t"
    assert vi.text_suffix == "\r\n"
    assert vi.translation_intent is None

    assert en.raw_text == "Ghi chú"
    assert en.text_prefix == "\t"
    assert en.text_suffix == "\r\n"

    assert (
        en.translation_intent
        == "legacy_translate_ve_daychuyen_double_pass"
    )


def test_normal_branch_geometry():
    result = project_certificate_detail_semantic_operations(
        family_code="CERTIFICATE_ISSUANCE_WORD",
        gxp_type="GMP",
        eng_part=False,
        taxonomy_nodes=[
            {
                "id": "n",
                "key": "7.1",
                "main_topic": "",
            }
        ],
        blocks=[
            {
                "id": "b1",
                "ordinal": 1,
                "name": "",
                "note": "",
                "selections": [
                    {
                        "taxonomy_node_id": "n",
                        "source_order": 1,
                        "custom_description": "A; B; C",
                    }
                ],
            }
        ],
    )

    custom_vi = next(
        op
        for op in result.operations
        if op.kind == "append_custom_description_vi"
    )

    assert custom_vi.branch == "normal"
    assert custom_vi.split_separator == ";"
    assert custom_vi.text_prefix == ":\r\n\t"
    assert custom_vi.text_suffix == ""


def test_empty_custom_description_emits_only_fragment_copy():
    result = project_certificate_detail_semantic_operations(
        family_code="CERTIFICATE_ISSUANCE_WORD",
        gxp_type="GMP",
        eng_part=True,
        taxonomy_nodes=[
            {
                "id": "n",
                "key": "1.1",
                "main_topic": "",
            }
        ],
        blocks=[
            {
                "id": "b1",
                "ordinal": 1,
                "name": "",
                "note": "",
                "selections": [
                    {
                        "taxonomy_node_id": "n",
                        "source_order": 1,
                        "custom_description": "",
                    }
                ],
            }
        ],
    )

    assert [
        op.kind
        for op in result.operations
    ] == [
        "formatted_fragment_copy",
    ]


def test_multiple_blocks_are_sorted_by_ordinal():
    result = project_certificate_detail_semantic_operations(
        family_code="CERTIFICATE_ISSUANCE_WORD",
        gxp_type="GMP",
        eng_part=False,
        taxonomy_nodes=[],
        blocks=[
            {
                "id": "b2",
                "ordinal": 2,
                "name": "Second",
                "note": "",
                "selections": [],
            },
            {
                "id": "b1",
                "ordinal": 1,
                "name": "First",
                "note": "",
                "selections": [],
            },
        ],
    )

    assert [
        op.block_id
        for op in result.operations
    ] == [
        "b1",
        "b1",
        "b2",
        "b2",
    ]

    assert [
        op.sequence
        for op in result.operations
    ] == [
        1,
        2,
        3,
        4,
    ]


def test_selection_order_is_deterministic():
    result = project_certificate_detail_semantic_operations(
        family_code="CERTIFICATE_ISSUANCE_WORD",
        gxp_type="GMP",
        eng_part=False,
        taxonomy_nodes=[
            {
                "id": "n1",
                "key": "1.1",
                "main_topic": "",
            },
            {
                "id": "n2",
                "key": "1.2",
                "main_topic": "",
            },
        ],
        blocks=[
            {
                "id": "b1",
                "ordinal": 1,
                "name": "",
                "note": "",
                "selections": [
                    {
                        "taxonomy_node_id": "n2",
                        "source_order": 2,
                        "custom_description": "",
                    },
                    {
                        "taxonomy_node_id": "n1",
                        "source_order": 1,
                        "custom_description": "",
                    },
                ],
            }
        ],
    )

    fragments = [
        op
        for op in result.operations
        if op.kind == "formatted_fragment_copy"
    ]

    assert [
        op.source_bookmark
        for op in fragments
    ] == [
        "L1_1",
        "L1_2",
    ]


def test_duplicate_taxonomy_selection_fails_closed():
    with pytest.raises(
        CertificateDetailSemanticProjectionError
    ):
        project_certificate_detail_semantic_operations(
            family_code="CERTIFICATE_ISSUANCE_WORD",
            gxp_type="GMP",
            eng_part=False,
            taxonomy_nodes=[
                {
                    "id": "n",
                    "key": "1.1",
                    "main_topic": "",
                }
            ],
            blocks=[
                {
                    "id": "b1",
                    "ordinal": 1,
                    "name": "",
                    "note": "",
                    "selections": [
                        {
                            "taxonomy_node_id": "n",
                            "source_order": 1,
                            "custom_description": "",
                        },
                        {
                            "taxonomy_node_id": "n",
                            "source_order": 2,
                            "custom_description": "",
                        },
                    ],
                }
            ],
        )


def test_fail_closed_for_unsupported_family():
    with pytest.raises(
        CertificateDetailSemanticProjectionError
    ):
        project_certificate_detail_semantic_operations(
            family_code="CERTIFICATE_DECISION",
            gxp_type="GMP",
            eng_part=True,
            taxonomy_nodes=[],
            blocks=[],
        )


def test_fail_closed_for_gdp():
    with pytest.raises(
        CertificateDetailSemanticProjectionError
    ):
        project_certificate_detail_semantic_operations(
            family_code="CERTIFICATE_ISSUANCE_WORD",
            gxp_type="GDP",
            eng_part=True,
            taxonomy_nodes=[],
            blocks=[],
        )


def test_fail_closed_for_foreign_taxonomy_id():
    with pytest.raises(
        CertificateDetailSemanticProjectionError
    ):
        project_certificate_detail_semantic_operations(
            family_code="CERTIFICATE_ISSUANCE_WORD",
            gxp_type="GMP",
            eng_part=True,
            taxonomy_nodes=[
                {
                    "id": "n1",
                    "key": "1",
                    "main_topic": "",
                }
            ],
            blocks=[
                {
                    "id": "b1",
                    "ordinal": 1,
                    "name": "",
                    "note": "",
                    "selections": [
                        {
                            "taxonomy_node_id": "outside",
                            "source_order": 1,
                            "custom_description": "",
                        }
                    ],
                }
            ],
        )


def test_blank_taxonomy_node_id_fails_closed():
    with pytest.raises(
        CertificateDetailSemanticProjectionError
    ):
        project_certificate_detail_semantic_operations(
            family_code="CERTIFICATE_ISSUANCE_WORD",
            gxp_type="GMP",
            eng_part=True,
            taxonomy_nodes=[
                {
                    "id": "",
                    "key": "1",
                    "main_topic": "",
                }
            ],
            blocks=[],
        )


def test_duplicate_taxonomy_node_id_fails_closed():
    with pytest.raises(
        CertificateDetailSemanticProjectionError
    ):
        project_certificate_detail_semantic_operations(
            family_code="CERTIFICATE_ISSUANCE_WORD",
            gxp_type="GMP",
            eng_part=True,
            taxonomy_nodes=[
                {
                    "id": "n",
                    "key": "1",
                    "main_topic": "",
                },
                {
                    "id": "n",
                    "key": "2",
                    "main_topic": "",
                },
            ],
            blocks=[],
        )


def test_blank_block_id_fails_closed():
    with pytest.raises(
        CertificateDetailSemanticProjectionError
    ):
        project_certificate_detail_semantic_operations(
            family_code="CERTIFICATE_ISSUANCE_WORD",
            gxp_type="GMP",
            eng_part=True,
            taxonomy_nodes=[],
            blocks=[
                {
                    "id": "",
                    "ordinal": 1,
                    "name": "Scope",
                    "note": "",
                    "selections": [],
                }
            ],
        )