"""Evidence-only QĐKT team source gates; no rendering inferred."""
from dataclasses import replace

import pytest

from backend.app.document.inspection_qd_kt_team_source import (
    QdKtTeamMemberSource, QdKtTeamSourceBlocked, require_qdkt_team_source,
)


def _member(**kwargs):
    default = dict(id="m1", sort_order=0, role_code="LEADER", display_name="Nguyễn A",
                   identity_kind="INSPECTOR_PROFILE", inspector_profile_id="person-1",
                   person_id=None, participant_catalog_id=None)
    default.update(kwargs)
    return QdKtTeamMemberSource(**default)


def _check(*members):
    return require_qdkt_team_source(case_id="case-1", team_id="team-1", members=members)


def test_verified_team_source_remains_unmapped():
    leader = _member()
    secretary = _member(id="m2", sort_order=1, role_code="SECRETARY",
                        identity_kind="LEGACY_PERSON", inspector_profile_id=None, display_name="Trần B")
    result = _check(leader, secretary)
    assert [r.id for r in result.members] == ["m1", "m2"]
    assert result.bookmark_mapping_verified is False


@pytest.mark.parametrize("members,reason", [
    ([], "INSPECTION_TEAM_EMPTY"),
    ([_member(), _member()], "INSPECTION_TEAM_MEMBER_ID_AMBIGUOUS"),
    ([_member(), _member(id="m2")], "INSPECTION_TEAM_ORDER_AMBIGUOUS"),
    ([_member(sort_order=1), _member(id="m2", sort_order=0)], "INSPECTION_TEAM_ORDER_UNSORTED"),
    ([_member(role_code=None)], "INSPECTION_TEAM_ROLE_UNPROVEN"),
    ([_member(display_name="  ")], "INSPECTION_TEAM_DISPLAY_NAME_UNPROVEN"),
    ([_member(display_name=" Name ")], "INSPECTION_TEAM_DISPLAY_NAME_UNPROVEN"),
    ([_member(identity_kind=None)], "INSPECTION_TEAM_IDENTITY_UNPROVEN"),
    ([_member(person_id="other")], "INSPECTION_TEAM_IDENTITY_UNPROVEN"),
    ([_member(identity_kind="ORGANIZATION_REPRESENTATIVE", inspector_profile_id=None)],
     "INSPECTION_TEAM_IDENTITY_UNPROVEN"),
])
def test_unproven_source_fails_closed(members, reason):
    with pytest.raises(QdKtTeamSourceBlocked, match=reason):
        _check(*members)


def test_proven_organization_representative_is_a_source_not_a_rendered_role():
    representative = _member(
        role_code="MEMBER", identity_kind="ORGANIZATION_REPRESENTATIVE",
        inspector_profile_id=None, participant_catalog_id="catalog-1",
    )
    result = _check(representative)
    assert result.members[0].participant_catalog_id == "catalog-1"
    assert not result.bookmark_mapping_verified
