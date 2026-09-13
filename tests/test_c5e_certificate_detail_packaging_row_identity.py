from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TOOL = (
    ROOT
    / "tools"
    / "audit_c5e_certificate_detail_packaging_row_identity.py"
)


def _load_tool():
    spec = importlib.util.spec_from_file_location(
        "c5e_packaging_identity",
        TOOL,
    )

    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(
        spec
    )

    spec.loader.exec_module(
        module
    )

    return module


def test_legacy_packaging_row_constants_are_locked():
    module = _load_tool()

    assert module.PVCN_ROW_PRI_PACK == 93
    assert module.PVCN_ROW_SEC_PACK == 96


def test_identity_uses_one_based_vba_range_index():
    module = _load_tool()

    rows = [
        {
            "source_order": index,
            "source_excel_row": index + 3,
            "key": str(index),
            "description": f"row {index}",
            "main_topic": "",
            "short_render": "",
            "no_expand": "",
        }
        for index in range(1, 101)
    ]

    result = module._identity(
        rows,
        93,
    )

    assert result["vba_array_index"] == 93
    assert result[
        "taxonomy_list_index_zero_based"
    ] == 92
    assert result["source_order"] == 93
    assert result["source_excel_row"] == 96
    assert result["node_key"] == "93"