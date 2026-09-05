from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Mapping
from xml.etree import ElementTree as ET

from backend.app.document.c5e_certificate_detail_semantic_projection import (
    CERTIFICATE_DETAIL_DESTINATION_BOOKMARK,
    CERTIFICATE_DETAIL_SOURCE_VARIANT,
    CertificateDetailSemanticProjection,
)


WORD_NS = (
    "http://schemas.openxmlformats.org/"
    "wordprocessingml/2006/main"
)

XML_NS = (
    "http://www.w3.org/XML/1998/namespace"
)

NS = {
    "w": WORD_NS,
}


def _w(
    tag: str,
) -> str:
    return f"{{{WORD_NS}}}{tag}"


class CertificateDetailOOXMLCompositionError(
    RuntimeError
):
    pass


@dataclass(frozen=True)
class CertificateDetailOOXMLCompositionResult:
    document_xml: bytes
    inserted_fragment_count: int
    emitted_text_operation_count: int
    destination_bookmark: str


def _parent_map(
    root: ET.Element,
) -> dict[
    ET.Element,
    ET.Element,
]:
    return {
        child: parent
        for parent in root.iter()
        for child in list(parent)
    }


def _nearest(
    node: ET.Element,
    parents: Mapping[
        ET.Element,
        ET.Element,
    ],
    tag: str,
) -> ET.Element | None:
    target = _w(
        tag
    )

    current = node

    while True:
        if (
            current.tag
            == target
        ):
            return current

        if (
            current
            not in parents
        ):
            return None

        current = parents[
            current
        ]


def _word_color_to_rgb_hex(
    value: int,
) -> str:
    """
    VBA/Word Color values use the classic OLE BGR integer
    representation.

    Convert:
        0x00BBGGRR
    to OOXML:
        RRGGBB
    """

    if (
        value < 0
        or value > 0xFFFFFF
    ):
        raise (
            CertificateDetailOOXMLCompositionError(
                "Unsupported Word color value: "
                f"{value!r}."
            )
        )

    red = (
        value
        & 0xFF
    )

    green = (
        value
        >> 8
    ) & 0xFF

    blue = (
        value
        >> 16
    ) & 0xFF

    return (
        f"{red:02X}"
        f"{green:02X}"
        f"{blue:02X}"
    )


CUSTOM_DESCRIPTION_COLOR = (
    _word_color_to_rgb_hex(
        12611584
    )
)


def _get_or_create_child(
    parent: ET.Element,
    tag: str,
    *,
    insert_first: bool = False,
) -> ET.Element:
    qualified = _w(
        tag
    )

    existing = parent.find(
        f"./w:{tag}",
        NS,
    )

    if existing is not None:
        return existing

    child = ET.Element(
        qualified
    )

    if insert_first:
        parent.insert(
            0,
            child,
        )

    else:
        parent.append(
            child
        )

    return child


def _set_on_off(
    rpr: ET.Element,
    tag: str,
    enabled: bool,
) -> None:
    node = rpr.find(
        f"./w:{tag}",
        NS,
    )

    if node is None:
        node = ET.SubElement(
            rpr,
            _w(
                tag
            ),
        )

    if enabled:
        node.attrib.pop(
            _w("val"),
            None,
        )

    else:
        node.set(
            _w("val"),
            "0",
        )


def _set_run_format(
    run: ET.Element,
    *,
    bold: bool,
    italic: bool,
    color: str | None = None,
) -> None:
    rpr = run.find(
        "./w:rPr",
        NS,
    )

    if rpr is None:
        rpr = ET.Element(
            _w("rPr")
        )

        run.insert(
            0,
            rpr,
        )

    _set_on_off(
        rpr,
        "b",
        bold,
    )

    _set_on_off(
        rpr,
        "i",
        italic,
    )

    color_node = rpr.find(
        "./w:color",
        NS,
    )

    if color is None:
        if color_node is not None:
            rpr.remove(
                color_node
            )

    else:
        if color_node is None:
            color_node = (
                ET.SubElement(
                    rpr,
                    _w("color"),
                )
            )

        color_node.set(
            _w("val"),
            color,
        )


