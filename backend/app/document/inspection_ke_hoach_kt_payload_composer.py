from __future__ import annotations

from dataclasses import dataclass

from backend.app.document.inspection_ke_hoach_kt_effective_template_contract import (
    InspectionKeHoachKtEffectiveTemplateContract,
)
from backend.app.document.inspection_ke_hoach_kt_payload_input import (
    InspectionKeHoachKtPayloadInput,
)
from backend.app.document.inspection_ke_hoach_kt_scope_suppression import (
    build_inspection_ke_hoach_kt_scope_suppression_plan,
)
from backend.app.document.inspection_ke_hoach_kt_team_projection import (
    project_inspection_ke_hoach_kt_team,
)


class InspectionKeHoachKtPayloadComposerError(RuntimeError):
    pass


@dataclass(frozen=True)
class InspectionKeHoachKtRenderPlan:
    bookmark_replacements: dict[str, str]
    delete_targets: tuple[str, ...]


def _format_date_ddmmyyyy(value) -> str:
    return f"{value.day:02d}/{value.month:02d}/{value.year:04d}"


def _source_values(
    payload: InspectionKeHoachKtPayloadInput,
    contract: InspectionKeHoachKtEffectiveTemplateContract,
) -> tuple[dict[str, str], tuple[str, ...]]:
    if payload.gxp_type != contract.gxp_type:
        raise InspectionKeHoachKtPayloadComposerError(
            "KHKT payload GxP type does not match effective template contract"
        )

    try:
        team = project_inspection_ke_hoach_kt_team(
            payload.team_members,
            separator_text=contract.team_separator_text,
        )
        scope_suppression = build_inspection_ke_hoach_kt_scope_suppression_plan(
            daychuyen=payload.daychuyen,
            contract=contract,
        )
    except RuntimeError as exc:
        raise InspectionKeHoachKtPayloadComposerError(str(exc)) from exc

    source_values: dict[str, str] = {
        "Fulldate": payload.fulldate,
        "Tencoso": payload.site_name,
        "Diadiem": payload.province_name,
        "Diadiemx": payload.diadiemx,
        "Diachicoso": payload.site_address.replace("\r\n", ";"),
        "VKNx": payload.vknx,
        "TT1x": team.tt1x,
        "TT2x": team.tt2x or "",
        "TT3x": team.tt3x or "",
        "TT_VKNx": team.tt_vknx or "",
        "TT_SYTx": team.tt_sytx or "",
        "QDKT": payload.decision_reference,
        "NgayQDKT": _format_date_ddmmyyyy(payload.decision_date),
        "Daychuyen": payload.daychuyen,
        "GioiHanPvi": payload.gioi_han_pvi,
        "TieuchuanKT": payload.applicable_standard,
    }
    if payload.dossier_code is not None:
        source_values["HsDK"] = payload.dossier_code
    if payload.submitted_on is not None:
        source_values["NgaynopHsDK"] = _format_date_ddmmyyyy(payload.submitted_on)

    delete_targets = list(scope_suppression.delete_targets)
    if team.delete_third_member:
        delete_targets.append(contract.third_member_delete_target)
    return source_values, tuple(dict.fromkeys(delete_targets))


def compose_inspection_ke_hoach_kt_render_plan(
    *,
    payload: InspectionKeHoachKtPayloadInput,
    contract: InspectionKeHoachKtEffectiveTemplateContract,
) -> InspectionKeHoachKtRenderPlan:
    """Compose only physical targets owned by the audited effective template."""

    source_values, delete_targets = _source_values(payload, contract)
    replacements: dict[str, str] = {}
    for source_name, targets in contract.scalar_targets.items():
        if not targets:
            continue
        if source_name not in source_values:
            raise InspectionKeHoachKtPayloadComposerError(
                f"KHKT active source {source_name} has no composed value"
            )
        value = source_values[source_name]
        for target in targets:
            if target in replacements:
                raise InspectionKeHoachKtPayloadComposerError(
                    f"KHKT physical bookmark target is multiply owned: {target}"
                )
            replacements[target] = value

    conflict = sorted(set(replacements) & set(delete_targets))
    if conflict:
        raise InspectionKeHoachKtPayloadComposerError(
            "KHKT render plan would both replace and delete: " + ", ".join(conflict)
        )
    return InspectionKeHoachKtRenderPlan(
        bookmark_replacements=replacements,
        delete_targets=delete_targets,
    )
