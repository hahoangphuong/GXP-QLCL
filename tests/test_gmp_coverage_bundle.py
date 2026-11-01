"""Issue #6: bundle cannot invent approvals by omission, duplication or nesting."""
from dataclasses import replace

import pytest

from backend.app.services.gmp_coverage_evidence import (
    CoveredSiteEvidence, LinkedCaseEvidence, ReviewDecision,
)
from backend.app.services.gmp_coverage_bundle import (
    ReviewedCoverageBundle, evaluate_reviewed_bundle,
)


def fixture():
    coverage = CoveredSiteEvidence(
        certificate_version_id="version-a",
        site_id="site-b",
        source_snapshot_sha256="a" * 64,
        source_document_sha256="b" * 64,
        source_page_reference="p2",
        decision=ReviewDecision.VERIFIED,
        reviewer_id="reviewer-1",
        reviewed_at_iso="2026-11-01T09:00:00+07:00",
        rationale="Source page reviewed",
    )
    link = LinkedCaseEvidence(
        certificate_version_id="version-a",
        case_id="case-1",
        site_id="site-b",
        gxp_type="GMP",
        coverage=coverage,
        case_link_decision=ReviewDecision.VERIFIED,
        reviewer_id="reviewer-2",
        reviewed_at_iso="2026-11-01T10:00:00+07:00",
    )
    return ReviewedCoverageBundle("version-a", (coverage,), (link,))


def test_complete_reviewed_bundle_has_two_distinct_approvals():
    result = evaluate_reviewed_bundle(fixture())
    assert result.verified_site_ids == frozenset({"site-b"})
    assert result.verified_case_ids == frozenset({"case-1"})
    assert not result.rejected_case_ids


@pytest.mark.parametrize("mutation", [
    lambda b: replace(b, certificate_version_id="version-new"),
    lambda b: replace(b, coverage=()),
    lambda b: replace(b, coverage=(replace(b.coverage[0], decision=ReviewDecision.UNRESOLVED),)),
    lambda b: replace(b, coverage=(replace(b.coverage[0], reviewed_at_iso="2026-11-01T09:00:00"),)),
    lambda b: replace(b, links=(replace(b.links[0], case_link_decision=ReviewDecision.UNRESOLVED),)),
    lambda b: replace(b, links=(replace(b.links[0], reviewed_at_iso="invalid"),)),
    lambda b: replace(b, links=(replace(b.links[0], site_id="other-site"),)),
    lambda b: replace(b, links=(replace(b.links[0], gxp_type="GLP"),)),
    lambda b: replace(b, links=(replace(b.links[0], coverage=replace(b.coverage[0], source_document_sha256="c"*64)),)),
])
def test_no_case_authorization_with_incomplete_or_mismatched_bundle(mutation):
    result = evaluate_reviewed_bundle(mutation(fixture()))
    assert "case-1" not in result.verified_case_ids
    assert result.rejected_case_ids == frozenset({"case-1"})


@pytest.mark.parametrize("attribute", ["coverage", "links"])
def test_duplicate_identity_is_rejected(attribute):
    base = fixture()
    item = getattr(base, attribute)[0]
    with pytest.raises(ValueError, match="Duplicate"):
        evaluate_reviewed_bundle(replace(base, **{attribute: (item, item)}))


def test_coverage_is_not_automatically_case_approval():
    base = fixture()
    result = evaluate_reviewed_bundle(replace(base, links=()))
    assert result.verified_site_ids == frozenset({"site-b"})
    assert result.verified_case_ids == frozenset()