def _set_paragraph_spacing(
    paragraph: ET.Element,
    *,
    before_points: int | None = None,
    after_points: int | None = None,
) -> None:
    ppr = paragraph.find(
        "./w:pPr",
        NS,
    )

    if ppr is None:
        ppr = ET.Element(
            _w("pPr")
        )

        paragraph.insert(
            0,
            ppr,
        )

    spacing = ppr.find(
        "./w:spacing",
        NS,
    )

    if spacing is None:
        spacing = ET.SubElement(
            ppr,
            _w("spacing"),
        )

    #
    # OOXML paragraph spacing is in twentieths of a point.
    #
    if (
        before_points
        is not None
    ):
        spacing.set(
            _w("before"),
            str(
                before_points
                * 20
            ),
        )

    if (
        after_points
        is not None
    ):
        spacing.set(
            _w("after"),
            str(
                after_points
                * 20
            ),
        )


def _append_text_tokens_to_paragraph(
    paragraph: ET.Element,
    text: str,
    *,
    bold: bool,
    italic: bool,
    color: str | None,
) -> None:
    """
    Append text to one paragraph.

    Tabs become w:tab. Newlines are handled by the caller
    because VBA vbCrLf creates paragraph boundaries in the
    relevant TypeText paths.
    """

    parts = text.split(
        "\t"
    )

    for index, part in enumerate(
        parts
    ):
        if index:
            tab_run = ET.SubElement(
                paragraph,
                _w("r"),
            )

            _set_run_format(
                tab_run,
                bold=bold,
                italic=italic,
                color=color,
            )

            ET.SubElement(
                tab_run,
                _w("tab"),
            )

        if not part:
            continue

        run = ET.SubElement(
            paragraph,
            _w("r"),
        )

        _set_run_format(
            run,
            bold=bold,
            italic=italic,
            color=color,
        )

        text_node = ET.SubElement(
            run,
            _w("t"),
        )

        if (
            part.startswith(" ")
            or part.endswith(" ")
        ):
            text_node.set(
                f"{{{XML_NS}}}space",
                "preserve",
            )

        text_node.text = part


def _copy_paragraph_properties(
    paragraph: ET.Element,
) -> ET.Element:
    result = ET.Element(
        _w("p")
    )

    ppr = paragraph.find(
        "./w:pPr",
        NS,
    )

    if ppr is not None:
        result.append(
            deepcopy(
                ppr
            )
        )

    return result


def _append_type_text_to_cell(
    cell: ET.Element,
    text: str,
    *,
    bold: bool,
    italic: bool,
    color: str | None,
) -> None:
    """
    Semantic equivalent of VBA TypeText inside one known
    certificate_9 cell.

    CRLF creates another paragraph within the same cell.
    Existing source cell content is preserved.
    """

    normalized = (
        text.replace(
            "\r\n",
            "\n",
        )
        .replace(
            "\r",
            "\n",
        )
    )

    paragraphs = cell.findall(
        "./w:p",
        NS,
    )

    if not paragraphs:
        paragraph = ET.SubElement(
            cell,
            _w("p"),
        )

    else:
        paragraph = paragraphs[
            -1
        ]

    segments = normalized.split(
        "\n"
    )

    for index, segment in enumerate(
        segments
    ):
        if index:
            new_paragraph = (
                _copy_paragraph_properties(
                    paragraph
                )
            )

            cell.append(
                new_paragraph
            )

            paragraph = (
                new_paragraph
            )

        _append_text_tokens_to_paragraph(
            paragraph,
            segment,
            bold=bold,
            italic=italic,
            color=color,
        )


def _new_paragraph_with_text(
    text: str,
    *,
    bold: bool,
    italic: bool,
    color: str | None = None,
    before_points: int | None = None,
    after_points: int | None = None,
) -> ET.Element:
    paragraph = ET.Element(
        _w("p")
    )

    if (
        before_points
        is not None
        or after_points
        is not None
    ):
        _set_paragraph_spacing(
            paragraph,
            before_points=(
                before_points
            ),
            after_points=(
                after_points
            ),
        )

    normalized = (
        text.replace(
            "\r\n",
            "\n",
        )
        .replace(
            "\r",
            "\n",
        )
    )

    #
    # This helper represents one VBA TypeText paragraph.
    # Ignore its final CRLF because the paragraph itself is
    # the paragraph boundary.
    #
    if normalized.endswith(
        "\n"
    ):
        normalized = (
            normalized[:-1]
        )

    #
    # Any unexpected embedded CRLF would require more than
    # one paragraph and therefore cannot silently be folded
    # into this helper.
    #
    if "\n" in normalized:
        raise (
            CertificateDetailOOXMLCompositionError(
                "Unexpected embedded paragraph break "
                "in single-paragraph text operation."
            )
        )

    _append_text_tokens_to_paragraph(
        paragraph,
        normalized,
        bold=bold,
        italic=italic,
        color=color,
    )

    return paragraph


