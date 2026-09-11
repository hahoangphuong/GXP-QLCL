from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from backend.app.document.template_binary_binding import (
    TemplateBinaryBindingError,
    normalize_template_binary_checksum,
    normalize_template_binary_relative_path,
)


CONTRACT_PATH = Path(__file__).with_name("inspection_qd_kt_template_assets.json")
INSPECTION_QD_KT_FAMILY = "INSPECTION_QD_KT"
SUPPORTED_GXP_TYPES = frozenset({"GMP", "GLP", "GMPbb", "GSP"})


class InspectionQdKtTemplateAssetContractError(RuntimeError):
    pass


@dataclass(frozen=True)
class InspectionQdKtTemplateAsset:
    gxp_type: str
    filename: str
    storage_root: str
    storage_relative_path: str
    checksum_sha256: str


def load_inspection_qd_kt_template_assets(
    path: Path = CONTRACT_PATH,
) -> tuple[InspectionQdKtTemplateAsset, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("family_code") != INSPECTION_QD_KT_FAMILY:
        raise InspectionQdKtTemplateAssetContractError(
            "Inspection QD KT template asset contract family_code mismatch."
        )

    assets: list[InspectionQdKtTemplateAsset] = []
    seen: set[str] = set()
    for item in payload.get("assets", []):
        gxp_type = str(item.get("gxp_type") or "").strip()
        if gxp_type not in SUPPORTED_GXP_TYPES:
            raise InspectionQdKtTemplateAssetContractError(
                f"Unsupported inspection QD KT template GxP type: {gxp_type!r}."
            )
        if gxp_type in seen:
            raise InspectionQdKtTemplateAssetContractError(
                f"Duplicate inspection QD KT template GxP type: {gxp_type!r}."
            )

        filename = str(item.get("filename") or "").strip()
        storage_root = str(item.get("storage_root") or "").strip()
        if storage_root != "template":
            raise InspectionQdKtTemplateAssetContractError(
                "Inspection QD KT templates must use storage_root='template'."
            )
        try:
            relative_path = normalize_template_binary_relative_path(
                str(item.get("storage_relative_path") or "")
            )
            checksum = normalize_template_binary_checksum(
                str(item.get("checksum_sha256") or "")
            )
        except TemplateBinaryBindingError as exc:
            raise InspectionQdKtTemplateAssetContractError(str(exc)) from exc
        if not filename:
            raise InspectionQdKtTemplateAssetContractError(
                "Inspection QD KT template filename must not be blank."
            )
        if relative_path.rsplit("/", 1)[-1] != filename:
            raise InspectionQdKtTemplateAssetContractError(
                "Inspection QD KT template filename must match the relative locator basename."
            )

        seen.add(gxp_type)
        assets.append(
            InspectionQdKtTemplateAsset(
                gxp_type=gxp_type,
                filename=filename,
                storage_root=storage_root,
                storage_relative_path=relative_path,
                checksum_sha256=checksum,
            )
        )

    if seen != SUPPORTED_GXP_TYPES:
        raise InspectionQdKtTemplateAssetContractError(
            "Inspection QD KT asset contract must contain exactly GMP, GLP, GMPbb, and GSP."
        )
    return tuple(sorted(assets, key=lambda asset: asset.gxp_type))


def get_inspection_qd_kt_template_asset(gxp_type: str) -> InspectionQdKtTemplateAsset:
    normalized = str(gxp_type or "").strip()
    for asset in load_inspection_qd_kt_template_assets():
        if asset.gxp_type == normalized:
            return asset
    raise InspectionQdKtTemplateAssetContractError(
        f"No inspection QD KT template asset is defined for GxP type {normalized!r}."
    )
