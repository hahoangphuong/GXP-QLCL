"""Explicit issuance team choice independent from the draft generation process.

Pure validation only: no DB writes, no legal-approval assertions, no document
renderer enablement. A draft may suggest a roster but never issues a decision.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from backend.app.document.inspection_qd_kt_team_handoff import (
    DraftTeamHandoff, QdKtHandoffBlocked,
)


@dataclass(frozen=True)
class IssuedTeamChoice:
    case_id: str
    decision_reference: str
    issued_on: date
    member_ids: tuple[str, ...]
    confirmed_by_user: bool
    roster_source: str  # DRAFT_UNCHANGED | DRAFT_EDITED | USER_ENTERED
    draft_id: str | None = None
    draft_team_id: str | None = None
    draft_team_revision: int | None = None
    acknowledged_changes: bool = False


def require_issued_team_choice(
    *, choice: IssuedTeamChoice, draft: DraftTeamHandoff | None = None,
) -> IssuedTeamChoice:
    """Validate provenance + explicit user approval of the *final* roster.

    Source choice is explicit. Draft-linked choices are pinned to the exact
    Case/draft/team revision. Edited drafts require an extra acknowledgement;
    entirely independent manual entry must not fake a draft association.
    """
    if not isinstance(choice, IssuedTeamChoice):
        raise QdKtHandoffBlocked("QDKT_ISSUANCE_CHOICE_TYPE_INVALID")
    if (not isinstance(choice.case_id, str) or not choice.case_id.strip()
            or choice.case_id != choice.case_id.strip()
            or not isinstance(choice.decision_reference, str)
            or not choice.decision_reference.strip()
            or choice.decision_reference != choice.decision_reference.strip()
            or not isinstance(choice.issued_on, date)
            or isinstance(choice.issued_on, datetime)):
        raise QdKtHandoffBlocked("QDKT_ISSUANCE_METADATA_MISSING")
    if (not isinstance(choice.member_ids, tuple) or not choice.member_ids
            or any(not isinstance(m, str) or not m.strip() or m != m.strip()
                   for m in choice.member_ids)
            or len(set(choice.member_ids)) != len(choice.member_ids)):
        raise QdKtHandoffBlocked("QDKT_ISSUED_ROSTER_INVALID")
    if choice.confirmed_by_user is not True:
        raise QdKtHandoffBlocked("QDKT_ISSUED_TEAM_CONFIRMATION_REQUIRED")
    if choice.roster_source == "USER_ENTERED":
        if (draft is not None or choice.draft_id is not None
                or choice.draft_team_id is not None or choice.draft_team_revision is not None
                or choice.acknowledged_changes is not False):
            raise QdKtHandoffBlocked("QDKT_MANUAL_TEAM_DRAFT_PROVENANCE_FORBIDDEN")
        return choice
    if choice.roster_source not in ("DRAFT_UNCHANGED", "DRAFT_EDITED"):
        raise QdKtHandoffBlocked("QDKT_ISSUED_TEAM_SOURCE_INVALID")
    if (not isinstance(draft, DraftTeamHandoff)
            or (choice.case_id, choice.draft_id, choice.draft_team_id,
                choice.draft_team_revision) !=
               (draft.case_id, draft.draft_id, draft.team_id, draft.team_revision)
            or type(draft.team_revision) is not int or draft.team_revision < 1):
        raise QdKtHandoffBlocked("QDKT_DRAFT_TEAM_PROVENANCE_MISMATCH")
    if (not isinstance(draft.member_ids, tuple) or not draft.member_ids
            or any(not isinstance(m, str) or not m.strip() for m in draft.member_ids)
            or len(set(draft.member_ids)) != len(draft.member_ids)):
        raise QdKtHandoffBlocked("QDKT_DRAFT_ROSTER_INVALID")
    changed = choice.member_ids != draft.member_ids
    if choice.roster_source == "DRAFT_UNCHANGED":
        if changed or choice.acknowledged_changes is not False:
            raise QdKtHandoffBlocked("QDKT_DRAFT_ROSTER_CHANGED")
    elif not changed or choice.acknowledged_changes is not True:
        raise QdKtHandoffBlocked("QDKT_EDITED_ROSTER_REVIEW_REQUIRED")
    return choice
