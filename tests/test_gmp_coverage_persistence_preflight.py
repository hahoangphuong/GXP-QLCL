"""Deterministic preflight, not a persisted GMP site adjudication."""
from dataclasses import replace

import pytest

from backend.app.services.gmp_coverage_evidence import CoveredSiteEvidence, LinkedCaseEvidence, ReviewDecision
from backend.app.services.gmp_coverage_bundle import ReviewedCoverageBundle
from backend.app.services.gmp_coverage_persistence_preflight import prepare_coverage_persistence


def evidence():
    site = CoveredSiteEvidence(
        certificate_version_id="version-a", site_id="site-b",
        source_snapshot_sha256="a" * 64, source_document_sha256="b" * 64,
        source_page_reference="p2", decision=ReviewDecision.VERIFIED,
        reviewer_id="reviewer-1", reviewed_at_iso="2026-11-01T09:00:00+07:00",
        rationale="Source verified",
    )
    link = LinkedCaseEvidence(
        certificate_version_id="version-a", case_id="case-1", site_id="site-b",
        gxp_type="GMP", coverage=site, case_link_decision=ReviewDecision.VERIFIED,
        reviewer_id="reviewer-2", reviewed_at_iso="2026-11-01T10:00:00+07:00",
    )
    return ReviewedCoverageBundle("version-a", (site,), (link,))


def test_preflight_stable_digest_and_counts():
    bundle = evidence()
    a = prepare_coverage_persistence(bundle)
    b = prepare_coverage_persistence(bundle)
    assert a == b
    assert a.coverage_count == 1 and a.case_link_count == 1
    assert len(a.canonical_payload_sha256) == 64
    assert a.certificate_version_id == "version-a"


@pytest.mark.parametrize("change", [
    lambda b: replace(b, coverage=()),
    lambda b: replace(b, links=()),
    lambda b: replace(b, certificate_version_id=""),
    lambda b: replace(b, coverage=(replace(b.coverage[0], decision=ReviewDecision.UNRESOLVED),)),
    lambda b: replace(b, links=(replace(b.links[0], case_link_decision=ReviewDecision.REJECTED),)),
    lambda b: replace(b, links=(replace(b.links[0], case_id="wrong"),), coverage=()),
    lambda b: replace(b, links=(replace(b.links[0], reviewed_at_iso="naive"),)),
])
def test_incomplete_bundle_cannot_prepare_persistence(change):
    with pytest.raises(ValueError):
        prepare_coverage_persistence(change(evidence()))


def test_different_reviewed_content_changes_digest():
    before = evidence()
    after_site = replace(before.coverage[0], rationale="Different reviewed provenance")
    after = replace(before, coverage=(after_site,), links=(replace(before.links[0], coverage=after_site),))
    assert prepare_coverage_persistence(before).canonical_payload_sha256 != prepare_coverage_persistence(after).canonical_payload_sha256
