"""Read-only composition of Case roster identity and persisted draft version.

Combines independent gates without confirming binary contents, authorizing
document generation, approval, or a production storage read/write.
"""
from __future__ import annotations

from dataclasses import dataclass

from backend.app.document.inspection_qd_kt_case_source_bundle import (
    QdKtPreapprovalCaseSource, read_qdkt_preapproval_case_source,
)
from backend.app.document.inspection_qd_kt_draft_case_team_binding import (
    QdKtDraftCaseTeamBinding, require_qdkt_draft_case_team_binding,
)
from backend.app.document.inspection_qd_kt_draft_version_binding import (
    QdKtDraftVersionBinding, require_qdkt_draft_version_binding,
)
from backend.app.document.inspection_qd_kt_team_snapshot_review import DraftTeamSnapshot


class QdKtDraftProvenanceBlocked(ValueError):
    pass


@dataclass(frozen=True)
class QdKtDraftProvenance:
    case_id: str
    draft_id: str
    document_version_id: str
    document_id: str
    stored_checksum_sha256: str
    team_id: str
    team_revision: int
    ordered_member_ids: tuple[str, ...]
    case_roster_identity_verified: bool = True
    version_case_ownership_verified: bool = True
    binary_content_verified: bool = False
    job_title_provenance_verified: bool = False
    issuance_approved: bool = False
    ready_to_render: bool = False


def require_qdkt_draft_provenance(
    *, roster: QdKtDraftCaseTeamBinding,
    version: QdKtDraftVersionBinding,
) -> QdKtDraftProvenance:
    """Require identical Case, draft, version, roster before composing proof."""
    if not isinstance(roster, QdKtDraftCaseTeamBinding) or not isinstance(version, QdKtDraftVersionBinding):
        raise QdKtDraftProvenanceBlocked("QDKT_DRAFT_PROVENANCE_TYPE_INVALID")
    if (
        not roster.case_id or not roster.draft_id or not roster.document_version_id
        or not roster.source_team_id or roster.source_team_id != roster.snapshot_team_id
        or not version.document_id or not version.stored_checksum_sha256
        or not roster.ordered_member_ids or not isinstance(roster.team_revision, int)
        or roster.team_revision < 1
        or roster.case_id != version.case_id
        or roster.draft_id != version.draft_id
        or roster.document_version_id != version.document_version_id
        or roster.ordered_member_ids != version.roster_member_ids
    ):
        raise QdKtDraftProvenanceBlocked("QDKT_DRAFT_PROVENANCE_IDENTITY_MISMATCH")
    if (
        roster.identity_display_parity_verified is not True
        or roster.binary_roster_match_verified is not False
        or roster.job_title_provenance_verified is not False
        or roster.ready_to_render is not False
        or version.confirmed_binary_roster_match is not False
        or version.approved_decision_link is not False
    ):
        raise QdKtDraftProvenanceBlocked("QDKT_DRAFT_PROVENANCE_UNSUPPORTED_CLAIM")
    return QdKtDraftProvenance(
        case_id=roster.case_id, draft_id=roster.draft_id,
        document_version_id=roster.document_version_id,
        document_id=version.document_id,
        stored_checksum_sha256=version.stored_checksum_sha256,
        team_id=roster.source_team_id, team_revision=roster.team_revision,
        ordered_member_ids=roster.ordered_member_ids,
    )


def read_qdkt_draft_provenance(
    session, *, case_id: str, snapshot: DraftTeamSnapshot,
) -> QdKtDraftProvenance:
    """Compose under one no-autoflush boundary; never query issued decision."""
    if not isinstance(snapshot, DraftTeamSnapshot) or snapshot.case_id != case_id:
        raise QdKtDraftProvenanceBlocked("QDKT_DRAFT_PROVENANCE_CASE_MISMATCH")
    with session.no_autoflush:
        source: QdKtPreapprovalCaseSource = read_qdkt_preapproval_case_source(
            session, case_id=case_id,
        )
        roster = require_qdkt_draft_case_team_binding(source=source, snapshot=snapshot)
        version = require_qdkt_draft_version_binding(session, snapshot=snapshot)
    return require_qdkt_draft_provenance(roster=roster, version=version)
