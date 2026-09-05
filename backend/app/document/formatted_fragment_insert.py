from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from xml.etree import ElementTree as ET

WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NSMAP = {"w": WORD_NS}


class FormattedFragmentInsertError(RuntimeError):
    """Raised when a formatted block fragment cannot be inserted without ambiguity."""


@dataclass(frozen=True)
class FormattedFragmentInsertResult:
    bookmark_name: str
    inserted_root_tag: str
    destination_parent_tag: str
    destination_child_index: int


def _w(tag: str) -> str:
    return f"{{{WORD_NS}}}{tag}"


def _local(tag: str) -> str:
    return tag.split("}", 1)[1] if tag.startswith("{") else tag


def _build_parent_map(root: ET.Element) -> dict[ET.Element, ET.Element]:
    return {
        child: parent
        for parent in root.iter()
        for child in list(parent)
    }


def _has_semantic_content(element: ET.Element) -> bool:
    if element.tag == _w("pPr"):
        return False
    if element.tag == _w("r"):
        for child in list(element):
            if child.tag == _w("rPr"):
                continue
            if child.tag == _w("t") and not (child.text or ""):
                continue
            return True
        return False
    return True


def _find_single_bookmark_start(root: ET.Element, bookmark_name: str) -> ET.Element:
    matches = [
        node
        for node in root.findall(".//w:bookmarkStart", NSMAP)
        if node.attrib.get(_w("name")) == bookmark_name
    ]
    if len(matches) != 1:
        raise FormattedFragmentInsertError(
            f"Expected exactly one bookmarkStart for {bookmark_name!r}; found {len(matches)}."
        )
    return matches[0]


def _find_matching_bookmark_end(root: ET.Element, bookmark_id: str | None) -> ET.Element:
    if bookmark_id is None:
        raise FormattedFragmentInsertError("Destination bookmarkStart has no w:id.")
    matches = [
        node
        for node in root.findall(".//w:bookmarkEnd", NSMAP)
        if node.attrib.get(_w("id")) == bookmark_id
    ]
    if len(matches) != 1:
        raise FormattedFragmentInsertError(
            f"Expected exactly one bookmarkEnd for id {bookmark_id!r}; found {len(matches)}."
        )
    return matches[0]


def _validate_fragment_root(fragment: ET.Element) -> None:
    if fragment.tag != _w("tbl"):
        raise FormattedFragmentInsertError(
            f"C.5e formatted fragment must be a w:tbl block; got {_local(fragment.tag)!r}."
        )
    if fragment.findall(".//w:bookmarkStart", NSMAP) or fragment.findall(".//w:bookmarkEnd", NSMAP):
        raise FormattedFragmentInsertError(
            "C.5e formatted fragment must not contain bookmark markup."
        )


def insert_table_fragment_at_empty_bookmark(
    document_root: ET.Element,
    *,
    bookmark_name: str,
    fragment: ET.Element,
) -> FormattedFragmentInsertResult:
    """
    Insert a table block at the audited C.5e destination bookmark shape.

    Proven legacy destination shape:
      w:p / [optional w:pPr, formatting-only empty runs] /
      w:bookmarkStart / w:bookmarkEnd / heading-content...

    The bookmark is a collapsed insertion point at the beginning of the heading
    paragraph. A w:tbl cannot be nested inside w:p, so the table is inserted as a
    sibling immediately before that paragraph. The heading paragraph and all of
    its suffix content remain unchanged except that the target bookmark markup is
    removed.

    Anything outside this exact contract fails closed.
    """
    _validate_fragment_root(fragment)

    start = _find_single_bookmark_start(document_root, bookmark_name)
    end = _find_matching_bookmark_end(document_root, start.attrib.get(_w("id")))
    parent_map = _build_parent_map(document_root)

    paragraph = parent_map.get(start)
    if paragraph is None or paragraph.tag != _w("p"):
        raise FormattedFragmentInsertError(
            f"Destination bookmark {bookmark_name!r} must be a direct child of w:p."
        )
    if parent_map.get(end) is not paragraph:
        raise FormattedFragmentInsertError(
            f"Destination bookmark {bookmark_name!r} start/end must share the same w:p."
        )

    children = list(paragraph)
    start_index = children.index(start)
    end_index = children.index(end)

    if end_index != start_index + 1:
        raise FormattedFragmentInsertError(
            f"Destination bookmark {bookmark_name!r} must be empty/adjacent."
        )

    for child in children[:start_index]:
        if child.tag == _w("pPr"):
            continue
        if _has_semantic_content(child):
            raise FormattedFragmentInsertError(
                f"Destination bookmark {bookmark_name!r} is not at the beginning "
                "of the paragraph; semantic content exists before the bookmark."
            )

    paragraph_parent = parent_map.get(paragraph)
    if paragraph_parent is None:
        raise FormattedFragmentInsertError(
            f"Destination paragraph for {bookmark_name!r} has no parent."
        )

    paragraph_index = list(paragraph_parent).index(paragraph)
    fragment_clone = deepcopy(fragment)

    paragraph.remove(start)
    paragraph.remove(end)
    paragraph_parent.insert(paragraph_index, fragment_clone)

    return FormattedFragmentInsertResult(
        bookmark_name=bookmark_name,
        inserted_root_tag=_local(fragment_clone.tag),
        destination_parent_tag=_local(paragraph_parent.tag),
        destination_child_index=paragraph_index,
    )


def insert_table_fragment_xml_at_empty_bookmark(
    document_xml: bytes,
    *,
    bookmark_name: str,
    fragment_xml: str,
) -> tuple[bytes, FormattedFragmentInsertResult]:
    try:
        document_root = ET.fromstring(document_xml)
    except ET.ParseError as exc:
        raise FormattedFragmentInsertError("Destination document XML is invalid.") from exc

    try:
        fragment = ET.fromstring(fragment_xml)
    except ET.ParseError as exc:
        raise FormattedFragmentInsertError("Formatted fragment XML is invalid.") from exc

    result = insert_table_fragment_at_empty_bookmark(
        document_root,
        bookmark_name=bookmark_name,
        fragment=fragment,
    )
    return (
        ET.tostring(document_root, encoding="utf-8", xml_declaration=True),
        result,
    )
