import pytest

from backend.app.document.inspection_qd_kt_team_layout_instructions import (
    QdKtTeamLayoutBlocked, plan_qdkt_team_layout,
)


@pytest.mark.parametrize("names,third,delete,extend", [
    ("A|B", (), True, False),
    ("A|B|C", ("C",), False, False),
    ("A|B|C|D|E", ("C", "D", "E"), False, True),
])
def test_source_attested_layout_is_never_renderer_authorization(names, third, delete, extend):
    result = plan_qdkt_team_layout(
        legacy_display=names, source_attested=True, template_extension=" - member"
    )
    assert result.first == "A" and result.second == "B"
    assert result.third_and_later == third
    assert result.delete_third_member_bookmark is delete
    assert result.template_extension_required is extend
    assert not result.source_equivalence_proven
    assert not result.renderer_authorized


@pytest.mark.parametrize("display,attested,fragment,error", [
    ("A|B", False, "-", "LEGACY_TEAM_DISPLAY_SOURCE_UNATTESTED"),
    ("", True, "-", "LEGACY_TEAM_DISPLAY_MISSING"),
    ("A", True, "-", "LEGACY_TEAM_MEMBER_CARDINALITY_OR_EMPTY_TOKEN"),
    ("A|", True, "-", "LEGACY_TEAM_MEMBER_CARDINALITY_OR_EMPTY_TOKEN"),
    ("A||C", True, "-", "LEGACY_TEAM_MEMBER_CARDINALITY_OR_EMPTY_TOKEN"),
    ("A|B|C|D", True, None, "TEAM_EXTENSION_FRAGMENT_MISSING"),
])
def test_three_members_need_no_overflow_fragment():
    result = plan_qdkt_team_layout(legacy_display="A|B|C", source_attested=True, template_extension=None)
    assert result.third_and_later == ("C",)
    assert result.template_extension_required is False


def test_unproven_source_refused(display, attested, fragment, error):
    with pytest.raises(QdKtTeamLayoutBlocked, match=error):
        plan_qdkt_team_layout(
            legacy_display=display, source_attested=attested, template_extension=fragment
        )
