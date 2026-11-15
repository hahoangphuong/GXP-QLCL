"""Narrowly witnessed legacy Certificate→Case read quarantine.

This is NOT an issuance exception, Case rebinding, or a permission to hide
unknown corrupt links. Only the exact source identities approved for historical
investigation may be excluded from facility search/current summary projections.
The source records and certificate detail remain unchanged and fail closed.
"""
from __future__ import annotations

from backend.app.db.models.phase1 import Case, Certificate, Site

# Source-origin anchors from the independently audited db.cc/db.ktra/db.cso
# legacy snapshot and the rehearsal read-only certificate witness. These
# identities are never used to repair a Certificate, Case, or Site.
_HISTORICAL_CROSS_SITE_SOURCE_ANCHORS: frozenset[tuple[int, int, int]] = frozenset({
    (376, 378, 73),
    (1037, 1023, 46),
    (1180, 1023, 46),
})


def is_witnessed_historical_search_quarantine(
    certificate: Certificate,
    linked_case: Case | None,
    certificate_site: Site | None,
) -> bool:
    """True only for an exact witnessed cross-Site GMP legacy source pair.

    An unknown mismatch, missing Case, wrong GxP, changed source identity,
    or newly issued certificate must still cause the existing HTTP 409.
    """
    return (
        linked_case is not None
        and certificate_site is not None
        and certificate.legacy_certificate_id is not None
        and linked_case.legacy_inspection_id is not None
        and certificate_site.legacy_site_id is not None
        and (
            certificate.legacy_certificate_id,
            linked_case.legacy_inspection_id,
            certificate_site.legacy_site_id,
        ) in _HISTORICAL_CROSS_SITE_SOURCE_ANCHORS
        and certificate.certificate_type == "GMP"
        and linked_case.gxp_type == "GMP"
        and certificate.issuance_basis == "inspection_case"
        and linked_case.site_id != certificate.site_id
        and certificate.case_id == linked_case.id
        and certificate.site_id == certificate_site.id
    )