def _append_run_text(
    paragraph: ET.Element,
    text: str,
    *,
    bold: bool,
    italic: bool,
    color: str | None = None,
) -> None:
    normalized = (
        text.replace(
            "\r\n",
            "\n",
        )
        .replace(
            "\r",
            "\n",
        )
    )

    if normalized.endswith(
        "\n"
    ):
        normalized = (
            normalized[:-1]
        )

    if "\n" in normalized:
        raise (
            CertificateDetailOOXMLCompositionError(
                "Unexpected embedded paragraph break "
                "while extending paragraph."
            )
        )

    _append_text_tokens_to_paragraph(
        paragraph,
        normalized,
        bold=bold,
        italic=italic,
        color=color,
    )


def _parse_certificate_9_fragment(
    fragment_xml: str,
) -> ET.Element:
    try:
        table = ET.fromstring(
            fragment_xml
        )

    except ET.ParseError as exc:
        raise (
            CertificateDetailOOXMLCompositionError(
                "Certificate-detail fragment XML "
                "is invalid."
            )
        ) from exc

    if (
        table.tag
        != _w("tbl")
    ):
        raise (
            CertificateDetailOOXMLCompositionError(
                "Certificate-detail source fragment "
                "must be w:tbl."
            )
        )

    rows = table.findall(
        "./w:tr",
        NS,
    )

    if not rows:
        raise (
            CertificateDetailOOXMLCompositionError(
                "certificate_9 fragment has no rows."
            )
        )

    #
    # Proven certificate_9 contract:
    #
    # row 1:
    #   cell 1 = VI
    #   cell 2 = spacer
    #   cell 3 = EN
    #
    # Optional row 2 is preserved unchanged.
    #
    first_row_cells = rows[
        0
    ].findall(
        "./w:tc",
        NS,
    )

    if (
        len(
            first_row_cells
        )
        != 3
    ):
        raise (
            CertificateDetailOOXMLCompositionError(
                "Unsupported certificate_9 fragment "
                "geometry: first row must contain "
                "exactly three cells."
            )
        )

    #
    # No merged geometry was observed in the complete
    # 401-fragment certificate_9 corpus. Fail closed if
    # runtime source drifts from that evidence.
    #
    for cell in (
        first_row_cells
    ):
        tcpr = cell.find(
            "./w:tcPr",
            NS,
        )

        if tcpr is None:
            continue

        if (
            tcpr.find(
                "./w:gridSpan",
                NS,
            )
            is not None
            or tcpr.find(
                "./w:vMerge",
                NS,
            )
            is not None
        ):
            raise (
                CertificateDetailOOXMLCompositionError(
                    "Unsupported merged-cell geometry "
                    "in certificate_9 fragment."
                )
            )

    return table


