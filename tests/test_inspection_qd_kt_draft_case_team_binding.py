"""Case→draft roster comparison does not assert Word or approval provenance."""
from dataclasses import replace

import pytest

from backend.app.document.inspection_qd_kt_case_source_bundle import (
    require_qdkt_preapproval_case_source,
)
from backend.app.document.inspection_qd_kt_registered_site import QdKtRegisteredSite
from backend.app.document.inspection_qd_kt_team_source import (
    QdKtTeamMemberSource, QdKtTeamSource,
)
from backend.app.document.inspection_qd_kt_team_snapshot_review import (
    DraftTeamSnapshot, TeamMemberAtDraft,
)
from backend.app.document.inspection_qd_kt_draft_case_team_binding import (
    QdKtDraftCaseTeamBindingBlocked, require_qdkt_draft_case_team_binding,
)


def atoms():
    site = QdKtRegisteredSite("case-1", "site-1", "Registered address", "Đà Nẵng")
    team = QdKtTeamSource("case-1", "team-1", (
        QdKtTeamMemberSource("person-a", 1, "LEADER", "Inspector A", "LEGACY_PERSON", None, None, None),
        QdKtTeamMemberSource("person-b", 2, "MEMBER", "Inspector B", "LEGACY_PERSON", None, None, None),
    ))
    source = require_qdkt_preapproval_case_source(
        case_id="case-1", site=site, proposed_team=team,
    )
    snapshot = DraftTeamSnapshot(
        "case-1", "draft-1", "doc-version-1", "team-1", 2, (
            TeamMemberAtDraft("person-a", "Inspector A", "LEADER", "Unknown title A"),
            TeamMemberAtDraft("person-b", "Inspector B", "MEMBER", "Unknown title B"),
        ),
    )
    return source, snapshot


def test_exact_case_owned_roster_identity_order_and_display_verified_without_approval():
    source, snapshot = atoms()
    result = require_qdkt_draft_case_team_binding(source=source, snapshot=snapshot)
    assert result.ordered_member_ids == ("person-a", "person-b")
    assert result.source_team_id == result.snapshot_team_id == "team-1"
    assert result.document_version_id == "doc-version-1"
    assert result.team_revision == 2
    assert result.identity_display_parity_verified is True
    assert result.job_title_provenance_verified is False
    assert result.binary_roster_match_verified is False
    assert result.ready_to_render is False


@pytest.mark.parametrize("changed,error", [
    ({"case_id": "case-other"}, "IDENTITY_MISMATCH"),
    ({"team_id": "team-other"}, "IDENTITY_MISMATCH"),
    ({"members": (TeamMemberAtDraft("person-a", "Inspector A", "LEADER", "Title"),)}, "ROSTER_MISMATCH"),
    ({"members": (
        TeamMemberAtDraft("person-b", "Inspector B", "MEMBER", "Title"),
        TeamMemberAtDraft("person-a", "Inspector A", "LEADER", "Title"),
    )}, "ROSTER_MISMATCH"),
    ({"members": (
        TeamMemberAtDraft("person-a", "Inspector A edited", "LEADER", "Title"),
        TeamMemberAtDraft("person-b", "Inspector B", "MEMBER", "Title"),
    )}, "ROSTER_MISMATCH"),
    ({"members": (
        TeamMemberAtDraft("person-a", "Inspector A", "MEMBER", "Title"),
        TeamMemberAtDraft("person-b", "Inspector B", "MEMBER", "Title"),
    )}, "ROSTER_MISMATCH"),
])
def test_changed_case_team_order_name_or_role_rejected(changed, error):
    source, snapshot = atoms()
    with pytest.raises(QdKtDraftCaseTeamBindingBlocked, match=error):
        require_qdkt_draft_case_team_binding(
            source=source, snapshot=replace(snapshot, **changed),
        )


def test_source_team_substitution_rejected():
    source, snapshot = atoms()
    with pytest.raises(QdKtDraftCaseTeamBindingBlocked, match="IDENTITY_MISMATCH"):
        require_qdkt_draft_case_team_binding(
            source=replace(source, proposed_team=replace(source.proposed_team, team_id="other-team")),
            snapshot=snapshot,
        )


def test_title_changes_do_not_claim_title_provenance():
    source, snapshot = atoms()
    new_members = tuple(replace(row, job_title="Different unverified title") for row in snapshot.members)
    result = require_qdkt_draft_case_team_binding(
        source=source, snapshot=replace(snapshot, members=new_members),
    )
    assert result.identity_display_parity_verified
    assert not result.job_title_provenance_verified
    assert not result.ready_to_render
