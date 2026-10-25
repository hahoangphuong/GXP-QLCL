"""Read-only, display-faithful QĐKT team snapshot and approval comparison.

This module is intentionally detached from persistence, issuance, and Word
rendering. The caller must pin the binary/document version separately.
"""
from __future__ import annotations

from dataclasses import dataclass

from backend.app.document.inspection_qd_kt_team_handoff import (
    DraftTeamHandoff, QdKtHandoffBlocked,
)
from backend.app.document.inspection_qd_kt_issued_team_choice import (
    IssuedTeamChoice, require_issued_team_choice,
)


@dataclass(frozen=True)
class TeamMemberAtDraft:
    inspector_id: str
    display_name: str
    role: str
    job_title: str


@dataclass(frozen=True)
class DraftTeamSnapshot:
    case_id: str
    draft_id: str
    document_version_id: str
    team_id: str
    team_revision: int
    members: tuple[TeamMemberAtDraft, ...]


@dataclass(frozen=True)
class TeamMemberChange:
    inspector_id: str
    before_position: int | None
    after_position: int | None
    before: TeamMemberAtDraft | None
    after: TeamMemberAtDraft | None


@dataclass(frozen=True)
class TeamReview:
    case_id: str
    draft_id: str | None
    changes: tuple[TeamMemberChange, ...]
    final_members: tuple[TeamMemberAtDraft, ...]


def _nonblank(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value == value.strip()


def validate_members(members: tuple[TeamMemberAtDraft, ...]) -> None:
    if (not isinstance(members, tuple) or not members
            or any(not isinstance(m, TeamMemberAtDraft)
                   or not all(_nonblank(v) for v in (
                       m.inspector_id, m.display_name, m.role, m.job_title))
                   for m in members)
            or len({m.inspector_id for m in members}) != len(members)):
        raise QdKtHandoffBlocked("QDKT_TEAM_DISPLAY_SNAPSHOT_INVALID")


def validate_draft_snapshot(snapshot: DraftTeamSnapshot) -> DraftTeamHandoff:
    if (not isinstance(snapshot, DraftTeamSnapshot)
            or not all(_nonblank(v) for v in (
                snapshot.case_id, snapshot.draft_id, snapshot.document_version_id,
                snapshot.team_id))
            or type(snapshot.team_revision) is not int
            or snapshot.team_revision < 1):
        raise QdKtHandoffBlocked("QDKT_DRAFT_DISPLAY_PROVENANCE_INVALID")
    validate_members(snapshot.members)
    return DraftTeamHandoff(
        case_id=snapshot.case_id,
        draft_id=snapshot.draft_id,
        team_id=snapshot.team_id,
        member_ids=tuple(member.inspector_id for member in snapshot.members),
        team_revision=snapshot.team_revision,
    )


def review_issued_team(
    *, choice: IssuedTeamChoice, final_members: tuple[TeamMemberAtDraft, ...],
    draft_snapshot: DraftTeamSnapshot | None = None,
) -> TeamReview:
    """Produce a deterministic ordered diff; NEVER modify the draft snapshot.

    Display-name/role/title edits count as edits even when member IDs stay the
    same. A caller cannot label those edits DRAFT_UNCHANGED. The final roster
    remains pending until an authorized persistence workflow records it.
    """
    if not isinstance(choice, IssuedTeamChoice):
        raise QdKtHandoffBlocked("QDKT_ISSUANCE_CHOICE_TYPE_INVALID")
    validate_members(final_members)
    if tuple(m.inspector_id for m in final_members) != choice.member_ids:
        raise QdKtHandoffBlocked("QDKT_ISSUED_DISPLAY_ROSTER_MISMATCH")
    draft = validate_draft_snapshot(draft_snapshot) if draft_snapshot is not None else None
    if draft_snapshot is None:
        require_issued_team_choice(choice=choice, draft=draft)
        return TeamReview(choice.case_id, None, (), final_members)

    before = {m.inspector_id: (pos, m) for pos, m in enumerate(draft_snapshot.members, 1)}
    after = {m.inspector_id: (pos, m) for pos, m in enumerate(final_members, 1)}
    changes = tuple(
        TeamMemberChange(
            inspector_id=mid,
            before_position=before.get(mid, (None, None))[0],
            after_position=after.get(mid, (None, None))[0],
            before=before.get(mid, (None, None))[1],
            after=after.get(mid, (None, None))[1],
        )
        for mid in dict.fromkeys((*before, *after))
        if before.get(mid) != after.get(mid)
    )
    display_changed = any(c.before is not None and c.after is not None and c.before != c.after for c in changes)
    require_issued_team_choice(choice=choice, draft=draft, display_changed=display_changed)
    if choice.roster_source == "DRAFT_UNCHANGED" and changes:
        raise QdKtHandoffBlocked("QDKT_DRAFT_DISPLAY_CHANGED")
    if choice.roster_source == "DRAFT_EDITED" and not changes:
        raise QdKtHandoffBlocked("QDKT_EDITED_DISPLAY_REVIEW_REQUIRED")
    return TeamReview(choice.case_id, draft_snapshot.draft_id, changes, final_members)
