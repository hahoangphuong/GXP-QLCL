"""Validate Process B audit evidence without asserting legal issuance."""
from __future__ import annotations

import json
from datetime import date

from backend.app.db.enums import AuditActorType


class QdKtAttestationBlocked(ValueError):
    pass


def require_qdkt_attestation_integrity(
    *, evidence, case_id: str, plan_id: str, roster_id: str,
    roster_actor_id: str, roster_source: str, reference: str,
    decision_on: date, relation_type: str | None, related_decision_id: str | None,
) -> None:
    """Check one persisted audit record against the same scalar DB snapshot."""
    audit_id, actor_type, actor_id, reason, raw_payload, raw_after = evidence
    try:
        payload = json.loads(raw_payload)
        after = json.loads(raw_after)
    except (TypeError, ValueError) as exc:
        raise QdKtAttestationBlocked("QDKT_ATTESTATION_INVALID") from exc
    if (
        not audit_id or actor_type is not AuditActorType.USER
        or not actor_id or actor_id != roster_actor_id
        or not isinstance(reason, str) or not reason.strip()
        or not isinstance(payload, dict) or not isinstance(after, dict)
        or payload.get("case_id") != case_id
        or payload.get("inspection_plan_id") != plan_id
        or payload.get("roster_id") != roster_id
        or payload.get("external_approval_confirmed") is not True
        or payload.get("signed_document_independently_verified") is not False
        or not isinstance(payload.get("approval_basis"), str)
        or not payload["approval_basis"].strip()
        or after.get("reference") != reference
        or after.get("decision_on") != decision_on.isoformat()
        or after.get("relation_type") != (relation_type or "INITIAL")
        or "related_decision_id" not in after
        or after["related_decision_id"] != related_decision_id
        or after.get("roster_source") != roster_source
    ):
        raise QdKtAttestationBlocked("QDKT_ATTESTATION_INVALID")
