"""Read-only, bounded verification of exact Process B PDF bytes.

This measures stored bytes, not a signature, the document's legal effect,
the decision's text, or an authorization to issue another document.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from re import fullmatch

from sqlalchemy import select

from backend.app.db.enums import DocumentVariantType
from backend.app.db.models.phase1 import (
    Document, DocumentVariant, DocumentVersion, InspectionDecision,
    InspectionPlan, QdKtIssuedDocumentBinding, StorageBinding,
)
from backend.app.document.inspection_qd_kt_storage_locator_policy import (
    is_safe_qdkt_relative_path,
)
from backend.app.storage.types import StorageServiceProtocol

MAX_PDF_BYTES = 32 * 1024 * 1024
_CHUNK_BYTES = 1024 * 1024


class QdKtIssuedPdfBinaryAuditBlocked(ValueError):
    pass


@dataclass(frozen=True)
class QdKtIssuedPdfBinaryLocator:
    case_id: str
    decision_id: str
    binding_id: str
    document_id: str
    document_version_id: str
    variant_type: DocumentVariantType
    storage_root: str
    storage_relative_path: str
    recorded_checksum_sha256: str


@dataclass(frozen=True)
class QdKtIssuedPdfBinaryEvidence:
    case_id: str
    decision_id: str
    binding_id: str
    document_version_id: str
    verified_sha256: str
    verified_pdf_bytes: int
    actual_binary_checksum_verified: bool = True
    basic_pdf_envelope_verified: bool = True
    signature_cryptographically_verified: bool = False
    pdf_decision_content_verified: bool = False
    independent_legal_issuance_verified: bool = False
    ready_to_render: bool = False


def resolve_exact_issued_pdf_binary_locator(
    session, *, case_id: str, decision_id: str,
) -> QdKtIssuedPdfBinaryLocator:
    """One coherent scalar read: binding, version, document and folder."""
    with session.no_autoflush:
        rows = session.execute(
            select(
                QdKtIssuedDocumentBinding.id,
                QdKtIssuedDocumentBinding.document_version_id,
                QdKtIssuedDocumentBinding.recorded_checksum_sha256,
                InspectionDecision.id,
                InspectionPlan.case_id,
                DocumentVersion.id,
                DocumentVersion.document_variant_id,
                DocumentVersion.checksum_sha256,
                DocumentVersion.storage_binding_id,
                DocumentVersion.storage_root,
                DocumentVersion.storage_relative_path,
                DocumentVariant.id,
                DocumentVariant.document_id,
                DocumentVariant.variant_type,
                Document.id,
                Document.case_id,
                Document.family_code,
                StorageBinding.id,
                StorageBinding.case_id,
                StorageBinding.relative_path,
            )
            .join(InspectionDecision,
                  QdKtIssuedDocumentBinding.inspection_decision_id == InspectionDecision.id)
            .join(InspectionPlan,
                  InspectionDecision.inspection_plan_id == InspectionPlan.id)
            .join(DocumentVersion,
                  QdKtIssuedDocumentBinding.document_version_id == DocumentVersion.id)
            .join(DocumentVariant,
                  DocumentVersion.document_variant_id == DocumentVariant.id)
            .join(Document, DocumentVariant.document_id == Document.id)
            .join(StorageBinding,
                  DocumentVersion.storage_binding_id == StorageBinding.id)
            .where(QdKtIssuedDocumentBinding.inspection_decision_id == decision_id)
        ).all()
    if len(rows) != 1:
        raise QdKtIssuedPdfBinaryAuditBlocked("QDKT_ISSUED_BINARY_BINDING_NOT_UNIQUE")
    (
        binding_id, linked_version, linked_checksum, owner_decision_id,
        decision_case_id, version_id, version_variant,
        version_checksum, version_storage_binding, root, path,
        variant_id, variant_document, variant_type, document_id, document_case,
        document_family, storage_binding_id, storage_case, folder,
    ) = rows[0]
    if (
        not isinstance(case_id, str) or not isinstance(decision_id, str)
        or not case_id or not decision_id
        or owner_decision_id != decision_id or decision_case_id != case_id
        or linked_version != version_id or version_variant != variant_id
        or variant_document != document_id
        or document_case != case_id or document_family != "INSPECTION_QD_KT"
        or variant_type not in (
            DocumentVariantType.SCANNED_PDF, DocumentVariantType.SIGNED_PDF,
        )
        or version_storage_binding != storage_binding_id
        or storage_case != case_id or root != "inspection"
        or not is_safe_qdkt_relative_path(folder)
        or not is_safe_qdkt_relative_path(path)
        or not path.startswith(folder + "/")
        or not isinstance(linked_checksum, str)
        or fullmatch(r"[0-9a-fA-F]{64}", linked_checksum) is None
        or not isinstance(version_checksum, str)
        or fullmatch(r"[0-9a-fA-F]{64}", version_checksum) is None
        or linked_checksum.lower() != version_checksum.lower()
    ):
        raise QdKtIssuedPdfBinaryAuditBlocked("QDKT_ISSUED_BINARY_OWNER_OR_SOURCE_DRIFT")
    return QdKtIssuedPdfBinaryLocator(
        case_id=case_id, decision_id=decision_id,
        binding_id=binding_id, document_id=document_id,
        document_version_id=version_id, variant_type=variant_type,
        storage_root=root, storage_relative_path=path,
        recorded_checksum_sha256=linked_checksum.lower(),
    )


def measure_exact_issued_pdf_bytes(
    storage: StorageServiceProtocol, *, locator: QdKtIssuedPdfBinaryLocator,
) -> QdKtIssuedPdfBinaryEvidence:
    """Bounded streaming SHA-256 and conservative PDF file envelope check."""
    if (
        not isinstance(locator, QdKtIssuedPdfBinaryLocator)
        or not locator.binding_id or not locator.case_id or not locator.decision_id
        or not locator.document_version_id or locator.storage_root != "inspection"
        or locator.variant_type not in (
            DocumentVariantType.SIGNED_PDF, DocumentVariantType.SCANNED_PDF,
        )
        or not is_safe_qdkt_relative_path(locator.storage_relative_path)
        or not isinstance(locator.recorded_checksum_sha256, str)
        or fullmatch(r"[0-9a-f]{64}", locator.recorded_checksum_sha256) is None
    ):
        raise QdKtIssuedPdfBinaryAuditBlocked("QDKT_ISSUED_BINARY_LOCATOR_UNPROVEN")
    digest = sha256()
    size = 0
    prefix = b""
    tail = b""
    try:
        with storage.read_stream(
            locator.storage_relative_path, root=locator.storage_root,
        ) as stream:
            while True:
                chunk = stream.read(_CHUNK_BYTES)
                if type(chunk) is not bytes:
                    raise QdKtIssuedPdfBinaryAuditBlocked("QDKT_ISSUED_BINARY_STREAM_INVALID")
                if len(chunk) > _CHUNK_BYTES:
                    raise QdKtIssuedPdfBinaryAuditBlocked("QDKT_ISSUED_BINARY_CHUNK_UNSAFE")
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_PDF_BYTES:
                    raise QdKtIssuedPdfBinaryAuditBlocked("QDKT_ISSUED_BINARY_TOO_LARGE")
                digest.update(chunk)
                prefix = (prefix + chunk)[:8]
                tail = (tail + chunk)[-1024:]
    except (OSError, RuntimeError, EOFError, ConnectionError, TimeoutError) as exc:
        raise QdKtIssuedPdfBinaryAuditBlocked("QDKT_ISSUED_BINARY_READ_FAILED") from exc
    if not prefix.startswith(b"%PDF-"):
        raise QdKtIssuedPdfBinaryAuditBlocked("QDKT_ISSUED_BINARY_NOT_PDF")
    if b"%%EOF" not in tail or tail.split(b"%%EOF")[-1].strip(b"\x00\x09\x0a\x0c\x0d\x20"):
        raise QdKtIssuedPdfBinaryAuditBlocked("QDKT_ISSUED_BINARY_PDF_TRAILER_INVALID")
    actual = digest.hexdigest()
    if actual != locator.recorded_checksum_sha256:
        raise QdKtIssuedPdfBinaryAuditBlocked("QDKT_ISSUED_BINARY_CHECKSUM_MISMATCH")
    return QdKtIssuedPdfBinaryEvidence(
        case_id=locator.case_id, decision_id=locator.decision_id,
        binding_id=locator.binding_id, document_version_id=locator.document_version_id,
        verified_sha256=actual, verified_pdf_bytes=size,
    )


def audit_case_issued_pdf_binary_readonly(
    session, storage: StorageServiceProtocol, *, case_id: str, decision_id: str,
) -> QdKtIssuedPdfBinaryEvidence:
    """Trusted internal entrypoint. Caller must authenticate/authorize first.

    Detects observable DB/object changes across two complete source reads.
    Not an atomic object snapshot, a signature check, or a legal approval.
    """
    with session.no_autoflush:
        initial = resolve_exact_issued_pdf_binary_locator(
            session, case_id=case_id, decision_id=decision_id,
        )
        first = measure_exact_issued_pdf_bytes(storage, locator=initial)
        second_locator = resolve_exact_issued_pdf_binary_locator(
            session, case_id=case_id, decision_id=decision_id,
        )
        if second_locator != initial:
            raise QdKtIssuedPdfBinaryAuditBlocked("QDKT_ISSUED_BINARY_SOURCE_CHANGED")
        repeated = measure_exact_issued_pdf_bytes(storage, locator=second_locator)
        if repeated != first:
            raise QdKtIssuedPdfBinaryAuditBlocked("QDKT_ISSUED_BINARY_SOURCE_CHANGED")
        final = resolve_exact_issued_pdf_binary_locator(
            session, case_id=case_id, decision_id=decision_id,
        )
        if final != initial:
            raise QdKtIssuedPdfBinaryAuditBlocked("QDKT_ISSUED_BINARY_SOURCE_CHANGED")
        return first
