from dataclasses import replace
from datetime import date, datetime
import pytest

from backend.app.document.inspection_qd_kt_team_handoff import DraftTeamHandoff, QdKtHandoffBlocked
from backend.app.document.inspection_qd_kt_issued_team_choice import IssuedTeamChoice, require_issued_team_choice


def draft():
    return DraftTeamHandoff("case-1", "draft-1", "team-1", ("member-a", "member-b"), 4)


def choice():
    return IssuedTeamChoice("case-1", "42/QD-KT", date(2026, 10, 25),
                            ("member-a", "member-b"), True, "DRAFT_UNCHANGED",
                            "draft-1", "team-1", 4)


def test_unchanged_draft_confirmed():
    assert require_issued_team_choice(choice=choice(), draft=draft()) == choice()


def test_edited_draft_requires_acknowledgment_and_does_not_mutate_draft():
    edited = replace(choice(), member_ids=("member-a", "member-c"),
                     roster_source="DRAFT_EDITED", acknowledged_changes=True)
    assert require_issued_team_choice(choice=edited, draft=draft()) == edited
    assert draft().member_ids == ("member-a", "member-b")


def test_manual_issued_roster_requires_no_draft():
    manual = IssuedTeamChoice("case-1", "42/QD-KT", date(2026, 10, 25),
                              ("member-c",), True, "USER_ENTERED")
    assert require_issued_team_choice(choice=manual) == manual


@pytest.mark.parametrize("change,error", [
    ({"confirmed_by_user": False}, "CONFIRMATION_REQUIRED"),
    ({"case_id": "case-2"}, "PROVENANCE_MISMATCH"),
    ({"draft_id": "other"}, "PROVENANCE_MISMATCH"),
    ({"draft_team_revision": 5}, "PROVENANCE_MISMATCH"),
    ({"member_ids": ("member-b", "member-a")}, "DRAFT_ROSTER_CHANGED"),
    ({"roster_source": "DRAFT_EDITED", "acknowledged_changes": True}, "EDITED_ROSTER_REVIEW_REQUIRED"),
    ({"member_ids": ("member-b", "member-a"), "roster_source": "DRAFT_EDITED"}, "EDITED_ROSTER_REVIEW_REQUIRED"),
    ({"member_ids": ("member-a", "member-a")}, "ISSUED_ROSTER_INVALID"),
    ({"issued_on": datetime(2026, 10, 25)}, "ISSUANCE_METADATA_MISSING"),
    ({"decision_reference": ""}, "ISSUANCE_METADATA_MISSING"),
    ({"roster_source": "KHKT_AUTOCOPY"}, "SOURCE_INVALID"),
])
def test_invalid_final_roster_blocked(change, error):
    with pytest.raises(QdKtHandoffBlocked, match=error):
        require_issued_team_choice(choice=replace(choice(), **change), draft=draft())


def test_manual_roster_cannot_claim_draft_source():
    with pytest.raises(QdKtHandoffBlocked, match="MANUAL_TEAM_DRAFT_PROVENANCE_FORBIDDEN"):
        require_issued_team_choice(choice=replace(choice(), roster_source="USER_ENTERED"))


def test_draft_roster_requires_actual_draft():
    with pytest.raises(QdKtHandoffBlocked, match="DRAFT_TEAM_PROVENANCE_MISMATCH"):
        require_issued_team_choice(choice=choice())
