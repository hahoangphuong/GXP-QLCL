"""Adversarial source-only multi-Site evidence proposals: never approve DB writes."""
from __future__ import annotations

from copy import deepcopy

import pytest

from backend.app.domain.certificate_site_coverage_readiness import (
    audit_site_coverage_proposal,
)

PROOF = "a" * 64
SCOPE = "b" * 64


def _case_site(site_id: str):
    return {
        "case_id": "case-1",
        "site_id": site_id,
        "source_document_sha256": PROOF,
        "source_locator": "inspection-annex:page-2",
        "evaluated_scope_sha256": SCOPE,
    }


def _certificate_site(site_id: str, *, address: str):
    return {
        "certificate_version_id": "version-1",
        "site_id": site_id,
        "source_document_sha256": PROOF,
        "source_locator": "certificate-annex:page-1",
        "site_address_at_issuance": address,
        "certified_scope_fragment_sha256": SCOPE,
        "scope_fragment_locator": "certificate-annex:page-2/site-section",
    }


def _fixture():
    return {
        "case": {"id": "case-1", "site_id": "site-b", "gxp_type": "GMP"},
        "certificate": {
            "id": "certificate-1", "case_id": "case-1",
            "site_id": "site-a", "certificate_type": "GMP",
        },
        "certificate_version": {"id": "version-1", "certificate_id": "certificate-1"},
        "case_sites": [_case_site("site-a"), _case_site("site-b")],
        "version_sites": [
            _certificate_site("site-a", address="Old address at grant"),
            _certificate_site("site-b", address="Other independent facility address"),
        ],
    }


def _run(fixture):
    return audit_site_coverage_proposal(**fixture)


def test_two_distinct_sites_with_different_case_and_certificate_anchors_are_reviewable_not_approved():
    fixture = _fixture()
    before = deepcopy(fixture)
    result = _run(fixture)
    assert fixture == before
    assert result["shape_status"] == "COMPLETE_FOR_DOMAIN_OWNER_REVIEW"
    assert result["unresolved_evidence_codes"] == []
    assert result["case_site_count"] == 2
    assert result["certificate_version_site_count"] == 2
    for field in (
        "source_document_authenticity_verified", "physical_site_identity_verified",
        "site_scope_allocation_approved", "case_rebinding_authorized",
        "runtime_validator_change_authorized", "database_mutated",
    ):
        assert result[field] is False
    assert "Old address at grant" not in str(result)


def test_single_site_evidence_is_also_reviewable_not_automatically_legalized():
    fixture = _fixture()
    fixture["case"]["site_id"] = "site-a"
    fixture["case_sites"] = fixture["case_sites"][:1]
    fixture["version_sites"] = fixture["version_sites"][:1]
    assert _run(fixture)["shape_status"] == "COMPLETE_FOR_DOMAIN_OWNER_REVIEW"


@pytest.mark.parametrize(("field", "value", "error"), [
    ("case_id", "unrelated-case", "ORIGINATING_CASE_MISMATCH"),
    ("site_id", "not-certified", "CERTIFICATE_ANCHOR_SITE_NOT_EVIDENCED"),
    ("certificate_type", "GLP", "GXP_TYPE_MISMATCH"),
])
def test_mismatched_certificate_context_fails_closed(field, value, error):
    fixture = _fixture()
    fixture["certificate"][field] = value
    assert error in _run(fixture)["unresolved_evidence_codes"]


def test_version_identity_must_match_certificate_and_coverage_rows():
    fixture = _fixture()
    fixture["certificate_version"]["certificate_id"] = "unrelated"
    fixture["version_sites"][1]["certificate_version_id"] = "other-version"
    errors = _run(fixture)["unresolved_evidence_codes"]
    assert "VERSION_CERTIFICATE_MISMATCH" in errors
    assert "VERSION_SITE_OWNER_MISMATCH" in errors


