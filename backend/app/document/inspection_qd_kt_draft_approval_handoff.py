"""Independent QĐKT draft and approved-decision handoff contracts.

Legacy workflow: planning inputs produce a DOCX *draft*. Later the user records
the issued reference, issue date, and approved inspection team. Reuse of draft
team is a proposed convenience only, not implicit approval or Case creation.
No persistence, renderer, planning-sheet lookup, or approval action here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable

from backend.app.document.inspection_qd_kt_team_source import QdKtTeamMemberSource


class QdKtHandoffBlocked(ValueError):
    pass


@dataclass(frozen=True)
class QdKtDraftTeamProposal:
    case_id: str
    draft_id: str
    members: tuple[QdKtTeamMemberSource, ...]
    approved: bool = False


@dataclass(frozen=True)
class QdKtApprovedDecisionInput:
    case_id: str
    draft_id: str | None
    decision_reference: str
    decision_on: date
    members: tuple[QdKtTeamMemberSource, ...]
    team_source: str
    user_confirmed: bool


def propose_qdkt_draft_team(*, case_id: str, draft_id: str,
                            members: Iterable[QdKtTeamMemberSource]) -> QdKtDraftTeamProposal:
    """Bind proposed members to a draft, never an issued decision."""
    from backend.app.document.inspection_qd_kt_team_source import require_qdkt_team_source
    if not isinstance(draft_id, str) or not draft_id.strip():
        raise QdKtHandoffBlocked("DRAFT_ID_MISSING")
    team = require_qdkt_team_source(
        case_id=case_id, team_id=draft_id, members=members,
    )
    return QdKtDraftTeamProposal(case_id=case_id, draft_id=draft_id, members=team.members)


def validate_approved_qdkt_input(
    *, case_id: str, decision_reference: str, decision_on: date,
    approved_members: Iterable[QdKtTeamMemberSource],
    user_confirmed: bool, draft: QdKtDraftTeamProposal | None = None,
    reuse_draft_team: bool = False,
) -> QdKtApprovedDecisionInput:
    """Require explicit approved decision data even when reusing draft members.

    A saved draft cannot silently become an issued decision. When reuse is
    requested, the caller must present the exact proposed ordered identities,
    in addition to explicit user confirmation of the issued decision.
    """
    from backend.app.document.inspection_qd_kt_team_source import require_qdkt_team_source
    if not isinstance(case_id, str) or not case_id.strip():
        raise QdKtHandoffBlocked("CASE_ID_MISSING")
    if not isinstance(decision_reference, str) or not decision_reference.strip() or decision_reference != decision_reference.strip():
        raise QdKtHandoffBlocked("DECISION_REFERENCE_REQUIRED")
    if not isinstance(decision_on, date) or isinstance(decision_on, datetime):
        raise QdKtHandoffBlocked("DECISION_DATE_REQUIRED")
    if user_confirmed is not True:
        raise QdKtHandoffBlocked("USER_APPROVAL_CONFIRMATION_REQUIRED")
    if reuse_draft_team and (
        draft is None or draft.case_id != case_id or not draft.draft_id
    ):
        raise QdKtHandoffBlocked("DRAFT_TEAM_CASE_MISMATCH")
    approved = require_qdkt_team_source(
        case_id=case_id, team_id=(draft.draft_id if reuse_draft_team else "user-entered-approved-team"),
        members=approved_members,
    )
    if reuse_draft_team and approved.members != draft.members:
        raise QdKtHandoffBlocked("DRAFT_TEAM_CHANGED_REQUIRES_EXPLICIT_ENTRY")
    return QdKtApprovedDecisionInput(
        case_id=case_id, draft_id=draft.draft_id if reuse_draft_team else None,
        decision_reference=decision_reference, decision_on=decision_on,
        members=approved.members,
        team_source="CONFIRMED_DRAFT_PROPOSAL" if reuse_draft_team else "USER_ENTERED",
        user_confirmed=True,
    )
