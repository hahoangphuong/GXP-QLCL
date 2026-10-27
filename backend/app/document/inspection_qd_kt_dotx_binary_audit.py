"""Offline inspection of actual QĐKT DOTX bytes; no rendering or storage writes.

A manifest locator is not binary evidence. This verifies SHA-256 and records
Word bookmark IDs/names observed in a supplied DOTX. It deliberately never
declares typed-input ownership or renderer readiness.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from backend.app.document.inspection_qd_kt_template_asset_contract import (
    InspectionQdKtTemplateAsset,
    load_inspection_qd_kt_template_assets,
)

_WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_MAX_WORD_PART_XML_BYTES = 16 * 1024 * 1024
_MAX_CONTENT_TYPES_BYTES = 1024 * 1024
_OPC_NS = "{http://schemas.openxmlformats.org/package/2006/content-types}"
_DOTX_MAIN_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.template.main+xml"
_WORD_STORY_PART = re.compile(r"word/(?:document|header\d+|footer\d+)\.xml")


class QdKtDotxAuditBlocked(ValueError):
    pass


@dataclass(frozen=True)
class QdKtBookmarkSpan:
    name: str
    bookmark_id: str
    part_name: str
    start_location: str
    end_location: str
    start_paragraph_index: int | None
    end_paragraph_index: int | None
    paragraph_text: str
    field_code_text: str
    nested_with: tuple[str, ...]
    overlapping_with: tuple[str, ...]


@dataclass(frozen=True)
class QdKtTargetBookmarkEvidence:
    requested_name: str
    status: str
    exact_spans: tuple[QdKtBookmarkSpan, ...]
    case_variant_names: tuple[str, ...]


@dataclass(frozen=True)
class QdKtDotxBinaryAudit:
    gxp_type: str
    expected_sha256: str
    actual_sha256: str
    bookmark_names: tuple[str, ...]
    bookmark_count: int
    binary_checksum_verified: bool
    scanned_word_parts: tuple[str, ...]
    bookmark_spans: tuple[QdKtBookmarkSpan, ...]
    nested_bookmark_pairs: tuple[tuple[str, str], ...]
    overlapping_bookmark_pairs: tuple[tuple[str, str], ...]
    dossier_plain_text_paragraph_count: int
    bookmark_owner_parity_verified: bool = False
    ready_to_render: bool = False


def _tag_label(tag: str) -> str:
    if tag.startswith(_WORD_NS):
        return f"w:{tag.removeprefix(_WORD_NS)}"
    return tag.rsplit("}", 1)[-1]


def _tree_locations(root: ElementTree.Element) -> dict[int, str]:
    locations = {id(root): f"/{_tag_label(root.tag)}[1]"}

    def visit(parent: ElementTree.Element) -> None:
        counts: Counter[str] = Counter()
        for child in parent:
            label = _tag_label(child.tag)
            counts[label] += 1
            locations[id(child)] = f"{locations[id(parent)]}/{label}[{counts[label]}]"
            visit(child)

    visit(root)
    return locations


def _paragraph_for(
    node: ElementTree.Element,
    *,
    parents: dict[ElementTree.Element, ElementTree.Element],
) -> ElementTree.Element | None:
    current: ElementTree.Element | None = node
    while current is not None and current.tag != f"{_WORD_NS}p":
        current = parents.get(current)
    return current


def _read_word_part(archive: ZipFile, part_name: str) -> ElementTree.Element:
    info = archive.getinfo(part_name)
    if info.file_size > _MAX_WORD_PART_XML_BYTES:
        raise QdKtDotxAuditBlocked("QDKT_DOTX_WORD_PART_UNSUPPORTED")
    with archive.open(info) as source:
        xml_bytes = source.read(_MAX_WORD_PART_XML_BYTES + 1)
    if len(xml_bytes) > _MAX_WORD_PART_XML_BYTES:
        raise QdKtDotxAuditBlocked("QDKT_DOTX_WORD_PART_UNSUPPORTED")
    return ElementTree.fromstring(xml_bytes)


def _inspect_bookmark_part(
    root: ElementTree.Element,
    *,
    part_name: str,
) -> tuple[
    list[QdKtBookmarkSpan],
    list[tuple[str, str]],
    list[tuple[str, str]],
]:
    locations = _tree_locations(root)
    parents = {child: parent for parent in root.iter() for child in parent}
    paragraphs = list(root.iter(f"{_WORD_NS}p"))
    paragraph_indexes = {id(paragraph): index for index, paragraph in enumerate(paragraphs, 1)}
    starts: dict[str, tuple[ElementTree.Element, str, tuple[str, ...]]] = {}
    ends: dict[str, ElementTree.Element] = {}
    active: list[str] = []
    nested_pairs: list[tuple[str, str]] = []
    overlap_by_id: dict[str, set[str]] = {}

    for node in root.iter():
        if node.tag == f"{_WORD_NS}bookmarkStart":
            identifier = node.get(f"{_WORD_NS}id")
            name = node.get(f"{_WORD_NS}name")
            if not identifier or not name or identifier in starts:
                raise QdKtDotxAuditBlocked("QDKT_DOTX_BOOKMARK_STRUCTURE_UNVERIFIED")
            enclosing = tuple(starts[item][1] for item in active)
            nested_pairs.extend((parent, name) for parent in enclosing)
            starts[identifier] = (node, name, enclosing)
            active.append(identifier)
        elif node.tag == f"{_WORD_NS}bookmarkEnd":
            identifier = node.get(f"{_WORD_NS}id")
            if not identifier or identifier in ends or identifier not in starts:
                raise QdKtDotxAuditBlocked("QDKT_DOTX_BOOKMARK_STRUCTURE_UNVERIFIED")
            ends[identifier] = node
            if identifier not in active:
                raise QdKtDotxAuditBlocked("QDKT_DOTX_BOOKMARK_STRUCTURE_UNVERIFIED")
            position = active.index(identifier)
            later = active[position + 1 :]
            for other in later:
                overlap_by_id.setdefault(identifier, set()).add(starts[other][1])
                overlap_by_id.setdefault(other, set()).add(starts[identifier][1])
            active.pop(position)

    if active or set(starts) != set(ends):
        raise QdKtDotxAuditBlocked("QDKT_DOTX_BOOKMARK_STRUCTURE_UNVERIFIED")

    spans: list[QdKtBookmarkSpan] = []
    for identifier, (start, name, enclosing) in starts.items():
        end = ends[identifier]
        start_paragraph = _paragraph_for(start, parents=parents)
        end_paragraph = _paragraph_for(end, parents=parents)
        paragraph_text = ""
        field_code_text = ""
        if start_paragraph is not None:
            paragraph_text = "".join(
                text.text or "" for text in start_paragraph.iter(f"{_WORD_NS}t")
            ).strip()
            field_code_text = " ".join(
                (text.text or "").strip()
                for text in start_paragraph.iter(f"{_WORD_NS}instrText")
                if (text.text or "").strip()
            )
        spans.append(
            QdKtBookmarkSpan(
                name=name,
                bookmark_id=identifier,
                part_name=part_name,
                start_location=locations[id(start)],
                end_location=locations[id(end)],
                start_paragraph_index=(
                    None if start_paragraph is None else paragraph_indexes[id(start_paragraph)]
                ),
                end_paragraph_index=(
                    None if end_paragraph is None else paragraph_indexes[id(end_paragraph)]
                ),
                paragraph_text=paragraph_text,
                field_code_text=field_code_text,
                nested_with=enclosing,
                overlapping_with=tuple(sorted(overlap_by_id.get(identifier, set()))),
            )
        )
    overlaps = sorted(
        {
            tuple(sorted((spans_by_id, other)))
            for spans_by_id, others in (
                (starts[identifier][1], names) for identifier, names in overlap_by_id.items()
            )
            for other in others
        }
    )
    return spans, nested_pairs, overlaps


def inspect_qdkt_dotx_binary(
    path: Path, *, asset: InspectionQdKtTemplateAsset,
) -> QdKtDotxBinaryAudit:
    """Measure one *provided* local DOTX, without modifying it or trusting its name."""
    path = Path(path)
    try:
        with path.open("rb") as stream:
            digest = sha256()
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
        actual = digest.hexdigest()
    except OSError as exc:
        raise QdKtDotxAuditBlocked("QDKT_DOTX_BINARY_UNAVAILABLE") from exc
    if actual != asset.checksum_sha256:
        raise QdKtDotxAuditBlocked("QDKT_DOTX_CHECKSUM_MISMATCH")
    try:
        with ZipFile(path) as archive:
            names = [info.filename for info in archive.infolist()]
            if len(names) != len(set(names)):
                raise QdKtDotxAuditBlocked("QDKT_DOTX_PACKAGE_MEMBER_AMBIGUOUS")
            types_info = archive.getinfo("[Content_Types].xml")
            if types_info.file_size > _MAX_CONTENT_TYPES_BYTES:
                raise QdKtDotxAuditBlocked("QDKT_DOTX_PACKAGE_TYPE_UNVERIFIED")
            with archive.open(types_info) as types_stream:
                types_bytes = types_stream.read(_MAX_CONTENT_TYPES_BYTES + 1)
            if len(types_bytes) > _MAX_CONTENT_TYPES_BYTES:
                raise QdKtDotxAuditBlocked("QDKT_DOTX_PACKAGE_TYPE_UNVERIFIED")
            types_root = ElementTree.fromstring(types_bytes)
            package_main_types = [
                entry.get("ContentType")
                for entry in types_root.findall(f"{_OPC_NS}Override")
                if entry.get("PartName") == "/word/document.xml"
            ]
            if (
                types_root.tag != f"{_OPC_NS}Types"
                or package_main_types != [_DOTX_MAIN_TYPE]
            ):
                raise QdKtDotxAuditBlocked("QDKT_DOTX_PACKAGE_TYPE_UNVERIFIED")
            part_names = tuple(sorted(name for name in names if _WORD_STORY_PART.fullmatch(name)))
            if "word/document.xml" not in part_names:
                raise QdKtDotxAuditBlocked("QDKT_DOTX_WORD_XML_UNVERIFIED")
            roots = tuple((name, _read_word_part(archive, name)) for name in part_names)
    except (BadZipFile, KeyError, ElementTree.ParseError, OSError, RuntimeError) as exc:
        raise QdKtDotxAuditBlocked("QDKT_DOTX_WORD_XML_UNVERIFIED") from exc

    spans: list[QdKtBookmarkSpan] = []
    nested_pairs: list[tuple[str, str]] = []
    overlapping_pairs: list[tuple[str, str]] = []
    dossier_plain_text_paragraph_count = 0
    for part_name, root in roots:
        part_spans, part_nested, part_overlapping = _inspect_bookmark_part(
            root,
            part_name=part_name,
        )
        spans.extend(part_spans)
        nested_pairs.extend(part_nested)
        overlapping_pairs.extend(part_overlapping)
        dossier_plain_text_paragraph_count += sum(
            1
            for paragraph in root.iter(f"{_WORD_NS}p")
            if "hồ sơ" in "".join(
                text.text or "" for text in paragraph.iter(f"{_WORD_NS}t")
            ).casefold()
        )
    bookmark_names = [span.name for span in spans]
    if len(set(bookmark_names)) != len(bookmark_names):
        raise QdKtDotxAuditBlocked("QDKT_DOTX_BOOKMARK_STRUCTURE_UNVERIFIED")
    return QdKtDotxBinaryAudit(
        gxp_type=asset.gxp_type,
        expected_sha256=asset.checksum_sha256,
        actual_sha256=actual,
        bookmark_names=tuple(sorted(bookmark_names)),
        bookmark_count=len(spans),
        binary_checksum_verified=True,
        scanned_word_parts=part_names,
        bookmark_spans=tuple(sorted(spans, key=lambda span: (span.part_name, span.start_location))),
        nested_bookmark_pairs=tuple(sorted(set(nested_pairs))),
        overlapping_bookmark_pairs=tuple(sorted(set(overlapping_pairs))),
        dossier_plain_text_paragraph_count=dossier_plain_text_paragraph_count,
    )


def classify_qdkt_target_bookmark(
    audit: QdKtDotxBinaryAudit,
    requested_name: str,
) -> QdKtTargetBookmarkEvidence:
    """Classify one exact bookmark without treating case variants as matches."""
    if not isinstance(requested_name, str) or not requested_name:
        raise ValueError("QDKT_TARGET_BOOKMARK_NAME_INVALID")
    exact = tuple(span for span in audit.bookmark_spans if span.name == requested_name)
    variants = tuple(sorted({
        span.name
        for span in audit.bookmark_spans
        if span.name != requested_name and span.name.casefold() == requested_name.casefold()
    }))
    if exact:
        status = "EXACT_PRESENT"
    elif variants:
        status = "CASE_VARIANT_ONLY"
    else:
        status = "ABSENT"
    return QdKtTargetBookmarkEvidence(
        requested_name=requested_name,
        status=status,
        exact_spans=exact,
        case_variant_names=variants,
    )


def inspect_supplied_qdkt_dotx_set(
    directory: Path,
    *, assets: tuple[InspectionQdKtTemplateAsset, ...] | None = None,
) -> tuple[QdKtDotxBinaryAudit, ...]:
    """Require all four specified files, not a best-effort partial pass."""
    declared = assets if assets is not None else load_inspection_qd_kt_template_assets()
    if {asset.gxp_type for asset in declared} != {"GMP", "GLP", "GMPbb", "GSP"}:
        raise QdKtDotxAuditBlocked("QDKT_DOTX_GXP_SET_UNVERIFIED")
    base = Path(directory)
    return tuple(
        inspect_qdkt_dotx_binary(base / asset.filename, asset=asset)
        for asset in sorted(declared, key=lambda value: value.gxp_type)
    )
