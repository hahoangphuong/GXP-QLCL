"""Bind a Case-owned proposed QĐKT team to an immutable draft display snapshot.

This is identity/ordering parity only, never title provenance, Word bookmark
mapping, rendering permission, or proof that a DOCX binary displays the roster.
"""
from __future__ import annotations

from dataclasses import dataclass

from backend.app.document.inspection_qd_kt_case_source_bundle import (
    QdKtPreapprovalCaseSource, require_qdkt_preapproval_case_source,
)
from backend.app.document.inspection_qd_kt_team_snapshot_review import (
    DraftTeamSnapshot, validate_draft_snapshot,
)


class QdKtDraftCaseTeamBindingBlocked(ValueError):
    pass


@dataclass(frozen=True)
class QdKtDraftCaseTeamBinding:
    case_id: str
    draft_id: str
    source_team_id: str
    snapshot_team_id: str
    document_version_id: str
    ordered_member_ids: tuple[str, ...]
    team_revision: int
    identity_display_parity_verified: bool = True
    job_title_provenance_verified: bool = False
    binary_roster_match_verified: bool = False
    ready_to_render: bool = False


def require_qdkt_draft_case_team_binding(
    *, source: QdKtPreapprovalCaseSource, snapshot: DraftTeamSnapshot,
) -> QdKtDraftCaseTeamBinding:
    """Reject an unowned/stale draft snapshot without inventing display fields.

    Source team IDs refer to persisted Case rows; snapshot member IDs are
    compared by exact order, display name and role. Job titles do not exist
    in QdKtTeamMemberSource, so they remain unverified here.
    """
    if not isinstance(source, QdKtPreapprovalCaseSource):
        raise QdKtDraftCaseTeamBindingBlocked("QDKT_DRAFT_CASE_SOURCE_INVALID")
    # Revalidate caller-owned frozen dataclasses: synthetic/stale objects are
    # not allowed to bypass their original source gate.
    checked = require_qdkt_preapproval_case_source(
        case_id=source.case_id, site=source.site, proposed_team=source.proposed_team,
    )
    validate_draft_snapshot(snapshot)
    if checked.case_id != snapshot.case_id or checked.proposed_team.team_id != snapshot.team_id:
        raise QdKtDraftCaseTeamBindingBlocked("QDKT_DRAFT_CASE_TEAM_IDENTITY_MISMATCH")
    members = checked.proposed_team.members
    if len(members) != len(snapshot.members):
        raise QdKtDraftCaseTeamBindingBlocked("QDKT_DRAFT_CASE_TEAM_ROSTER_MISMATCH")
    for current, frozen in zip(members, snapshot.members, strict=True):
        if (
            current.id != frozen.inspector_id
            or current.display_name != frozen.display_name
            or current.role_code != frozen.role
        ):
            raise QdKtDraftCaseTeamBindingBlocked("QDKT_DRAFT_CASE_TEAM_ROSTER_MISMATCH")
    return QdKtDraftCaseTeamBinding(
        case_id=snapshot.case_id, draft_id=snapshot.draft_id,
        source_team_id=checked.proposed_team.team_id,
        snapshot_team_id=snapshot.team_id,
        document_version_id=snapshot.document_version_id,
        ordered_member_ids=tuple(row.inspector_id for row in snapshot.members),
        team_revision=snapshot.team_revision,
    )
