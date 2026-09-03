from __future__ import annotations

import pytest

from backend.app.domain.evaluation_scope_document_projection import (
    DOCUMENT_SCOPE_BRANCHES,
    build_vba_document_scope_variants,
    project_vba_document_scope_fields,
)


def _taxonomy():
    return [
        {"id": "root", "key": "1", "parent_key": None, "short_render": "* Root", "description": "Root", "source_order": 1},
        {"id": "child", "key": "1.1", "parent_key": "1", "short_render": "Child $$", "description": "Child", "source_order": 2},
    ]


def _blocks(*, include_unkeyed: bool = False):
    block = {
        "id": "block-1",
        "ordinal": 1,
        "name": None,
        "note": None,
        "selections": [{"taxonomy_node_id": "child", "key": "1.1", "source_order": 1, "custom_description": "beta lactam"}],
    }
    if include_unkeyed:
        block["unkeyed_entries"] = [{"source_order": 2, "text": "- NEVER RESURRECT"}]
    return [block]


def test_source_derived_document_branch_table_is_exact_and_comment_only_write_stays_inactive():
    assert DOCUMENT_SCOPE_BRANCHES["INSPECTION_QD_KT"]["fields"] == {}
    assert set(DOCUMENT_SCOPE_BRANCHES["INSPECTION_KE_HOACH_KT"]["fields"]) == {"Daychuyen", "GioiHanPvi"}
    assert set(DOCUMENT_SCOPE_BRANCHES["INSPECTION_BB_KT"]["fields"]) == {"Daychuyen", "GhPviDG", "GhPviCN"}
    assert DOCUMENT_SCOPE_BRANCHES["CERTIFICATE_DECISION"]["fields"] == {}
    assert DOCUMENT_SCOPE_BRANCHES["CERTIFICATE_DECISION"]["commented_only"] == {"Daychuyen": "DaychuyenX"}


def test_variants_are_built_from_canonical_scope_and_never_from_unkeyed_legacy_rows():
    variants = build_vba_document_scope_variants(
        blocks=_blocks(include_unkeyed=True),
        taxonomy_nodes=_taxonomy(),
        limitation_text="Phạm vi chứng nhận beta lactam",
        gxp_type="GLP",
    )
    assert "NEVER RESURRECT" not in variants.dc_cu
    assert "β-Lactam" in variants.dc_cu
    assert variants.daychuyen_dd == variants.dc_cu
    assert "*" not in variants.daychuyen_lf
    assert variants.ghan_dc == "Phạm vi chứng nhận β-Lactam"


def test_branch_aware_scalar_fields_match_active_vba_writes():
    common = dict(blocks=_blocks(), taxonomy_nodes=_taxonomy(), limitation_text="Phạm vi chứng nhận A", gxp_type="GLP")

    assert set(project_vba_document_scope_fields(family_code="INSPECTION_BBTD_HOSO_DK", **common).fields) == {"Daychuyen"}
    assert project_vba_document_scope_fields(family_code="INSPECTION_QD_KT", **common).fields == {}
    assert set(project_vba_document_scope_fields(family_code="INSPECTION_KE_HOACH_KT", **common).fields) == {"Daychuyen", "GioiHanPvi"}

    bbkt = project_vba_document_scope_fields(family_code="INSPECTION_BB_KT", **common).fields
    assert set(bbkt) == {"Daychuyen", "GhPviDG", "GhPviCN"}
    assert bbkt["GhPviDG"] == "Phạm vi đánh giá A"
    assert bbkt["GhPviCN"] == "Phạm vi chứng nhận A"

    pct = project_vba_document_scope_fields(family_code="INSPECTION_PT_PCT", **common).fields
    assert set(pct) == {"Daychuyen", "Daychuyen2", "GioihanPvi"}

    assessment = project_vba_document_scope_fields(family_code="ASSESSMENT_MINUTES", **common).fields
    assert set(assessment) == {"DayChuyen", "GioiHanPvi"}
    assert assessment["GioiHanPvi"] == "Phạm vi đánh giá A"
    assert project_vba_document_scope_fields(family_code="CERTIFICATE_DECISION", **common).fields == {}


def test_blank_limitation_defaults_only_on_branches_where_vba_used_iif_default():
    common = dict(blocks=_blocks(), taxonomy_nodes=_taxonomy(), limitation_text="", gxp_type="GLP")
    assert project_vba_document_scope_fields(family_code="INSPECTION_KE_HOACH_KT", **common).fields["GioiHanPvi"] == "Không"
    bbkt = project_vba_document_scope_fields(family_code="INSPECTION_BB_KT", **common).fields
    assert bbkt["GhPviDG"] == "Không"
    assert bbkt["GhPviCN"] == "Không"
    assert project_vba_document_scope_fields(family_code="ASSESSMENT_MINUTES", **common).fields["GioiHanPvi"] == "Không"
    assert project_vba_document_scope_fields(family_code="INSPECTION_PT_PCT", **common).fields["GioihanPvi"] == ""


def test_pt_ct_copypt_branch_bypasses_scalar_scope_writes():
    common = dict(blocks=_blocks(), taxonomy_nodes=_taxonomy(), limitation_text="GH", gxp_type="GLP")
    assert project_vba_document_scope_fields(family_code="INSPECTION_PT_CT", copy_pt=True, **common).fields == {}
    assert set(project_vba_document_scope_fields(family_code="INSPECTION_PT_CT", copy_pt=False, **common).fields) == {"Daychuyen", "Daychuyen2", "GioihanPvi"}


def test_unsupported_document_family_fails_closed():
    with pytest.raises(ValueError, match="Unsupported C.5e"):
        project_vba_document_scope_fields(
            family_code="UNKNOWN",
            blocks=_blocks(),
            taxonomy_nodes=_taxonomy(),
            limitation_text=None,
            gxp_type="GLP",
        )
