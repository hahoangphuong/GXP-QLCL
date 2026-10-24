"""Read-only QĐKT Case readiness composed from already implemented owner gates.

This preflight is *not* a document creation endpoint and never authorizes a
renderer. Closed business contracts remain explicit hard blockers regardless of
whether individual source atoms are available. Case creation uses user-entered
facts or approved inheritance from an originating Case, never KHKT values.
KHKT lineage is not a renderer readiness gate.
"""
from __future__ import annotations

from dataclasses import dataclass
from sqlalchemy.orm import Session

from backend.app.document.inspection_qd_kt_decision_source import (
    QdKtDecisionSourceBlocked, read_latest_qdkt_reference_for_case,
)
from backend.app.document.inspection_qd_kt_legacy_province_band import classify_qdkt_legacy_province_zone
from backend.app.document.inspection_qd_kt_vkn_authority import QdKtAuthorityBlocked
from backend.app.document.inspection_qd_kt_registered_site import (
    QdKtRegisteredSiteBlocked, read_qdkt_registered_site,
)


_PENDING_CONTRACTS = (
    "MANUFACTURING_CLASSIFICATION_SOURCE_UNPROVEN",
    "LOCATION_BOOKMARK_FORMAT_UNPROVEN",
    "BLANK_ISSUANCE_DATE_BOOKMARK_UNVERIFIED",
    "INSPECTION_TEAM_BOOKMARK_CONTRACT_UNRESOLVED",
    "QDKT_TYPED_RENDER_CONTRACT_MISSING",
)


@dataclass(frozen=True)
class QdKtCaseReadiness:
    case_id: str
    decision_source_id: str | None
    registered_site_id: str | None
    ready_to_render: bool
    blockers: tuple[str, ...]


def inspect_qdkt_case_readiness(session: Session, *, case_id: str) -> QdKtCaseReadiness:
    """Return guarded readiness diagnostics without exposing source values.

    The reference gate only supports explicit replacement lineage. Unknown
    amendments cannot silently fall back to an older original decision.
    """
    blockers: list[str] = []
    decision_source_id: str | None = None
    registered_site_id: str | None = None
    try:
        decision = read_latest_qdkt_reference_for_case(session, case_id=case_id)
        decision_source_id = decision.source_decision_id
    except QdKtDecisionSourceBlocked as exc:
        blockers.append(str(exc))
    try:
        site = read_qdkt_registered_site(session, case_id=case_id)
        registered_site_id = site.site_id
        if not site.province_name:
            blockers.append("REGISTERED_PROVINCE_MISSING")
        else:
            # Check source province mapping without inferring manufacturing kind.
            try:
                classify_qdkt_legacy_province_zone(
                    registered_province=site.province_name,
                )
            except QdKtAuthorityBlocked as exc:
                blockers.append(str(exc))
    except QdKtRegisteredSiteBlocked as exc:
        blockers.append(str(exc))
    blockers.extend(_PENDING_CONTRACTS)
    return QdKtCaseReadiness(
        case_id=case_id,
        decision_source_id=decision_source_id,
        registered_site_id=registered_site_id,
        ready_to_render=False,
        blockers=tuple(dict.fromkeys(blockers)),
    )
