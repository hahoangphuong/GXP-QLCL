from __future__ import annotations

from contextlib import contextmanager
from io import BytesIO
from types import SimpleNamespace

import pytest

from backend.app.document.c5e_certificate_detail_docx_render import (
    CertificateDetailDocxRenderResult,
)
from backend.app.document.c5e_certificate_detail_runtime import (
    CertificateDetailRuntimeError,
    build_certificate_detail_runtime_docx,
)
from backend.app.document.c5e_certificate_detail_source_asset_locator import (
    CertificateDetailSourceAssetLocator,
)


CHECKSUM = "a" * 64


def _projection(
    *,
    gxp_type: str = "GMP",
    source_variant: str = "certificate_9",
):
    return SimpleNamespace(
        family_code="CERTIFICATE_ISSUANCE_WORD",
        source_variant=source_variant,
        destination_bookmark="Pvi",
        gxp_type=gxp_type,
        eng_part=True,
        operations=(),
    )


def _locator(
    *,
    gxp_type: str = "GMP",
    source_variant: str = "certificate_9",
    storage_root: str = "template",
):
    return CertificateDetailSourceAssetLocator(
        source_variant=source_variant,
        gxp_type=gxp_type,
        storage_root=storage_root,
        storage_relative_path="legacy/9. PhamviGMP.docx",
        original_filename="9. PhamviGMP.docx",
        checksum_sha256=CHECKSUM,
    )


def _requirement():
    return SimpleNamespace(
        asset=SimpleNamespace(),
        storage_root="template",
        storage_relative_path="legacy/9. PhamviGMP.docx",
        readiness_status="direct_stream_ready",
        detail="verified",
    )


def _render_result():
    return CertificateDetailDocxRenderResult(
        binary_payload=b"DOCX",
        destination_bookmark="Pvi",
        source_variant="certificate_9",
        gxp_type="GMP",
        extracted_bookmarks=("L1",),
        inserted_fragment_count=1,
        emitted_text_operation_count=2,
    )


def test_runtime_opens_verified_source_then_renders(
    monkeypatch,
):
    calls = []

    monkeypatch.setattr(
        (
            "backend.app.document."
            "c5e_certificate_detail_runtime."
            "build_source_asset_requirement"
        ),
        lambda locator: _requirement(),
    )

    @contextmanager
    def fake_open(
        storage,
        requirement,
    ):
        calls.append(
            (
                "open",
                storage,
                requirement,
            )
        )

        yield BytesIO(
            b"SOURCE-DOCX"
        )

    monkeypatch.setattr(
        (
            "backend.app.document."
            "c5e_certificate_detail_runtime."
            "open_verified_source_asset_stream"
        ),
        fake_open,
    )

    def fake_render(
        destination_template_bytes,
        *,
        source_docx_bytes,
        projection,
    ):
        calls.append(
            (
                "render",
                destination_template_bytes,
                source_docx_bytes,
                projection.gxp_type,
            )
        )

        return _render_result()

    monkeypatch.setattr(
        (
            "backend.app.document."
            "c5e_certificate_detail_runtime."
            "build_certificate_detail_docx_bytes"
        ),
        fake_render,
    )

    storage = object()

    result = build_certificate_detail_runtime_docx(
        storage,
        destination_template_bytes=b"TEMPLATE",
        projection=_projection(),
        source_locator=_locator(),
    )

    assert calls[0][0] == "open"

    assert calls[1] == (
        "render",
        b"TEMPLATE",
        b"SOURCE-DOCX",
        "GMP",
    )

    assert (
        result.render_result.binary_payload
        == b"DOCX"
    )

    assert (
        result.source_storage_root
        == "template"
    )

    assert (
        result.source_storage_relative_path
        == "legacy/9. PhamviGMP.docx"
    )

    assert (
        result.source_checksum_sha256
        == CHECKSUM
    )

    assert (
        result.source_readiness_status
        == "direct_stream_ready"
    )


@pytest.mark.parametrize(
    ("projection_gxp", "locator_gxp"),
    [
        ("GMP", "GLP"),
        ("GLP", "GSP"),
        ("GSP", "GMP"),
    ],
)
def test_runtime_rejects_projection_source_gxp_mismatch(
    projection_gxp,
    locator_gxp,
):
    with pytest.raises(
        CertificateDetailRuntimeError,
        match="GxP mismatch",
    ):
        build_certificate_detail_runtime_docx(
            object(),
            destination_template_bytes=b"TEMPLATE",
            projection=_projection(
                gxp_type=projection_gxp
            ),
            source_locator=_locator(
                gxp_type=locator_gxp
            ),
        )


def test_runtime_rejects_gdp_before_storage_access(
    monkeypatch,
):
    called = False

    def must_not_build(_locator):
        nonlocal called
        called = True
        raise AssertionError(
            "Storage requirement must not be built for GDP."
        )

    monkeypatch.setattr(
        (
            "backend.app.document."
            "c5e_certificate_detail_runtime."
            "build_source_asset_requirement"
        ),
        must_not_build,
    )

    with pytest.raises(
        CertificateDetailRuntimeError,
        match="Unsupported.*GDP",
    ):
        build_certificate_detail_runtime_docx(
            object(),
            destination_template_bytes=b"TEMPLATE",
            projection=_projection(
                gxp_type="GDP"
            ),
            source_locator=_locator(),
        )

    assert called is False


def test_runtime_rejects_appendix_z3(
    monkeypatch,
):
    called = False

    def must_not_build(_locator):
        nonlocal called
        called = True
        raise AssertionError(
            "appendix_z3 must not reach storage."
        )

    monkeypatch.setattr(
        (
            "backend.app.document."
            "c5e_certificate_detail_runtime."
            "build_source_asset_requirement"
        ),
        must_not_build,
    )

    with pytest.raises(
        CertificateDetailRuntimeError,
        match="certificate_9",
    ):
        build_certificate_detail_runtime_docx(
            object(),
            destination_template_bytes=b"TEMPLATE",
            projection=_projection(),
            source_locator=_locator(
                source_variant="appendix_z3"
            ),
        )

    assert called is False


def test_runtime_rejects_non_template_storage_root(
    monkeypatch,
):
    called = False

    def must_not_build(_locator):
        nonlocal called
        called = True
        raise AssertionError(
            "Wrong storage root must fail before storage."
        )

    monkeypatch.setattr(
        (
            "backend.app.document."
            "c5e_certificate_detail_runtime."
            "build_source_asset_requirement"
        ),
        must_not_build,
    )

    with pytest.raises(
        CertificateDetailRuntimeError,
        match="storage_root='template'",
    ):
        build_certificate_detail_runtime_docx(
            object(),
            destination_template_bytes=b"TEMPLATE",
            projection=_projection(),
            source_locator=_locator(
                storage_root="case"
            ),
        )

    assert called is False


def test_runtime_fails_closed_when_requirement_not_ready(
    monkeypatch,
):
    requirement = SimpleNamespace(
        asset=SimpleNamespace(),
        storage_root="template",
        storage_relative_path="legacy/9. PhamviGMP.docx",
        readiness_status="missing",
        detail="asset unavailable",
    )

    monkeypatch.setattr(
        (
            "backend.app.document."
            "c5e_certificate_detail_runtime."
            "build_source_asset_requirement"
        ),
        lambda locator: requirement,
    )

    with pytest.raises(
        CertificateDetailRuntimeError,
        match="not ready",
    ):
        build_certificate_detail_runtime_docx(
            object(),
            destination_template_bytes=b"TEMPLATE",
            projection=_projection(),
            source_locator=_locator(),
        )