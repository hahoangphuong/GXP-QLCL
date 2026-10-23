"""Fail-closed source identity/ordering gate for QĐKT inspection teams.

This establishes trustworthy Case-owned source rows; it deliberately does NOT
claim that TT1x/TT2x/TT3x/TT3Del/TT_ext rendering is resolved.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


class QdKtTeamSourceBlocked(ValueError):
    """Team source cannot safely be used as evidence for document rendering."""


@dataclass(frozen=True)
class QdKtTeamMemberSource:
    id: str
    sort_order: int
    role_code: str | None
    display_name: str | None
    identity_kind: str | None
    inspector_profile_id: str | None
    person_id: str | None
    participant_catalog_id: str | None


@dataclass(frozen=True)
class QdKtTeamSource:
    case_id: str
    team_id: str
    members: tuple[QdKtTeamMemberSource, ...]
    bookmark_mapping_verified: bool = False


_ALLOWED_ROLES = frozenset({"LEADER", "SECRETARY", "MEMBER"})


def require_qdkt_team_source(*, case_id: str, team_id: str,
                             members: Iterable[QdKtTeamMemberSource]) -> QdKtTeamSource:
    if not case_id or not team_id:
        raise QdKtTeamSourceBlocked("CASE_TEAM_LINK_MISSING")
    ordered = tuple(members)
    if not ordered:
        raise QdKtTeamSourceBlocked("INSPECTION_TEAM_EMPTY")
    if len({row.id for row in ordered}) != len(ordered) or any(not row.id for row in ordered):
        raise QdKtTeamSourceBlocked("INSPECTION_TEAM_MEMBER_ID_AMBIGUOUS")
    positions = [row.sort_order for row in ordered]
    if any(type(pos) is not int or pos < 0 for pos in positions) or len(set(positions)) != len(positions):
        raise QdKtTeamSourceBlocked("INSPECTION_TEAM_ORDER_AMBIGUOUS")
    if sorted(positions) != positions:
        raise QdKtTeamSourceBlocked("INSPECTION_TEAM_ORDER_UNSORTED")
    for row in ordered:
        if row.role_code not in _ALLOWED_ROLES:
            raise QdKtTeamSourceBlocked("INSPECTION_TEAM_ROLE_UNPROVEN")
        if not isinstance(row.display_name, str) or not row.display_name.strip() or row.display_name != row.display_name.strip():
            raise QdKtTeamSourceBlocked("INSPECTION_TEAM_DISPLAY_NAME_UNPROVEN")
        sources = (row.inspector_profile_id, row.person_id, row.participant_catalog_id)
        if row.identity_kind == "INSPECTOR_PROFILE":
            valid = bool(sources[0]) and not any(sources[1:])
        elif row.identity_kind == "LEGACY_PERSON":
            # Imported legacy identities may be known only by verified display text.
            valid = not any(sources)
        elif row.identity_kind == "ORGANIZATION_REPRESENTATIVE":
            valid = bool(sources[2]) and not any(sources[:2])
        else:
            valid = False
        if not valid:
            raise QdKtTeamSourceBlocked("INSPECTION_TEAM_IDENTITY_UNPROVEN")
    return QdKtTeamSource(case_id=case_id, team_id=team_id, members=ordered)


def read_qdkt_team_source(session, *, case_id: str) -> QdKtTeamSource:
    """Read persisted Case-owned rows without flushing unrelated pending ORM changes."""
    from sqlalchemy import select
    from backend.app.db.models.phase1 import Case, InspectionTeam, InspectionTeamMember

    if not isinstance(case_id, str) or not case_id.strip():
        raise QdKtTeamSourceBlocked("CASE_ID_MISSING")
    with session.no_autoflush:
        if session.get(Case, case_id) is None:
            raise QdKtTeamSourceBlocked("CASE_NOT_FOUND")
        teams = session.scalars(
            select(InspectionTeam).where(InspectionTeam.case_id == case_id)
        ).all()
        if len(teams) != 1:
            raise QdKtTeamSourceBlocked("CASE_INSPECTION_TEAM_NOT_UNIQUE")
        team = teams[0]
        rows = session.scalars(
            select(InspectionTeamMember)
            .where(InspectionTeamMember.team_id == team.id)
            .order_by(InspectionTeamMember.sort_order, InspectionTeamMember.id)
        ).all()
    return require_qdkt_team_source(
        case_id=case_id, team_id=team.id,
        members=(
            QdKtTeamMemberSource(
                id=row.id, sort_order=row.sort_order, role_code=row.role_code,
                display_name=row.display_name, identity_kind=row.identity_kind,
                inspector_profile_id=row.inspector_profile_id, person_id=row.person_id,
                participant_catalog_id=row.participant_catalog_id,
            )
            for row in rows
        ),
    )
