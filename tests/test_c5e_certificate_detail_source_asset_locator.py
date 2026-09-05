from __future__ import annotations

from contextlib import contextmanager
from io import BytesIO

import pytest

from backend.app.document.c5e_certificate_detail_source_asset_contract import (
    resolve_source_asset,
)
from backend.app.document.c5e_certificate_detail_source_asset_locator import (
    CertificateDetailSourceAssetLocator,
    CertificateDetailSourceAssetLocatorError,
    build_source_asset_requirement,
    open_verified_source_asset_stream,
)


class FakeStorage:
    def __init__(self, payload: bytes):
        self.payload = payload
        self.calls = []

    @contextmanager
    def read_stream(self, path: str, *, root: str):
        self.calls.append((path, root))
        yield BytesIO(self.payload)


def _locator(
    *,
    source_variant: str = "certificate_9",
    gxp_type: str = "GMP",
) -> CertificateDetailSourceAssetLocator:
    asset = resolve_source_asset(
        source_variant=source_variant,
        gxp_type=gxp_type,
    )

    return CertificateDetailSourceAssetLocator(
        source_variant=source_variant,
        gxp_type=gxp_type,
        storage_root="template",
        storage_relative_path=f"c5e/source/{asset.filename}",
        original_filename=asset.filename,
        checksum_sha256=asset.sha256,
    )


def test_builds_exact_requirement_for_audited_asset():
    requirement = build_source_asset_requirement(_locator())

    assert requirement.asset.filename == "9. PhamviGMP.docx"
    assert requirement.storage_root == "template"
    assert (
        requirement.storage_relative_path
        == "c5e/source/9. PhamviGMP.docx"
    )
    assert requirement.readiness_status == "direct_stream_ready"


def test_gdp_is_rejected_through_locator_contract():
    with pytest.raises(
        CertificateDetailSourceAssetLocatorError,
        match="GDP",
    ):
        build_source_asset_requirement(
            CertificateDetailSourceAssetLocator(
                source_variant="certificate_9",
                gxp_type="GDP",
                storage_root="template",
                storage_relative_path="c5e/source/9. PhamviGDP.docx",
                original_filename="9. PhamviGDP.docx",
                checksum_sha256="0" * 64,
            )
        )


def test_path_traversal_is_rejected():
    locator = _locator()

    with pytest.raises(
        CertificateDetailSourceAssetLocatorError,
        match="traversal",
    ):
        build_source_asset_requirement(
            CertificateDetailSourceAssetLocator(
                source_variant=locator.source_variant,
                gxp_type=locator.gxp_type,
                storage_root=locator.storage_root,
                storage_relative_path="../secret.docx",
                original_filename=locator.original_filename,
                checksum_sha256=locator.checksum_sha256,
            )
        )


def test_filename_must_match_registry():
    locator = _locator()

    with pytest.raises(
        CertificateDetailSourceAssetLocatorError,
        match="filename mismatch",
    ):
        build_source_asset_requirement(
            CertificateDetailSourceAssetLocator(
                source_variant=locator.source_variant,
                gxp_type=locator.gxp_type,
                storage_root=locator.storage_root,
                storage_relative_path=locator.storage_relative_path,
                original_filename="wrong.docx",
                checksum_sha256=locator.checksum_sha256,
            )
        )


def test_locator_checksum_must_match_registry():
    locator = _locator()

    with pytest.raises(
        CertificateDetailSourceAssetLocatorError,
        match="locator checksum mismatch",
    ):
        build_source_asset_requirement(
            CertificateDetailSourceAssetLocator(
                source_variant=locator.source_variant,
                gxp_type=locator.gxp_type,
                storage_root=locator.storage_root,
                storage_relative_path=locator.storage_relative_path,
                original_filename=locator.original_filename,
                checksum_sha256="0" * 64,
            )
        )


def test_stream_bytes_are_verified_before_use():
    requirement = build_source_asset_requirement(_locator())

    storage = FakeStorage(b"not the audited source file")

    with pytest.raises(
        CertificateDetailSourceAssetLocatorError,
        match="checksum mismatch",
    ):
        with open_verified_source_asset_stream(
            storage,
            requirement,
        ):
            pass

    assert storage.calls == [
        (
            requirement.storage_relative_path,
            "template",
        )
    ]