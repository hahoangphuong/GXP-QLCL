"""Read-only check that a draft roster refers to an actual Case DOCX version.

This verifies identity and stored checksum, NOT that the DOCX content matches
the proposed roster. It deliberately cannot make a draft an issued decision.
"""
from __future__ import annotations

from dataclasses import dataclass
from re import fullmatch

from sqlalchemy import select
from backend.app.db.models.phase1 import Document, DocumentVariant, DocumentVersion
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
    with session.no_autoflush:
        match = session.execute(
            select(DocumentVersion, DocumentVariant, Document)
            .join(DocumentVariant, DocumentVersion.document_variant_id == DocumentVariant.id)
            .join(Document, DocumentVariant.document_id == Document.id)
            .where(DocumentVersion.id == snapshot.document_version_id)
            .execution_options(populate_existing=True)
        ).one_or_none()
    if match is None:
        raise QdKtDraftVersionBindingBlocked("QDKT_DRAFT_VERSION_NOT_FOUND")
    version, variant, document = match
    if (document.case_id != snapshot.case_id
            or document.family_code != "INSPECTION_QD_KT"
            or document.id != variant.document_id
            or variant.id != version.document_variant_id):
        raise QdKtDraftVersionBindingBlocked("QDKT_DRAFT_VERSION_OWNER_MISMATCH")
    checksum = version.checksum_sha256
    if not isinstance(checksum, str) or fullmatch(r"[0-9a-fA-F]{64}", checksum) is None:
        raise QdKtDraftVersionBindingBlocked("QDKT_DRAFT_VERSION_CHECKSUM_MISSING")
    if not version.storage_binding_id and not (
        version.storage_root and version.storage_relative_path
    ):
        raise QdKtDraftVersionBindingBlocked("QDKT_DRAFT_VERSION_STORAGE_UNBOUND")
    return QdKtDraftVersionBinding(
        case_id=snapshot.case_id,
        draft_id=snapshot.draft_id,
        document_version_id=version.id,
        document_id=document.id,
        stored_checksum_sha256=checksum.lower(),
        roster_member_ids=tuple(m.inspector_id for m in snapshot.members),
    )
