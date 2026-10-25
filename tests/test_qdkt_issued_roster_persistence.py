"""Fail-closed regression for decision-specific issued roster transaction staging."""
from datetime import date
from types import SimpleNamespace
import pytest

from backend.app.document.inspection_qd_kt_issued_team_choice import IssuedTeamChoice
from backend.app.document.inspection_qd_kt_team_snapshot_review import TeamMemberAtDraft
from backend.app.document.inspection_qd_kt_issued_roster_persistence import (
    QdKtIssuedRosterWriteBlocked, stage_qdkt_issued_roster,
)

MEMBERS = (TeamMemberAtDraft("m-1", "Member One", "LEADER", "Inspector"),)


class Session:
    def __init__(self, *, case_id="case", decision_reference="QD-1", decision_on=date(2026, 10, 1), existing=None):
        self.rows = [
            SimpleNamespace(id="decision", inspection_plan_id="plan",
                            reference=decision_reference, decision_on=decision_on),
            SimpleNamespace(id="plan", case_id=case_id),
            existing,
        ]
        self.items = []
        self.flushed = 0

    def scalar(self, _query):
        return self.rows.pop(0)

    def scalars(self, _query):
        return SimpleNamespace(all=lambda: [])

    def add(self, row):
        self.items.append(row)

    def flush(self):
        self.flushed += 1
        for row in self.items:
            if row.__class__.__name__ == "QdKtIssuedRoster":
                row.id = "roster"


def choice(**overrides):
    data = dict(case_id="case", decision_reference="QD-1", issued_on=date(2026, 10, 1),
                member_ids=("m-1",), confirmed_by_user=True, roster_source="USER_ENTERED")
    return IssuedTeamChoice(**{**data, **overrides})


def stage(session, **overrides):
    return stage_qdkt_issued_roster(session, decision_id="decision",
                                   choice=choice(**overrides), final_members=MEMBERS,
                                   actor_user_id="actor")


def test_manual_roster_stages_parent_members_and_audit_without_commit():
    session = Session()
    row = stage(session)
    assert row.inspection_decision_id == "decision"
    assert row.roster_source == "USER_ENTERED"
    assert row.source_draft_snapshot_id is None
    assert session.flushed == 1
    assert [type(x).__name__ for x in session.items] == [
        "QdKtIssuedRoster", "QdKtIssuedRosterMember", "AuditEvent"]


@pytest.mark.parametrize("override,error", [
    ({"case_id": "another"}, "DECISION_CASE_MISMATCH"),
    ({"decision_reference": "other"}, "DECISION_METADATA_MISMATCH"),
    ({"issued_on": date(2026, 10, 2)}, "DECISION_METADATA_MISMATCH"),
])
def test_decision_scope_and_metadata_rejected_before_staging(override, error):
    session = Session()
    with pytest.raises(QdKtIssuedRosterWriteBlocked, match=error):
        stage(session, **override)
    assert not session.items


def test_draft_link_must_be_persisted_in_same_case():
    session = Session()
    with pytest.raises(QdKtIssuedRosterWriteBlocked, match="DRAFT_SNAPSHOT_NOT_FOUND"):
        stage(session, roster_source="DRAFT_UNCHANGED", draft_id="draft",
              draft_team_id="team", draft_team_revision=2)
    assert not session.items


def test_duplicate_decision_roster_conflict_fails_closed():
    existing = SimpleNamespace(
        id="roster-old", roster_source="USER_ENTERED",
        source_draft_snapshot_id=None, confirmed_by_user_id="actor",
        roster_sha256="0" * 64,
    )
    session = Session(existing=existing)
    with pytest.raises(QdKtIssuedRosterWriteBlocked, match="ALREADY_BOUND"):
        stage(session)
    assert not session.items


def test_invalid_confirmation_does_not_stage():
    session = Session()
    with pytest.raises(ValueError, match="CONFIRMATION_REQUIRED"):
        stage(session, confirmed_by_user=False)
    assert not session.items
