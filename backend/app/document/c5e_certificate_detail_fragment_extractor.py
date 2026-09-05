from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import zipfile
from xml.etree import ElementTree as ET

WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": WORD_NS}

SUPPORTED_GEOMETRY_SHAPES = {
    "parent=False|p=False|tc=False|tr=False|tbl=True|lca=tbl|sp=p|ep=p",
    "parent=False|p=False|tc=False|tr=False|tbl=True|lca=tbl|sp=p|ep=tbl",
}


class CertificateDetailFragmentExtractionError(RuntimeError):
    pass


@dataclass(frozen=True)
class CertificateDetailExtractedFragment:
    bookmark_name: str
    geometry_shape: str
    fragment_xml: str
    visible_text: str


def _w(tag: str) -> str:
    return f"{{{WORD_NS}}}{tag}"


def _local(tag: str) -> str:
    return tag.split("}", 1)[1] if tag.startswith("{") else tag


def _parent_map(root: ET.Element):
    return {
        child: parent
        for parent in root.iter()
        for child in list(parent)
    }


def _ancestors(node: ET.Element, parents):
    result = [node]
    current = node

    while current in parents:
        current = parents[current]
        result.append(current)

    return result


def _nearest(node: ET.Element, parents, tag: str):
    target = _w(tag)
    current = node

    while True:
        if current.tag == target:
            return current

        if current not in parents:
            return None

        current = parents[current]


def _lowest_common_ancestor(
    left: ET.Element,
    right: ET.Element,
    parents,
):
    right_nodes = set(
        _ancestors(right, parents)
    )

    for node in _ancestors(
        left,
        parents,
    ):
        if node in right_nodes:
            return node

    return None


def _geometry(
    start: ET.Element,
    end: ET.Element,
    parents,
):
    sp = parents.get(start)
    ep = parents.get(end)

    start_p = _nearest(
        start,
        parents,
        "p",
    )
    end_p = _nearest(
        end,
        parents,
        "p",
    )

    start_tc = _nearest(
        start,
        parents,
        "tc",
    )
    end_tc = _nearest(
        end,
        parents,
        "tc",
    )

    start_tr = _nearest(
        start,
        parents,
        "tr",
    )
    end_tr = _nearest(
        end,
        parents,
        "tr",
    )

    start_tbl = _nearest(
        start,
        parents,
        "tbl",
    )
    end_tbl = _nearest(
        end,
        parents,
        "tbl",
    )

    lca = _lowest_common_ancestor(
        start,
        end,
        parents,
    )

    if lca is None:
        raise CertificateDetailFragmentExtractionError(
            "Bookmark start/end have no common ancestor."
        )

    shape = (
        f"parent={sp is ep}"
        f"|p={start_p is not None and start_p is end_p}"
        f"|tc={start_tc is not None and start_tc is end_tc}"
        f"|tr={start_tr is not None and start_tr is end_tr}"
        f"|tbl={start_tbl is not None and start_tbl is end_tbl}"
        f"|lca={_local(lca.tag)}"
        f"|sp={_local(sp.tag) if sp is not None else 'none'}"
        f"|ep={_local(ep.tag) if ep is not None else 'none'}"
    )

    return shape, lca


def _preorder_ranges(root: ET.Element):
    start_index = {}
    end_index = {}
    counter = 0

    def visit(node: ET.Element):
        nonlocal counter

        start_index[node] = counter
        counter += 1

        for child in list(node):
            visit(child)

        end_index[node] = counter - 1

    visit(root)

    return start_index, end_index


def _clone_open_interval(
    node: ET.Element,
    *,
    start_boundary: int,
    end_boundary: int,
    start_index,
    end_index,
):
    node_start = start_index[node]
    node_end = end_index[node]

    if (
        node_end <= start_boundary
        or node_start >= end_boundary
    ):
        return None

    clone = ET.Element(
        node.tag,
        dict(node.attrib),
    )

    clone.text = node.text
    clone.tail = node.tail

    for child in list(node):
        child_clone = (
            _clone_open_interval(
                child,
                start_boundary=start_boundary,
                end_boundary=end_boundary,
                start_index=start_index,
                end_index=end_index,
            )
        )

        if child_clone is not None:
            clone.append(child_clone)

    if (
        len(clone) == 0
        and not (
            start_boundary
            < node_start
            < end_boundary
        )
    ):
        return None

    return clone


