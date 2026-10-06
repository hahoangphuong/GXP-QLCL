from __future__ import annotations

from dataclasses import dataclass
from xml.etree import ElementTree as ET

WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NSMAP = {"w": WORD_NS}


class DocxBookmarkRangeError(RuntimeError):
    pass


@dataclass(frozen=True)
class BookmarkRangeDeleteResult:
    requested_bookmarks: tuple[str, ...]
    planned_bookmarks: tuple[str, ...]
    deleted_paragraph_count: int


def _w(tag: str) -> str:
    return f"{{{WORD_NS}}}{tag}"


def _parent_map(root: ET.Element) -> dict[ET.Element, ET.Element]:
    return {child: parent for parent in root.iter() for child in parent}


def _nearest_ancestor(
    node: ET.Element,
    parents: dict[ET.Element, ET.Element],
    tag: str,
) -> ET.Element | None:
    current = node
    while current in parents:
        current = parents[current]
        if current.tag == tag:
            return current
    return None


def _direct_child_under(
    node: ET.Element,
    ancestor: ET.Element,
    parents: dict[ET.Element, ET.Element],
) -> ET.Element:
    current = node
    while current in parents and parents[current] is not ancestor:
        current = parents[current]
    if current not in parents or parents[current] is not ancestor:
        raise DocxBookmarkRangeError("bookmark marker is not inside the expected range container")
    return current


def _visible_text_before(paragraph: ET.Element, marker: ET.Element) -> bool:
    children = list(paragraph)
    try:
        marker_index = children.index(marker)
    except ValueError as exc:
        raise DocxBookmarkRangeError("bookmark marker must be a direct paragraph child") from exc
    return any(
        (text.text or "")
        for child in children[:marker_index]
        for text in child.findall(".//w:t", NSMAP)
    )


def _remove_orphan_bookmark_markup(root: ET.Element) -> None:
    starts: dict[str, list[ET.Element]] = {}
    ends: dict[str, list[ET.Element]] = {}
    for node in root.iter():
        if node.tag == _w("bookmarkStart"):
            starts.setdefault(node.attrib.get(_w("id"), ""), []).append(node)
        elif node.tag == _w("bookmarkEnd"):
            ends.setdefault(node.attrib.get(_w("id"), ""), []).append(node)
    valid_ids = {
        bookmark_id
        for bookmark_id, start_nodes in starts.items()
        if bookmark_id and len(start_nodes) == 1 and len(ends.get(bookmark_id, ())) == 1
    }
    parents = _parent_map(root)
    for mapping in (starts, ends):
        for bookmark_id, nodes in mapping.items():
            if bookmark_id in valid_ids:
                continue
            for node in nodes:
                parent = parents.get(node)
                if parent is not None and node in list(parent):
                    parent.remove(node)


def _locate_range(
    root: ET.Element,
    parents: dict[ET.Element, ET.Element],
    bookmark_name: str,
) -> tuple[ET.Element, ET.Element] | None:
    start = next(
        (
            node
            for node in root.iter(_w("bookmarkStart"))
            if node.attrib.get(_w("name")) == bookmark_name
        ),
        None,
    )
    if start is None:
        return None
    bookmark_id = start.attrib.get(_w("id"))
    end = next(
        (
            node
            for node in root.iter(_w("bookmarkEnd"))
            if node.attrib.get(_w("id")) == bookmark_id
        ),
        None,
    )
    if end is None:
        raise DocxBookmarkRangeError(f"bookmark {bookmark_name!r} has no matching end marker")
    return start, end


