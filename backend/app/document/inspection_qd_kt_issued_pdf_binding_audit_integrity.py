"""Validate the recorded operator link between QĐKT and an exact PDF version.

The audit ties an operator to a stored metadata binding only. It does not
verify signature, document contents, or legal issuance.
"""
from __future__ import annotations

import json

from backend.app.db.enums import AuditActorType


class QdKtIssuedPdfBindingAuditBlocked(ValueError):
    pass


def require_qdkt_issued_pdf_binding_audit_integrity(
    *, binding_id: str, case_id: str, decision_id: str,
    document_version_id: str, recorded_checksum_sha256: str,
    binding_actor_id: str, binding_reason: str, evidence: tuple,
) -> None:
    """Check exactly one audit scalar row against the persisted binding atom."""
    audit_id, actor_type, actor_id, reason, raw_payload = evidence
    if (
        not audit_id
        or actor_type is not AuditActorType.USER
        or not actor_id
        or actor_id != binding_actor_id
        or not isinstance(binding_reason, str)
        or not binding_reason.strip()
        or reason != binding_reason
        or not isinstance(reason, str)
        or not reason.strip()
    ):
        raise QdKtIssuedPdfBindingAuditBlocked("QDKT_ISSUED_PDF_AUDIT_INVALID")
    try:
        payload = json.loads(raw_payload)
    except (ValueError, TypeError) as exc:
        raise QdKtIssuedPdfBindingAuditBlocked("QDKT_ISSUED_PDF_AUDIT_INVALID") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("case_id") != case_id
        or payload.get("decision_id") != decision_id
        or payload.get("document_version_id") != document_version_id
        or payload.get("recorded_checksum_sha256") != recorded_checksum_sha256
        or payload.get("binary_checksum_verified") is not False
        or payload.get("independent_signature_verified") is not False
    ):
        raise QdKtIssuedPdfBindingAuditBlocked("QDKT_ISSUED_PDF_AUDIT_INVALID")