def _strip_bookmarks(root: ET.Element) -> None:
    parents = _parent_map(root)

    targets = [
        node
        for node in root.iter()
        if node.tag
        in {
            _w("bookmarkStart"),
            _w("bookmarkEnd"),
        }
    ]

    for node in targets:
        parent = parents.get(node)

        if parent is not None:
            parent.remove(node)


def extract_bookmark_table_fragment_from_docx_bytes(
    source_docx_bytes: bytes,
    *,
    bookmark_name: str,
) -> CertificateDetailExtractedFragment:
    try:
        with zipfile.ZipFile(
            BytesIO(source_docx_bytes),
            "r",
        ) as archive:
            document_xml = archive.read(
                "word/document.xml"
            )

    except (
        zipfile.BadZipFile,
        KeyError,
    ) as exc:
        raise CertificateDetailFragmentExtractionError(
            "Source asset is not a valid DOCX "
            "containing word/document.xml."
        ) from exc

    try:
        root = ET.fromstring(
            document_xml
        )

    except ET.ParseError as exc:
        raise CertificateDetailFragmentExtractionError(
            "Source word/document.xml is invalid."
        ) from exc

    starts = [
        node
        for node
        in root.findall(
            ".//w:bookmarkStart",
            NS,
        )
        if node.attrib.get(
            _w("name")
        )
        == bookmark_name
    ]

    if len(starts) != 1:
        raise CertificateDetailFragmentExtractionError(
            "Expected exactly one source bookmark "
            f"{bookmark_name!r}; "
            f"found {len(starts)}."
        )

    start = starts[0]

    bookmark_id = start.attrib.get(
        _w("id")
    )

    if bookmark_id is None:
        raise CertificateDetailFragmentExtractionError(
            f"Bookmark {bookmark_name!r} "
            "has no w:id."
        )

    ends = [
        node
        for node
        in root.findall(
            ".//w:bookmarkEnd",
            NS,
        )
        if node.attrib.get(
            _w("id")
        )
        == bookmark_id
    ]

    if len(ends) != 1:
        raise CertificateDetailFragmentExtractionError(
            "Expected exactly one bookmarkEnd "
            f"for {bookmark_name!r}; "
            f"found {len(ends)}."
        )

    end = ends[0]

    parents = _parent_map(root)

    geometry_shape, lca = _geometry(
        start,
        end,
        parents,
    )

    if (
        geometry_shape
        not in SUPPORTED_GEOMETRY_SHAPES
    ):
        raise CertificateDetailFragmentExtractionError(
            "Unsupported C.5e source bookmark "
            f"geometry: {geometry_shape}"
        )

    if lca.tag != _w("tbl"):
        raise CertificateDetailFragmentExtractionError(
            "C.5e source bookmark must have "
            "w:tbl as its LCA."
        )

    start_index, end_index = (
        _preorder_ranges(root)
    )

    start_boundary = start_index[
        start
    ]
    end_boundary = start_index[
        end
    ]

    if (
        end_boundary
        <= start_boundary
    ):
        raise CertificateDetailFragmentExtractionError(
            "Invalid source bookmark order."
        )

    fragment = _clone_open_interval(
        lca,
        start_boundary=start_boundary,
        end_boundary=end_boundary,
        start_index=start_index,
        end_index=end_index,
    )

    if (
        fragment is None
        or fragment.tag != _w("tbl")
    ):
        raise CertificateDetailFragmentExtractionError(
            "Could not reconstruct "
            "C.5e table fragment."
        )

    _strip_bookmarks(fragment)

    if (
        fragment.findall(
            ".//w:bookmarkStart",
            NS,
        )
        or fragment.findall(
            ".//w:bookmarkEnd",
            NS,
        )
    ):
        raise CertificateDetailFragmentExtractionError(
            "Extracted fragment still contains "
            "bookmark markup."
        )

    fragment_xml = ET.tostring(
        fragment,
        encoding="unicode",
    )

    visible_text = "".join(
        node.text or ""
        for node
        in fragment.findall(
            ".//w:t",
            NS,
        )
    )

    return (
        CertificateDetailExtractedFragment(
            bookmark_name=bookmark_name,
            geometry_shape=geometry_shape,
            fragment_xml=fragment_xml,
            visible_text=visible_text,
        )
    )