@pytest.mark.parametrize(("collection", "error"), [
    ("case_sites", "CASE_SITE_EVIDENCE_MISSING"),
    ("version_sites", "VERSION_SITE_EVIDENCE_MISSING"),
])
def test_absent_source_coverage_is_not_inferred_from_shared_company(collection, error):
    fixture = _fixture()
    fixture[collection] = []
    result = _run(fixture)
    assert result["shape_status"] == "BLOCKED_INCOMPLETE_SOURCE_PROPOSAL"
    assert error in result["unresolved_evidence_codes"]


def test_unproven_additional_certified_site_is_not_treated_as_inspected():
    fixture = _fixture()
    fixture["case_sites"] = fixture["case_sites"][:1]
    fixture["case"]["site_id"] = "site-a"
    assert "CERTIFIED_SITE_NOT_EVIDENCED_IN_CASE" in _run(fixture)["unresolved_evidence_codes"]


@pytest.mark.parametrize(("collection", "error"), [
    ("case_sites", "DUPLICATE_CASE_SITE"),
    ("version_sites", "DUPLICATE_CERTIFICATE_VERSION_SITE"),
])
def test_duplicate_evidence_rows_are_not_silently_deduplicated(collection, error):
    fixture = _fixture()
    fixture[collection].append(deepcopy(fixture[collection][0]))
    assert error in _run(fixture)["unresolved_evidence_codes"]


@pytest.mark.parametrize(("collection", "key", "replacement", "error"), [
    ("case_sites", "source_document_sha256", "not-a-real-hash", "CASE_SITE_SOURCE_PROVENANCE_INCOMPLETE"),
    ("case_sites", "source_locator", " ", "CASE_SITE_SOURCE_PROVENANCE_INCOMPLETE"),
    ("case_sites", "evaluated_scope_sha256", "", "CASE_SITE_SCOPE_EVIDENCE_INCOMPLETE"),
    ("case_sites", "case_id", "wrong-owner", "CASE_SITE_OWNER_MISMATCH"),
    ("version_sites", "source_document_sha256", "0", "VERSION_SITE_SOURCE_PROVENANCE_INCOMPLETE"),
    ("version_sites", "source_locator", "", "VERSION_SITE_SOURCE_PROVENANCE_INCOMPLETE"),
    ("version_sites", "site_address_at_issuance", " ", "ISSUANCE_ADDRESS_EVIDENCE_MISSING"),
    ("version_sites", "certified_scope_fragment_sha256", None, "SITE_LOCAL_CERTIFIED_SCOPE_EVIDENCE_MISSING"),
    ("version_sites", "scope_fragment_locator", None, "SITE_LOCAL_CERTIFIED_SCOPE_EVIDENCE_MISSING"),
])
def test_missing_document_or_site_local_scope_evidence_blocks_review(collection, key, replacement, error):
    fixture = _fixture()
    fixture[collection][0][key] = replacement
    assert error in _run(fixture)["unresolved_evidence_codes"]


def test_address_change_is_preserved_as_version_source_evidence_not_normalized():
    first = _fixture()
    second = _fixture()
    second["certificate_version"]["id"] = "version-2"
    for row in second["version_sites"]:
        row["certificate_version_id"] = "version-2"
    second["version_sites"][0]["site_address_at_issuance"] = "Different address in later granted version"
    assert _run(first)["shape_status"] == "COMPLETE_FOR_DOMAIN_OWNER_REVIEW"
    assert _run(second)["shape_status"] == "COMPLETE_FOR_DOMAIN_OWNER_REVIEW"
    assert first["version_sites"][0]["site_address_at_issuance"] == "Old address at grant"
    assert second["version_sites"][0]["site_address_at_issuance"] != first["version_sites"][0]["site_address_at_issuance"]


def test_no_evidence_shape_can_authorize_data_or_runtime_mutation():
    for fixture in (_fixture(), {"case": {}, "certificate": {}, "certificate_version": {},
                                 "case_sites": [], "version_sites": []}):
        result = _run(fixture)
        assert result["runtime_validator_change_authorized"] is False
        assert result["case_rebinding_authorized"] is False
        assert result["database_mutated"] is False
