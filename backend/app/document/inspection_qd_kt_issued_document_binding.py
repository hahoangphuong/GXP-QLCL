"""Process B exact PDF-version owner. Metadata binding, never signature proof.

A version belongs to one decision only; the linked binary must be inspected by
a separate trusted bytes verifier before any stronger status can be asserted.
"""
from __future__ import annotations

from re import fullmatch

from sqlalchemy import select

from backend.app.db.enums import DocumentVariantType
from backend.app.db.models.phase1 import (
    Document, DocumentVariant, DocumentVersion, StorageBinding,
)
from backend.app.document.inspection_qd_kt_storage_locator_policy import (
    is_safe_qdkt_relative_path,
)


class QdKtIssuedDocumentBlocked(ValueError):
    pass


def require_exact_qdkt_issued_pdf_version(
    session, *, case_id: str, document_version_id: str,
) -> dict[str, str]:
    """Single scalar snapshot: Case / document / PDF variant / version / folder."""
    with session.no_autoflush:
        rows = session.execute(
            select(
                DocumentVersion.id, DocumentVersion.document_variant_id,
                DocumentVariant.id, DocumentVariant.document_id,
                DocumentVariant.variant_type, Document.id, Document.case_id,
                Document.family_code, DocumentVersion.checksum_sha256,
                DocumentVersion.storage_binding_id, DocumentVersion.storage_root,
                DocumentVersion.storage_relative_path, StorageBinding.id,
                StorageBinding.case_id, StorageBinding.relative_path,
            )
            .join(DocumentVariant, DocumentVersion.document_variant_id == DocumentVariant.id)
            .join(Document, DocumentVariant.document_id == Document.id)
            .outerjoin(StorageBinding, DocumentVersion.storage_binding_id == StorageBinding.id)
            .where(DocumentVersion.id == document_version_id)
        ).all()
    if len(rows) != 1:
        raise QdKtIssuedDocumentBlocked("QDKT_ISSUED_PDF_VERSION_NOT_FOUND")
    (
        version_id, version_variant_id, variant_id, variant_document_id,
        variant_type, document_id, owner_case_id, family_code, checksum,
        storage_binding_id, storage_root, path, bound_id, bound_case_id, folder,
    ) = rows[0]
    if (
        owner_case_id != case_id
        or family_code != "INSPECTION_QD_KT"
        or document_id != variant_document_id
        or version_variant_id != variant_id
    ):
        raise QdKtIssuedDocumentBlocked("QDKT_ISSUED_PDF_OWNER_MISMATCH")
    # A prepared DOCX, generated PDF, spreadsheet or ambiguous variant is not
    # an externally supplied issued-decision PDF. Neither admitted variant
    # proves its PDF bytes, signature or legal effect.
    if variant_type not in (
        DocumentVariantType.SIGNED_PDF, DocumentVariantType.SCANNED_PDF,
    ):
        raise QdKtIssuedDocumentBlocked("QDKT_ISSUED_PDF_VARIANT_INVALID")
    if type(checksum) is not str or fullmatch(r"[0-9a-fA-F]{64}", checksum) is None:
        raise QdKtIssuedDocumentBlocked("QDKT_ISSUED_PDF_CHECKSUM_MISSING")
    if (
        storage_binding_id is None or bound_id != storage_binding_id
        or bound_case_id != case_id or storage_root != "inspection"
        or not is_safe_qdkt_relative_path(folder)
        or not is_safe_qdkt_relative_path(path)
        or not path.startswith(folder + "/")
    ):
        raise QdKtIssuedDocumentBlocked("QDKT_ISSUED_PDF_STORAGE_OWNER_MISMATCH")
    return {
        "document_id": document_id,
        "document_version_id": version_id,
        "recorded_checksum_sha256": checksum.lower(),
        "variant_type": variant_type.value,
    }
