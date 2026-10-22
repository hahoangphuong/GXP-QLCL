"""Source-bound legacy geography classification for QĐKT VKN selection.

Reuses the already validated legacy Dia_danh reference used by KHKT;
does not use current administrative codes or infer manufacturing status.
"""
from __future__ import annotations

from backend.app.document.inspection_ke_hoach_kt_province_projection import (
    InspectionKeHoachKtProvinceProjectionError,
    InspectionKeHoachKtProvinceReference,
    load_inspection_ke_hoach_kt_province_reference,
)
from backend.app.document.inspection_qd_kt_vkn_authority import (
    QdKtAuthorityBlocked,
    QdKtVknAuthority,
    select_qdkt_vkn_authority,
)


def qdkt_vkn_from_source_province(
    *, manufacture_kind: str,
    registered_province: str | None,
    reference: InspectionKeHoachKtProvinceReference | None = None,
) -> QdKtVknAuthority:
    """Return institute only for explicitly classified manufacturing and province.

    For medicine manufacturers, the geography comes solely from the verified
    source row index. Vaccine/biological manufacturers always use the national
    institute, but the registered province is still not invented or normalized.
    """
    if manufacture_kind == "VACCINE_OR_BIOLOGICAL":
        return select_qdkt_vkn_authority(
            manufacture_kind="VACCINE_OR_BIOLOGICAL", geography="UNPROVEN"
        )
    if manufacture_kind != "MEDICINE":
        raise QdKtAuthorityBlocked("MANUFACTURE_CLASSIFICATION_UNPROVEN")
    if not isinstance(registered_province, str) or not registered_province.strip():
        raise QdKtAuthorityBlocked("REGISTERED_PROVINCE_MISSING")
    source = reference or load_inspection_ke_hoach_kt_province_reference()
    matches = [
        entry for entry in source.entries
        if entry.province_name.casefold() == registered_province.strip().casefold()
    ]
    if len(matches) != 1:
        raise QdKtAuthorityBlocked("LEGACY_PROVINCE_MAPPING_UNPROVEN")
    zone = (
        "DA_NANG_AND_NORTH"
        if matches[0].legacy_index <= source.vkn_central_institute_max_legacy_index
        else "SOUTH_OF_DA_NANG"
    )
    return select_qdkt_vkn_authority(
        manufacture_kind="MEDICINE", geography=zone
    )
