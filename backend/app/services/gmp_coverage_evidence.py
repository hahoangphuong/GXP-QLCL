"""Pure, conservative evidence adjudication for a proposed multi-site GMP model.

No database writes, legacy ID exceptions, or certificate-link acceptance changes.
Issue #6: distinguish positive coverage from authority to link an Inspection Case.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ReviewDecision(str, Enum):
    UNRESOLVED = "UNRESOLVED"
    REJECTED = "REJECTED"
    VERIFIED = "VERIFIED"


@dataclass(frozen=True)
class CoveredSiteEvidence:
    certificate_version_id: str
    site_id: str
    source_snapshot_sha256: str
    source_document_sha256: str
    source_page_reference: str
    decision: ReviewDecision
    reviewer_id: str | None = None
    reviewed_at_iso: str | None = None
    rationale: str | None = None


@dataclass(frozen=True)
class LinkedCaseEvidence:
    certificate_version_id: str
    case_id: str
    site_id: str
    gxp_type: str
    coverage: CoveredSiteEvidence
    case_link_decision: ReviewDecision
    reviewer_id: str | None = None
    reviewed_at_iso: str | None = None


def _complete_review(*, decision: ReviewDecision, reviewer: str | None, when: str | None) -> bool:
    return (
        decision == ReviewDecision.VERIFIED
        and bool(reviewer and reviewer.strip())
        and bool(when and when.strip())
    )


def has_verified_site_coverage(
    evidence: CoveredSiteEvidence,
    *,
    certificate_version_id: str,
    site_id: str,
) -> bool:
    """Return True only for exact, traceable, explicitly reviewed version/site scope."""
    return (
        evidence.certificate_version_id == certificate_version_id
        and evidence.site_id == site_id
        and _complete_review(
            decision=evidence.decision,
            reviewer=evidence.reviewer_id,
            when=evidence.reviewed_at_iso,
        )
        and len(evidence.source_snapshot_sha256) == 64
        and len(evidence.source_document_sha256) == 64
        and all(ch in "0123456789abcdefABCDEF" for ch in evidence.source_snapshot_sha256)
        and all(ch in "0123456789abcdefABCDEF" for ch in evidence.source_document_sha256)
        and bool(evidence.source_page_reference.strip())
        and bool(evidence.rationale and evidence.rationale.strip())
    )


def has_verified_case_link(
    evidence: LinkedCaseEvidence,
    *,
    certificate_version_id: str,
    case_id: str,
    site_id: str,
    gxp_type: str,
) -> bool:
    """Coverage alone never authorizes a cross-site Inspection Case link."""
    return (
        evidence.certificate_version_id == certificate_version_id
        and evidence.case_id == case_id
        and evidence.site_id == site_id
        and evidence.gxp_type == gxp_type
        and gxp_type == "GMP"
        and _complete_review(
            decision=evidence.case_link_decision,
            reviewer=evidence.reviewer_id,
            when=evidence.reviewed_at_iso,
        )
        and has_verified_site_coverage(
            evidence.coverage,
            certificate_version_id=certificate_version_id,
            site_id=site_id,
        )
    )
