"""Offline inspection of actual QĐKT DOTX bytes; no rendering or storage writes.

A manifest locator is not binary evidence. This verifies SHA-256 and records
Word bookmark IDs/names observed in a supplied DOTX. It deliberately never
declares typed-input ownership or renderer readiness.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from backend.app.document.inspection_qd_kt_template_asset_contract import (
    InspectionQdKtTemplateAsset,
    load_inspection_qd_kt_template_assets,
)

_WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_MAX_DOCUMENT_XML_BYTES = 16 * 1024 * 1024


class QdKtDotxAuditBlocked(ValueError):
    pass


@dataclass(frozen=True)
class QdKtDotxBinaryAudit:
    gxp_type: str
    expected_sha256: str
    actual_sha256: str
    bookmark_names: tuple[str, ...]
    bookmark_count: int
    binary_checksum_verified: bool
    bookmark_owner_parity_verified: bool = False
    ready_to_render: bool = False


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
            info = archive.getinfo("word/document.xml")
            if info.file_size > _MAX_DOCUMENT_XML_BYTES:
                raise QdKtDotxAuditBlocked("QDKT_DOTX_DOCUMENT_XML_UNSUPPORTED")
            with archive.open(info) as source:
                xml_bytes = source.read(_MAX_DOCUMENT_XML_BYTES + 1)
            if len(xml_bytes) > _MAX_DOCUMENT_XML_BYTES:
                raise QdKtDotxAuditBlocked("QDKT_DOTX_DOCUMENT_XML_UNSUPPORTED")
        root = ElementTree.fromstring(xml_bytes)
    except (BadZipFile, KeyError, ElementTree.ParseError, OSError, RuntimeError) as exc:
        raise QdKtDotxAuditBlocked("QDKT_DOTX_WORD_XML_UNVERIFIED") from exc
    starts = root.iter(f"{_WORD_NS}bookmarkStart")
    bookmarks: dict[str, str] = {}
    for start in starts:
        ident = start.get(f"{_WORD_NS}id")
        name = start.get(f"{_WORD_NS}name")
        if not ident or not name or ident in bookmarks:
            raise QdKtDotxAuditBlocked("QDKT_DOTX_BOOKMARK_STRUCTURE_UNVERIFIED")
        bookmarks[ident] = name
    ends = [end.get(f"{_WORD_NS}id") for end in root.iter(f"{_WORD_NS}bookmarkEnd")]
    if len(ends) != len(bookmarks) or set(ends) != set(bookmarks) or len(ends) != len(set(ends)):
        raise QdKtDotxAuditBlocked("QDKT_DOTX_BOOKMARK_STRUCTURE_UNVERIFIED")
    return QdKtDotxBinaryAudit(
        gxp_type=asset.gxp_type,
        expected_sha256=asset.checksum_sha256,
        actual_sha256=actual,
        bookmark_names=tuple(sorted(bookmarks.values())),
        bookmark_count=len(bookmarks),
        binary_checksum_verified=True,
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
