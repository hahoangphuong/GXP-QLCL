"""Process A QĐKT draft source must not require or infer an issued decision."""
from contextlib import nullcontext
from dataclasses import replace

import pytest

from backend.app.document.inspection_qd_kt_case_source_bundle import (
    QdKtCaseSourceBlocked, read_qdkt_preapproval_case_source,
    require_qdkt_preapproval_case_source,
)
from backend.app.document.inspection_qd_kt_registered_site import QdKtRegisteredSite
from backend.app.document.inspection_qd_kt_team_source import (
    QdKtTeamMemberSource, QdKtTeamSource,
)


def atoms():
    site = QdKtRegisteredSite("case-1", "site-1", "Registered address", "Đà Nẵng")
    member = QdKtTeamMemberSource(
        "member-1", 1, "LEADER", "Test Inspector", "LEGACY_PERSON",
        None, None, None,
    )
    team = QdKtTeamSource("case-1", "team-1", (member,))
    return site, team


def test_preapproval_contract_contains_no_issued_reference_or_date():
    site, team = atoms()
    result = require_qdkt_preapproval_case_source(
        case_id="case-1", site=site, proposed_team=team,
    )
    assert result.process == "DRAFT_QDKT"
    assert result.case_id == "case-1"
    assert result.ready_to_render is False
    assert result.proposed_team.members == team.members
    assert not hasattr(result, "decision")
    assert not hasattr(result, "decision_reference")
    assert not hasattr(result, "decision_on")


@pytest.mark.parametrize("changed,error", [
    ({"case_id": "case-2"}, "QDKT_DRAFT_CASE_SOURCE_MISMATCH"),
    ({"case_id": " case-1"}, "QDKT_DRAFT_CASE_ID_INVALID"),
    ({"site": None}, "QDKT_DRAFT_SOURCE_TYPE_INVALID"),
    ({"proposed_team": None}, "QDKT_DRAFT_SOURCE_TYPE_INVALID"),
])
def test_preapproval_rejects_unowned_or_invalid_sources(changed, error):
    site, team = atoms()
    data = dict(case_id="case-1", site=site, proposed_team=team)
    data.update(changed)
    with pytest.raises(QdKtCaseSourceBlocked, match=error):
        require_qdkt_preapproval_case_source(**data)


def test_preapproval_rejects_claimed_bookmark_equivalence():
    site, team = atoms()
    with pytest.raises(QdKtCaseSourceBlocked, match="BOOKMARK_EQUIVALENCE_UNPROVEN"):
        require_qdkt_preapproval_case_source(
            case_id="case-1", site=site,
            proposed_team=replace(team, bookmark_mapping_verified=True),
        )


@pytest.mark.parametrize("prior_decisions", [0, 1, 3])
def test_draft_read_does_not_query_prior_issuance(monkeypatch, prior_decisions):
    import backend.app.document.inspection_qd_kt_case_source_bundle as module
    site, team = atoms()
    calls = []

    def read_site(session, *, case_id):
        calls.append(("site", case_id))
        return site

    def read_team(session, *, case_id):
        calls.append(("team", case_id))
        return team

    def forbidden_decision(*args, **kwargs):
        raise AssertionError("DRAFT_MUST_NOT_QUERY_ISSUED_DECISIONS")

    monkeypatch.setattr(module, "read_qdkt_registered_site", read_site)
    monkeypatch.setattr(module, "read_qdkt_team_source", read_team)
    monkeypatch.setattr(module, "read_latest_qdkt_reference_for_case", forbidden_decision)

    class Session:
        no_autoflush = nullcontext()

    session = Session()
    session.prior_decisions = prior_decisions
    result = read_qdkt_preapproval_case_source(session, case_id="case-1")
    assert result.process == "DRAFT_QDKT"
    assert result.ready_to_render is False
    assert calls == [("site", "case-1"), ("team", "case-1")]


def test_draft_source_read_fails_closed_if_no_team(monkeypatch):
    import backend.app.document.inspection_qd_kt_case_source_bundle as module
    from backend.app.document.inspection_qd_kt_team_source import QdKtTeamSourceBlocked
    site, _ = atoms()

    monkeypatch.setattr(module, "read_qdkt_registered_site", lambda session, *, case_id: site)

    def missing_team(session, *, case_id):
        raise QdKtTeamSourceBlocked("CASE_INSPECTION_TEAM_NOT_UNIQUE")

    monkeypatch.setattr(module, "read_qdkt_team_source", missing_team)

    class Session:
        no_autoflush = nullcontext()

    with pytest.raises(QdKtTeamSourceBlocked, match="CASE_INSPECTION_TEAM_NOT_UNIQUE"):
        read_qdkt_preapproval_case_source(Session(), case_id="case-1")
