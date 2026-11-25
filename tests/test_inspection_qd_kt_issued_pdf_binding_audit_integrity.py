"""Recorded PDF link must have a single matching operator audit, not only a hash."""
import json

import pytest

from backend.app.audit_payload import normalize_and_redact_audit_payload
from backend.app.db.enums import AuditActorType
from backend.app.document.inspection_qd_kt_issued_pdf_binding_audit_integrity import (
    QdKtIssuedPdfBindingAuditBlocked,
    require_qdkt_issued_pdf_binding_audit_integrity,
)


def payload(**overrides):
    values = {
        "case_id": "case-a",
        "decision_id": "decision-a",
        "document_version_id": "version-a",
        "recorded_checksum_sha256": "a" * 64,
        "binary_checksum_verified": False,
        "independent_signature_verified": False,
    }
    values.update(overrides)
    return json.dumps(normalize_and_redact_audit_payload(values))


def check(evidence=None, **overrides):
    args = {
        "binding_id": "binding-a",
        "case_id": "case-a",
        "decision_id": "decision-a",
        "document_version_id": "version-a",
        "recorded_checksum_sha256": "a" * 64,
        "binding_actor_id": "operator-a",
        "binding_reason": "Operator linked issued PDF",
        "evidence": ("audit-a", AuditActorType.USER, "operator-a",
                     "Operator linked issued PDF", payload()),
    }
    if evidence is not None:
        args["evidence"] = evidence
    args.update(overrides)
    require_qdkt_issued_pdf_binding_audit_integrity(**args)


def test_valid_operator_audit_evidence():
    check()


@pytest.mark.parametrize("field,value", [
    ("case_id", "foreign-case"),
    ("decision_id", "foreign-decision"),
    ("document_version_id", "newer-version"),
    ("recorded_checksum_sha256", "b" * 64),
    ("independent_signature_verified", True),
    ("independent_signature_verified", None),
])
def test_mismatched_or_overclaimed_audit_payload_fails_closed(field, value):
    with pytest.raises(QdKtIssuedPdfBindingAuditBlocked, match="AUDIT_INVALID"):
        check(evidence=("audit-a", AuditActorType.USER, "operator-a",
                        "Operator linked issued PDF", payload(**{field: value})))


@pytest.mark.parametrize("evidence", [
    (None, AuditActorType.USER, "operator-a", "Operator linked issued PDF", payload()),
    ("audit-a", AuditActorType.SYSTEM, "operator-a", "Operator linked issued PDF", payload()),
    ("audit-a", AuditActorType.USER, "operator-b", "Operator linked issued PDF", payload()),
    ("audit-a", AuditActorType.USER, "operator-a", "different reason", payload()),
    ("audit-a", AuditActorType.USER, "operator-a", "", payload()),
    ("audit-a", AuditActorType.USER, "operator-a", "Operator linked issued PDF", "{invalid"),
    ("audit-a", AuditActorType.USER, "operator-a", "Operator linked issued PDF", "[]"),
    ("audit-a", AuditActorType.USER, "operator-a", "Operator linked issued PDF", None),
])
def test_missing_or_malformed_operator_evidence_blocks(evidence):
    with pytest.raises(QdKtIssuedPdfBindingAuditBlocked, match="AUDIT_INVALID"):
        check(evidence=evidence)


def test_bad_binding_actor_or_reason_blocks():
    with pytest.raises(QdKtIssuedPdfBindingAuditBlocked, match="AUDIT_INVALID"):
        check(binding_actor_id="different-operator")
    with pytest.raises(QdKtIssuedPdfBindingAuditBlocked, match="AUDIT_INVALID"):
        check(binding_reason=" ")



def test_binary_redaction_marker_required_without_claiming_byte_verification():
    raw = json.loads(payload())
    assert raw["binary_checksum_verified"] == "<redacted>"
    check()
    raw["binary_checksum_verified"] = False
    with pytest.raises(QdKtIssuedPdfBindingAuditBlocked, match="AUDIT_INVALID"):
        check(evidence=("audit-a", AuditActorType.USER, "operator-a",
                        "Operator linked issued PDF", json.dumps(raw)))
