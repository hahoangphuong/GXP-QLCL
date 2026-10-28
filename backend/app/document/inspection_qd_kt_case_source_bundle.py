"""Case-owned QĐKT source bundle, without rendering or storage writes.

Joins existing conservative owner gates in one read-only preflight. It does
not claim modern team rows reproduce legacy formatted TTVdd strings.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from backend.app.document.inspection_qd_kt_decision_source import (
    QdKtDecisionAtoms, read_latest_qdkt_reference_for_case,
)
from backend.app.document.inspection_qd_kt_registered_site import (
    QdKtRegisteredSite, read_qdkt_registered_site,
    QdKtRegisteredSiteBlocked, require_registered_site_address,
)
from backend.app.document.inspection_qd_kt_team_source import (
    QdKtTeamSource, read_qdkt_team_source,
    QdKtTeamSourceBlocked, require_qdkt_team_source,
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

    def __post_init__(self):
        if self.ready_to_render is not False:
            raise QdKtCaseSourceBlocked("QDKT_RENDER_ACTIVATION_FORBIDDEN")


def require_qdkt_case_source_bundle(
    *, case_id: str, decision: QdKtDecisionAtoms,
    site: QdKtRegisteredSite, team: QdKtTeamSource,
) -> QdKtCaseSourceBundle:
    """Reject cross-Case atoms before even considering document generation."""
    if type(case_id) is not str or not case_id.strip() or case_id != case_id.strip():
        raise QdKtCaseSourceBlocked("CASE_ID_MISSING")
    if type(decision) is not QdKtDecisionAtoms or type(site) is not QdKtRegisteredSite or type(team) is not QdKtTeamSource:
        raise QdKtCaseSourceBlocked("QDKT_CASE_SOURCE_TYPE_INVALID")
    if any(type(scope) is not str for scope in (site.case_id, team.case_id, decision.case_id)):
        raise QdKtCaseSourceBlocked("QDKT_CASE_SOURCE_IDENTITY_MISMATCH")
    if site.case_id != case_id or team.case_id != case_id or decision.case_id != case_id:
        raise QdKtCaseSourceBlocked("QDKT_CASE_SOURCE_IDENTITY_MISMATCH")
    if type(decision.inspection_plan_id) is not str or not decision.inspection_plan_id.strip():
        raise QdKtCaseSourceBlocked("QDKT_DECISION_PLAN_OWNERSHIP_MISSING")
    if any(type(identity) is not str or not identity.strip() for identity in (decision.source_decision_id, site.site_id, team.team_id)):
        raise QdKtCaseSourceBlocked("QDKT_SOURCE_IDENTITY_MISSING")
    # These objects are assembled from separate owner gates. Validate their
    # value contracts again: synthetic or stale caller-supplied dataclasses
    # must not bypass the Case-owned source invariants.
    if (
        type(decision.source_decision_id) is not str
        or not decision.source_decision_id.strip()
        or type(decision.reference) is not str
        or not decision.reference.strip()
        or decision.reference != decision.reference.strip()
        or type(decision.decision_on) is not date
        or type(decision.legacy_raw) is not str
        or not decision.legacy_raw.strip()
    ):
        raise QdKtCaseSourceBlocked("QDKT_DECISION_SOURCE_INCOMPLETE")
    try:
        require_registered_site_address(
            case_id=site.case_id, site_id=site.site_id,
            address=site.registered_address, province_name=site.province_name,
        )
    except QdKtRegisteredSiteBlocked as exc:
        raise QdKtCaseSourceBlocked(str(exc)) from exc
    try:
        require_qdkt_team_source(
            case_id=team.case_id, team_id=team.team_id, members=team.members,
        )
    except QdKtTeamSourceBlocked as exc:
        raise QdKtCaseSourceBlocked(str(exc)) from exc
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


@dataclass(frozen=True)
class QdKtPreapprovalCaseSource:
    """Process A only: registered Site and proposed team, never an issued decision."""
    case_id: str
    site: QdKtRegisteredSite
    proposed_team: QdKtTeamSource
    process: str = "DRAFT_QDKT"
    # No issued reference/date belongs in this contract.
    ready_to_render: bool = False

    def __post_init__(self):
        if type(self.process) is not str or self.process != "DRAFT_QDKT":
            raise QdKtCaseSourceBlocked("QDKT_DRAFT_PROCESS_INVALID")
        if self.ready_to_render is not False:
            raise QdKtCaseSourceBlocked("QDKT_RENDER_ACTIVATION_FORBIDDEN")


def require_qdkt_preapproval_case_source(
    *, case_id: str, site: QdKtRegisteredSite, proposed_team: QdKtTeamSource,
) -> QdKtPreapprovalCaseSource:
    """Validate the two independent Case-owned atoms for a *draft*.

    This does not assert KHKT-to-legacy dossier-row identity or permit Word
    generation. An issued-decision source is intentionally not accepted.
    """
    if not isinstance(case_id, str) or not case_id.strip() or case_id != case_id.strip():
        raise QdKtCaseSourceBlocked("QDKT_DRAFT_CASE_ID_INVALID")
    if not isinstance(site, QdKtRegisteredSite) or not isinstance(proposed_team, QdKtTeamSource):
        raise QdKtCaseSourceBlocked("QDKT_DRAFT_SOURCE_TYPE_INVALID")
    if site.case_id != case_id or proposed_team.case_id != case_id:
        raise QdKtCaseSourceBlocked("QDKT_DRAFT_CASE_SOURCE_MISMATCH")
    try:
        require_registered_site_address(
            case_id=site.case_id, site_id=site.site_id,
            address=site.registered_address, province_name=site.province_name,
        )
        checked_team = require_qdkt_team_source(
            case_id=proposed_team.case_id, team_id=proposed_team.team_id,
            members=proposed_team.members,
        )
    except (QdKtRegisteredSiteBlocked, QdKtTeamSourceBlocked) as exc:
        raise QdKtCaseSourceBlocked(str(exc)) from exc
    if proposed_team.bookmark_mapping_verified:
        raise QdKtCaseSourceBlocked("QDKT_DRAFT_BOOKMARK_EQUIVALENCE_UNPROVEN")
    return QdKtPreapprovalCaseSource(case_id=case_id, site=site, proposed_team=checked_team)


def read_qdkt_preapproval_case_source(session, *, case_id: str) -> QdKtPreapprovalCaseSource:
    """Read Site and proposed team without querying any InspectionDecision.

    Process B uses read_qdkt_case_source_bundle separately. Nothing here
    creates or infers an issued decision or a renderer permission.
    """
    with session.no_autoflush:
        site = read_qdkt_registered_site(session, case_id=case_id)
        proposed_team = read_qdkt_team_source(session, case_id=case_id)
    return require_qdkt_preapproval_case_source(
        case_id=case_id, site=site, proposed_team=proposed_team,
    )
