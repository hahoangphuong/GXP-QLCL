from __future__ import annotations

import pytest

from backend.app.document.inspection_ke_hoach_kt_team_projection import (
    CORE_ROSTER_GROUP,
    InspectionKeHoachKtTeamMemberInput,
    InspectionKeHoachKtTeamProjectionError,
    project_inspection_ke_hoach_kt_team,
)


def _member(
    name: str,
    order: int,
    *,
    group: str | None = CORE_ROSTER_GROUP,
    identity_kind: str = "INSPECTOR_PROFILE",
    catalog_code: str | None = None,
) -> InspectionKeHoachKtTeamMemberInput:
    return InspectionKeHoachKtTeamMemberInput(
        display_name=name,
        sort_order=order,
        role_code="LEADER" if order == 1 else "SECRETARY" if order == 2 else "MEMBER",
        identity_kind=identity_kind,
        roster_group=group,
        participant_catalog_code=catalog_code,
    )


def test_team_projection_partitions_source_proven_roster_groups():
    projection = project_inspection_ke_hoach_kt_team(
        (
            _member("Trưởng đoàn", 1),
            _member("Thành viên", 2),
            _member(
                "Viện TW",
                3,
                group="NATIONAL_INSTITUTE_OF_DRUG_QUALITY_CONTROL",
            ),
            _member(
                "Sở Y tế",
                4,
                group="PROVINCIAL_HEALTH_DEPARTMENTS",
            ),
        ),
        separator_text=" – Thành viên;",
    )

    assert projection.tt1x == "Trưởng đoàn"
    assert projection.tt2x == "Thành viên"
    assert projection.tt3x is None
    assert projection.delete_third_member is True
    assert projection.tt_vknx == "Viện TW "
    assert projection.tt_sytx == "Sở Y tế "


def test_team_projection_preserves_legacy_separator_and_crlf_for_tail_members():
    projection = project_inspection_ke_hoach_kt_team(
        (
            _member("A", 1),
            _member("B", 2),
            _member("C", 3),
            _member("D", 4),
            _member(
                "E",
                5,
                group="HO_CHI_MINH_CITY_DRUG_QUALITY_CONTROL_INSTITUTE",
            ),
            _member(
                "F",
                6,
                group="NATIONAL_INSTITUTE_FOR_VACCINE_AND_BIOLOGICALS_CONTROL",
            ),
        ),
        separator_text=" – Thành viên;",
    )

    assert projection.tt3x == "C – Thành viên;\r\nD"
    assert projection.delete_third_member is False
    assert projection.tt_vknx == "E – Thành viên;\r\nF "


def test_team_projection_keeps_approved_organization_representatives_in_core_team():
    projection = project_inspection_ke_hoach_kt_team(
        (
            _member("A", 1),
            _member(
                "Đại diện Cục KHCNĐT",
                2,
                group=None,
                identity_kind="ORGANIZATION_REPRESENTATIVE",
                catalog_code="ORG_REP_SCIENCE_TECH_TRAINING",
            ),
        ),
        separator_text=" – Thành viên;",
    )

    assert projection.tt2x == "Đại diện Cục KHCNĐT"
    assert projection.delete_third_member is True


@pytest.mark.parametrize(
    "member",
    [
        _member("Unknown group", 2, group=None),
        _member(
            "Unknown org",
            2,
            group=None,
            identity_kind="ORGANIZATION_REPRESENTATIVE",
            catalog_code="ORG_REP_UNKNOWN",
        ),
        _member("Legacy", 2, group=None, identity_kind="LEGACY_PERSON"),
    ],
)
def test_team_projection_fails_closed_when_member_bucket_is_not_source_proven(member):
    with pytest.raises(InspectionKeHoachKtTeamProjectionError):
        project_inspection_ke_hoach_kt_team(
            (_member("A", 1), member),
            separator_text=" – Thành viên;",
        )


def test_team_projection_fails_closed_when_core_leader_is_missing():
    with pytest.raises(
        InspectionKeHoachKtTeamProjectionError,
        match="core leader",
    ):
        project_inspection_ke_hoach_kt_team(
            (
                _member(
                    "Viện trưởng nhóm",
                    1,
                    group="NATIONAL_INSTITUTE_OF_DRUG_QUALITY_CONTROL",
                ),
                _member("Core member", 2),
            ),
            separator_text=" – Thành viên;",
        )