def _plan_paragraph_aligned_range(
    bookmark_name: str,
    start: ET.Element,
    end: ET.Element,
    parents: dict[ET.Element, ET.Element],
) -> tuple[ET.Element, tuple[ET.Element, ...]]:
    start_cell = _nearest_ancestor(start, parents, _w("tc"))
    end_cell = _nearest_ancestor(end, parents, _w("tc"))
    if start_cell is not None or end_cell is not None:
        if start_cell is None or start_cell is not end_cell:
            raise DocxBookmarkRangeError(
                f"bookmark {bookmark_name!r} crosses table-cell boundaries"
            )
        container = start_cell
    else:
        start_body = _nearest_ancestor(start, parents, _w("body"))
        end_body = _nearest_ancestor(end, parents, _w("body"))
        if start_body is None or start_body is not end_body:
            raise DocxBookmarkRangeError(
                f"bookmark {bookmark_name!r} does not share a supported body container"
            )
        container = start_body

    start_direct = _direct_child_under(start, container, parents)
    end_direct = end if parents.get(end) is container else _direct_child_under(end, container, parents)
    if start_direct.tag != _w("p") or parents.get(start) is not start_direct:
        raise DocxBookmarkRangeError(
            f"bookmark {bookmark_name!r} does not start at a direct paragraph boundary"
        )
    if _visible_text_before(start_direct, start):
        raise DocxBookmarkRangeError(
            f"bookmark {bookmark_name!r} starts after visible paragraph text"
        )
    if end_direct is start_direct:
        raise DocxBookmarkRangeError(
            f"bookmark {bookmark_name!r} is not a paragraph-aligned cross-boundary range"
        )
    if end_direct.tag == _w("p"):
        if parents.get(end) is not end_direct:
            raise DocxBookmarkRangeError(
                f"bookmark {bookmark_name!r} end marker is not a direct paragraph child"
            )
        if _visible_text_before(end_direct, end):
            raise DocxBookmarkRangeError(
                f"bookmark {bookmark_name!r} ends after visible paragraph text"
            )
    elif end_direct is not end:
        raise DocxBookmarkRangeError(
            f"bookmark {bookmark_name!r} has an unsupported end boundary"
        )

    children = list(container)
    start_index = children.index(start_direct)
    end_index = children.index(end_direct)
    if end_index <= start_index:
        raise DocxBookmarkRangeError(f"bookmark {bookmark_name!r} markers are reversed")
    segment = children[start_index:end_index]
    unsupported = [
        child.tag
        for child in segment
        if child.tag not in {_w("p"), _w("bookmarkStart"), _w("bookmarkEnd")}
    ]
    if unsupported:
        raise DocxBookmarkRangeError(
            f"bookmark {bookmark_name!r} crosses unsupported structural nodes: {unsupported!r}"
        )
    paragraphs = tuple(child for child in segment if child.tag == _w("p"))
    if not paragraphs:
        raise DocxBookmarkRangeError(
            f"bookmark {bookmark_name!r} does not cover a deletable paragraph"
        )
    return container, paragraphs


def delete_bookmark_ranges(
    root: ET.Element,
    bookmark_names: tuple[str, ...],
    *,
    missing_ok: bool = False,
) -> BookmarkRangeDeleteResult:
    """Delete paragraph-aligned Word bookmark ranges as one immutable plan.

    Planning every range against the untouched XML is essential for the KHKT
    templates because legacy bookmarks overlap. Word adjusts overlapping
    bookmark boundaries internally as `.Range.Delete` runs; a naive sequential
    XML mutation would destroy a later range marker. The final visible effect
    is equivalent to deleting the union of the original paragraph-aligned
    ranges, so this helper plans first and mutates once.
    """
    parents = _parent_map(root)
    plans: list[tuple[str, ET.Element, tuple[ET.Element, ...], ET.Element, ET.Element]] = []
    for bookmark_name in bookmark_names:
        located = _locate_range(root, parents, bookmark_name)
        if located is None:
            if missing_ok:
                continue
            raise DocxBookmarkRangeError(f"bookmark {bookmark_name!r} was not found")
        start, end = located
        container, paragraphs = _plan_paragraph_aligned_range(
            bookmark_name,
            start,
            end,
            parents,
        )
        plans.append((bookmark_name, container, paragraphs, start, end))

    paragraph_owners: dict[ET.Element, ET.Element] = {}
    markers_to_remove: set[ET.Element] = set()
    for _, container, paragraphs, start, end in plans:
        for paragraph in paragraphs:
            owner = parents.get(paragraph)
            if owner is not container:
                raise DocxBookmarkRangeError("planned paragraph owner changed before mutation")
            paragraph_owners[paragraph] = container
        markers_to_remove.update((start, end))

    for paragraph, container in paragraph_owners.items():
        if paragraph in list(container):
            container.remove(paragraph)

    current_parents = _parent_map(root)
    for marker in markers_to_remove:
        parent = current_parents.get(marker)
        if parent is not None and marker in list(parent):
            parent.remove(marker)
    _remove_orphan_bookmark_markup(root)

    return BookmarkRangeDeleteResult(
        requested_bookmarks=bookmark_names,
        planned_bookmarks=tuple(plan[0] for plan in plans),
        deleted_paragraph_count=len(paragraph_owners),
    )
