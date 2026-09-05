from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re

DEFAULT_REGISTRY_PATH = Path(__file__).with_name("c5e_certificate_detail_source_assets.json")

ALLOWED_GXP_TYPES = ("GMP", "GLP", "GSP")
EXCLUDED_GXP_TYPES = ("GDP",)
ALLOWED_SOURCE_VARIANTS = ("certificate_9", "appendix_z3")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class CertificateDetailSourceAssetContractError(RuntimeError):
    pass


@dataclass(frozen=True)
class CertificateDetailSourceAsset:
    source_variant: str
    gxp_type: str
    filename: str
    sha256: str


def _validate_asset(asset: CertificateDetailSourceAsset) -> None:
    if asset.gxp_type in EXCLUDED_GXP_TYPES:
        raise CertificateDetailSourceAssetContractError(
            f"{asset.gxp_type} is explicitly excluded from C.5e certificate-detail scope."
        )
    if asset.gxp_type not in ALLOWED_GXP_TYPES:
        raise CertificateDetailSourceAssetContractError(
            f"Unsupported C.5e GxP type: {asset.gxp_type!r}."
        )
    if asset.source_variant not in ALLOWED_SOURCE_VARIANTS:
        raise CertificateDetailSourceAssetContractError(
            f"Unsupported C.5e source variant: {asset.source_variant!r}."
        )
    if not asset.filename or "/" in asset.filename or "\\" in asset.filename:
        raise CertificateDetailSourceAssetContractError(
            "C.5e source asset filename must be a basename only."
        )
    if not _SHA256_RE.fullmatch(asset.sha256):
        raise CertificateDetailSourceAssetContractError(
            f"Invalid SHA256 for {asset.filename!r}."
        )


def load_source_asset_registry(
    path: Path = DEFAULT_REGISTRY_PATH,
) -> tuple[CertificateDetailSourceAsset, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "c5e-certificate-detail-source-assets/v1":
        raise CertificateDetailSourceAssetContractError("Unsupported C.5e source-asset registry schema.")

    scope = payload.get("scope") or {}
    if tuple(scope.get("gxp_types") or ()) != ALLOWED_GXP_TYPES:
        raise CertificateDetailSourceAssetContractError(
            "C.5e source-asset registry must contain exactly GMP/GLP/GSP in that order."
        )
    if tuple(scope.get("excluded_gxp_types") or ()) != EXCLUDED_GXP_TYPES:
        raise CertificateDetailSourceAssetContractError(
            "C.5e source-asset registry must explicitly exclude GDP."
        )
    if tuple(scope.get("source_variants") or ()) != ALLOWED_SOURCE_VARIANTS:
        raise CertificateDetailSourceAssetContractError(
            "C.5e source-asset registry source variants do not match the contract."
        )

    assets = tuple(
        CertificateDetailSourceAsset(
            source_variant=str(item["source_variant"]),
            gxp_type=str(item["gxp_type"]),
            filename=str(item["filename"]),
            sha256=str(item["sha256"]).lower(),
        )
        for item in payload.get("assets") or ()
    )
    for asset in assets:
        _validate_asset(asset)

    expected_keys = {
        (source_variant, gxp_type)
        for source_variant in ALLOWED_SOURCE_VARIANTS
        for gxp_type in ALLOWED_GXP_TYPES
    }
    actual_keys = {(asset.source_variant, asset.gxp_type) for asset in assets}
    if len(actual_keys) != len(assets):
        raise CertificateDetailSourceAssetContractError(
            "Duplicate C.5e source asset key detected."
        )
    if actual_keys != expected_keys:
        missing = sorted(expected_keys - actual_keys)
        extra = sorted(actual_keys - expected_keys)
        raise CertificateDetailSourceAssetContractError(
            f"C.5e source-asset matrix must be exactly 2x3; missing={missing}, extra={extra}."
        )

    filenames = [asset.filename for asset in assets]
    if len(set(filenames)) != len(filenames):
        raise CertificateDetailSourceAssetContractError(
            "C.5e source asset filenames must be unique."
        )
    return assets


def resolve_source_asset(
    *,
    source_variant: str,
    gxp_type: str,
    registry: tuple[CertificateDetailSourceAsset, ...] | None = None,
) -> CertificateDetailSourceAsset:
    if gxp_type in EXCLUDED_GXP_TYPES:
        raise CertificateDetailSourceAssetContractError(
            "GDP is outside C.5e certificate-detail scope."
        )
    assets = registry if registry is not None else load_source_asset_registry()
    matches = [
        asset
        for asset in assets
        if asset.source_variant == source_variant and asset.gxp_type == gxp_type
    ]
    if len(matches) != 1:
        raise CertificateDetailSourceAssetContractError(
            f"Expected exactly one C.5e source asset for "
            f"source_variant={source_variant!r}, gxp_type={gxp_type!r}; found {len(matches)}."
        )
    return matches[0]


def verify_source_asset_bytes(
    asset: CertificateDetailSourceAsset,
    payload: bytes,
) -> None:
    actual = hashlib.sha256(payload).hexdigest()
    if actual != asset.sha256:
        raise CertificateDetailSourceAssetContractError(
            f"C.5e source asset checksum mismatch for {asset.filename!r}: "
            f"expected={asset.sha256}, actual={actual}."
        )
