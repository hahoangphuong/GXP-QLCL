"""Case-owned QĐKT source bundle, without rendering or storage writes.

Joins existing conservative owner gates in one read-only preflight. It does
not claim modern team rows reproduce legacy formatted TTVdd strings.
"""
from __future__ import annotations

from dataclasses import dataclass

from backend.app.document.inspection_qd_kt_decision_source import (
    QdKtDecisionAtoms, read_latest_qdkt_reference_for_case,
)
from backend.app.document.inspection_qd_kt_registered_site import (
    QdKtRegisteredSite, read_qdkt_registered_site,
)
from backend.app.document.inspection_qd_kt_team_source import (
    QdKtTeamSource, read_qdkt_team_source,
)


class QdKtCaseSourceBlocked(ValueError):
    pass


@dataclass(frozen=True)
class QdKtCaseSourceBundle:
    case_id: str
    decision: QdKtDecisionAtoms
    site: QdKtRegisteredSite
    team: QdKtTeamSource
    team_display_equivalence_verified: bool = False
    location_render_format_verified: bool = False
    ready_to_render: bool = False


def require_qdkt_case_source_bundle(
    *, case_id: str, decision: QdKtDecisionAtoms,
    site: QdKtRegisteredSite, team: QdKtTeamSource,
) -> QdKtCaseSourceBundle:
    """Reject cross-Case atoms before even considering document generation."""
    if not isinstance(case_id, str) or not case_id.strip():
        raise QdKtCaseSourceBlocked("CASE_ID_MISSING")
    if site.case_id != case_id or team.case_id != case_id:
        raise QdKtCaseSourceBlocked("QDKT_CASE_SOURCE_IDENTITY_MISMATCH")
    if not decision.source_decision_id or not site.site_id or not team.team_id:
        raise QdKtCaseSourceBlocked("QDKT_SOURCE_IDENTITY_MISSING")
    if not team.members or team.bookmark_mapping_verified:
        # A true flag in an unreviewed source cannot authorize rendering.
        raise QdKtCaseSourceBlocked("QDKT_TEAM_CONTRACT_UNSUPPORTED")
    return QdKtCaseSourceBundle(
        case_id=case_id, decision=decision, site=site, team=team,
    )


def read_qdkt_case_source_bundle(session, *, case_id: str) -> QdKtCaseSourceBundle:
    """Read related Case source atoms under a single no-autoflush boundary."""
    with session.no_autoflush:
        decision = read_latest_qdkt_reference_for_case(session, case_id=case_id)
        site = read_qdkt_registered_site(session, case_id=case_id)
        team = read_qdkt_team_source(session, case_id=case_id)
    return require_qdkt_case_source_bundle(
        case_id=case_id, decision=decision, site=site, team=team,
    )
