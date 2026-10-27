"""Bounded read-only QĐKT draft binary audit through the existing StorageService.

The caller must supply a separately authorized exact locator. This function
does not discover file paths, verify a StorageBinding owner, issue documents,
or write to storage. It never treats a checksum alone as Word visual UAT.
"""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from sqlalchemy import select
from backend.app.db.models.phase1 import Document, DocumentVariant, DocumentVersion, StorageBinding

from backend.app.document.inspection_qd_kt_draft_binary_evidence import (
    QdKtDraftBinaryEvidence, verify_supplied_qdkt_draft_docx,
)
from backend.app.document.inspection_qd_kt_draft_provenance import (\n    QdKtDraftProvenance, read_qdkt_draft_provenance,\n)\nfrom backend.app.document.inspection_qd_kt_team_snapshot_review import DraftTeamSnapshot
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


def resolve_qdkt_draft_storage_locator(
    session, *, provenance: QdKtDraftProvenance,
) -> QdKtExactDraftLocator:
    """Verify persisted version, document and binding ownership; no writes."""
    if not isinstance(provenance, QdKtDraftProvenance):
        raise QdKtDraftStorageAuditBlocked("QDKT_STORAGE_AUDIT_CONTRACT_INVALID")
    with session.no_autoflush:
        matches = session.execute(
            select(DocumentVersion, DocumentVariant, Document, StorageBinding)
            .join(DocumentVariant, DocumentVersion.document_variant_id == DocumentVariant.id)
            .join(Document, DocumentVariant.document_id == Document.id)
            .join(StorageBinding, DocumentVersion.storage_binding_id == StorageBinding.id)
            .where(DocumentVersion.id == provenance.document_version_id)
        ).all()
    if len(matches) != 1:
        raise QdKtDraftStorageAuditBlocked("QDKT_STORAGE_AUDIT_BINDING_NOT_UNIQUE")
    version, variant, document, binding = matches[0]
    path = version.storage_relative_path
    folder = binding.relative_path
    if (
        document.id != provenance.document_id
        or document.case_id != provenance.case_id
        or document.family_code != "INSPECTION_QD_KT"
        or variant.document_id != document.id
        or version.document_variant_id != variant.id
        or version.storage_binding_id != binding.id
        or binding.case_id != provenance.case_id
        or version.checksum_sha256 != provenance.stored_checksum_sha256
        or version.storage_root != "inspection"
        or not isinstance(path, str)
        or not isinstance(folder, str)
        or not folder\n        or not _safe_inspection_relative_path(folder)\n        or not _safe_inspection_relative_path(path)\n        or not path.startswith(folder + "/")
    ):
        raise QdKtDraftStorageAuditBlocked("QDKT_STORAGE_AUDIT_OWNER_MISMATCH")
    locator = QdKtExactDraftLocator(
        case_id=provenance.case_id,
        document_version_id=provenance.document_version_id,
        storage_root=version.storage_root,
        storage_relative_path=path,
        storage_binding_owner_verified=True,
    )
    return locator


def _safe_inspection_relative_path(value: str) -> bool:
    return (
        isinstance(value, str) and bool(value)
        and "\\" not in value and not value.startswith("/")
        and ":" not in value
        and all(part not in ("", ".", "..") for part in value.split("/"))
    )


def audit_case_qdkt_draft_binary_readonly(
    session, storage: StorageServiceProtocol, *, case_id: str,
    snapshot: DraftTeamSnapshot,
) -> QdKtDraftBinaryEvidence:
    """Trusted internal entrypoint: Case/snapshot/DB-binding/bytes in one flow.

    This is not an authentication or permission boundary. Only an already
    authorized service may call it; no public endpoint or implicit permission.
    """
    if (
        not isinstance(case_id, str) or not case_id.strip()
        or not isinstance(snapshot, DraftTeamSnapshot)
        or snapshot.case_id != case_id
    ):
        raise QdKtDraftStorageAuditBlocked("QDKT_STORAGE_AUDIT_CASE_MISMATCH")
    with session.no_autoflush:
        provenance = read_qdkt_draft_provenance(
            session, case_id=case_id, snapshot=snapshot,
        )
        locator = resolve_qdkt_draft_storage_locator(
            session, provenance=provenance,
        )
        # A read-only stream cannot authorize generation or approval.
        return audit_qdkt_draft_storage_binary(
            storage, provenance=provenance, locator=locator,
        )
