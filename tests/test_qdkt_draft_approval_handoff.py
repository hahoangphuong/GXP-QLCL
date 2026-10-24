"""Two independent legacy steps: draft -> optional proposal; issued data -> explicit user confirmation."""
from datetime import date, datetime
import pytest
from backend.app.document.inspection_qd_kt_team_source import QdKtTeamMemberSource
from backend.app.document.inspection_qd_kt_draft_approval_handoff import (
    QdKtHandoffBlocked, propose_qdkt_draft_team, validate_approved_qdkt_input,
)


def _members():
    return (QdKtTeamMemberSource(
        id="m1", sort_order=0, role_code="LEADER", display_name="Member A",
        identity_kind="LEGACY_PERSON", inspector_profile_id=None,
        person_id=None, participant_catalog_id=None,
    ),)


def _draft():
    return propose_qdkt_draft_team(case_id="case-a", draft_id="draft-1", members=_members())


def _approve(**changes):
    opts = dict(case_id="case-a", decision_reference="123/QD", decision_on=date(2026, 10, 24),
                approved_members=_members(), user_confirmed=True,
                draft=_draft(), reuse_draft_team=True)
    opts.update(changes)
    return validate_approved_qdkt_input(**opts)


def test_draft_is_never_approved_or_decision_by_itself():
    draft = _draft()
    assert draft.approved is False
    assert not hasattr(draft, "decision_reference")
    assert not hasattr(draft, "decision_on")


def test_explicit_approved_fields_accept_reuse_without_retyping_team():
    out = _approve()
    assert out.team_source == "CONFIRMED_DRAFT_PROPOSAL"
    assert out.members == _draft().members
    assert out.decision_reference == "123/QD"
    assert out.user_confirmed is True


def test_manual_approved_team_does_not_require_draft():
    out = _approve(draft=None, reuse_draft_team=False)
    assert out.team_source == "USER_ENTERED"
    assert out.draft_id is None


@pytest.mark.parametrize("changes,error", [
    ({"user_confirmed": False}, "USER_APPROVAL_CONFIRMATION_REQUIRED"),
    ({"decision_reference": ""}, "DECISION_REFERENCE_REQUIRED"),
    ({"decision_on": datetime(2026, 10, 24, 9, 0)}, "DECISION_DATE_REQUIRED"),
    ({"case_id": "case-b"}, "DRAFT_TEAM_CASE_MISMATCH"),
    ({"draft": None}, "DRAFT_TEAM_CASE_MISMATCH"),
])
def test_issued_decision_never_inferred_from_draft(changes, error):
    with pytest.raises(QdKtHandoffBlocked, match=error):
        _approve(**changes)


def test_changed_team_requires_explicit_entry_not_silent_reuse():
    changed = (QdKtTeamMemberSource(
        id="m2", sort_order=0, role_code="LEADER", display_name="Member B",
        identity_kind="LEGACY_PERSON", inspector_profile_id=None,
        person_id=None, participant_catalog_id=None,
    ),)
    with pytest.raises(QdKtHandoffBlocked, match="DRAFT_TEAM_CHANGED_REQUIRES_EXPLICIT_ENTRY"):
        _approve(approved_members=changed)
    out = _approve(approved_members=changed, reuse_draft_team=False)
    assert out.team_source == "USER_ENTERED"
