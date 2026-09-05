from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from backend.app.document.c5e_certificate_detail_docx_render import (
    CertificateDetailDocxRenderError,
    CertificateDetailDocxRenderResult,
    build_certificate_detail_docx_bytes,
)
from backend.app.document.c5e_certificate_detail_semantic_projection import (
    CERTIFICATE_DETAIL_FAMILY,
    CERTIFICATE_DETAIL_SOURCE_VARIANT,
    CertificateDetailSemanticProjection,
)
from backend.app.document.c5e_certificate_detail_source_asset_locator import (
    CertificateDetailSourceAssetLocator,
    CertificateDetailSourceAssetLocatorError,
    build_source_asset_requirement,
    open_verified_source_asset_stream,
)


if TYPE_CHECKING:
    from backend.app.storage.types import StorageServiceProtocol


SUPPORTED_GXP_TYPES = frozenset(
    {
        "GMP",
        "GLP",
        "GSP",
    }
)


class CertificateDetailRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True)
class CertificateDetailRuntimeResult:
    render_result: CertificateDetailDocxRenderResult
    source_storage_root: str
    source_storage_relative_path: str
    source_checksum_sha256: str
    source_readiness_status: str


def _validate_runtime_boundary(
    *,
    projection: CertificateDetailSemanticProjection,
    source_locator: CertificateDetailSourceAssetLocator,
) -> None:
    if projection.family_code != CERTIFICATE_DETAIL_FAMILY:
        raise CertificateDetailRuntimeError(
            "C.5e certificate-detail runtime only supports "
            f"family_code={CERTIFICATE_DETAIL_FAMILY!r}; "
            f"got {projection.family_code!r}."
        )

    if projection.source_variant != CERTIFICATE_DETAIL_SOURCE_VARIANT:
        raise CertificateDetailRuntimeError(
            "C.5e certificate-detail runtime only supports "
            f"projection source_variant={CERTIFICATE_DETAIL_SOURCE_VARIANT!r}; "
            f"got {projection.source_variant!r}."
        )

    if source_locator.source_variant != CERTIFICATE_DETAIL_SOURCE_VARIANT:
        raise CertificateDetailRuntimeError(
            "C.5e certificate-detail runtime only supports "
            f"source locator variant={CERTIFICATE_DETAIL_SOURCE_VARIANT!r}; "
            f"got {source_locator.source_variant!r}."
        )

    if projection.gxp_type not in SUPPORTED_GXP_TYPES:
        raise CertificateDetailRuntimeError(
            "Unsupported C.5e certificate-detail projection GxP type: "
            f"{projection.gxp_type!r}."
        )

    if source_locator.gxp_type not in SUPPORTED_GXP_TYPES:
        raise CertificateDetailRuntimeError(
            "Unsupported C.5e certificate-detail source GxP type: "
            f"{source_locator.gxp_type!r}."
        )

    if projection.gxp_type != source_locator.gxp_type:
        raise CertificateDetailRuntimeError(
            "C.5e certificate-detail projection/source GxP mismatch: "
            f"projection={projection.gxp_type!r}, "
            f"source={source_locator.gxp_type!r}."
        )

    if source_locator.storage_root != "template":
        raise CertificateDetailRuntimeError(
            "C.5e certificate-detail source asset must use "
            "storage_root='template'; "
            f"got {source_locator.storage_root!r}."
        )

    if not source_locator.storage_relative_path:
        raise CertificateDetailRuntimeError(
            "C.5e certificate-detail source asset relative path "
            "must not be blank."
        )

    if not source_locator.original_filename:
        raise CertificateDetailRuntimeError(
            "C.5e certificate-detail source asset filename "
            "must not be blank."
        )

    if (
        not isinstance(source_locator.checksum_sha256, str)
        or len(source_locator.checksum_sha256) != 64
    ):
        raise CertificateDetailRuntimeError(
            "C.5e certificate-detail source asset SHA256 "
            "must be exactly 64 hexadecimal characters."
        )


def build_certificate_detail_runtime_docx(
    storage: "StorageServiceProtocol",
    *,
    destination_template_bytes: bytes,
    projection: CertificateDetailSemanticProjection,
    source_locator: CertificateDetailSourceAssetLocator,
) -> CertificateDetailRuntimeResult:
    """
    Runtime owner for the legacy Input_DC_to_CC certificate-detail region.

    Responsibilities:
    - validate the already-resolved C.5e source locator against projection;
    - construct the source-asset requirement;
    - open the source through the verified locator/checksum boundary;
    - pass verified source bytes to the deterministic DOCX assembly owner.

    Deliberately not responsible for:
    - selecting the source asset from registry;
    - loading canonical evaluation scope from DB;
    - creating semantic projection;
    - resolving destination TemplateDefinition;
    - scalar/table rendering;
    - output persistence/finalization;
    - GDP;
    - appendix_z3;
    - unkeyed_entries.
    """

    _validate_runtime_boundary(
        projection=projection,
        source_locator=source_locator,
    )

    try:
        requirement = build_source_asset_requirement(
            source_locator
        )
    except CertificateDetailSourceAssetLocatorError as exc:
        raise CertificateDetailRuntimeError(
            "C.5e certificate-detail source requirement "
            f"could not be built: {exc}"
        ) from exc

    if requirement.readiness_status != "direct_stream_ready":
        raise CertificateDetailRuntimeError(
            "C.5e certificate-detail source asset is not ready: "
            f"{requirement.readiness_status}: {requirement.detail}"
        )

    try:
        with open_verified_source_asset_stream(
            storage,
            requirement,
        ) as stream:
            source_docx_bytes = stream.read()
    except CertificateDetailSourceAssetLocatorError as exc:
        raise CertificateDetailRuntimeError(
            "C.5e certificate-detail source asset verification failed: "
            f"{exc}"
        ) from exc

    if not source_docx_bytes:
        raise CertificateDetailRuntimeError(
            "C.5e certificate-detail verified source asset is empty."
        )

    try:
        render_result = build_certificate_detail_docx_bytes(
            destination_template_bytes,
            source_docx_bytes=source_docx_bytes,
            projection=projection,
        )
    except CertificateDetailDocxRenderError as exc:
        raise CertificateDetailRuntimeError(
            "C.5e certificate-detail DOCX assembly failed: "
            f"{exc}"
        ) from exc

    return CertificateDetailRuntimeResult(
        render_result=render_result,
        source_storage_root=requirement.storage_root,
        source_storage_relative_path=requirement.storage_relative_path,
        source_checksum_sha256=source_locator.checksum_sha256,
        source_readiness_status=requirement.readiness_status,
    )