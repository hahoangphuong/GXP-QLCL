from dataclasses import replace
from datetime import date

import pytest

from backend.app.document.inspection_qd_kt_team_handoff import QdKtHandoffBlocked
from backend.app.document.inspection_qd_kt_issued_team_choice import IssuedTeamChoice
from backend.app.document.inspection_qd_kt_team_snapshot_review import (
    DraftTeamSnapshot, TeamMemberAtDraft, review_issued_team, validate_draft_snapshot,
)


def member(mid, role="THANH_VIEN", title="Thanh tra viên"):
    return TeamMemberAtDraft(mid, "Name " + mid, role, title)


def snapshot(*members):
    return DraftTeamSnapshot("case-1", "draft-1", "doc-v1", "team-1", 3, tuple(members))


def choice(member_ids, source="DRAFT_UNCHANGED", acknowledged=False):
    return IssuedTeamChoice(
        "case-1", "123/QD", date(2026, 10, 25), tuple(member_ids),
        True, source, "draft-1", "team-1", 3, acknowledged,
    )


@pytest.mark.parametrize("n", [2, 3, 5])
def test_same_order_and_display_snapshot_can_be_reused_without_reentry(n):
    members = tuple(member(str(i)) for i in range(n))
    src = snapshot(*members)
    result = review_issued_team(
        choice=choice(tuple(m.inspector_id for m in members)),
        final_members=members, draft_snapshot=src,
    )
    assert result.changes == ()
    assert result.final_members == src.members


def test_display_only_change_requires_edited_mode_and_review_acknowledgment():
    src = snapshot(member("a", "TRUONG_DOAN"), member("b"))
    updated = (member("a", "TRUONG_DOAN", "Phó trưởng phòng"), member("b"))
    with pytest.raises(QdKtHandoffBlocked, match="DRAFT_ROSTER_CHANGED"):
        review_issued_team(choice=choice(("a", "b")), final_members=updated, draft_snapshot=src)
    with pytest.raises(QdKtHandoffBlocked, match="EDITED_ROSTER_REVIEW_REQUIRED"):
        review_issued_team(choice=choice(("a", "b"), "DRAFT_EDITED"), final_members=updated, draft_snapshot=src)
    result = review_issued_team(
        choice=choice(("a", "b"), "DRAFT_EDITED", True),
        final_members=updated, draft_snapshot=src,
    )
    assert len(result.changes) == 1
    assert result.changes[0].inspector_id == "a"
    assert src.members[0].job_title == "Thanh tra viên"


def test_reorder_and_replacement_are_reported_with_positions():
    src = snapshot(member("a"), member("b"), member("c"))
    updated = (member("b"), member("d"), member("a"))
    result = review_issued_team(
        choice=choice(("b", "d", "a"), "DRAFT_EDITED", True),
        final_members=updated, draft_snapshot=src,
    )
    assert {c.inspector_id for c in result.changes} == {"a", "b", "c", "d"}
    assert next(c for c in result.changes if c.inspector_id == "c").after_position is None
    assert next(c for c in result.changes if c.inspector_id == "d").before_position is None


def test_manual_team_has_no_forged_draft_association():
    final = (member("x"),)
    manual = IssuedTeamChoice("case-1", "123/QD", date(2026, 10, 25),
                              ("x",), True, "USER_ENTERED")
    result = review_issued_team(choice=manual, final_members=final)
    assert result.draft_id is None
    with pytest.raises(QdKtHandoffBlocked, match="MANUAL_TEAM_DRAFT_PROVENANCE_FORBIDDEN"):
        review_issued_team(choice=manual, final_members=final, draft_snapshot=snapshot(member("x")))


@pytest.mark.parametrize("members", [
    (),
    (member("a"), member("a")),
    (replace(member("a"), display_name=""),),
    (replace(member("a"), role=" "),),
])
def test_invalid_snapshot_fails_closed(members):
    with pytest.raises(QdKtHandoffBlocked, match="TEAM_DISPLAY_SNAPSHOT_INVALID"):
        validate_draft_snapshot(snapshot(*members))


def test_cross_case_and_stale_revision_fail_closed():
    src = snapshot(member("a"), member("b"))
    final = src.members
    with pytest.raises(QdKtHandoffBlocked, match="PROVENANCE_MISMATCH"):
        review_issued_team(choice=replace(choice(("a", "b")), case_id="case-2"),
                           final_members=final, draft_snapshot=src)
    with pytest.raises(QdKtHandoffBlocked, match="PROVENANCE_MISMATCH"):
        review_issued_team(choice=replace(choice(("a", "b")), draft_team_revision=4),
                           final_members=final, draft_snapshot=src)


def test_mismatched_member_display_ids_fail_closed():
    with pytest.raises(QdKtHandoffBlocked, match="ISSUED_DISPLAY_ROSTER_MISMATCH"):
        review_issued_team(choice=choice(("a", "b")), final_members=(member("a"),),
                           draft_snapshot=snapshot(member("a"), member("b")))
