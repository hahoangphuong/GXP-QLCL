"""Two independent QĐKT processes with an explicit team handoff boundary.

A planning-stage draft and an issued decision are distinct records/events.
This contract never persists data or treats draft membership as approved.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


class QdKtHandoffBlocked(ValueError):
    pass


@dataclass(frozen=True)
class DraftTeamHandoff:
    case_id: str
    draft_id: str
    team_id: str
    member_ids: tuple[str, ...]
    team_revision: int


@dataclass(frozen=True)
class IssuanceTeamSelection:
    case_id: str
    draft_id: str
    team_id: str
    member_ids: tuple[str, ...]
    team_revision: int
    decision_reference: str
    issued_on: date
    user_confirmed_team: bool
    source: str = "DRAFT_TEAM_CONFIRMED"


def require_confirmed_issuance_team(
    *, draft: DraftTeamHandoff, selection: IssuanceTeamSelection,
) -> IssuanceTeamSelection:
    """Validate user confirmation and the exact draft version at issuance.

    Team revision must match the reviewed draft, and the user must explicitly
    confirm the roster. Any post-draft change requires review; never silently
    backfill approved decisions from KHKT or reuse an unrelated Case's team.
    """
    if (not isinstance(draft, DraftTeamHandoff)
            or not isinstance(selection, IssuanceTeamSelection)):
        raise QdKtHandoffBlocked("QDKT_HANDOFF_TYPE_INVALID")
    if (not draft.case_id or not draft.draft_id or not draft.team_id
            or not selection.case_id or not selection.draft_id or not selection.team_id
            or (draft.case_id, draft.draft_id, draft.team_id) !=
               (selection.case_id, selection.draft_id, selection.team_id)):
        raise QdKtHandoffBlocked("QDKT_HANDOFF_IDENTITY_MISMATCH")
    if (type(draft.team_revision) is not int or draft.team_revision < 1
            or type(selection.team_revision) is not int
            or selection.team_revision != draft.team_revision):
        raise QdKtHandoffBlocked("QDKT_TEAM_REVISION_CHANGED")
    if (not draft.member_ids or any(not isinstance(m, str) or not m.strip() for m in draft.member_ids)
            or len(set(draft.member_ids)) != len(draft.member_ids)
            or selection.member_ids != draft.member_ids):
        raise QdKtHandoffBlocked("QDKT_TEAM_MEMBERS_CHANGED")
    if selection.user_confirmed_team is not True:
        raise QdKtHandoffBlocked("QDKT_TEAM_CONFIRMATION_REQUIRED")
    if (not isinstance(selection.decision_reference, str)
            or not selection.decision_reference.strip()
            or selection.decision_reference != selection.decision_reference.strip()
            or not isinstance(selection.issued_on, date)
            or isinstance(selection.issued_on, datetime)):
        raise QdKtHandoffBlocked("QDKT_ISSUANCE_METADATA_MISSING")
    if selection.source != "DRAFT_TEAM_CONFIRMED":
        raise QdKtHandoffBlocked("QDKT_TEAM_SOURCE_INVALID")
    return selection
