"""Cross-gate Case/source/version composition cannot promote approval or Word UAT."""
from contextlib import nullcontext
from dataclasses import replace
from types import SimpleNamespace

import pytest

from backend.app.document.inspection_qd_kt_draft_case_team_binding import QdKtDraftCaseTeamBinding
from backend.app.document.inspection_qd_kt_draft_version_binding import QdKtDraftVersionBinding
from backend.app.document.inspection_qd_kt_draft_provenance import (
    QdKtDraftProvenanceBlocked, require_qdkt_draft_provenance,
    read_qdkt_draft_provenance,
)
from backend.app.document.inspection_qd_kt_team_snapshot_review import (
    DraftTeamSnapshot, TeamMemberAtDraft,
)


def proofs():
    roster = QdKtDraftCaseTeamBinding(
        case_id="case-1", draft_id="draft-1",
        source_team_id="team-1", snapshot_team_id="team-1",
        document_version_id="version-1", ordered_member_ids=("member-1",),
        team_revision=3,
    )
    version = QdKtDraftVersionBinding(
        case_id="case-1", draft_id="draft-1", document_version_id="version-1",
        document_id="doc-1", stored_checksum_sha256="a" * 64,
        roster_member_ids=("member-1",),
    )
    return roster, version


def test_composed_identity_keeps_binary_and_approval_claims_false():
    roster, version = proofs()
    result = require_qdkt_draft_provenance(roster=roster, version=version)
    assert result.case_id == "case-1"
    assert result.document_version_id == "version-1"
    assert result.document_id == "doc-1"
    assert result.team_revision == 3
    assert result.ordered_member_ids == ("member-1",)
    assert result.case_roster_identity_verified is True
    assert result.version_case_ownership_verified is True
    assert result.binary_content_verified is False
    assert result.job_title_provenance_verified is False
    assert result.issuance_approved is False
    assert result.ready_to_render is False


@pytest.mark.parametrize("field,value", [
    ("case_id", "other-case"),
    ("draft_id", "other-draft"),
    ("document_version_id", "other-version"),
    ("roster_member_ids", ("other-member",)),
])
def test_cross_gate_version_mismatch_rejected(field, value):
    roster, version = proofs()
    with pytest.raises(QdKtDraftProvenanceBlocked, match="IDENTITY_MISMATCH"):
        require_qdkt_draft_provenance(roster=roster, version=replace(version, **{field: value}))


@pytest.mark.parametrize("field", [
    "binary_roster_match_verified", "job_title_provenance_verified", "ready_to_render",
])
def test_forged_roster_approval_claim_rejected(field):
    roster, version = proofs()
    with pytest.raises(QdKtDraftProvenanceBlocked, match="UNSUPPORTED_CLAIM"):
        require_qdkt_draft_provenance(roster=replace(roster, **{field: True}), version=version)


@pytest.mark.parametrize("field", ["confirmed_binary_roster_match", "approved_decision_link"])
def test_forged_version_claim_rejected(field):
    roster, version = proofs()
    with pytest.raises(QdKtDraftProvenanceBlocked, match="UNSUPPORTED_CLAIM"):
        require_qdkt_draft_provenance(roster=roster, version=replace(version, **{field: True}))


def test_invalid_type_rejected():
    roster, version = proofs()
    with pytest.raises(QdKtDraftProvenanceBlocked, match="TYPE_INVALID"):
        require_qdkt_draft_provenance(roster=SimpleNamespace(**vars(roster)), version=version)


def test_reader_rejects_cross_case_before_access(monkeypatch):
    import backend.app.document.inspection_qd_kt_draft_provenance as module
    def forbidden(*args, **kwargs):
        raise AssertionError("NO_DB_LOOKUP_ALLOWED")
    monkeypatch.setattr(module, "read_qdkt_preapproval_case_source", forbidden)
    snapshot = DraftTeamSnapshot(
        "case-1", "draft-1", "version-1", "team-1", 3,
        (TeamMemberAtDraft("member-1", "Inspector", "LEADER", "Unverified title"),),
    )
    with pytest.raises(QdKtDraftProvenanceBlocked, match="CASE_MISMATCH"):
        read_qdkt_draft_provenance(
            SimpleNamespace(no_autoflush=nullcontext()), case_id="case-2", snapshot=snapshot,
        )


def test_reader_composes_without_issuing_or_mutating(monkeypatch):
    import backend.app.document.inspection_qd_kt_draft_provenance as module
    roster, version = proofs()
    calls = []
    monkeypatch.setattr(module, "read_qdkt_preapproval_case_source",
        lambda session, *, case_id: calls.append(("source", case_id)) or "source")
    monkeypatch.setattr(module, "require_qdkt_draft_case_team_binding",
        lambda *, source, snapshot: calls.append(("roster", snapshot.draft_id)) or roster)
    monkeypatch.setattr(module, "require_qdkt_draft_version_binding",
        lambda session, *, snapshot: calls.append(("version", snapshot.document_version_id)) or version)
    snapshot = DraftTeamSnapshot(
        "case-1", "draft-1", "version-1", "team-1", 3,
        (TeamMemberAtDraft("member-1", "Inspector", "LEADER", "Unverified title"),),
    )
    result = read_qdkt_draft_provenance(
        SimpleNamespace(no_autoflush=nullcontext()), case_id="case-1", snapshot=snapshot,
    )
    assert calls == [("source", "case-1"), ("roster", "draft-1"), ("version", "version-1")]
    assert not result.binary_content_verified
    assert not result.ready_to_render
