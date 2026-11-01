"""Read-only boundary for a reviewed GMP coverage evidence bundle (Issue #6).

No database writes and no change to existing Case/Certificate validation.
All rows are independently bound to exact certificate-version, Site and Case.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from backend.app.services.gmp_coverage_evidence import (
    CoveredSiteEvidence,
    LinkedCaseEvidence,
    ReviewDecision,
    has_verified_case_link,
    has_verified_site_coverage,
)


@dataclass(frozen=True)
class ReviewedCoverageBundle:
    certificate_version_id: str
    coverage: tuple[CoveredSiteEvidence, ...]
    links: tuple[LinkedCaseEvidence, ...]


@dataclass(frozen=True)
class CoverageEvaluation:
    verified_site_ids: frozenset[str]
    verified_case_ids: frozenset[str]
    rejected_site_ids: frozenset[str]
    rejected_case_ids: frozenset[str]


def _valid_review_datetime(value: str | None) -> bool:
    if not value:
        return False
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def evaluate_reviewed_bundle(bundle: ReviewedCoverageBundle) -> CoverageEvaluation:
    """Fail closed for ambiguous/duplicated evidence; no 'latest wins' policy.

    The bundle is a review artifact, NOT authority to change runtime certificate
    links. Reject conflicting or duplicate identities instead of choosing a row.
    """
    coverage_by_site: dict[str, CoveredSiteEvidence] = {}
    links_by_case: dict[str, LinkedCaseEvidence] = {}
    for row in bundle.coverage:
        if row.site_id in coverage_by_site:
            raise ValueError("Duplicate coverage evidence for Site.")
        coverage_by_site[row.site_id] = row
    for row in bundle.links:
        if row.case_id in links_by_case:
            raise ValueError("Duplicate linked Case evidence.")
        links_by_case[row.case_id] = row

    verified_sites: set[str] = set()
    rejected_sites: set[str] = set()
    for site_id, row in coverage_by_site.items():
        verified = (
            _valid_review_datetime(row.reviewed_at_iso)
            and has_verified_site_coverage(
                row, certificate_version_id=bundle.certificate_version_id, site_id=site_id
            )
        )
        (verified_sites if verified else rejected_sites).add(site_id)

    verified_cases: set[str] = set()
    rejected_cases: set[str] = set()
    for case_id, row in links_by_case.items():
        # The nested evidence must be the *exact* independently reviewed row
        # present in this version's bundle. No unbundled asserted coverage.
        site_coverage = coverage_by_site.get(row.site_id)
        verified = (
            site_coverage is not None
            and site_coverage == row.coverage
            and row.site_id in verified_sites
            and _valid_review_datetime(row.reviewed_at_iso)
            and has_verified_case_link(
                row,
                certificate_version_id=bundle.certificate_version_id,
                case_id=case_id,
                site_id=row.site_id,
                gxp_type="GMP",
            )
        )
        (verified_cases if verified else rejected_cases).add(case_id)

    return CoverageEvaluation(
        verified_site_ids=frozenset(verified_sites),
        verified_case_ids=frozenset(verified_cases),
        rejected_site_ids=frozenset(rejected_sites),
        rejected_case_ids=frozenset(rejected_cases),
    )
