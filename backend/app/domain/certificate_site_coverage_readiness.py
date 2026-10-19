"""Read-only shape audit of HISTORICAL Case/CertificateVersion multi-site evidence.

A shape-complete proposal is NOT an adjudicated Site, scope, or Case link.
The business owner requires new GMP issuance to be strictly one Case, one Site,
and at most one Certificate per Case. This helper is for historical source
exceptions ONLY and is NOT an alternative forward GMP issuance pathway.
It does not alter the strict single-Site validator, SQL or database.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Any, Iterable, Mapping

_SHA256 = re.compile(r"^[a-fA-F0-9]{64}$")


def _has_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _valid_sha256(value: object) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


def audit_site_coverage_proposal(
    *,
    case: Mapping[str, Any],
    certificate: Mapping[str, Any],
    certificate_version: Mapping[str, Any],
    case_sites: Iterable[Mapping[str, Any]],
    version_sites: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Check only structural completeness of independently documented site rows.

    Required CaseSite proposal row:
      case_id, site_id, source_document_sha256, source_locator,
      evaluated_scope_sha256.
    Required CertificateVersionSite proposal row:
      certificate_version_id, site_id, source_document_sha256, source_locator,
      site_address_at_issuance, certified_scope_fragment_sha256,
      scope_fragment_locator.

    SHA-256 and locators are *claims*, not verified original documents. The
    function cannot authenticate source bytes, authorize coverage, or infer
    that a Site/address/ProductionLine represents the same physical identity.
    """
    errors: set[str] = set()
    case_id = case.get("id")
    certificate_id = certificate.get("id")
    version_id = certificate_version.get("id")
    case_anchor = case.get("site_id")
    certificate_anchor = certificate.get("site_id")
    case_gxp = case.get("gxp_type")
    certificate_gxp = certificate.get("certificate_type")
    if not all(_has_text(x) for x in (
        case_id, certificate_id, version_id, case_anchor, certificate_anchor,
        case_gxp, certificate_gxp,
    )):
        errors.add("CONTEXT_IDENTITY_INCOMPLETE")
    if not _has_text(certificate.get("case_id")) or certificate.get("case_id") != case_id:
        errors.add("ORIGINATING_CASE_MISMATCH")
    if not _has_text(certificate_version.get("certificate_id")) or certificate_version.get("certificate_id") != certificate_id:
        errors.add("VERSION_CERTIFICATE_MISMATCH")
    if not _has_text(case_gxp) or case_gxp != certificate_gxp:
        errors.add("GXP_TYPE_MISMATCH")

    proposed_case_sites = list(case_sites)
    proposed_cert_sites = list(version_sites)
    case_ids: list[str] = []
    certified_ids: list[str] = []
    if not proposed_case_sites:
        errors.add("CASE_SITE_EVIDENCE_MISSING")
    if not proposed_cert_sites:
        errors.add("VERSION_SITE_EVIDENCE_MISSING")

    for entry in proposed_case_sites:
        site_id = entry.get("site_id")
        if not _has_text(site_id):
            errors.add("CASE_SITE_ID_MISSING")
        else:
            case_ids.append(site_id)
        if entry.get("case_id") != case_id:
            errors.add("CASE_SITE_OWNER_MISMATCH")
        if not _valid_sha256(entry.get("source_document_sha256")) or not _has_text(entry.get("source_locator")):
            errors.add("CASE_SITE_SOURCE_PROVENANCE_INCOMPLETE")
        if not _valid_sha256(entry.get("evaluated_scope_sha256")):
            errors.add("CASE_SITE_SCOPE_EVIDENCE_INCOMPLETE")

    for entry in proposed_cert_sites:
        site_id = entry.get("site_id")
        if not _has_text(site_id):
            errors.add("CERTIFIED_SITE_ID_MISSING")
        else:
            certified_ids.append(site_id)
        if entry.get("certificate_version_id") != version_id:
            errors.add("VERSION_SITE_OWNER_MISMATCH")
        if not _valid_sha256(entry.get("source_document_sha256")) or not _has_text(entry.get("source_locator")):
            errors.add("VERSION_SITE_SOURCE_PROVENANCE_INCOMPLETE")
        if not _has_text(entry.get("site_address_at_issuance")):
            errors.add("ISSUANCE_ADDRESS_EVIDENCE_MISSING")
        if not _valid_sha256(entry.get("certified_scope_fragment_sha256")) or not _has_text(entry.get("scope_fragment_locator")):
            errors.add("SITE_LOCAL_CERTIFIED_SCOPE_EVIDENCE_MISSING")

    if any(count > 1 for count in Counter(case_ids).values()):
        errors.add("DUPLICATE_CASE_SITE")
    if any(count > 1 for count in Counter(certified_ids).values()):
        errors.add("DUPLICATE_CERTIFICATE_VERSION_SITE")
    if _has_text(case_anchor) and case_anchor not in case_ids:
        errors.add("CASE_ANCHOR_SITE_NOT_EVIDENCED")
    if _has_text(certificate_anchor) and certificate_anchor not in certified_ids:
        errors.add("CERTIFICATE_ANCHOR_SITE_NOT_EVIDENCED")
    if set(certified_ids) - set(case_ids):
        # This is a review gap, not a claim that certification of a site not
        # inspected in the same Case is universally invalid.
        errors.add("CERTIFIED_SITE_NOT_EVIDENCED_IN_CASE")

    return {
        "schema_version": "historical-case-certificate-version-site-coverage-shape/v1",
        "historical_exception_review_only": True,
        "prospective_multisite_gmp_issuance_allowed": False,
        "shape_status": (
            "COMPLETE_FOR_DOMAIN_OWNER_REVIEW" if not errors
            else "BLOCKED_INCOMPLETE_SOURCE_PROPOSAL"
        ),
        "unresolved_evidence_codes": sorted(errors),
        "case_site_count": len(proposed_case_sites),
        "certificate_version_site_count": len(proposed_cert_sites),
        "source_document_authenticity_verified": False,
        "physical_site_identity_verified": False,
        "site_scope_allocation_approved": False,
        "case_rebinding_authorized": False,
        "runtime_validator_change_authorized": False,
        "database_mutated": False,
    }
