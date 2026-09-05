from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from backend.app.project_paths import phase_artifact_path


CONTRACT_PATH = Path(__file__).with_name("c5e_certificate_destination_assets.json")
CERTIFICATE_DETAIL_FAMILY = "CERTIFICATE_ISSUANCE_WORD"
SUPPORTED_GXP_TYPES = frozenset({"GMP", "GLP"})


class CertificateDestinationAssetContractError(RuntimeError):
    pass


@dataclass(frozen=True)
class CertificateDestinationAsset:
    gxp_type: str
    filename: str
    storage_root: str
    storage_relative_path: str
    checksum_sha256: str


def load_certificate_destination_assets(
    path: Path = CONTRACT_PATH,
) -> tuple[CertificateDestinationAsset, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("family_code") != CERTIFICATE_DETAIL_FAMILY:
        raise CertificateDestinationAssetContractError(
            "C.5e destination asset contract family_code mismatch."
        )

    assets: list[CertificateDestinationAsset] = []
    seen: set[str] = set()
    for item in payload.get("assets", []):
        gxp_type = str(item.get("gxp_type") or "").strip()
        if gxp_type not in SUPPORTED_GXP_TYPES:
            raise CertificateDestinationAssetContractError(
                f"Unsupported C.5e destination asset GxP type: {gxp_type!r}."
            )
        if gxp_type in seen:
            raise CertificateDestinationAssetContractError(
                f"Duplicate C.5e destination asset GxP type: {gxp_type!r}."
            )
        seen.add(gxp_type)

        storage_root = str(item.get("storage_root") or "").strip()
        if storage_root != "template":
            raise CertificateDestinationAssetContractError(
                "C.5e destination assets must use storage_root='template'."
            )

        relative_path = str(item.get("storage_relative_path") or "").strip()
        filename = str(item.get("filename") or "").strip()
        checksum = str(item.get("checksum_sha256") or "").strip().lower()
        if not relative_path or not filename:
            raise CertificateDestinationAssetContractError(
                "C.5e destination asset filename/path must not be blank."
            )
        if len(checksum) != 64 or any(ch not in "0123456789abcdef" for ch in checksum):
            raise CertificateDestinationAssetContractError(
                "C.5e destination asset checksum must be a lowercase SHA256 hex digest."
            )

        assets.append(
            CertificateDestinationAsset(
                gxp_type=gxp_type,
                filename=filename,
                storage_root=storage_root,
                storage_relative_path=relative_path,
                checksum_sha256=checksum,
            )
        )

    if seen != SUPPORTED_GXP_TYPES:
        raise CertificateDestinationAssetContractError(
            "C.5e destination asset contract must contain exactly GMP and GLP."
        )

    return tuple(sorted(assets, key=lambda asset: asset.gxp_type))


def get_certificate_destination_asset(gxp_type: str) -> CertificateDestinationAsset:
    normalized = str(gxp_type or "").strip().upper()
    for asset in load_certificate_destination_assets():
        if asset.gxp_type == normalized:
            return asset
    raise CertificateDestinationAssetContractError(
        f"No production-enabled C.5e destination asset for GxP type {normalized!r}."
    )
