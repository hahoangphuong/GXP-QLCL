"""Current Case-owned inspection team projection for QĐKT preparation.

No historical draft ownership or issued-decision ownership is inferred from
Case team rows. No persistence and no document render authorization.
"""
from __future__ import annotations

from sqlalchemy import select

from backend.app.db.models.phase1 import InspectionTeam
from backend.app.document.inspection_qd_kt_team_source import (
    QdKtTeamSourceBlocked, read_qdkt_team_source,
)


def read_qdkt_current_case_team(session, *, case_id: str) -> dict:
    source = read_qdkt_team_source(session, case_id=case_id)
    with session.no_autoflush:
        team = session.scalar(
            select(InspectionTeam).where(
                InspectionTeam.id == source.team_id,
                InspectionTeam.case_id == source.case_id,
            )
        )
    if team is None or type(team.row_version) is not int or team.row_version < 1:
        raise QdKtTeamSourceBlocked("CASE_TEAM_VERSION_UNPROVEN")
    return {
        "case_id": source.case_id,
        "team_id": source.team_id,
        "team_revision": team.row_version,
        "source_kind": "CURRENT_CASE_TEAM",
        "draft_snapshot_available": False,
        "issued_team_confirmed": False,
        "members": [
            {
                "member_id": member.id,
                "sort_order": member.sort_order,
                "role_code": member.role_code,
                "display_name": member.display_name,
                "identity_kind": member.identity_kind,
                "inspector_profile_id": member.inspector_profile_id,
                "person_id": member.person_id,
                "participant_catalog_id": member.participant_catalog_id,
            }
            for member in source.members
        ],
    }
