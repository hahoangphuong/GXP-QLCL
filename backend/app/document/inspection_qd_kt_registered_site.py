"""Read the registered Site address for a QĐKT Case without rendering it.

Business owner confirmed inspection address is always the registered Site
address. This module deliberately does not derive Diadiem/Diadiemx formatting
or mutate a plan from the Site projection.
"""
from __future__ import annotations
from dataclasses import dataclass


class QdKtRegisteredSiteBlocked(ValueError):
    """Site identity or registered address cannot be established."""


@dataclass(frozen=True)
class QdKtRegisteredSite:
    case_id: str
    site_id: str
    registered_address: str
    province_name: str | None


def require_registered_site_address(*, case_id: str, site_id: str,
                                    address: str | None,
                                    province_name: str | None) -> QdKtRegisteredSite:
    if not case_id or not site_id:
        raise QdKtRegisteredSiteBlocked("CASE_SITE_LINK_MISSING")
    if not isinstance(address, str) or not address.strip():
        raise QdKtRegisteredSiteBlocked("REGISTERED_SITE_ADDRESS_MISSING")
    if address != address.strip():
        raise QdKtRegisteredSiteBlocked("REGISTERED_SITE_ADDRESS_UNNORMALIZED")
    return QdKtRegisteredSite(
        case_id=case_id, site_id=site_id, registered_address=address,
        province_name=province_name if province_name and province_name.strip() else None,
    )


def read_qdkt_registered_site(session, *, case_id: str) -> QdKtRegisteredSite:
    """Bind Case.site_id to Site primary key in one read-only ORM query."""
    from sqlalchemy import select
    from backend.app.db.models.phase1 import Case, Site
    if not isinstance(case_id, str) or not case_id.strip():
        raise QdKtRegisteredSiteBlocked("CASE_ID_MISSING")
    with session.no_autoflush:
        row = session.execute(
            select(Case.id, Case.site_id, Site.id, Site.site_address, Site.province_name)
            .join(Site, Case.site_id == Site.id)
            .where(Case.id == case_id)
        ).one_or_none()
    if row is None:
        raise QdKtRegisteredSiteBlocked("CASE_REGISTERED_SITE_NOT_FOUND")
    case_pk, linked_site_id, site_pk, address, province = row
    if linked_site_id != site_pk:
        raise QdKtRegisteredSiteBlocked("CASE_SITE_LINK_MISMATCH")
    return require_registered_site_address(
        case_id=case_pk, site_id=site_pk, address=address, province_name=province,
    )
