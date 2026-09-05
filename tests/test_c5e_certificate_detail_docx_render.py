from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from backend.app.document.c5e_certificate_detail_fragment_extractor import (
    CertificateDetailExtractedFragment,
)
from backend.app.document.c5e_certificate_detail_semantic_projection import (
    project_certificate_detail_semantic_operations,
)
from backend.app.document.c5e_certificate_detail_typetext_resolver import (
    CertificateDetailTranslationDictionary,
)
from backend.app.document.c5e_certificate_detail_docx_render import (
    CertificateDetailDocxRenderError,
    build_certificate_detail_docx_bytes,
)


WORD_NS = (
    "http://schemas.openxmlformats.org/"
    "wordprocessingml/2006/main"
)


def _destination_document_xml() -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="{WORD_NS}">
  <w:body>
    <w:p>
      <w:bookmarkStart w:id="7" w:name="Pvi"/>
      <w:bookmarkEnd w:id="7"/>
      <w:r>
        <w:t>STATIC SUFFIX</w:t>
      </w:r>
    </w:p>
    <w:sectPr/>
  </w:body>
</w:document>
""".encode(
        "utf-8"
    )


def _destination_package() -> bytes:
    output = BytesIO()

    with ZipFile(
        output,
        "w",
        compression=ZIP_DEFLATED,
    ) as archive:
        archive.writestr(
            "[Content_Types].xml",
            "<Types/>",
        )

        archive.writestr(
            "word/document.xml",
            _destination_document_xml(),
        )

        archive.writestr(
            "word/custom-preserved-part.txt",
            b"PRESERVE-ME",
        )

    return output.getvalue()


def _three_cell_fragment(
    *,
    vi: str = "VI SOURCE",
    en: str = "EN SOURCE",
) -> str:
    return f"""
<w:tbl xmlns:w="{WORD_NS}">
  <w:tr>
    <w:tc>
      <w:p>
        <w:r>
          <w:t>{vi}</w:t>
        </w:r>
      </w:p>
    </w:tc>
    <w:tc>
      <w:p/>
    </w:tc>
    <w:tc>
      <w:p>
        <w:r>
          <w:t>{en}</w:t>
        </w:r>
      </w:p>
    </w:tc>
  </w:tr>
  <w:tr>
    <w:tc>
      <w:p/>
    </w:tc>
  </w:tr>
