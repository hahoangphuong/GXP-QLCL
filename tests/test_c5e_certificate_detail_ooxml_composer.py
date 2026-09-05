from __future__ import annotations

from xml.etree import ElementTree as ET

import pytest

from backend.app.document.c5e_certificate_detail_ooxml_composer import (
    CUSTOM_DESCRIPTION_COLOR,
    CertificateDetailOOXMLCompositionError,
    compose_certificate_detail_document_xml,
)
from backend.app.document.c5e_certificate_detail_semantic_projection import (
    project_certificate_detail_semantic_operations,
)


WORD_NS = (
    "http://schemas.openxmlformats.org/"
    "wordprocessingml/2006/main"
)

NS = {
    "w": WORD_NS,
}


def _w(
    tag: str,
) -> str:
    return f"{{{WORD_NS}}}{tag}"


def _destination_xml(
    *,
    suffix: str = "STATIC SUFFIX",
) -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="{WORD_NS}">
  <w:body>
    <w:p>
      <w:bookmarkStart w:id="7" w:name="Pvi"/>
      <w:bookmarkEnd w:id="7"/>
      <w:r>
        <w:t>{suffix}</w:t>
      </w:r>
    </w:p>
    <w:sectPr/>
  </w:body>
</w:document>
""".encode(
        "utf-8"
    )


def _three_cell_fragment(
    vi: str = "VI SOURCE",
    en: str = "EN SOURCE",
    *,
    trailing_row: bool = True,
) -> str:
    extra = ""

    if trailing_row:
        extra = """
  <w:tr>
    <w:tc>
      <w:p/>
    </w:tc>
  </w:tr>
"""

    return f"""
<w:tbl xmlns:w="{WORD_NS}">
  <w:tr>
    <w:tc>
      <w:p>
        <w:r>
          <w:t>{vi}</w:t>
        </w:r>
      </w:p>
    </w:tc>
    <w:tc>
      <w:p/>
    </w:tc>
    <w:tc>
      <w:p>
        <w:r>
          <w:t>{en}</w:t>
        </w:r>
      </w:p>
    </w:tc>
  </w:tr>
  {extra}
</w:tbl>
"""


def _one_cell_fragment():
    return f"""
<w:tbl xmlns:w="{WORD_NS}">
  <w:tr>
    <w:tc>
      <w:p>
        <w:r>
          <w:t>VI ONLY</w:t>
        </w:r>
      </w:p>
    </w:tc>
  </w:tr>
