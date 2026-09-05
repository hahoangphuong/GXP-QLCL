from __future__ import annotations

from contextlib import contextmanager
from io import BytesIO
from types import SimpleNamespace
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from backend.app.document import docx_template_render, service
from backend.app.document.c5e_certificate_detail_semantic_projection import (
    CERTIFICATE_DETAIL_DESTINATION_BOOKMARK,
    CertificateDetailSemanticProjection,
)
from backend.app.document.docx_template_render import (
    DocxTemplateRenderError,
    build_template_aware_docx_bytes,
)
from backend.app.document.payload_builders import DocumentPayloadBuildError
from backend.app.document.service_contract import DocumentGenerationRequest


WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _docx_bytes(*, bookmark_name: str = "Other", text: str = "OLD") -> bytes:
    document_xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="{WORD_NS}">
  <w:body>
    <w:p>
      <w:bookmarkStart w:id="1" w:name="{bookmark_name}"/>
      <w:r><w:t>{text}</w:t></w:r>
      <w:bookmarkEnd w:id="1"/>
    </w:p>
  </w:body>
</w:document>
'''.encode("utf-8")
    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", document_xml)
    return buffer.getvalue()


def _projection(*, gxp_type: str = "GMP") -> CertificateDetailSemanticProjection:
    return CertificateDetailSemanticProjection(
        family_code="CERTIFICATE_ISSUANCE_WORD",
        source_variant="certificate_9",
        destination_bookmark="Pvi",
        gxp_type=gxp_type,
        eng_part=True,
        operations=(),
    )


def _allocated(
    *,
    projection: CertificateDetailSemanticProjection | None,
    table_regions: tuple[object, ...] = (),
):
    prepared = SimpleNamespace(
        source_binary_requirements=(),
        generation_plan=SimpleNamespace(
            template=SimpleNamespace(
                family_code="CERTIFICATE_ISSUANCE_WORD",
            )
        ),
        payload_result=SimpleNamespace(
            envelope=SimpleNamespace(fields=()),
        ),
        table_regions=table_regions,
        certificate_detail_projection=projection,
    )
    return SimpleNamespace(
        template_render_ready=True,
        template_binary_requirement=SimpleNamespace(
            readiness_status="direct_stream_ready",
        ),
        allocated=SimpleNamespace(
            prepared=prepared,
        ),
    )


def _install_template_mocks(monkeypatch, *, template_bytes: bytes, replacements: dict[str, str]):
    @contextmanager
    def fake_open_template_binary_stream(storage, requirement):
        yield BytesIO(template_bytes)

    monkeypatch.setattr(
        docx_template_render,
        "open_template_binary_stream",
        fake_open_template_binary_stream,
    )
    monkeypatch.setattr(
        docx_template_render,
        "load_default_template_contract_reconciliation",
        lambda: object(),
    )
    monkeypatch.setattr(
        docx_template_render,
        "build_scalar_replacement_plan_for_template",
        lambda *args, **kwargs: SimpleNamespace(
            bookmark_replacements=replacements,
            mode="test",
            template_variant_key=None,
        ),
    )


def test_certificate_detail_runtime_runs_before_generic_xml_mutation(monkeypatch):
    original = _docx_bytes(bookmark_name="Other", text="ORIGINAL")
    composed = _docx_bytes(bookmark_name="Other", text="COMPOSED")
    calls: list[str] = []

    _install_template_mocks(
        monkeypatch,
        template_bytes=original,
        replacements={},
    )

    def fake_locator(*, gxp_type: str):
        calls.append(f"locator:{gxp_type}")
        return SimpleNamespace(gxp_type=gxp_type)

    def fake_runtime(storage, *, destination_template_bytes, projection, source_locator):
        calls.append("c5e_runtime")
        assert destination_template_bytes == original
        assert projection.gxp_type == "GMP"
        assert source_locator.gxp_type == "GMP"
        return SimpleNamespace(
            render_result=SimpleNamespace(
                binary_payload=composed,
            )
        )

    monkeypatch.setattr(
        docx_template_render,
        "build_runtime_source_asset_locator",
        fake_locator,
    )
    monkeypatch.setattr(
        docx_template_render,
        "build_certificate_detail_runtime_docx",
        fake_runtime,
    )

    payload, replaced, regions, parts, mode, variant = build_template_aware_docx_bytes(
        object(),
        _allocated(projection=_projection()),
    )

    assert calls == ["locator:GMP", "c5e_runtime"]
    assert replaced == ()
    assert regions == ()
    assert parts == ()
    assert mode == "test"
    assert variant is None

    with ZipFile(BytesIO(payload), "r") as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    texts = [node.text for node in root.findall(f".//{{{WORD_NS}}}t")]
    assert "COMPOSED" in texts
    assert "ORIGINAL" not in texts


def test_generic_scalar_plan_must_never_own_pvi(monkeypatch):
    original = _docx_bytes(bookmark_name=CERTIFICATE_DETAIL_DESTINATION_BOOKMARK)
    runtime_called = False

    _install_template_mocks(
        monkeypatch,
        template_bytes=original,
        replacements={CERTIFICATE_DETAIL_DESTINATION_BOOKMARK: "wrong owner"},
    )

    def fake_runtime(*args, **kwargs):
        nonlocal runtime_called
        runtime_called = True
        raise AssertionError("runtime must not run after an ownership conflict")

    monkeypatch.setattr(
        docx_template_render,
        "build_certificate_detail_runtime_docx",
        fake_runtime,
    )

    with pytest.raises(
        DocxTemplateRenderError,
        match="must not appear in the generic scalar replacement plan",
    ):
        build_template_aware_docx_bytes(
            object(),
            _allocated(projection=_projection()),
        )

    assert runtime_called is False


def test_generic_table_region_must_never_own_pvi(monkeypatch):
    original = _docx_bytes(bookmark_name=CERTIFICATE_DETAIL_DESTINATION_BOOKMARK)
    runtime_called = False

    _install_template_mocks(
        monkeypatch,
        template_bytes=original,
        replacements={},
    )

    def fake_runtime(*args, **kwargs):
        nonlocal runtime_called
        runtime_called = True
        raise AssertionError("runtime must not run after an ownership conflict")

    monkeypatch.setattr(
        docx_template_render,
        "build_certificate_detail_runtime_docx",
        fake_runtime,
    )

    table_region = SimpleNamespace(
        region_bookmark_name=CERTIFICATE_DETAIL_DESTINATION_BOOKMARK,
        rows=(),
    )

    with pytest.raises(
        DocxTemplateRenderError,
        match="must not be used as a generic table-region bookmark",
    ):
        build_template_aware_docx_bytes(
            object(),
            _allocated(
                projection=_projection(),
                table_regions=(table_region,),
            ),
        )

    assert runtime_called is False


def test_non_certificate_path_remains_generic_only(monkeypatch):
    original = _docx_bytes(bookmark_name="Other", text="ORIGINAL")
    runtime_called = False

    _install_template_mocks(
        monkeypatch,
        template_bytes=original,
        replacements={},
    )

    def fake_runtime(*args, **kwargs):
        nonlocal runtime_called
        runtime_called = True
        raise AssertionError("runtime must not run without a certificate projection")

    monkeypatch.setattr(
        docx_template_render,
        "build_certificate_detail_runtime_docx",
        fake_runtime,
    )

    payload, *_ = build_template_aware_docx_bytes(
        object(),
        _allocated(projection=None),
    )

    assert runtime_called is False
    with ZipFile(BytesIO(payload), "r") as archive:
        ET.fromstring(archive.read("word/document.xml"))


def test_service_projection_builder_returns_none_for_other_family():
    request = DocumentGenerationRequest(
        family_code="INSPECTION_BBTD_HOSO_DK",
        requested_by_user_id=None,
    )
    assert service._build_certificate_detail_projection(object(), request=request) is None


def test_service_projection_builder_requires_case_id():
    request = DocumentGenerationRequest(
        family_code="CERTIFICATE_ISSUANCE_WORD",
        requested_by_user_id=None,
        gxp_type="GMP",
    )
    with pytest.raises(DocumentPayloadBuildError, match="requires case_id"):
        service._build_certificate_detail_projection(object(), request=request)


def test_service_projection_builder_fails_on_request_case_gxp_mismatch(monkeypatch):
    monkeypatch.setattr(
        service,
        "load_c5e_evaluation_scope_projection_input",
        lambda session, *, case_id: SimpleNamespace(
            blocks=(),
            taxonomy_nodes=(),
            limitation_text=None,
            gxp_type="GLP",
        ),
    )
    request = DocumentGenerationRequest(
        family_code="CERTIFICATE_ISSUANCE_WORD",
        requested_by_user_id=None,
        case_id="case-1",
        gxp_type="GMP",
    )
    with pytest.raises(DocumentPayloadBuildError, match="request/case GxP mismatch"):
        service._build_certificate_detail_projection(object(), request=request)


def test_service_projection_builder_uses_canonical_scope_and_eng_part_true(monkeypatch):
    expected = _projection(gxp_type="GSP")
    calls: dict[str, object] = {}

    projection_input = SimpleNamespace(
        blocks=({"id": "block-1"},),
        taxonomy_nodes=({"id": "node-1"},),
        limitation_text="ignored by certificate detail",
        gxp_type="GSP",
    )

    monkeypatch.setattr(
        service,
        "load_c5e_evaluation_scope_projection_input",
        lambda session, *, case_id: projection_input,
    )

    def fake_project(**kwargs):
        calls.update(kwargs)
        return expected

    monkeypatch.setattr(
        service,
        "project_certificate_detail_semantic_operations",
        fake_project,
    )

    request = DocumentGenerationRequest(
        family_code="CERTIFICATE_ISSUANCE_WORD",
        requested_by_user_id=None,
        case_id="case-1",
        gxp_type="GSP",
    )

    result = service._build_certificate_detail_projection(object(), request=request)

    assert result is expected
    assert calls == {
        "family_code": "CERTIFICATE_ISSUANCE_WORD",
        "blocks": projection_input.blocks,
        "taxonomy_nodes": projection_input.taxonomy_nodes,
        "gxp_type": "GSP",
        "eng_part": True,
    }
