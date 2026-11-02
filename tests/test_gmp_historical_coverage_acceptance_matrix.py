"""Issue #6 historical multi-site acceptance: shape is not adjudication.

Synthetic-only fixtures, no DB access or special-case legacy IDs. New GMP
issuance remains one Case, one Site and at most one Certificate per Case.
"""
from copy import deepcopy

import pytest

from backend.app.domain.certificate_site_coverage_readiness import (
    audit_site_coverage_proposal,
)


def proposal():
    case = {"id": "case-1", "site_id": "site-b", "gxp_type": "GMP"}
    certificate = {
        "id": "certificate-1", "case_id": "case-1",
        "site_id": "site-a", "certificate_type": "GMP",
    }
    version = {"id": "version-1", "certificate_id": "certificate-1"}
    case_sites = [
        {
            "case_id": "case-1", "site_id": site,
            "source_document_sha256": "a" * 64,
            "source_locator": f"inspection annex/{site}",
            "evaluated_scope_sha256": "b" * 64,
        }
        for site in ("site-a", "site-b")
    ]
    version_sites = [
        {
            "certificate_version_id": "version-1", "site_id": site,
            "source_document_sha256": "c" * 64,
            "source_locator": f"certificate annex/{site}",
            "site_address_at_issuance": f"Manufacturing address {site}",
            "certified_scope_fragment_sha256": "d" * 64,
            "scope_fragment_locator": f"certificate scope/{site}",
        }
        for site in ("site-a", "site-b")
    ]
    return [case, certificate, version, case_sites, version_sites]


def evaluate(rows):
    return audit_site_coverage_proposal(
        case=rows[0], certificate=rows[1],
        certificate_version=rows[2],
        case_sites=rows[3], version_sites=rows[4],
    )


def test_historical_cross_site_multi_site_proposal_is_only_ready_for_review():
    result = evaluate(proposal())
    assert result["shape_status"] == "COMPLETE_FOR_DOMAIN_OWNER_REVIEW"
    assert result["case_site_count"] == 2
    assert result["certificate_version_site_count"] == 2
    assert result["historical_exception_review_only"] is True
    assert result["prospective_multisite_gmp_issuance_allowed"] is False
    assert result["source_document_authenticity_verified"] is False
    assert result["physical_site_identity_verified"] is False
    assert result["site_scope_allocation_approved"] is False
    assert result["case_rebinding_authorized"] is False
    assert result["runtime_validator_change_authorized"] is False
    assert result["database_mutated"] is False


@pytest.mark.parametrize("mutation,code", [
    (lambda x: x[1].update(case_id="unrelated-case"), "ORIGINATING_CASE_MISMATCH"),
    (lambda x: x[2].update(certificate_id="different-cert"), "VERSION_CERTIFICATE_MISMATCH"),
    (lambda x: x[0].update(gxp_type="GDP"), "GXP_TYPE_MISMATCH"),
    (lambda x: x[3][0].update(case_id="other-case"), "CASE_SITE_OWNER_MISMATCH"),
    (lambda x: x[4][0].update(certificate_version_id="old-version"), "VERSION_SITE_OWNER_MISMATCH"),
    (lambda x: x[3][0].update(source_document_sha256="not-a-digest"), "CASE_SITE_SOURCE_PROVENANCE_INCOMPLETE"),
    (lambda x: x[4][0].update(source_locator=""), "VERSION_SITE_SOURCE_PROVENANCE_INCOMPLETE"),
    (lambda x: x[3][0].update(evaluated_scope_sha256="bad"), "CASE_SITE_SCOPE_EVIDENCE_INCOMPLETE"),
    (lambda x: x[4][0].update(site_address_at_issuance=" "), "ISSUANCE_ADDRESS_EVIDENCE_MISSING"),
    (lambda x: x[4][0].update(scope_fragment_locator=""), "SITE_LOCAL_CERTIFIED_SCOPE_EVIDENCE_MISSING"),
    (lambda x: x[3].append(deepcopy(x[3][0])), "DUPLICATE_CASE_SITE"),
    (lambda x: x[4].append(deepcopy(x[4][0])), "DUPLICATE_CERTIFICATE_VERSION_SITE"),
    (lambda x: x[3].pop(0), "CERTIFIED_SITE_NOT_EVIDENCED_IN_CASE"),
    (lambda x: x[4].pop(0), "CERTIFICATE_ANCHOR_SITE_NOT_EVIDENCED"),
    (lambda x: x[0].update(site_id="not-inspected"), "CASE_ANCHOR_SITE_NOT_EVIDENCED"),
    (lambda x: x[1].update(site_id="unproven-primary"), "CERTIFICATE_ANCHOR_SITE_NOT_EVIDENCED"),
])
def test_incomplete_or_contradictory_proposals_remain_blocked(mutation, code):
    values = proposal()
    mutation(values)
    result = evaluate(values)
    assert result["shape_status"] == "BLOCKED_INCOMPLETE_SOURCE_PROPOSAL"
    assert code in result["unresolved_evidence_codes"]
    assert result["case_rebinding_authorized"] is False
    assert result["database_mutated"] is False


def test_positive_only_site_coverage_without_inspection_evidence_is_not_ready():
    values = proposal()
    values[3] = [values[3][1]]
    result = evaluate(values)
    assert result["shape_status"] == "BLOCKED_INCOMPLETE_SOURCE_PROPOSAL"
    assert "CERTIFIED_SITE_NOT_EVIDENCED_IN_CASE" in result["unresolved_evidence_codes"]


def test_source_anchored_one_site_historical_proposal_is_not_forward_issuance_permission():
    values = proposal()
    values[0]["site_id"] = "site-a"
    values[3] = [values[3][0]]
    values[4] = [values[4][0]]
    result = evaluate(values)
    assert result["shape_status"] == "COMPLETE_FOR_DOMAIN_OWNER_REVIEW"
    assert result["prospective_multisite_gmp_issuance_allowed"] is False
    assert result["case_rebinding_authorized"] is False