def _find_collapsed_destination_bookmark(
    root: ET.Element,
    *,
    bookmark_name: str,
) -> tuple[
    ET.Element,
    ET.Element,
    ET.Element,
]:
    starts = [
        node
        for node
        in root.findall(
            ".//w:bookmarkStart",
            NS,
        )
        if (
            node.attrib.get(
                _w("name")
            )
            == bookmark_name
        )
    ]

    if len(
        starts
    ) != 1:
        raise (
            CertificateDetailOOXMLCompositionError(
                "Expected exactly one destination "
                f"bookmark {bookmark_name!r}; "
                f"found {len(starts)}."
            )
        )

    start = starts[
        0
    ]

    bookmark_id = (
        start.attrib.get(
            _w("id")
        )
    )

    if bookmark_id is None:
        raise (
            CertificateDetailOOXMLCompositionError(
                "Destination bookmark has no w:id."
            )
        )

    ends = [
        node
        for node
        in root.findall(
            ".//w:bookmarkEnd",
            NS,
        )
        if (
            node.attrib.get(
                _w("id")
            )
            == bookmark_id
        )
    ]

    if len(
        ends
    ) != 1:
        raise (
            CertificateDetailOOXMLCompositionError(
                "Expected exactly one matching "
                "destination bookmarkEnd."
            )
        )

    end = ends[
        0
    ]

    parents = _parent_map(
        root
    )

    start_parent = parents.get(
        start
    )

    end_parent = parents.get(
        end
    )

    if (
        start_parent is None
        or end_parent is None
        or start_parent
        is not end_parent
        or start_parent.tag
        != _w("p")
    ):
        raise (
            CertificateDetailOOXMLCompositionError(
                "Destination Pvi bookmark must be "
                "collapsed in one paragraph."
            )
        )

    paragraph = (
        start_parent
    )

    children = list(
        paragraph
    )

    start_index = children.index(
        start
    )

    end_index = children.index(
        end
    )

    if (
        end_index
        != start_index + 1
    ):
        raise (
            CertificateDetailOOXMLCompositionError(
                "Destination Pvi bookmark markers "
                "must be adjacent."
            )
        )

    paragraph_parent = (
        parents.get(
            paragraph
        )
    )

    if paragraph_parent is None:
        raise (
            CertificateDetailOOXMLCompositionError(
                "Destination Pvi paragraph "
                "has no parent."
            )
        )

    return (
        paragraph_parent,
        paragraph,
        start,
    )


def _require_rendered_text(
    *,
    sequence: int,
    rendered_text_by_sequence: Mapping[
        int,
        str,
    ],
) -> str:
    if (
        sequence
        not in rendered_text_by_sequence
    ):
        raise (
            CertificateDetailOOXMLCompositionError(
                "Missing resolved TypeText payload "
                f"for semantic operation "
                f"sequence={sequence}."
            )
        )

    value = (
        rendered_text_by_sequence[
            sequence
        ]
    )

    if not isinstance(
        value,
        str,
    ):
        raise (
            CertificateDetailOOXMLCompositionError(
                "Resolved TypeText payload must "
                "be a string."
            )
        )

    return value


