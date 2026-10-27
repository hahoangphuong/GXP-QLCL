"""Isolated proof: draft QĐKT issuance date must retain no administrative year."""
import re
from xml.etree import ElementTree as ET

import pytest

from backend.app.document.inspection_qd_kt_draft_issuance_xml import (
    QdKtIssuanceDateBlocked, blank_issuance_year_xml,
)

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'


def _xml(*year_parts, other=''):
    runs = ''.join(f'<w:r><w:t>{text}</w:t></w:r>' for text in year_parts)
    return (
        f'<w:document xmlns:w="{W[1:-1]}"><w:body>'
        '<w:p><w:r><w:t>Hà Nội, ngày     tháng     năm </w:t></w:r>'
        + runs + '</w:p>' + other + '</w:body></w:document>'
    ).encode()


@pytest.mark.parametrize('parts,year', [
    (('202', '6'), '2026'),
    (('202', '1'), '2021'),
    (('20', '20'), '2020'),
    (('2026',), '2026'),
])
def test_clear_split_year_without_touching_other_paragraphs(parts, year):
    unrelated = '<w:p><w:r><w:t>Hồ sơ nộp 01/02/2025</w:t></w:r></w:p>'
    source = _xml(*parts, other=unrelated)
    result, removed = blank_issuance_year_xml(source)
    assert removed == year
    assert source != result
    assert 'Hồ sơ nộp 01/02/2025' in result.decode()
    root = ET.fromstring(result)
    first = next(root.iter(W + 'p'))
    text = ''.join(node.text or '' for node in first.iter(W + 't'))
    assert text == 'Hà Nội, ngày     tháng     năm '
    assert not re.search(r'\d', text)


@pytest.mark.parametrize('source,blocked', [
    (_xml(''), 'ISSUANCE_YEAR_NOT_UNIQUE'),
    (_xml('20','26', other='<w:p><w:r><w:t>Hà Nội, ngày tháng năm 2021</w:t></w:r></w:p>'), 'ISSUANCE_PARAGRAPH_NOT_UNIQUE'),
    (_xml('2026').replace(b'ng\xc3\xa0y     th\xc3\xa1ng', b'ng\xc3\xa0y 12 th\xc3\xa1ng'), 'ISSUANCE_DATE_HAS_OTHER_NUMERALS'),
    (b'not xml', 'DOCUMENT_XML_INVALID'),
])
def test_unproven_date_fails_closed(source, blocked):
    with pytest.raises(QdKtIssuanceDateBlocked, match=blocked):
        blank_issuance_year_xml(source)


@pytest.mark.parametrize("markup", [
    '<w:ins w:id="1"><w:r><w:t>2026</w:t></w:r></w:ins>',
    '<w:del w:id="2"><w:r><w:delText>2024</w:delText></w:r></w:del>'
    '<w:r><w:t>2026</w:t></w:r>',
    '<w:fldSimple w:instr="DATE"><w:r><w:t>2026</w:t></w:r></w:fldSimple>',
    '<w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:t>2026</w:t></w:r>'
    '<w:r><w:fldChar w:fldCharType="end"/></w:r>',
    '<w:sdt><w:sdtContent><w:r><w:t>2026</w:t></w:r></w:sdtContent></w:sdt>',
    '<w:moveTo w:id="3"><w:r><w:t>2026</w:t></w:r></w:moveTo>',
])
def test_refuses_issuance_date_with_word_revision_or_field_markup(markup):
    xml = _xml('', other='')
    xml = xml.replace(
        b'</w:p>', markup.encode('utf-8') + b'</w:p>', 1,
    )
    with pytest.raises(QdKtIssuanceDateBlocked, match='ISSUANCE_DATE_MARKUP_UNPROVEN'):
        blank_issuance_year_xml(xml)


def test_unrelated_field_or_revision_paragraph_is_not_rewritten():
    unrelated = (
        '<w:p><w:ins w:id="4"><w:r><w:t>Unrelated evidence</w:t></w:r></w:ins></w:p>'
    )
    output, year = blank_issuance_year_xml(_xml('2026', other=unrelated))
    assert year == '2026'
    assert 'Unrelated evidence' in output.decode('utf-8')
    assert 'w:ins' in output.decode('utf-8')
