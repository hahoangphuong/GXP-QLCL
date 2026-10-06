from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models.phase1 import (
    InspectionTeam,
    InspectionTeamMember,
    InspectionTeamParticipantCatalog,
    InspectorProfile,
)
from backend.app.domain.inspection_contracts import role_code_for_sort_order


CORE_ROSTER_GROUP = "DRUG_ADMINISTRATION_AND_TRADITIONAL_MEDICINE"
CENTRAL_INSTITUTE_ROSTER_GROUPS = frozenset(
    {
        "NATIONAL_INSTITUTE_OF_DRUG_QUALITY_CONTROL",
        "HO_CHI_MINH_CITY_DRUG_QUALITY_CONTROL_INSTITUTE",
        "NATIONAL_INSTITUTE_FOR_VACCINE_AND_BIOLOGICALS_CONTROL",
    }
)
PROVINCIAL_HEALTH_ROSTER_GROUP = "PROVINCIAL_HEALTH_DEPARTMENTS"
CORE_ORGANIZATION_CATALOG_CODES = frozenset(
    {
        "ORG_REP_SCIENCE_TECH_TRAINING",
        "ORG_REP_TRADITIONAL_MEDICINE",
    }
)


class InspectionKeHoachKtTeamProjectionError(RuntimeError):
    pass


@dataclass(frozen=True)
class InspectionKeHoachKtTeamMemberInput:
    display_name: str
    sort_order: int
    role_code: str
    identity_kind: str
    roster_group: str | None = None
    participant_catalog_code: str | None = None


@dataclass(frozen=True)
class InspectionKeHoachKtTeamProjection:
    tt1x: str
    tt2x: str | None
    tt3x: str | None
    tt_vknx: str | None
    tt_sytx: str | None
    delete_third_member: bool


def _member_bucket(member: InspectionKeHoachKtTeamMemberInput) -> str:
    if member.identity_kind == "ORGANIZATION_REPRESENTATIVE":
        if member.participant_catalog_code in CORE_ORGANIZATION_CATALOG_CODES:
            return "CORE"
        raise InspectionKeHoachKtTeamProjectionError(
            "KHKT organization representative has no source-proven team bucket"
        )
    if member.identity_kind != "INSPECTOR_PROFILE":
        raise InspectionKeHoachKtTeamProjectionError(
            "KHKT team projection requires a canonical inspector profile or approved organization representative"
        )
    if member.roster_group == CORE_ROSTER_GROUP:
        return "CORE"
    if member.roster_group in CENTRAL_INSTITUTE_ROSTER_GROUPS:
        return "CENTRAL_INSTITUTE"
    if member.roster_group == PROVINCIAL_HEALTH_ROSTER_GROUP:
        return "PROVINCIAL_HEALTH"
    raise InspectionKeHoachKtTeamProjectionError(
        "KHKT inspector profile has no source-proven roster group"
    )


def _joined_tail(names: tuple[str, ...], separator_text: str) -> str | None:
    if not names:
        return None
    return (separator_text + "\r\n").join(names)


def project_inspection_ke_hoach_kt_team(
    members: tuple[InspectionKeHoachKtTeamMemberInput, ...],
    *,
    separator_text: str,
) -> InspectionKeHoachKtTeamProjection:
    """Project the legacy i=3 TT* bookmark values without inferring identities.

    Legacy TTVForm.Get_TTV2 reads the core TTviên named range separately from
    three central-institute ranges and the provincial-health range. The modern
    personnel import preserves those exact source groups in roster_group.
    """

    if not separator_text:
        raise InspectionKeHoachKtTeamProjectionError(
            "KHKT TT_ext separator text must not be blank"
        )
    ordered = tuple(sorted(members, key=lambda item: item.sort_order))
    if not ordered:
        raise InspectionKeHoachKtTeamProjectionError("KHKT inspection team is empty")
    seen_orders: set[int] = set()
    buckets: dict[str, list[str]] = {
        "CORE": [],
        "CENTRAL_INSTITUTE": [],
        "PROVINCIAL_HEALTH": [],
    }
    for member in ordered:
        name = member.display_name.strip()
        if not name:
            raise InspectionKeHoachKtTeamProjectionError(
                "KHKT inspection team contains a blank display name"
            )
        if member.sort_order in seen_orders:
            raise InspectionKeHoachKtTeamProjectionError(
                "KHKT inspection team sort_order is duplicated"
            )
        seen_orders.add(member.sort_order)
        try:
            expected_role = role_code_for_sort_order(member.sort_order)
        except ValueError as exc:
            raise InspectionKeHoachKtTeamProjectionError(str(exc)) from exc
        if member.role_code != expected_role:
            raise InspectionKeHoachKtTeamProjectionError(
                "KHKT inspection team role_code does not match canonical sort_order"
            )
        buckets[_member_bucket(member)].append(name)

    core = tuple(buckets["CORE"])
    if not core:
        raise InspectionKeHoachKtTeamProjectionError(
            "KHKT inspection team has no source-proven core member"
        )
    if ordered[0].sort_order != 1 or ordered[0].display_name.strip() != core[0]:
        raise InspectionKeHoachKtTeamProjectionError(
            "KHKT source-proven core leader must own sort_order 1"
        )

    central = tuple(buckets["CENTRAL_INSTITUTE"])
    provincial = tuple(buckets["PROVINCIAL_HEALTH"])
    return InspectionKeHoachKtTeamProjection(
        tt1x=core[0],
        tt2x=core[1] if len(core) > 1 else None,
        tt3x=_joined_tail(core[2:], separator_text),
        tt_vknx=(
            None
            if not central
            else f"{_joined_tail(central, separator_text)} "
        ),
        tt_sytx=(
            None
            if not provincial
            else f"{_joined_tail(provincial, separator_text)} "
        ),
        delete_third_member=len(core) <= 2,
    )


