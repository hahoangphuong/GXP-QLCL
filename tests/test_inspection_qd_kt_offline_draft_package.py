"""Disposable template package smoke; explicitly not a QĐKT business renderer."""
from hashlib import sha256
from io import BytesIO
from zipfile import ZipFile
from xml.etree import ElementTree as ET

import pytest

from backend.app.document.inspection_qd_kt_offline_draft_package import (
    QdKtDraftPackageBlocked, build_offline_date_only_docx, DOTX_TYPE, DOCX_TYPE,
)

CT = "http://schemas.openxmlformats.org/package/2006/content-types"
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _source(*, year="2026", template_type=DOTX_TYPE, duplicate=False):
    xml = (f'<w:document xmlns:w="{W}"><w:body>'
           '<w:p><w:r><w:t>Hà Nội, ngày    tháng    năm </w:t></w:r>'
           f'<w:r><w:t>{year[:3]}</w:t></w:r>'
           f'<w:r><w:t>{year[3:]}</w:t></w:r></w:p>'
           '<w:p><w:r><w:t>Hồ sơ ngày 01/02/2024</w:t></w:r></w:p>'
           '</w:body></w:document>')
    manifest = (f'<Types xmlns="{CT}">'
                f'<Override PartName="/word/document.xml" ContentType="{template_type}"/>'
                '</Types>')
    buff = BytesIO()
    with ZipFile(buff, "w") as f:
        f.writestr("[Content_Types].xml", manifest)
        f.writestr("word/document.xml", xml)
        f.writestr("docProps/custom.xml", "<custom/>")
        if duplicate:
            f.writestr("docProps/custom.xml", "<duplicate/>")
    return buff.getvalue()


@pytest.mark.parametrize("year", ("2026", "2021", "2020"))
def test_offline_package_changes_only_allowed_parts(year):
    original = _source(year=year)
    output = build_offline_date_only_docx(template=original, expected_sha256=sha256(original).hexdigest())
    assert original != output
    with ZipFile(BytesIO(original)) as source, ZipFile(BytesIO(output)) as changed:
        assert source.namelist() == changed.namelist()
        assert source.read("docProps/custom.xml") == changed.read("docProps/custom.xml")
        assert DOCX_TYPE.encode() in changed.read("[Content_Types].xml")
        assert DOTX_TYPE.encode() in source.read("[Content_Types].xml")
        root = ET.fromstring(changed.read("word/document.xml"))
        paragraphs = ["".join(n.text or "" for n in p.iter(f"{{{W}}}t"))
                      for p in root.iter(f"{{{W}}}p")]
        assert paragraphs[0] == "Hà Nội, ngày    tháng    năm "
        assert paragraphs[1] == "Hồ sơ ngày 01/02/2024"


def test_wrong_checksum_fails_closed():
    with pytest.raises(QdKtDraftPackageBlocked, match="QDKT_TEMPLATE_CHECKSUM_MISMATCH"):
        build_offline_date_only_docx(template=_source(), expected_sha256="0" * 64)


def test_wrong_main_type_fails_closed():
    original = _source(template_type=DOCX_TYPE)
    with pytest.raises(QdKtDraftPackageBlocked, match="QDKT_PACKAGE_TEMPLATE_CONTENT_TYPE_UNPROVEN"):
        build_offline_date_only_docx(template=original, expected_sha256=sha256(original).hexdigest())


def test_duplicate_part_fails_closed():
    original = _source(duplicate=True)
    with pytest.raises(QdKtDraftPackageBlocked, match="QDKT_PACKAGE_DUPLICATE_PART"):
        build_offline_date_only_docx(template=original, expected_sha256=sha256(original).hexdigest())


def test_preserves_word_namespace_prefixes_and_ignorable_declarations():
    original = _source()
    with ZipFile(BytesIO(original)) as source:
        text = source.read('word/document.xml').replace(
            b'<w:document ',
            b'<w:document xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml" mc:Ignorable="w14" ',
        )
        target = BytesIO()
        with ZipFile(target, 'w') as out:
            for item in source.infolist():
                out.writestr(item, text if item.filename == 'word/document.xml' else source.read(item.filename))
    package = target.getvalue()
    result = build_offline_date_only_docx(template=package, expected_sha256=sha256(package).hexdigest())
    with ZipFile(BytesIO(result)) as output:
        doc = output.read('word/document.xml')
    assert b'<w:document' in doc
    assert b'xmlns:w14=' in doc
    assert b'mc:Ignorable="w14"' in doc
    assert b'<ns0:document' not in doc
