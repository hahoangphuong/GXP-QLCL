"""Issue #6: approved scope and linked Case are independent evidence decisions."""
from dataclasses import replace

import pytest

from backend.app.services.gmp_coverage_evidence import (
    CoveredSiteEvidence,
    LinkedCaseEvidence,
    ReviewDecision,
    has_verified_case_link,
    has_verified_site_coverage,
)


def approved():
    scope = CoveredSiteEvidence(
        certificate_version_id="version-a",
        site_id="site-b",
        source_snapshot_sha256="a" * 64,
        source_document_sha256="b" * 64,
        source_page_reference="Certificate page 2, manufacturing sites",
        decision=ReviewDecision.VERIFIED,
        reviewer_id="reviewer-1",
        reviewed_at_iso="2026-11-01T09:00:00+07:00",
        rationale="Address/scope checked against issuance source",
    )
    link = LinkedCaseEvidence(
        certificate_version_id="version-a",
        case_id="case-1",
        site_id="site-b",
        gxp_type="GMP",
        coverage=scope,
        case_link_decision=ReviewDecision.VERIFIED,
        reviewer_id="reviewer-2",
        reviewed_at_iso="2026-11-01T10:00:00+07:00",
    )
    return scope, link


def test_version_scoped_coverage_and_separate_case_link_review():
    coverage, link = approved()
    assert has_verified_site_coverage(coverage, certificate_version_id="version-a", site_id="site-b")
    assert has_verified_case_link(link, certificate_version_id="version-a", case_id="case-1", site_id="site-b", gxp_type="GMP")
    assert not has_verified_case_link(
        replace(link, case_link_decision=ReviewDecision.UNRESOLVED),
        certificate_version_id="version-a", case_id="case-1", site_id="site-b", gxp_type="GMP",
    )


@pytest.mark.parametrize(
    "change",
    [
        {"decision": ReviewDecision.UNRESOLVED},
        {"decision": ReviewDecision.REJECTED},
        {"reviewer_id": None},
        {"reviewed_at_iso": None},
        {"source_snapshot_sha256": "a" * 63},
        {"source_document_sha256": "not-a-digest"},
        {"source_page_reference": " "},
        {"rationale": None},
        {"site_id": "site-other"},
        {"certificate_version_id": "version-obsolete"},
    ],
)
def test_missing_unreviewed_or_mismatched_coverage_fails_closed(change):
    scope, link = approved()
    changed = replace(scope, **change)
    assert not has_verified_site_coverage(changed, certificate_version_id="version-a", site_id="site-b")
    assert not has_verified_case_link(
        replace(link, coverage=changed),
        certificate_version_id="version-a", case_id="case-1", site_id="site-b", gxp_type="GMP",
    )


@pytest.mark.parametrize(
    "change",
    [
        {"case_id": "other-case"},
        {"site_id": "other-site"},
        {"certificate_version_id": "older-version"},
        {"gxp_type": "GLP"},
        {"reviewer_id": None},
        {"reviewed_at_iso": None},
        {"case_link_decision": ReviewDecision.REJECTED},
    ],
)
def test_case_link_requires_exact_identity_and_explicit_approval(change):
    _, link = approved()
    assert not has_verified_case_link(
        replace(link, **change),
        certificate_version_id="version-a", case_id="case-1", site_id="site-b", gxp_type="GMP",
    )