</w:tbl>
"""


def _dictionary():
    return CertificateDetailTranslationDictionary(
        acchs="Đđ",
        rgchs="Dd",
        matrices={
            "TV_Words": (
                (
                    "Thuốc vô trùng",
                ),
            ),
            "TA_Words": (
                (
                    "Sterile Products",
                ),
            ),
            "TV_Words2": (
                (
                    "Đường",
                ),
            ),
            "TA_Words2": (
                (
                    "Street",
                ),
            ),
            "TA_Words2_Loc": (
                (
                    "T",
                    "T",
                ),
            ),
            "TV_Words4": (
                (
                    "Bảo quản",
                ),
            ),
            "TA_Words4": (
                (
                    "Storage",
                ),
            ),
            "TV_Words6": (
                (
                    "GDP",
                ),
            ),
            "TA_Words6": (
                (
                    "GDP",
                ),
            ),
        },
    )


def _projection(
    *,
    gxp_type: str = "GMP",
    selections=None,
):
    if selections is None:
        selections = [
            {
                "taxonomy_node_id": "n1",
                "source_order": 1,
                "custom_description": "",
            }
        ]

    return project_certificate_detail_semantic_operations(
        family_code=(
            "CERTIFICATE_ISSUANCE_WORD"
        ),
        gxp_type=gxp_type,
        eng_part=True,
        taxonomy_nodes=[
            {
                "id": "n1",
                "key": "1",
                "main_topic": "",
                "source_order": 1,
            },
            {
                "id": "n2",
                "key": "2",
                "main_topic": "",
                "source_order": 2,
            },
        ],
        blocks=[
            {
                "id": "b1",
                "ordinal": 1,
                "name": "Đường 12",
                "note": "",
                "selections": selections,
            }
        ],
    )


def test_build_certificate_detail_docx_bytes_integrates_chain(
    monkeypatch,
):
    projection = _projection()

    calls = []

    def fake_extract(
        source_docx_bytes,
        *,
        bookmark_name,
    ):
        calls.append(
            (
                source_docx_bytes,
                bookmark_name,
            )
        )

        return CertificateDetailExtractedFragment(
            bookmark_name=bookmark_name,
            geometry_shape="test",
            fragment_xml=_three_cell_fragment(),
            visible_text=(
                "VI SOURCE EN SOURCE"
            ),
        )

    monkeypatch.setattr(
        (
            "backend.app.document."
            "c5e_certificate_detail_docx_render."
            "extract_bookmark_table_fragment_from_docx_bytes"
        ),
        fake_extract,
    )

    result = build_certificate_detail_docx_bytes(
        _destination_package(),
        source_docx_bytes=b"SOURCE-DOCX",
        projection=projection,
        dictionary=_dictionary(),
    )

    assert calls == [
        (
            b"SOURCE-DOCX",
            "L1",
        )
    ]

    assert result.extracted_bookmarks == (
        "L1",
    )

    assert (
        result.inserted_fragment_count
        == 1
    )

    assert (
        result.destination_bookmark
        == "Pvi"
    )

    assert (
        result.source_variant
        == "certificate_9"
    )

    assert (
        result.gxp_type
        == "GMP"
    )

    with ZipFile(
        BytesIO(
            result.binary_payload
        ),
        "r",
    ) as archive:
        document_xml = (
            archive.read(
                "word/document.xml"
            )
            .decode(
                "utf-8"
            )
        )

        assert "VI SOURCE" in document_xml
        assert "EN SOURCE" in document_xml
        assert "STATIC SUFFIX" in document_xml

        assert (
            'w:name="Pvi"'
            not in document_xml
        )

        assert archive.read(
            "word/custom-preserved-part.txt"
        ) == b"PRESERVE-ME"


def test_multiple_bookmarks_are_extracted_in_projection_order(
    monkeypatch,
):
    projection = _projection(
        selections=[
            {
                "taxonomy_node_id": "n1",
                "source_order": 1,
                "custom_description": "",
            },
            {
                "taxonomy_node_id": "n2",
                "source_order": 2,
                "custom_description": "",
            },
        ]
    )

    calls = []

    def fake_extract(
        source_docx_bytes,
        *,
        bookmark_name,
    ):
        calls.append(
            bookmark_name
        )

        return CertificateDetailExtractedFragment(
            bookmark_name=bookmark_name,
            geometry_shape="test",
            fragment_xml=(
                _three_cell_fragment(
                    vi=bookmark_name,
                    en=bookmark_name
                    + "-EN",
                )
            ),
            visible_text="",
        )

    monkeypatch.setattr(
        (
            "backend.app.document."
            "c5e_certificate_detail_docx_render."
            "extract_bookmark_table_fragment_from_docx_bytes"
        ),
        fake_extract,
    )

    result = build_certificate_detail_docx_bytes(
        _destination_package(),
        source_docx_bytes=b"SOURCE",
        projection=projection,
        dictionary=_dictionary(),
    )

    assert calls == [
        "L1",
        "L2",
    ]

    assert (
        result.extracted_bookmarks
        == (
            "L1",
            "L2",
        )
    )

    assert (
        result.inserted_fragment_count
        == 2
    )


def test_extractor_identity_mismatch_fails_closed(
    monkeypatch,
):
    projection = _projection()

    def fake_extract(
        source_docx_bytes,
        *,
        bookmark_name,
    ):
        return CertificateDetailExtractedFragment(
            bookmark_name="WRONG",
            geometry_shape="test",
            fragment_xml=(
                _three_cell_fragment()
            ),
            visible_text="",
        )

    monkeypatch.setattr(
        (
            "backend.app.document."
            "c5e_certificate_detail_docx_render."
            "extract_bookmark_table_fragment_from_docx_bytes"
        ),
        fake_extract,
    )

    with pytest.raises(
        CertificateDetailDocxRenderError,
        match=(
            "unexpected bookmark identity"
        ),
    ):
        build_certificate_detail_docx_bytes(
            _destination_package(),
            source_docx_bytes=b"SOURCE",
            projection=projection,
            dictionary=_dictionary(),
        )


def test_missing_document_xml_fails_before_source_extraction(
    monkeypatch,
):
    package = BytesIO()

    with ZipFile(
        package,
        "w",
        compression=ZIP_DEFLATED,
    ) as archive:
        archive.writestr(
            "[Content_Types].xml",
            "<Types/>",
        )

    extraction_called = False

    def fail_if_called(
        source_docx_bytes,
        *,
        bookmark_name,
    ):
        nonlocal extraction_called
        extraction_called = True

        raise AssertionError(
            "Source extractor must not run "
            "before destination validation."
        )

    monkeypatch.setattr(
        (
            "backend.app.document."
            "c5e_certificate_detail_docx_render."
            "extract_bookmark_table_fragment_from_docx_bytes"
        ),
        fail_if_called,
    )

    with pytest.raises(
        CertificateDetailDocxRenderError,
        match="word/document.xml",
    ):
        build_certificate_detail_docx_bytes(
            package.getvalue(),
            source_docx_bytes=b"SOURCE",
            projection=_projection(),
            dictionary=_dictionary(),
        )

    assert extraction_called is False


def test_invalid_destination_zip_fails_before_source_extraction(
    monkeypatch,
):
    extraction_called = False

    def fail_if_called(
        source_docx_bytes,
        *,
        bookmark_name,
    ):
        nonlocal extraction_called
        extraction_called = True

        raise AssertionError(
            "Source extractor must not run "
            "before destination validation."
        )

    monkeypatch.setattr(
        (
            "backend.app.document."
            "c5e_certificate_detail_docx_render."
            "extract_bookmark_table_fragment_from_docx_bytes"
        ),
        fail_if_called,
    )

    with pytest.raises(
        CertificateDetailDocxRenderError,
        match="valid DOCX/DOTX ZIP",
    ):
        build_certificate_detail_docx_bytes(
            b"not-a-zip",
            source_docx_bytes=b"SOURCE",
            projection=_projection(),
            dictionary=_dictionary(),
        )

    assert extraction_called is False


def test_renderer_rejects_gdp_even_if_upstream_boundary_is_bypassed():
    projection = SimpleNamespace(
        family_code=(
            "CERTIFICATE_ISSUANCE_WORD"
        ),
        source_variant=(
            "certificate_9"
        ),
        destination_bookmark=(
            "Pvi"
        ),
        gxp_type="GDP",
        operations=(),
    )

    with pytest.raises(
        CertificateDetailDocxRenderError,
        match="Unsupported.*GDP",
    ):
        build_certificate_detail_docx_bytes(
            _destination_package(),
            source_docx_bytes=b"SOURCE",
            projection=projection,
            dictionary=_dictionary(),
        )