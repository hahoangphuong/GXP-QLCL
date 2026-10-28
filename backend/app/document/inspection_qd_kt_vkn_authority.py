"""QĐKT VKN/VKNx institution prose from explicitly proven business atoms.

Inputs MUST be verified by a separate canonical Case/Site owner. In particular
do not infer vaccine status from company names or north/south location from
lexicographic province names. This module does not enable document creation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


ManufactureKind = Literal["VACCINE_OR_BIOLOGICAL", "MEDICINE", "UNPROVEN"]
GeoZone = Literal["DA_NANG_AND_NORTH", "SOUTH_OF_DA_NANG", "UNPROVEN"]


class QdKtAuthorityBlocked(ValueError):
    """Required VKN business atoms have not been proved."""


@dataclass(frozen=True)
class QdKtVknAuthority:
    branch: str
    vkn: str
    vknx: str


_AUTHORITY = {
    "VACCINE": QdKtVknAuthority(
        "VACCINE",
        "VKĐQG Vắc xin & Sinh phẩm y tế",
        "Viện kiểm định Quốc gia Vắc xin & Sinh phẩm y tế",
    ),
    "NORTH": QdKtVknAuthority(
        "NORTH",
        "VKN thuốc Trung ương",
        "Viện Kiểm nghiệm thuốc Trung ương",
    ),
    "SOUTH": QdKtVknAuthority(
        "SOUTH",
        "VKN thuốc Tp. Hồ Chí Minh",
        "Viện Kiểm nghiệm thuốc Tp. Hồ Chí Minh",
    ),
}


def require_qdkt_manufacture_kind(value: ManufactureKind) -> ManufactureKind:
    if type(value) is not str or value not in {"VACCINE_OR_BIOLOGICAL", "MEDICINE", "UNPROVEN"}:
        raise QdKtAuthorityBlocked("MANUFACTURE_CLASSIFICATION_UNPROVEN")
    return value


def select_qdkt_vkn_authority(
    *, manufacture_kind: ManufactureKind, geography: GeoZone
) -> QdKtVknAuthority:
    """Use source-verified classification, not an invented location heuristic."""
    manufacture_kind = require_qdkt_manufacture_kind(manufacture_kind)
    if type(geography) is not str or geography not in {"DA_NANG_AND_NORTH", "SOUTH_OF_DA_NANG", "UNPROVEN"}:
        raise QdKtAuthorityBlocked("GEOGRAPHY_CLASSIFICATION_UNPROVEN")
    if manufacture_kind == "VACCINE_OR_BIOLOGICAL":
        return _AUTHORITY["VACCINE"]
    if manufacture_kind != "MEDICINE":
        raise QdKtAuthorityBlocked("MANUFACTURE_CLASSIFICATION_UNPROVEN")
    if geography == "DA_NANG_AND_NORTH":
        return _AUTHORITY["NORTH"]
    if geography == "SOUTH_OF_DA_NANG":
        return _AUTHORITY["SOUTH"]
    raise QdKtAuthorityBlocked("GEOGRAPHY_CLASSIFICATION_UNPROVEN")
