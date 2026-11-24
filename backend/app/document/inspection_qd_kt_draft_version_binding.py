"""Read-only check that a draft roster refers to an actual Case DOCX version.

This verifies identity and stored checksum, NOT that the DOCX content matches
the proposed roster. It deliberately cannot make a draft an issued decision.
"""
from __future__ import annotations

from dataclasses import dataclass
from re import fullmatch

from sqlalchemy import select
from backend.app.db.enums import DocumentVariantType
from backend.app.db.models.phase1 import Document, DocumentVariant, DocumentVersion, StorageBinding
from backend.app.document.inspection_qd_kt_team_snapshot_review import (
    DraftTeamSnapshot, validate_draft_snapshot,
)


class QdKtDraftVersionBindingBlocked(ValueError):
    pass


@dataclass(frozen=True)
class QdKtDraftVersionBinding:
    case_id: str
    draft_id: str
    document_version_id: str
    document_id: str
    stored_checksum_sha256: str
    roster_member_ids: tuple[str, ...]
    confirmed_binary_roster_match: bool = False
    approved_decision_link: bool = False


def require_qdkt_draft_version_binding(
    session, *, snapshot: DraftTeamSnapshot,
) -> QdKtDraftVersionBinding:
    """Reject cross-Case, wrong-family and unpinned versions without writes."""
    validate_draft_snapshot(snapshot)
    # A scalar read must not hydrate/refresh ORM entities. populate_existing
    # previously overwrote dirty or stale DocumentVersion instances in the
    # caller's identity map even inside no_autoflush. A single SELECT provides
    # one coherent PostgreSQL READ COMMITTED snapshot for the entire binding.
    with session.no_autoflush:
        match = session.execute(
            select(
                DocumentVersion.id, DocumentVersion.document_variant_id,
                DocumentVariant.id, DocumentVariant.document_id,
                DocumentVariant.variant_type,
                Document.id, Document.case_id, Document.family_code,
                DocumentVersion.checksum_sha256,
                DocumentVersion.storage_binding_id,
                DocumentVersion.storage_root,
                DocumentVersion.storage_relative_path,
                StorageBinding.id, StorageBinding.case_id,
            )
            .join(DocumentVariant, DocumentVersion.document_variant_id == DocumentVariant.id)
            .join(Document, DocumentVariant.document_id == Document.id)
            .outerjoin(StorageBinding, StorageBinding.id == DocumentVersion.storage_binding_id)
            .where(DocumentVersion.id == snapshot.document_version_id)
        ).one_or_none()
    if match is None:
        raise QdKtDraftVersionBindingBlocked("QDKT_DRAFT_VERSION_NOT_FOUND")
    (
        version_id, version_variant_id, variant_id, variant_document_id,
        variant_type, document_id, owner_case_id, family_code, checksum, binding_id,
        storage_root, storage_relative_path, persisted_binding_id,
        binding_case_id,
    ) = match
    if (
        owner_case_id != snapshot.case_id
        or family_code != "INSPECTION_QD_KT"
        or document_id != variant_document_id
        or variant_id != version_variant_id
    ):
        raise QdKtDraftVersionBindingBlocked("QDKT_DRAFT_VERSION_OWNER_MISMATCH")
    # A PDF scan, signed PDF, spreadsheet, or arbitrary stored variant cannot
    # masquerade as the editable DOCX used by Process A. The variant type is
    # only metadata: this does NOT independently inspect DOCX bytes, prove
    # the rendered roster, or certify an issued QĐKT.
    if variant_type is not DocumentVariantType.EDITABLE_DOCX:
        raise QdKtDraftVersionBindingBlocked("QDKT_DRAFT_VERSION_NOT_EDITABLE_DOCX")
    if not isinstance(checksum, str) or fullmatch(r"[0-9a-fA-F]{64}", checksum) is None:
        raise QdKtDraftVersionBindingBlocked("QDKT_DRAFT_VERSION_CHECKSUM_MISSING")
    if binding_id is not None:
        if persisted_binding_id != binding_id or binding_case_id != snapshot.case_id:
            raise QdKtDraftVersionBindingBlocked("QDKT_DRAFT_VERSION_STORAGE_OWNER_MISMATCH")
    elif not (
        isinstance(storage_root, str) and storage_root.strip()
        and isinstance(storage_relative_path, str) and storage_relative_path.strip()
    ):
        raise QdKtDraftVersionBindingBlocked("QDKT_DRAFT_VERSION_STORAGE_UNBOUND")
    return QdKtDraftVersionBinding(
        case_id=snapshot.case_id,
        draft_id=snapshot.draft_id,
        document_version_id=version_id,
        document_id=document_id,
        stored_checksum_sha256=checksum.lower(),
        roster_member_ids=tuple(m.inspector_id for m in snapshot.members),
    )
