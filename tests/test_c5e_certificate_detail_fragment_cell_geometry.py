from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = (
    Path(__file__)
    .resolve()
    .parents[1]
)

TOOL = (
    ROOT
    / "tools"
    / "audit_c5e_certificate_detail_fragment_cell_geometry.py"
)


def _load_tool():
    spec = (
        importlib.util.spec_from_file_location(
            "c5e_fragment_cell_geometry",
            TOOL,
        )
    )

    assert spec is not None
    assert spec.loader is not None

    module = (
        importlib.util.module_from_spec(
            spec
        )
    )

    spec.loader.exec_module(
        module
    )

    return module


def test_single_row_three_cell_table():
    module = _load_tool()

    xml = f"""
<w:tbl
 xmlns:w="{module.WORD_NS}">
  <w:tr>
    <w:tc>
      <w:p>
        <w:r>
          <w:t>A</w:t>
        </w:r>
      </w:p>
    </w:tc>
    <w:tc>
      <w:p>
        <w:r>
          <w:t>B</w:t>
        </w:r>
      </w:p>
    </w:tc>
    <w:tc>
      <w:p>
        <w:r>
          <w:t>C</w:t>
        </w:r>
      </w:p>
    </w:tc>
  </w:tr>
</w:tbl>
"""

    result = (
        module._fragment_profile(
            xml
        )
    )

    assert (
        result[
            "row_count"
        ]
        == 1
    )

    assert (
        result[
            "total_cell_count"
        ]
        == 3
    )

    assert (
        result[
            "row_cell_counts"
        ]
        == [3]
    )

    assert [
        cell["text"]
        for cell
        in result[
            "rows"
        ][0]["cells"]
    ] == [
        "A",
        "B",
        "C",
    ]


def test_gridspan_and_vmerge_are_profiled():
    module = _load_tool()

    xml = f"""
<w:tbl
 xmlns:w="{module.WORD_NS}">
  <w:tr>
    <w:tc>
      <w:tcPr>
        <w:gridSpan w:val="2"/>
        <w:vMerge w:val="restart"/>
      </w:tcPr>
      <w:p>
        <w:r>
          <w:t>A</w:t>
        </w:r>
      </w:p>
    </w:tc>
    <w:tc>
      <w:tcPr>
        <w:vMerge/>
      </w:tcPr>
      <w:p/>
    </w:tc>
  </w:tr>
</w:tbl>
"""

    result = (
        module._fragment_profile(
            xml
        )
    )

    cells = (
        result["rows"][0][
            "cells"
        ]
    )

    assert (
        cells[0][
            "grid_span"
        ]
        == 2
    )

    assert (
        cells[0]["vmerge"]
        == "restart"
    )

    assert (
        cells[1]["vmerge"]
        == "continue"
    )


def test_paragraph_count_is_profiled():
    module = _load_tool()

    xml = f"""
<w:tbl
 xmlns:w="{module.WORD_NS}">
  <w:tr>
    <w:tc>
      <w:p>
        <w:r>
          <w:t>A</w:t>
        </w:r>
      </w:p>
      <w:p>
        <w:r>
          <w:t>B</w:t>
        </w:r>
      </w:p>
    </w:tc>
  </w:tr>
</w:tbl>
"""

    result = (
        module._fragment_profile(
            xml
        )
    )

    cell = (
        result["rows"][0][
            "cells"
        ][0]
    )

    assert (
        cell[
            "paragraph_count"
        ]
        == 2
    )

    assert (
        cell["text"]
        == "AB"
    )


def test_non_table_root_fails_closed():
    module = _load_tool()

    xml = f"""
<w:p
 xmlns:w="{module.WORD_NS}">
  <w:r>
    <w:t>A</w:t>
  </w:r>
</w:p>
"""

    try:
        module._fragment_profile(
            xml
        )

    except RuntimeError as exc:
        assert (
            "not w:tbl"
            in str(exc)
        )

    else:
        raise AssertionError(
            "Expected non-table root "
            "to fail closed."
        )


def test_table_without_cells_fails_closed():
    module = _load_tool()

    xml = f"""
<w:tbl
 xmlns:w="{module.WORD_NS}">
  <w:tr/>
</w:tbl>
"""

    try:
        module._fragment_profile(
            xml
        )

    except RuntimeError as exc:
        assert (
            "no direct w:tc"
            in str(exc)
        )

    else:
        raise AssertionError(
            "Expected empty table "
            "to fail closed."
        )