from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from io import BytesIO
from typing import BinaryIO, Iterator

from backend.app.document.c5e_certificate_detail_source_asset_contract import (
    CertificateDetailSourceAsset,
    CertificateDetailSourceAssetContractError,
    resolve_source_asset,
    verify_source_asset_bytes,
)
from backend.app.storage.types import StorageServiceProtocol


CERTIFICATE_DETAIL_RUNTIME_PREFIX = "c5e_certificate_detail"
CERTIFICATE_DETAIL_RUNTIME_VARIANT = "certificate_9"


class CertificateDetailSourceAssetLocatorError(RuntimeError):
    pass


@dataclass(frozen=True)
class CertificateDetailSourceAssetLocator:
    source_variant: str
    gxp_type: str
    storage_root: str
    storage_relative_path: str
    original_filename: str
    checksum_sha256: str


@dataclass(frozen=True)
class CertificateDetailSourceAssetRequirement:
    asset: CertificateDetailSourceAsset
    storage_root: str
    storage_relative_path: str
    readiness_status: str
    detail: str


def _normalize_relative_path(value: str) -> str:
    normalized = (
        str(value or "")
        .replace("\\", "/")
        .strip()
        .strip("/")
    )

    if not normalized:
        raise CertificateDetailSourceAssetLocatorError(
            "C.5e source asset storage path must not be blank."
        )

    parts = [
        part
        for part in normalized.split("/")
        if part not in {"", "."}
    ]

    if any(part == ".." for part in parts):
        raise CertificateDetailSourceAssetLocatorError(
            "C.5e source asset path traversal is not allowed."
        )

    return "/".join(parts)


def build_runtime_source_asset_locator(
    *,
    gxp_type: str,
) -> CertificateDetailSourceAssetLocator:
    """
    Resolve the production certificate_9 asset and map it to its
    deterministic location under the configured template root.

    appendix_z3 is intentionally not exposed by this runtime factory.
    """

    try:
        asset = resolve_source_asset(
            source_variant=CERTIFICATE_DETAIL_RUNTIME_VARIANT,
            gxp_type=gxp_type,
        )
    except CertificateDetailSourceAssetContractError as exc:
        raise CertificateDetailSourceAssetLocatorError(
            str(exc)
        ) from exc

    relative_path = _normalize_relative_path(
        f"{CERTIFICATE_DETAIL_RUNTIME_PREFIX}/{asset.filename}"
    )

    return CertificateDetailSourceAssetLocator(
        source_variant=asset.source_variant,
        gxp_type=asset.gxp_type,
        storage_root="template",
        storage_relative_path=relative_path,
        original_filename=asset.filename,
        checksum_sha256=asset.sha256,
    )


def build_source_asset_requirement(
    locator: CertificateDetailSourceAssetLocator,
) -> CertificateDetailSourceAssetRequirement:
    if locator.storage_root != "template":
        raise CertificateDetailSourceAssetLocatorError(
            "C.5e source assets must use storage_root='template'."
        )

    try:
        asset = resolve_source_asset(
            source_variant=locator.source_variant,
            gxp_type=locator.gxp_type,
        )
    except CertificateDetailSourceAssetContractError as exc:
        raise CertificateDetailSourceAssetLocatorError(
            str(exc)
        ) from exc

    normalized_path = _normalize_relative_path(
        locator.storage_relative_path
    )

    if locator.original_filename != asset.filename:
        raise CertificateDetailSourceAssetLocatorError(
            "C.5e source asset filename mismatch: "
            f"expected={asset.filename!r}, "
            f"actual={locator.original_filename!r}."
        )

    if locator.checksum_sha256.lower() != asset.sha256:
        raise CertificateDetailSourceAssetLocatorError(
            "C.5e source asset locator checksum mismatch for "
            f"{asset.filename!r}."
        )

    return CertificateDetailSourceAssetRequirement(
        asset=asset,
        storage_root="template",
        storage_relative_path=normalized_path,
        readiness_status="direct_stream_ready",
        detail=(
            "C.5e source asset locator matches the audited registry "
            "and is ready for checksum-verified StorageService access."
        ),
    )


@contextmanager
def open_verified_source_asset_stream(
    storage: StorageServiceProtocol,
    requirement: CertificateDetailSourceAssetRequirement,
) -> Iterator[BinaryIO]:
    if requirement.readiness_status != "direct_stream_ready":
        raise CertificateDetailSourceAssetLocatorError(
            "C.5e source asset is not ready: "
            f"{requirement.readiness_status}."
        )

    with storage.read_stream(
        requirement.storage_relative_path,
        root=requirement.storage_root,
    ) as stream:
        payload = stream.read()

    try:
        verify_source_asset_bytes(
            requirement.asset,
            payload,
        )
    except CertificateDetailSourceAssetContractError as exc:
        raise CertificateDetailSourceAssetLocatorError(
            str(exc)
        ) from exc

    verified_stream = BytesIO(payload)

    try:
        yield verified_stream
    finally:
        verified_stream.close()