def load_inspection_ke_hoach_kt_team_members(
    session: Session,
    *,
    case_id: str,
) -> tuple[InspectionKeHoachKtTeamMemberInput, ...]:
    team = session.scalar(select(InspectionTeam).where(InspectionTeam.case_id == case_id))
    if team is None:
        raise InspectionKeHoachKtTeamProjectionError(
            "KHKT inspection team is not available for the case"
        )
    members = list(
        session.scalars(
            select(InspectionTeamMember)
            .where(InspectionTeamMember.team_id == team.id)
            .order_by(InspectionTeamMember.sort_order.asc(), InspectionTeamMember.id.asc())
        )
    )
    if not members:
        raise InspectionKeHoachKtTeamProjectionError("KHKT inspection team is empty")

    profile_ids = {
        member.inspector_profile_id
        for member in members
        if member.inspector_profile_id is not None
    }
    profiles = (
        {
            profile.id: profile
            for profile in session.scalars(
                select(InspectorProfile).where(InspectorProfile.id.in_(profile_ids))
            )
        }
        if profile_ids
        else {}
    )
    catalog_ids = {
        member.participant_catalog_id
        for member in members
        if member.participant_catalog_id is not None
    }
    catalogs = (
        {
            item.id: item
            for item in session.scalars(
                select(InspectionTeamParticipantCatalog).where(
                    InspectionTeamParticipantCatalog.id.in_(catalog_ids)
                )
            )
        }
        if catalog_ids
        else {}
    )

    result: list[InspectionKeHoachKtTeamMemberInput] = []
    for member in members:
        display_name = str(member.display_name or "").strip()
        identity_kind = str(member.identity_kind or "")
        if identity_kind == "INSPECTOR_PROFILE":
            profile = profiles.get(member.inspector_profile_id)
            if profile is None or not profile.is_active:
                raise InspectionKeHoachKtTeamProjectionError(
                    "KHKT inspection team references an unavailable inspector profile"
                )
            result.append(
                InspectionKeHoachKtTeamMemberInput(
                    display_name=display_name,
                    sort_order=member.sort_order,
                    role_code=str(member.role_code or ""),
                    identity_kind=identity_kind,
                    roster_group=profile.roster_group,
                )
            )
            continue
        if identity_kind == "ORGANIZATION_REPRESENTATIVE":
            catalog = catalogs.get(member.participant_catalog_id)
            if (
                catalog is None
                or not catalog.is_active
                or catalog.participant_kind != "ORGANIZATION_REPRESENTATIVE"
            ):
                raise InspectionKeHoachKtTeamProjectionError(
                    "KHKT inspection team references an unavailable organization representative"
                )
            result.append(
                InspectionKeHoachKtTeamMemberInput(
                    display_name=display_name,
                    sort_order=member.sort_order,
                    role_code=str(member.role_code or ""),
                    identity_kind=identity_kind,
                    participant_catalog_code=catalog.code,
                )
            )
            continue
        raise InspectionKeHoachKtTeamProjectionError(
            "KHKT inspection team contains a legacy or unclassified identity"
        )
    return tuple(result)
