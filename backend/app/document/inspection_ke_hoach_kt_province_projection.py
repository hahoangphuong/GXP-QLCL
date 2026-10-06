from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


REFERENCE_SCHEMA_VERSION = "inspection-ke-hoach-kt-province-reference/v1"
REFERENCE_WORKBOOK_SHA256 = "c12537ea5a5c9f470e42fb5bdbe214f36983e310fceac7c560ad38885209fe3d"
REFERENCE_NAMED_RANGE = "Dia_danh_x"
REFERENCE_RANGE = "'Địa danh'!$C$4:$H$66"

VACCINE_AUTHORITY = "Viện kiểm định Quốc gia Vắc xin & Sinh phẩm y tế"
CENTRAL_DRUG_AUTHORITY = "Viện Kiểm nghiệm thuốc Trung ương"
HCM_DRUG_AUTHORITY = "Viện Kiểm nghiệm thuốc Tp. Hồ Chí Minh"
_VACCINE_SIGNALS = ("vắc xin", "vắcxin", "vacxin", "vac xin")


class InspectionKeHoachKtProvinceProjectionError(RuntimeError):
    pass


@dataclass(frozen=True)
class InspectionKeHoachKtProvinceReferenceEntry:
    legacy_index: int
    province_name: str
    display_prefix: str | None


@dataclass(frozen=True)
class InspectionKeHoachKtProvinceReference:
    entries: tuple[InspectionKeHoachKtProvinceReferenceEntry, ...]
    vkn_central_institute_max_legacy_index: int


@dataclass(frozen=True)
class InspectionKeHoachKtProvinceProjection:
    province_name: str
    legacy_index: int
    diadiemx: str
    vknx: str


def load_inspection_ke_hoach_kt_province_reference(
    path: Path | None = None,
) -> InspectionKeHoachKtProvinceReference:
    target = path or Path(__file__).with_name("inspection_ke_hoach_kt_province_reference.json")
    payload = json.loads(target.read_text(encoding="utf-8"))
    source = payload.get("source") or {}
    if payload.get("schema_version") != REFERENCE_SCHEMA_VERSION:
        raise InspectionKeHoachKtProvinceProjectionError("KHKT province reference schema changed")
    if source.get("workbook_sha256") != REFERENCE_WORKBOOK_SHA256:
        raise InspectionKeHoachKtProvinceProjectionError("KHKT province reference workbook provenance changed")
    if source.get("named_range") != REFERENCE_NAMED_RANGE or source.get("range") != REFERENCE_RANGE:
        raise InspectionKeHoachKtProvinceProjectionError("KHKT province reference named-range provenance changed")

    raw_entries = payload.get("provinces")
    if not isinstance(raw_entries, list):
        raise InspectionKeHoachKtProvinceProjectionError("KHKT province reference entries are missing")
    entries: list[InspectionKeHoachKtProvinceReferenceEntry] = []
    for item in raw_entries:
        if not isinstance(item, dict):
            raise InspectionKeHoachKtProvinceProjectionError("KHKT province reference entry is invalid")
        entries.append(
            InspectionKeHoachKtProvinceReferenceEntry(
                legacy_index=int(item["legacy_index"]),
                province_name=str(item["province_name"]),
                display_prefix=None if item.get("display_prefix") is None else str(item["display_prefix"]),
            )
        )
    indexes = [entry.legacy_index for entry in entries]
    if indexes != list(range(1, 64)):
        raise InspectionKeHoachKtProvinceProjectionError(
            "KHKT province reference must preserve the exact 63-row legacy order"
        )
    folded_names = [entry.province_name.casefold() for entry in entries]
    if len(set(folded_names)) != len(folded_names):
        raise InspectionKeHoachKtProvinceProjectionError(
            "KHKT province reference contains duplicate province names"
        )
    cutoff = int(payload.get("vkn_central_institute_max_legacy_index", 0))
    if cutoff != 32:
        raise InspectionKeHoachKtProvinceProjectionError(
            "KHKT VKN province cutoff changed from the source-proven value"
        )
    return InspectionKeHoachKtProvinceReference(
        entries=tuple(entries),
        vkn_central_institute_max_legacy_index=cutoff,
    )


def _lookup_province(
    reference: InspectionKeHoachKtProvinceReference,
    province_name: str,
) -> InspectionKeHoachKtProvinceReferenceEntry:
    value = str(province_name or "").strip()
    matches = [
        entry for entry in reference.entries
        if entry.province_name.casefold() == value.casefold()
    ]
    if len(matches) != 1:
        raise InspectionKeHoachKtProvinceProjectionError(
            "KHKT province is outside the source-proven Dia_danh reference"
        )
    return matches[0]


def _legacy_diadiemx(
    entry: InspectionKeHoachKtProvinceReferenceEntry,
    *,
    province_name: str,
) -> str:
    # GetTT_CsCty concatenates Dia_danh_x column 2 with Tinhthanh, rewrites
    # the historical "TP " spelling, then the caller applies LCase_FirstChar.
    base = (
        str(province_name).strip()
        if entry.display_prefix is None
        else f"{entry.display_prefix.strip()} {str(province_name).strip()}"
    )
    base = base.replace("TP ", "thành phố ")
    if not base:
        raise InspectionKeHoachKtProvinceProjectionError("KHKT province display text is blank")
    return base[0].lower() + base[1:]


def _legacy_vknx(
    entry: InspectionKeHoachKtProvinceReferenceEntry,
    *,
    daychuyen: str,
    cutoff: int,
) -> str:
    scope = str(daychuyen or "").casefold()
    if any(signal.casefold() in scope for signal in _VACCINE_SIGNALS):
        return VACCINE_AUTHORITY
    if entry.legacy_index <= cutoff:
        return CENTRAL_DRUG_AUTHORITY
    return HCM_DRUG_AUTHORITY


def project_inspection_ke_hoach_kt_province(
    *,
    province_name: str,
    daychuyen: str,
    reference: InspectionKeHoachKtProvinceReference | None = None,
) -> InspectionKeHoachKtProvinceProjection:
    active_reference = reference or load_inspection_ke_hoach_kt_province_reference()
    entry = _lookup_province(active_reference, province_name)
    return InspectionKeHoachKtProvinceProjection(
        province_name=str(province_name).strip(),
        legacy_index=entry.legacy_index,
        diadiemx=_legacy_diadiemx(entry, province_name=province_name),
        vknx=_legacy_vknx(
            entry,
            daychuyen=daychuyen,
            cutoff=active_reference.vkn_central_institute_max_legacy_index,
        ),
    )
