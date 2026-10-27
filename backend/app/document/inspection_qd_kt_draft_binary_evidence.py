"""Offline-only verification of supplied QĐKT draft DOCX bytes.

Checks the exact bytes against Case-owned draft provenance and the OOXML
package envelope. Does not read storage, interpret bookmarks, confirm roster
text, authorize issuance, or imply Microsoft Word visual acceptance.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from re import fullmatch
from zipfile import BadZipFile, ZipFile

from xml.etree import ElementTree as ET

from backend.app.document.inspection_qd_kt_draft_provenance import QdKtDraftProvenance
from backend.app.document.inspection_qd_kt_offline_package_integrity import (
    QdKtOfflinePackageIntegrityBlocked, require_safe_ooxml_members,
)

_CONTENT_TYPES = "{http://schemas.openxmlformats.org/package/2006/content-types}"
_DOCX_MAIN = "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
_WORD_ROOT = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}document"
_MAX_SUPPLIED_BYTES = 32 * 1024 * 1024


class QdKtDraftBinaryBlocked(ValueError):
    pass


@dataclass(frozen=True)
class QdKtDraftBinaryEvidence:
    case_id: str
    draft_id: str
    document_version_id: str
    verified_sha256: str
    actual_docx_bytes_verified: bool = True
    docx_package_structure_verified: bool = True
    roster_in_document_verified: bool = False
    bookmark_owner_parity_verified: bool = False
    visual_word_uat_verified: bool = False
    ready_to_render: bool = False


def require_qdkt_draft_binary_provenance(provenance: QdKtDraftProvenance) -> None:
    """Reject unproven source flags and malformed checksum before storage I/O."""
    if not isinstance(provenance, QdKtDraftProvenance):
        raise QdKtDraftBinaryBlocked("QDKT_DRAFT_BINARY_PROVENANCE_INVALID")
    if (
        not provenance.case_id or not provenance.draft_id
        or not provenance.document_version_id or not provenance.document_id
        or provenance.case_roster_identity_verified is not True
        or provenance.version_case_ownership_verified is not True
        or provenance.binary_content_verified is not False
        or provenance.job_title_provenance_verified is not False
        or provenance.issuance_approved is not False
        or provenance.ready_to_render is not False
        or not isinstance(provenance.stored_checksum_sha256, str)
        or fullmatch(r"[0-9a-f]{64}", provenance.stored_checksum_sha256) is None
    ):
        raise QdKtDraftBinaryBlocked("QDKT_DRAFT_BINARY_PROVENANCE_UNPROVEN")

def verify_supplied_qdkt_draft_docx(
    *, provenance: QdKtDraftProvenance, payload: bytes,
) -> QdKtDraftBinaryEvidence:
    """Measure caller-supplied, bounded bytes, not a locator or persisted hash."""
    require_qdkt_draft_binary_provenance(provenance)
    if not isinstance(payload, bytes) or not payload or len(payload) > _MAX_SUPPLIED_BYTES:
        raise QdKtDraftBinaryBlocked("QDKT_DRAFT_BINARY_SIZE_UNSAFE")
    actual = sha256(payload).hexdigest()
    if actual != provenance.stored_checksum_sha256:
        raise QdKtDraftBinaryBlocked("QDKT_DRAFT_BINARY_CHECKSUM_MISMATCH")
    try:
        with ZipFile(BytesIO(payload)) as archive:
            names = {item.filename for item in require_safe_ooxml_members(archive)}
            if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                raise QdKtDraftBinaryBlocked("QDKT_DRAFT_BINARY_REQUIRED_PART_MISSING")
            types_raw = archive.read("[Content_Types].xml")
            document_raw = archive.read("word/document.xml")
            if any(marker in xml.upper() for xml in (types_raw, document_raw)
                   for marker in (b"<!DOCTYPE", b"<!ENTITY")):
                raise QdKtDraftBinaryBlocked("QDKT_DRAFT_BINARY_DTD_UNSAFE")
            types = ET.fromstring(types_raw)
            if types.tag != _CONTENT_TYPES + "Types":
                raise QdKtDraftBinaryBlocked("QDKT_DRAFT_BINARY_CONTENT_TYPE_INVALID")
            main = [
                node.get("ContentType") for node in types.findall(_CONTENT_TYPES + "Override")
                if node.get("PartName") == "/word/document.xml"
            ]
            if main != [_DOCX_MAIN]:
                raise QdKtDraftBinaryBlocked("QDKT_DRAFT_BINARY_CONTENT_TYPE_INVALID")
            document = ET.fromstring(document_raw)
            if document.tag != _WORD_ROOT:
                raise QdKtDraftBinaryBlocked("QDKT_DRAFT_BINARY_WORD_ROOT_INVALID")
    except (BadZipFile, OSError, KeyError, ET.ParseError,
            QdKtOfflinePackageIntegrityBlocked) as exc:
        raise QdKtDraftBinaryBlocked("QDKT_DRAFT_BINARY_PACKAGE_UNVERIFIED") from exc
    return QdKtDraftBinaryEvidence(
        case_id=provenance.case_id, draft_id=provenance.draft_id,
        document_version_id=provenance.document_version_id,
        verified_sha256=actual,
    )
