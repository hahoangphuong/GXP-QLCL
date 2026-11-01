"""Fail-closed preflight for eventual audited GMP coverage persistence.

This module does NOT persist anything. Callers must not mistake a validated
bundle for authorization to change Certificate/Case links or current flags.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json

from backend.app.services.gmp_coverage_bundle import (
    ReviewedCoverageBundle,
    evaluate_reviewed_bundle,
)


@dataclass(frozen=True)
class PersistencePreflight:
    certificate_version_id: str
    canonical_payload_sha256: str
    coverage_count: int
    case_link_count: int


def prepare_coverage_persistence(bundle: ReviewedCoverageBundle) -> PersistencePreflight:
    """Require *all* supplied decisions verified before preparing a stable digest.

    This is intentionally stricter than the read-only evaluator, which reports
    independently rejected identities. A partial review cannot be committed
    as though the full bundle had been accepted.
    """
    if not bundle.certificate_version_id.strip():
        raise ValueError("Certificate version identity is required.")
    if not bundle.coverage or not bundle.links:
        raise ValueError("Evidence coverage and Case link must both be present.")
    result = evaluate_reviewed_bundle(bundle)
    if result.rejected_site_ids or result.rejected_case_ids:
        raise ValueError("Unverified or mismatched evidence cannot be prepared.")
    if len(result.verified_site_ids) != len(bundle.coverage):
        raise ValueError("Not all covered Sites are verified.")
    if len(result.verified_case_ids) != len(bundle.links):
        raise ValueError("Not all linked Cases are verified.")
    payload = {
        "schema": "gmp-coverage-evidence-v1",
        "certificate_version_id": bundle.certificate_version_id,
        "coverage": [
            {
                "site_id": row.site_id,
                "source_snapshot_sha256": row.source_snapshot_sha256.lower(),
                "source_document_sha256": row.source_document_sha256.lower(),
                "source_page_reference": row.source_page_reference,
                "reviewer_id": row.reviewer_id,
                "reviewed_at_iso": row.reviewed_at_iso,
                "rationale": row.rationale,
                "decision": row.decision.value,
            }
            for row in sorted(bundle.coverage, key=lambda row: row.site_id)
        ],
        "links": [
            {
                "case_id": row.case_id,
                "site_id": row.site_id,
                "gxp_type": row.gxp_type,
                "reviewer_id": row.reviewer_id,
                "reviewed_at_iso": row.reviewed_at_iso,
                "decision": row.case_link_decision.value,
            }
            for row in sorted(bundle.links, key=lambda row: row.case_id)
        ],
    }
    serialized = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return PersistencePreflight(
        certificate_version_id=bundle.certificate_version_id,
        canonical_payload_sha256=sha256(serialized.encode("utf-8")).hexdigest(),
        coverage_count=len(bundle.coverage),
        case_link_count=len(bundle.links),
    )
