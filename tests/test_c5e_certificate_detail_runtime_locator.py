from __future__ import annotations

import pytest

from backend.app.document.c5e_certificate_detail_source_asset_locator import (
    CertificateDetailSourceAssetLocatorError,
    build_runtime_source_asset_locator,
)


@pytest.mark.parametrize(
    ("gxp_type", "filename"),
    [
        (
            "GMP",
            "9. PhamviGMP.docx",
        ),
        (
            "GLP",
            "9. PhamviGLP.docx",
        ),
        (
            "GSP",
            "9. PhamviGSP.docx",
        ),
    ],
)
def test_runtime_locator_maps_certificate_9_to_template_namespace(
    gxp_type,
    filename,
):
    locator = (
        build_runtime_source_asset_locator(
            gxp_type=gxp_type
        )
    )

    assert (
        locator.source_variant
        == "certificate_9"
    )

    assert (
        locator.gxp_type
        == gxp_type
    )

    assert (
        locator.storage_root
        == "template"
    )

    assert (
        locator.storage_relative_path
        == (
            "c5e_certificate_detail/"
            + filename
        )
    )

    assert (
        locator.original_filename
        == filename
    )

    assert (
        len(
            locator.checksum_sha256
        )
        == 64
    )


def test_runtime_locator_rejects_gdp():
    with pytest.raises(
        CertificateDetailSourceAssetLocatorError,
        match="GDP",
    ):
        build_runtime_source_asset_locator(
            gxp_type="GDP"
        )