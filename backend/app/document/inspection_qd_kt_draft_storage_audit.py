"""Bounded read-only QĐKT draft binary audit through the existing StorageService.

The caller must supply a separately authorized exact locator. This function
does not discover file paths, verify a StorageBinding owner, issue documents,
or write to storage. It never treats a checksum alone as Word visual UAT.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO

from backend.app.document.inspection_qd_kt_draft_binary_evidence import (
    QdKtDraftBinaryEvidence, verify_supplied_qdkt_draft_docx,
)
from backend.app.document.inspection_qd_kt_draft_provenance import QdKtDraftProvenance
from backend.app.storage.types import StorageServiceProtocol

MAX_BINARY_BYTES = 32 * 1024 * 1024


class QdKtDraftStorageAuditBlocked(ValueError):
    pass


@dataclass(frozen=True)
class QdKtExactDraftLocator:
    case_id: str
    document_version_id: str
    storage_root: str
    storage_relative_path: str
    storage_binding_owner_verified: bool = False


def audit_qdkt_draft_storage_binary(
    storage: StorageServiceProtocol, *, provenance: QdKtDraftProvenance,
    locator: QdKtExactDraftLocator,
) -> QdKtDraftBinaryEvidence:
    """Stream only a pinned, owner-attested file and verify its exact bytes."""
    if not isinstance(provenance, QdKtDraftProvenance) or not isinstance(locator, QdKtExactDraftLocator):
        raise QdKtDraftStorageAuditBlocked("QDKT_STORAGE_AUDIT_CONTRACT_INVALID")
    if (
        locator.storage_binding_owner_verified is not True
        or locator.case_id != provenance.case_id
        or locator.document_version_id != provenance.document_version_id
        or locator.storage_root != "inspection"
        or not isinstance(locator.storage_relative_path, str)
        or not locator.storage_relative_path
        or "\\" in locator.storage_relative_path
        or locator.storage_relative_path.startswith("/")
        or ":" in locator.storage_relative_path
        or any(piece in ("", ".", "..") for piece in locator.storage_relative_path.split("/"))
    ):
        raise QdKtDraftStorageAuditBlocked("QDKT_STORAGE_AUDIT_LOCATOR_UNPROVEN")
    try:
        with storage.read_stream(locator.storage_relative_path, root=locator.storage_root) as stream:
            payload = BytesIO()
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                if not isinstance(chunk, bytes) or payload.tell() + len(chunk) > MAX_BINARY_BYTES:
                    raise QdKtDraftStorageAuditBlocked("QDKT_STORAGE_AUDIT_BINARY_SIZE_UNSAFE")
                payload.write(chunk)
    except (OSError, RuntimeError) as exc:
        raise QdKtDraftStorageAuditBlocked("QDKT_STORAGE_AUDIT_READ_FAILED") from exc
    return verify_supplied_qdkt_draft_docx(provenance=provenance, payload=payload.getvalue())
