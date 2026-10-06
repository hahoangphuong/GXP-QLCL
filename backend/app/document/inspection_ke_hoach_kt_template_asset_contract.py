from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from backend.app.document.template_binary_binding import (
    TemplateBinaryBindingError,
    normalize_template_binary_checksum,
    normalize_template_binary_relative_path,
)


CONTRACT_PATH = Path(__file__).with_name("inspection_ke_hoach_kt_template_assets.json")
INSPECTION_KE_HOACH_KT_FAMILY = "INSPECTION_KE_HOACH_KT"
SUPPORTED_GXP_TYPES = frozenset({"GMP", "GLP", "GMPbb", "GSP"})


class InspectionKeHoachKtTemplateAssetContractError(RuntimeError):
    pass


@dataclass(frozen=True)
class InspectionKeHoachKtTemplateAsset:
    gxp_type: str
    filename: str
    storage_root: str
    storage_relative_path: str
    checksum_sha256: str


def load_inspection_ke_hoach_kt_template_assets(
    path: Path = CONTRACT_PATH,
) -> tuple[InspectionKeHoachKtTemplateAsset, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("family_code") != INSPECTION_KE_HOACH_KT_FAMILY:
        raise InspectionKeHoachKtTemplateAssetContractError(
            "Inspection KHKT template asset contract family_code mismatch."
        )

    assets: list[InspectionKeHoachKtTemplateAsset] = []
    seen: set[str] = set()
    for item in payload.get("assets", []):
        gxp_type = str(item.get("gxp_type") or "").strip()
        if gxp_type not in SUPPORTED_GXP_TYPES:
            raise InspectionKeHoachKtTemplateAssetContractError(
                f"Unsupported inspection KHKT template GxP type: {gxp_type!r}."
            )
        if gxp_type in seen:
            raise InspectionKeHoachKtTemplateAssetContractError(
                f"Duplicate inspection KHKT template GxP type: {gxp_type!r}."
            )

        filename = str(item.get("filename") or "").strip()
        storage_root = str(item.get("storage_root") or "").strip()
        if storage_root != "template":
            raise InspectionKeHoachKtTemplateAssetContractError(
                "Inspection KHKT templates must use storage_root='template'."
            )
        try:
            relative_path = normalize_template_binary_relative_path(
                str(item.get("storage_relative_path") or "")
            )
            checksum = normalize_template_binary_checksum(
                str(item.get("checksum_sha256") or "")
            )
        except TemplateBinaryBindingError as exc:
            raise InspectionKeHoachKtTemplateAssetContractError(str(exc)) from exc
        if not filename:
            raise InspectionKeHoachKtTemplateAssetContractError(
                "Inspection KHKT template filename must not be blank."
            )
        if relative_path.rsplit("/", 1)[-1] != filename:
            raise InspectionKeHoachKtTemplateAssetContractError(
                "Inspection KHKT template filename must match the relative locator basename."
            )

        seen.add(gxp_type)
        assets.append(
            InspectionKeHoachKtTemplateAsset(
                gxp_type=gxp_type,
                filename=filename,
                storage_root=storage_root,
                storage_relative_path=relative_path,
                checksum_sha256=checksum,
            )
        )

    if seen != SUPPORTED_GXP_TYPES:
        raise InspectionKeHoachKtTemplateAssetContractError(
            "Inspection KHKT asset contract must contain exactly GMP, GLP, GMPbb, and GSP."
        )
    return tuple(sorted(assets, key=lambda asset: asset.gxp_type))


def get_inspection_ke_hoach_kt_template_asset(
    gxp_type: str,
) -> InspectionKeHoachKtTemplateAsset:
    normalized = str(gxp_type or "").strip()
    for asset in load_inspection_ke_hoach_kt_template_assets():
        if asset.gxp_type == normalized:
            return asset
    raise InspectionKeHoachKtTemplateAssetContractError(
        f"No inspection KHKT template asset is defined for GxP type {normalized!r}."
    )


def get_inspection_ke_hoach_kt_output_filename(gxp_type: str) -> str:
    """Return the backend-owned editable output filename for a KHKT template variant."""
    filename = get_inspection_ke_hoach_kt_template_asset(gxp_type).filename
    if not filename.casefold().endswith(".dotx"):
        raise InspectionKeHoachKtTemplateAssetContractError(
            "Inspection KHKT template filename must end with .dotx to derive editable output."
        )
    return filename[:-5] + ".docx"
