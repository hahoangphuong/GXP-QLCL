from dataclasses import replace
from datetime import date, datetime

import pytest

from backend.app.document.inspection_qd_kt_team_handoff import (
    DraftTeamHandoff, IssuanceTeamSelection, QdKtHandoffBlocked,
    require_confirmed_issuance_team,
)


def _pair():
    draft = DraftTeamHandoff("case-a", "draft-a", "team-a", ("one", "two"), 3)
    selection = IssuanceTeamSelection(
        "case-a", "draft-a", "team-a", ("one", "two"), 3,
        "123/QD-QLD", date(2026, 10, 24), True,
    )
    return draft, selection


def test_user_can_confirm_unchanged_draft_team_at_issuance():
    draft, selection = _pair()
    assert require_confirmed_issuance_team(draft=draft, selection=selection) == selection


@pytest.mark.parametrize("change,error", [
    ({"case_id": "case-b"}, "IDENTITY_MISMATCH"),
    ({"draft_id": "another-draft"}, "IDENTITY_MISMATCH"),
    ({"team_id": "another-team"}, "IDENTITY_MISMATCH"),
    ({"team_revision": 4}, "REVISION_CHANGED"),
    ({"member_ids": ("two", "one")}, "MEMBERS_CHANGED"),
    ({"member_ids": ("one",)}, "MEMBERS_CHANGED"),
    ({"user_confirmed_team": False}, "CONFIRMATION_REQUIRED"),
    ({"decision_reference": ""}, "ISSUANCE_METADATA_MISSING"),
    ({"issued_on": datetime(2026, 10, 24)}, "ISSUANCE_METADATA_MISSING"),
    ({"source": "KHKT_AUTO_IMPORT"}, "TEAM_SOURCE_INVALID"),
])
def test_unapproved_or_stale_draft_never_becomes_issued_team(change, error):
    draft, selected = _pair()
    with pytest.raises(QdKtHandoffBlocked, match=error):
        require_confirmed_issuance_team(draft=draft, selection=replace(selected, **change))


def test_incomplete_or_duplicate_roster_rejected():
    draft, selection = _pair()
    with pytest.raises(QdKtHandoffBlocked, match="MEMBERS_CHANGED"):
        require_confirmed_issuance_team(
            draft=replace(draft, member_ids=("one", "one")), selection=selection,
        )
