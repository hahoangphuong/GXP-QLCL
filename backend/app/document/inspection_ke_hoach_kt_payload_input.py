from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models.phase1 import Case, CaseApplication, InspectionPlan, Site
from backend.app.domain.evaluation_scope_document_projection import (
    project_vba_document_scope_fields,
)
from backend.app.document.evaluation_scope_payload import (
    load_c5e_evaluation_scope_projection_input,
)
from backend.app.document.inspection_ke_hoach_kt_generation_date import (
    project_inspection_ke_hoach_kt_generation_date,
)
from backend.app.document.inspection_ke_hoach_kt_province_projection import (
    project_inspection_ke_hoach_kt_province,
)
from backend.app.document.inspection_ke_hoach_kt_team_projection import (
    InspectionKeHoachKtTeamMemberInput,
    load_inspection_ke_hoach_kt_team_members,
)


FAMILY_CODE = "INSPECTION_KE_HOACH_KT"


class InspectionKeHoachKtPayloadInputError(RuntimeError):
    pass


@dataclass(frozen=True)
class InspectionKeHoachKtPayloadInput:
    case_id: str
    gxp_type: str
    site_name: str
    site_address: str
    province_name: str
    dossier_code: str | None
    submitted_on: datetime | None
    decision_reference: str
    decision_date: date
    applicable_standard: str
    daychuyen: str
    gioi_han_pvi: str
    diadiemx: str
    vknx: str
    team_members: tuple[InspectionKeHoachKtTeamMemberInput, ...]
    generated_on: date
    fulldate: str


def _required_text(value: object, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise InspectionKeHoachKtPayloadInputError(f"KHKT canonical {label} is missing")
    return text


def _load_case_application(session: Session, case_id: str) -> CaseApplication | None:
    return session.scalar(
        select(CaseApplication).where(CaseApplication.case_id == case_id)
    )


def _load_inspection_plan(session: Session, case_id: str) -> InspectionPlan:
    row = session.scalar(
        select(InspectionPlan).where(InspectionPlan.case_id == case_id)
    )
    if row is None:
        raise InspectionKeHoachKtPayloadInputError(
            "KHKT canonical inspection plan is missing"
        )
    return row


def load_inspection_ke_hoach_kt_payload_input(
    session: Session,
    *,
    case_id: str,
    generated_at: datetime,
) -> InspectionKeHoachKtPayloadInput:
    """Load the canonical owner-backed input aggregate for KHKT generation.

    This boundary deliberately performs no generic caller-payload fallback.
    Every value comes from a canonical owner or a previously proven projection.
    """

    case = session.get(Case, case_id)
    if case is None:
        raise InspectionKeHoachKtPayloadInputError("KHKT case was not found")

    site = session.get(Site, case.site_id)
    if site is None:
        raise InspectionKeHoachKtPayloadInputError("KHKT canonical site is missing")

    application = _load_case_application(session, case.id)
    plan = _load_inspection_plan(session, case.id)

    site_name = _required_text(site.site_name, "site_name")
    site_address = _required_text(site.site_address, "site_address")
    province_name = _required_text(site.province_name, "province_name")
    decision_reference = _required_text(plan.decision_reference, "decision_reference")
    if plan.decision_date is None:
        raise InspectionKeHoachKtPayloadInputError(
            "KHKT canonical decision_date is missing"
        )
    applicable_standard = _required_text(
        case.applicable_standard,
        "applicable_standard",
    )

    scope_input = load_c5e_evaluation_scope_projection_input(
        session,
        case_id=case.id,
    )
    try:
        scope = project_vba_document_scope_fields(
            family_code=FAMILY_CODE,
            blocks=scope_input.blocks,
            taxonomy_nodes=scope_input.taxonomy_nodes,
            limitation_text=scope_input.limitation_text,
            gxp_type=scope_input.gxp_type,
        )
    except (AssertionError, ValueError) as exc:
        raise InspectionKeHoachKtPayloadInputError(str(exc)) from exc
    daychuyen = _required_text(scope.fields.get("Daychuyen"), "Daychuyen")
    gioi_han_pvi = _required_text(
        scope.fields.get("GioiHanPvi"),
        "GioiHanPvi",
    )

    try:
        province = project_inspection_ke_hoach_kt_province(
            province_name=province_name,
            daychuyen=daychuyen,
        )
        team_members = load_inspection_ke_hoach_kt_team_members(
            session,
            case_id=case.id,
        )
        generation_date = project_inspection_ke_hoach_kt_generation_date(
            generated_at
        )
    except RuntimeError as exc:
        raise InspectionKeHoachKtPayloadInputError(str(exc)) from exc

    return InspectionKeHoachKtPayloadInput(
        case_id=case.id,
        gxp_type=_required_text(case.gxp_type, "gxp_type"),
        site_name=site_name,
        site_address=site_address,
        province_name=province_name,
        dossier_code=(
            None
            if application is None or not str(application.dossier_code or "").strip()
            else str(application.dossier_code).strip()
        ),
        submitted_on=None if application is None else application.submitted_on,
        decision_reference=decision_reference,
        decision_date=plan.decision_date,
        applicable_standard=applicable_standard,
        daychuyen=daychuyen,
        gioi_han_pvi=gioi_han_pvi,
        diadiemx=province.diadiemx,
        vknx=province.vknx,
        team_members=team_members,
        generated_on=generation_date.generated_on,
        fulldate=generation_date.fulldate,
    )