def compose_certificate_detail_document_xml(
    destination_document_xml: bytes,
    *,
    projection: CertificateDetailSemanticProjection,
    fragment_xml_by_bookmark: Mapping[
        str,
        str,
    ],
    rendered_text_by_sequence: Mapping[
        int,
        str,
    ],
) -> CertificateDetailOOXMLCompositionResult:
    """
    Single-pass C.5e certificate-detail composition.

    Production scope:
        CERTIFICATE_ISSUANCE_WORD
        -> certificate_9
        -> GMP / GLP / GSP
        -> Pvi

    The caller resolves:
    - Translate_VE_Diachi;
    - Translate_VE_Daychuyen;
    - SplitLines;
    - DelLastIf;
    into exact final TypeText strings.

    This composer owns only:
    - deterministic OOXML placement;
    - certificate_9 3-cell geometry;
    - legacy formatting;
    - Pvi one-time replacement.
    """

    if (
        projection.source_variant
        != CERTIFICATE_DETAIL_SOURCE_VARIANT
    ):
        raise (
            CertificateDetailOOXMLCompositionError(
                "Only production certificate_9 "
                "source variant is supported."
            )
        )

    if (
        projection.destination_bookmark
        != CERTIFICATE_DETAIL_DESTINATION_BOOKMARK
    ):
        raise (
            CertificateDetailOOXMLCompositionError(
                "Unexpected certificate-detail "
                "destination bookmark."
            )
        )

    if (
        projection.gxp_type
        not in {
            "GMP",
            "GLP",
            "GSP",
        }
    ):
        raise (
            CertificateDetailOOXMLCompositionError(
                "Unsupported certificate-detail "
                f"GxP type: "
                f"{projection.gxp_type!r}."
            )
        )

    try:
        root = ET.fromstring(
            destination_document_xml
        )

    except ET.ParseError as exc:
        raise (
            CertificateDetailOOXMLCompositionError(
                "Destination document.xml "
                "is invalid."
            )
        ) from exc

    (
        destination_parent,
        destination_paragraph,
        bookmark_start,
    ) = (
        _find_collapsed_destination_bookmark(
            root,
            bookmark_name=(
                projection.destination_bookmark
            ),
        )
    )

    children = list(
        destination_parent
    )

    destination_index = (
        children.index(
            destination_paragraph
        )
    )

    generated: list[
        ET.Element
    ] = []

    current_heading: (
        ET.Element | None
    ) = None

    current_fragment: (
        ET.Element | None
    ) = None

    current_fragment_vi_cell: (
        ET.Element | None
    ) = None

    current_fragment_en_cell: (
        ET.Element | None
    ) = None

    inserted_fragment_count = 0
    emitted_text_operation_count = 0

    def flush_fragment() -> None:
        nonlocal current_fragment
        nonlocal current_fragment_vi_cell
        nonlocal current_fragment_en_cell

        if (
            current_fragment
            is not None
        ):
            generated.append(
                current_fragment
            )

        current_fragment = None
        current_fragment_vi_cell = None
        current_fragment_en_cell = None

    for operation in (
        projection.operations
    ):
        kind = (
            operation.kind
        )

        if (
            kind
            == "scope_heading_vi"
        ):
            flush_fragment()

            text = (
                _require_rendered_text(
                    sequence=(
                        operation.sequence
                    ),
                    rendered_text_by_sequence=(
                        rendered_text_by_sequence
                    ),
                )
            )

            current_heading = (
                _new_paragraph_with_text(
                    text,
                    bold=True,
                    italic=False,
                    before_points=12,
                    after_points=3,
                )
            )

            generated.append(
                current_heading
            )

            emitted_text_operation_count += 1

            continue

        if (
            kind
            == "scope_heading_en"
        ):
            flush_fragment()

            if (
                current_heading
                is None
            ):
                raise (
                    CertificateDetailOOXMLCompositionError(
                        "scope_heading_en must follow "
                        "scope_heading_vi."
                    )
                )

            text = (
                _require_rendered_text(
                    sequence=(
                        operation.sequence
                    ),
                    rendered_text_by_sequence=(
                        rendered_text_by_sequence
                    ),
                )
            )

            _append_run_text(
                current_heading,
                text,
                bold=True,
                italic=True,
            )

            emitted_text_operation_count += 1

            current_heading = None

            continue

        if (
            kind
            == "formatted_fragment_copy"
        ):
            flush_fragment()
            current_heading = None

            bookmark = (
                operation.source_bookmark
            )

            if not bookmark:
                raise (
                    CertificateDetailOOXMLCompositionError(
                        "formatted_fragment_copy has "
                        "no source bookmark."
                    )
                )

            fragment_xml = (
                fragment_xml_by_bookmark.get(
                    bookmark
                )
            )

            if fragment_xml is None:
                raise (
                    CertificateDetailOOXMLCompositionError(
                        "Missing extracted fragment "
                        f"for bookmark "
                        f"{bookmark!r}."
                    )
                )

            current_fragment = (
                _parse_certificate_9_fragment(
                    fragment_xml
                )
            )

            first_row = (
                current_fragment.findall(
                    "./w:tr",
                    NS,
                )[0]
            )

            cells = (
                first_row.findall(
                    "./w:tc",
                    NS,
                )
            )

            current_fragment_vi_cell = (
                cells[0]
            )

            current_fragment_en_cell = (
                cells[2]
            )

            inserted_fragment_count += 1

            continue

        if (
            kind
            == "append_custom_description_vi"
        ):
            if (
                current_fragment
                is None
                or current_fragment_vi_cell
                is None
            ):
                raise (
                    CertificateDetailOOXMLCompositionError(
                        "VI custom description has "
                        "no active fragment."
                    )
                )

            text = (
                _require_rendered_text(
                    sequence=(
                        operation.sequence
                    ),
                    rendered_text_by_sequence=(
                        rendered_text_by_sequence
                    ),
                )
            )

            _append_type_text_to_cell(
                current_fragment_vi_cell,
                text,
                bold=False,
                italic=False,
                color=(
                    CUSTOM_DESCRIPTION_COLOR
                ),
            )

            emitted_text_operation_count += 1

            continue

        if (
            kind
            == "append_custom_description_en"
        ):
            if (
                current_fragment
                is None
                or current_fragment_en_cell
                is None
            ):
                raise (
                    CertificateDetailOOXMLCompositionError(
                        "EN custom description has "
                        "no active fragment."
                    )
                )

            text = (
                _require_rendered_text(
                    sequence=(
                        operation.sequence
                    ),
                    rendered_text_by_sequence=(
                        rendered_text_by_sequence
                    ),
                )
            )

            _append_type_text_to_cell(
                current_fragment_en_cell,
                text,
                bold=False,
                italic=False,
                color=(
                    CUSTOM_DESCRIPTION_COLOR
                ),
            )

            emitted_text_operation_count += 1

            continue

        if (
            kind
            == "append_scope_note_vi"
        ):
            flush_fragment()
            current_heading = None

            text = (
                _require_rendered_text(
                    sequence=(
                        operation.sequence
                    ),
                    rendered_text_by_sequence=(
                        rendered_text_by_sequence
                    ),
                )
            )

            generated.append(
                _new_paragraph_with_text(
                    text,
                    bold=False,
                    italic=False,
                    before_points=3,
                )
            )

            emitted_text_operation_count += 1

            continue

        if (
            kind
            == "append_scope_note_en"
        ):
            flush_fragment()
            current_heading = None

            text = (
                _require_rendered_text(
                    sequence=(
                        operation.sequence
                    ),
                    rendered_text_by_sequence=(
                        rendered_text_by_sequence
                    ),
                )
            )

            #
            # Legacy line 67 changes only Italic.
            # SpaceBefore remains 3 from the VI-note state.
            #
            generated.append(
                _new_paragraph_with_text(
                    text,
                    bold=False,
                    italic=True,
                    before_points=3,
                )
            )

            emitted_text_operation_count += 1

            #
            # Legacy lines 69-70 happen after the translated
            # note TypeText has already inserted vbCrLf.
            # Therefore they apply to the next paragraph,
            # which in our destination model is the original
            # Pvi/suffix paragraph.
            #
            _set_paragraph_spacing(
                destination_paragraph,
                before_points=9,
                after_points=0,
            )

            continue

        raise (
            CertificateDetailOOXMLCompositionError(
                "Unsupported certificate-detail "
                "semantic operation kind: "
                f"{kind!r}."
            )
        )

    flush_fragment()

    #
    # Insert the complete generated region once, immediately
    # before the original Pvi paragraph.
    #
    for offset, element in enumerate(
        generated
    ):
        destination_parent.insert(
            destination_index
            + offset,
            element,
        )

    #
    # Remove only Pvi bookmark markup.
    # Preserve every other node in the original paragraph.
    #
    parents = _parent_map(
        root
    )

    bookmark_end = None

    bookmark_id = (
        bookmark_start.attrib.get(
            _w("id")
        )
    )

    for node in root.findall(
        ".//w:bookmarkEnd",
        NS,
    ):
        if (
            node.attrib.get(
                _w("id")
            )
            == bookmark_id
        ):
            bookmark_end = node
            break

    if bookmark_end is None:
        raise (
            CertificateDetailOOXMLCompositionError(
                "Destination bookmarkEnd disappeared "
                "during composition."
            )
        )

    start_parent = (
        parents.get(
            bookmark_start
        )
    )

    end_parent = (
        parents.get(
            bookmark_end
        )
    )

    if (
        start_parent
        is not destination_paragraph
        or end_parent
        is not destination_paragraph
    ):
        raise (
            CertificateDetailOOXMLCompositionError(
                "Destination bookmark geometry changed "
                "during composition."
            )
        )

    destination_paragraph.remove(
        bookmark_start
    )

    destination_paragraph.remove(
        bookmark_end
    )

    result_xml = ET.tostring(
        root,
        encoding="utf-8",
        xml_declaration=True,
    )

    return (
        CertificateDetailOOXMLCompositionResult(
            document_xml=result_xml,
            inserted_fragment_count=(
                inserted_fragment_count
            ),
            emitted_text_operation_count=(
                emitted_text_operation_count
            ),
            destination_bookmark=(
                projection.destination_bookmark
            ),
        )
    )