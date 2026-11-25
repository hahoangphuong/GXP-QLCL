"""Pure guard regression: operator attestation is not a legal-signature proof."""
import json
from datetime import date

import pytest

from backend.app.db.enums import AuditActorType
from backend.app.document.inspection_qd_kt_attestation_integrity import (
    QdKtAttestationBlocked, require_qdkt_attestation_integrity,
)

DAY = date(2026, 10, 1)


def scenario():
    payload = {
        "case_id": "case-a",
        "inspection_plan_id": "plan-a",
        "roster_id": "roster-a",
        "approval_basis": "Operator examined a signed external decision",
        "external_approval_confirmed": True,
        "signed_document_independently_verified": False,
    }
    after = {
        "reference": "QDKT-01", "decision_on": DAY.isoformat(),
        "relation_type": "INITIAL", "related_decision_id": None,
        "roster_source": "USER_ENTERED",
    }
    evidence = ("audit-a", AuditActorType.USER, "actor-a", "Operator recording",
                json.dumps(payload), json.dumps(after))
    owner = dict(
        case_id="case-a", plan_id="plan-a", roster_id="roster-a",
        roster_actor_id="actor-a", roster_source="USER_ENTERED",
        reference="QDKT-01", decision_on=DAY, relation_type=None,
        related_decision_id=None,
    )
    return evidence, owner


def test_exact_attestation_is_only_operator_record():
    evidence, owner = scenario()
    assert require_qdkt_attestation_integrity(evidence=evidence, **owner) is None


@pytest.mark.parametrize("key,value", [
    ("case_id", "case-b"), ("inspection_plan_id", "plan-b"),
    ("roster_id", "roster-b"), ("approval_basis", ""),
    ("external_approval_confirmed", False),
    ("external_approval_confirmed", "true"),
    ("signed_document_independently_verified", True),
    ("signed_document_independently_verified", None),
])
def test_wrong_audit_payload_blocks(key, value):
    evidence, owner = scenario()
    values = json.loads(evidence[4])
    values[key] = value
    with pytest.raises(QdKtAttestationBlocked, match="ATTESTATION_INVALID"):
        require_qdkt_attestation_integrity(
            evidence=(*evidence[:4], json.dumps(values), evidence[5]), **owner)


@pytest.mark.parametrize("key,value", [
    ("reference", "other-reference"), ("decision_on", "2026-10-02"),
    ("relation_type", "REPLACES"), ("related_decision_id", "other"),
    ("roster_source", "DRAFT_EDITED"),
])
def test_wrong_recorded_decision_blocks(key, value):
    evidence, owner = scenario()
    values = json.loads(evidence[5])
    values[key] = value
    with pytest.raises(QdKtAttestationBlocked, match="ATTESTATION_INVALID"):
        require_qdkt_attestation_integrity(
            evidence=(*evidence[:5], json.dumps(values)), **owner)


@pytest.mark.parametrize("index,value", [
    (0, None), (1, None), (2, "other-actor"), (3, ""),
    (4, "{invalid"), (4, json.dumps(["not-a-dict"])),
    (5, "{invalid"), (5, json.dumps(["not-a-dict"])),
])
def test_invalid_actor_reason_or_json_blocks(index, value):
    evidence, owner = scenario()
    values = list(evidence)
    values[index] = value
    with pytest.raises(QdKtAttestationBlocked, match="ATTESTATION_INVALID"):
        require_qdkt_attestation_integrity(evidence=tuple(values), **owner)


def test_missing_related_decision_field_blocks():
    evidence, owner = scenario()
    after = json.loads(evidence[5])
    del after["related_decision_id"]
    with pytest.raises(QdKtAttestationBlocked, match="ATTESTATION_INVALID"):
        require_qdkt_attestation_integrity(
            evidence=(*evidence[:5], json.dumps(after)), **owner)


def test_explicit_amendment_remains_distinct_from_replacement():
    evidence, owner = scenario()
    after = json.loads(evidence[5])
    after.update(relation_type="AMENDS", related_decision_id="previous")
    owner.update(relation_type="AMENDS", related_decision_id="previous")
    assert require_qdkt_attestation_integrity(
        evidence=(*evidence[:5], json.dumps(after)), **owner) is None
    owner["relation_type"] = "REPLACES"
    with pytest.raises(QdKtAttestationBlocked, match="ATTESTATION_INVALID"):
        require_qdkt_attestation_integrity(
            evidence=(*evidence[:5], json.dumps(after)), **owner)