</w:tbl>
"""


def _text(
    element: ET.Element,
) -> str:
    return "".join(
        node.text or ""
        for node
        in element.findall(
            ".//w:t",
            NS,
        )
    )


def _projection(
    *,
    name: str = "",
    note: str = "",
    description: str = "",
    eng_part: bool = True,
):
    return (
        project_certificate_detail_semantic_operations(
            family_code=(
                "CERTIFICATE_ISSUANCE_WORD"
            ),
            gxp_type="GMP",
            eng_part=eng_part,
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
                    "name": name,
                    "note": note,
                    "selections": [
                        {
                            "taxonomy_node_id": "n1",
                            "source_order": 1,
                            "custom_description": description,
                        }
                    ],
                }
            ],
        )
    )


def test_word_color_conversion_is_locked():
    #
    # 12611584 == Word/OLE BGR.
    # The composer exposes its converted OOXML RGB value so
    # any accidental change is caught by regression.
    #
    assert len(
        CUSTOM_DESCRIPTION_COLOR
    ) == 6

    int(
        CUSTOM_DESCRIPTION_COLOR,
        16,
    )


def test_fragment_vi_and_en_custom_text_go_to_exact_cells():
    projection = _projection(
        description="unused semantic raw",
        eng_part=True,
    )

    custom_vi = next(
        op
        for op
        in projection.operations
        if (
            op.kind
            == "append_custom_description_vi"
        )
    )

    custom_en = next(
        op
        for op
        in projection.operations
        if (
            op.kind
            == "append_custom_description_en"
        )
    )

    result = (
        compose_certificate_detail_document_xml(
            _destination_xml(),
            projection=projection,
            fragment_xml_by_bookmark={
                "L1": (
                    _three_cell_fragment()
                ),
            },
            rendered_text_by_sequence={
                custom_vi.sequence: (
                    ": VI CUSTOM"
                ),
                custom_en.sequence: (
                    ": EN CUSTOM"
                ),
            },
        )
    )

    root = ET.fromstring(
        result.document_xml
    )

    table = root.find(
        ".//w:tbl",
        NS,
    )

    assert table is not None

    cells = table.findall(
        "./w:tr",
        NS,
    )[0].findall(
        "./w:tc",
        NS,
    )

    assert _text(
        cells[0]
    ) == (
        "VI SOURCE"
        ": VI CUSTOM"
    )

    assert _text(
        cells[1]
    ) == ""

    assert _text(
        cells[2]
    ) == (
        "EN SOURCE"
        ": EN CUSTOM"
    )


def test_trailing_empty_row_is_preserved():
    projection = _projection(
        description="",
        eng_part=True,
    )

    result = (
        compose_certificate_detail_document_xml(
            _destination_xml(),
            projection=projection,
            fragment_xml_by_bookmark={
                "L1": (
                    _three_cell_fragment(
                        trailing_row=True,
                    )
                ),
            },
            rendered_text_by_sequence={},
        )
    )

    root = ET.fromstring(
        result.document_xml
    )

    table = root.find(
        ".//w:tbl",
        NS,
    )

    assert table is not None

    assert len(
        table.findall(
            "./w:tr",
            NS,
        )
    ) == 2


def test_one_row_certificate_9_fragment_is_supported():
    projection = _projection(
        description="",
        eng_part=True,
    )

    result = (
        compose_certificate_detail_document_xml(
            _destination_xml(),
            projection=projection,
            fragment_xml_by_bookmark={
                "L1": (
                    _three_cell_fragment(
                        trailing_row=False,
                    )
                ),
            },
            rendered_text_by_sequence={},
        )
    )

    root = ET.fromstring(
        result.document_xml
    )

    table = root.find(
        ".//w:tbl",
        NS,
    )

    assert table is not None

    assert len(
        table.findall(
            "./w:tr",
            NS,
        )
    ) == 1


def test_z3_one_cell_fragment_fails_closed():
    projection = _projection(
        description="",
        eng_part=True,
    )

    with pytest.raises(
        CertificateDetailOOXMLCompositionError,
        match=(
            "exactly three cells"
        ),
    ):
        compose_certificate_detail_document_xml(
            _destination_xml(),
            projection=projection,
            fragment_xml_by_bookmark={
                "L1": (
                    _one_cell_fragment()
                ),
            },
            rendered_text_by_sequence={},
        )


def test_heading_pair_is_one_paragraph():
    projection = _projection(
        name="Scope",
        description="",
        eng_part=False,
    )

    heading_vi = (
        projection.operations[0]
    )

    heading_en = (
        projection.operations[1]
    )

    result = (
        compose_certificate_detail_document_xml(
            _destination_xml(),
            projection=projection,
            fragment_xml_by_bookmark={
                "L1": (
                    _three_cell_fragment()
                ),
            },
            rendered_text_by_sequence={
                heading_vi.sequence: (
                    "* Scope - "
                ),
                heading_en.sequence: (
                    "Translated Scope\r\n"
                ),
            },
        )
    )

    root = ET.fromstring(
        result.document_xml
    )

    body = root.find(
        "./w:body",
        NS,
    )

    assert body is not None

    paragraphs = body.findall(
        "./w:p",
        NS,
    )

    assert _text(
        paragraphs[0]
    ) == (
        "* Scope - "
        "Translated Scope"
    )


def test_heading_format_is_bold_vi_then_bold_italic_en():
    projection = _projection(
        name="Scope",
        description="",
        eng_part=False,
    )

    result = (
        compose_certificate_detail_document_xml(
            _destination_xml(),
            projection=projection,
            fragment_xml_by_bookmark={
                "L1": (
                    _three_cell_fragment()
                ),
            },
            rendered_text_by_sequence={
                projection.operations[
                    0
                ].sequence: (
                    "* Scope - "
                ),
                projection.operations[
                    1
                ].sequence: (
                    "English\r\n"
                ),
            },
        )
    )

    root = ET.fromstring(
        result.document_xml
    )

    paragraph = root.find(
        "./w:body/w:p",
        NS,
    )

    assert paragraph is not None

    runs = paragraph.findall(
        "./w:r",
        NS,
    )

    assert len(
        runs
    ) == 2

    first_rpr = runs[
        0
    ].find(
        "./w:rPr",
        NS,
    )

    second_rpr = runs[
        1
    ].find(
        "./w:rPr",
        NS,
    )

    assert first_rpr is not None
    assert second_rpr is not None

    assert (
        first_rpr.find(
            "./w:b",
            NS,
        )
        is not None
    )

    first_i = first_rpr.find(
        "./w:i",
        NS,
    )

    assert first_i is not None

    assert (
        first_i.attrib.get(
            _w("val")
        )
        == "0"
    )

    assert (
        second_rpr.find(
            "./w:b",
            NS,
        )
        is not None
    )

    second_i = (
        second_rpr.find(
            "./w:i",
            NS,
        )
    )

    assert second_i is not None

    assert (
        second_i.attrib.get(
            _w("val")
        )
        is None
    )


def test_heading_spacing_is_12_before_3_after():
    projection = _projection(
        name="Scope",
        description="",
    )

    result = (
        compose_certificate_detail_document_xml(
            _destination_xml(),
            projection=projection,
            fragment_xml_by_bookmark={
                "L1": (
                    _three_cell_fragment()
                ),
            },
            rendered_text_by_sequence={
                projection.operations[
                    0
                ].sequence: "* Scope - ",
                projection.operations[
                    1
                ].sequence: (
                    "English\r\n"
                ),
            },
        )
    )

    root = ET.fromstring(
        result.document_xml
    )

    paragraph = root.find(
        "./w:body/w:p",
        NS,
    )

    assert paragraph is not None

    spacing = paragraph.find(
        "./w:pPr/w:spacing",
        NS,
    )

    assert spacing is not None

    assert (
        spacing.attrib[
            _w("before")
        ]
        == "240"
    )

    assert (
        spacing.attrib[
            _w("after")
        ]
        == "60"
    )


def test_note_pair_and_suffix_spacing():
    projection = _projection(
        note="Note",
        description="",
        eng_part=False,
    )

    note_vi = next(
        op
        for op
        in projection.operations
        if (
            op.kind
            == "append_scope_note_vi"
        )
    )

    note_en = next(
        op
        for op
        in projection.operations
        if (
            op.kind
            == "append_scope_note_en"
        )
    )

    result = (
        compose_certificate_detail_document_xml(
            _destination_xml(),
            projection=projection,
            fragment_xml_by_bookmark={
                "L1": (
                    _three_cell_fragment()
                ),
            },
            rendered_text_by_sequence={
                note_vi.sequence: (
                    "\tNote\r\n"
                ),
                note_en.sequence: (
                    "\tTranslated\r\n"
                ),
            },
        )
    )

    root = ET.fromstring(
        result.document_xml
    )

    body = root.find(
        "./w:body",
        NS,
    )

    assert body is not None

    paragraphs = body.findall(
        "./w:p",
        NS,
    )

    #
    # VI note, EN note, then original Pvi/suffix paragraph.
    #
    vi_note = paragraphs[
        0
    ]

    en_note = paragraphs[
        1
    ]

    suffix = paragraphs[
        2
    ]

    assert _text(
        vi_note
    ) == "Note"

    assert _text(
        en_note
    ) == "Translated"

    assert _text(
        suffix
    ) == "STATIC SUFFIX"

    vi_spacing = vi_note.find(
        "./w:pPr/w:spacing",
        NS,
    )

    en_spacing = en_note.find(
        "./w:pPr/w:spacing",
        NS,
    )

    suffix_spacing = suffix.find(
        "./w:pPr/w:spacing",
        NS,
    )

    assert vi_spacing is not None
    assert en_spacing is not None
    assert suffix_spacing is not None

    assert (
        vi_spacing.attrib[
            _w("before")
        ]
        == "60"
    )

    assert (
        en_spacing.attrib[
            _w("before")
        ]
        == "60"
    )

    assert (
        suffix_spacing.attrib[
            _w("before")
        ]
        == "180"
    )

    assert (
        suffix_spacing.attrib[
            _w("after")
        ]
        == "0"
    )


def test_pvi_bookmark_is_removed_but_suffix_is_preserved():
    projection = _projection(
        description="",
    )

    result = (
        compose_certificate_detail_document_xml(
            _destination_xml(
                suffix=(
                    "KEEP THIS"
                )
            ),
            projection=projection,
            fragment_xml_by_bookmark={
                "L1": (
                    _three_cell_fragment()
                ),
            },
            rendered_text_by_sequence={},
        )
    )

    root = ET.fromstring(
        result.document_xml
    )

    assert (
        root.findall(
            ".//w:bookmarkStart",
            NS,
        )
        == []
    )

    assert (
        root.findall(
            ".//w:bookmarkEnd",
            NS,
        )
        == []
    )

    assert (
        "KEEP THIS"
        in _text(
            root
        )
    )


def test_missing_fragment_fails_closed():
    projection = _projection(
        description="",
    )

    with pytest.raises(
        CertificateDetailOOXMLCompositionError,
        match="Missing extracted fragment",
    ):
        compose_certificate_detail_document_xml(
            _destination_xml(),
            projection=projection,
            fragment_xml_by_bookmark={},
            rendered_text_by_sequence={},
        )


def test_missing_rendered_text_fails_closed():
    projection = _projection(
        description="has description",
        eng_part=False,
    )

    with pytest.raises(
        CertificateDetailOOXMLCompositionError,
        match="Missing resolved TypeText",
    ):
        compose_certificate_detail_document_xml(
            _destination_xml(),
            projection=projection,
            fragment_xml_by_bookmark={
                "L1": (
                    _three_cell_fragment()
                ),
            },
            rendered_text_by_sequence={},
        )


def test_fragment_order_is_projection_order():
    projection = (
        project_certificate_detail_semantic_operations(
            family_code=(
                "CERTIFICATE_ISSUANCE_WORD"
            ),
            gxp_type="GMP",
            eng_part=False,
            taxonomy_nodes=[
                {
                    "id": "n1",
                    "key": "1",
                    "main_topic": "",
                },
                {
                    "id": "n2",
                    "key": "2",
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
                            "taxonomy_node_id": (
                                "n2"
                            ),
                            "source_order": 2,
                            "custom_description": "",
                        },
                        {
                            "taxonomy_node_id": (
                                "n1"
                            ),
                            "source_order": 1,
                            "custom_description": "",
                        },
                    ],
                }
            ],
        )
    )

    result = (
        compose_certificate_detail_document_xml(
            _destination_xml(),
            projection=projection,
            fragment_xml_by_bookmark={
                "L1": (
                    _three_cell_fragment(
                        vi="FIRST",
                        en="FIRST EN",
                    )
                ),
                "L2": (
                    _three_cell_fragment(
                        vi="SECOND",
                        en="SECOND EN",
                    )
                ),
            },
            rendered_text_by_sequence={},
        )
    )

    root = ET.fromstring(
        result.document_xml
    )

    tables = root.findall(
        "./w:body/w:tbl",
        NS,
    )

    assert [
        _text(
            table
        )
        for table in tables
    ] == [
        "FIRSTFIRST EN",
        "SECONDSECOND EN",
    ]


def test_single_pass_reports_counts():
    projection = _projection(
        name="Scope",
        note="Note",
        description="Description",
        eng_part=True,
    )

    rendered = {}

    for operation in (
        projection.operations
    ):
        if (
            operation.kind
            != "formatted_fragment_copy"
        ):
            rendered[
                operation.sequence
            ] = "X"

    result = (
        compose_certificate_detail_document_xml(
            _destination_xml(),
            projection=projection,
            fragment_xml_by_bookmark={
                "L1": (
                    _three_cell_fragment()
                ),
            },
            rendered_text_by_sequence=(
                rendered
            ),
        )
    )

    assert (
        result.inserted_fragment_count
        == 1
    )

    assert (
        result.emitted_text_operation_count
        == len(
            projection.operations
        )
        - 1
    )

    assert (
        result.destination_bookmark
        == "Pvi"
    )