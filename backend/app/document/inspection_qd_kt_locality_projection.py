"""Read-only QĐKT locality display from the source-attested legacy province.

This does not assume Site.province_name equals the selected VBA planning row.
It never enables a render endpoint or writes data.
"""
from __future__ import annotations
from dataclasses import dataclass

from backend.app.document.inspection_ke_hoach_kt_province_projection import (
    InspectionKeHoachKtProvinceReference,
    InspectionKeHoachKtProvinceProjectionError,
    load_inspection_ke_hoach_kt_province_reference,
)


class QdKtLocationBlocked(ValueError):
    pass


@dataclass(frozen=True)
class QdKtLocalityAtoms:
    diadiem: str
    diadiemx: str
    legacy_province_index: int
    case_source_equivalence_verified: bool = False
    ready_to_render: bool = False


def project_qdkt_locality_from_attested_legacy(
    *, planning_row_province: str, source_attested: bool,
    reference: InspectionKeHoachKtProvinceReference | None = None,
) -> QdKtLocalityAtoms:
    """Project the known i=2 VBA province presentation, not a Site guess.

    Source evidence: RecordForm.frm:745-746 uses Tinhthanh and LCase_FirstChar
    of Tinhthanhx; Module1.bas:614-632 uses Dia_danh/Dia_danh_x index and
    spelling rewrite. The *provenance* of a live Case's planning-row field
    remains a separate unresolved owner boundary.
    """
    if source_attested is not True:
        raise QdKtLocationBlocked("QDKT_PLANNING_ROW_PROVINCE_UNATTESTED")
    if not isinstance(planning_row_province, str) or not planning_row_province.strip():
        raise QdKtLocationBlocked("QDKT_PLANNING_ROW_PROVINCE_MISSING")
    if planning_row_province != planning_row_province.strip():
        raise QdKtLocationBlocked("QDKT_PLANNING_ROW_PROVINCE_UNNORMALIZED")
    try:
        source = reference or load_inspection_ke_hoach_kt_province_reference()
        matches = [
            e for e in source.entries
            if e.province_name.casefold() == planning_row_province.casefold()
        ]
        if len(matches) != 1:
            raise QdKtLocationBlocked("QDKT_LEGACY_PROVINCE_NOT_UNIQUE")
        entry = matches[0]
        prefix = entry.display_prefix
        value = planning_row_province if prefix is None else f"{prefix.strip()} {planning_row_province}"
        value = value.replace("TP ", "thành phố ")
        if not value.strip():
            raise QdKtLocationBlocked("QDKT_LOCALITY_DISPLAY_EMPTY")
        diadiemx = value[0].lower() + value[1:]
        return QdKtLocalityAtoms(
            diadiem=planning_row_province,
            diadiemx=diadiemx,
            legacy_province_index=entry.legacy_index,
        )
    except InspectionKeHoachKtProvinceProjectionError as exc:
        raise QdKtLocationBlocked("QDKT_LEGACY_REFERENCE_UNPROVEN") from exc
