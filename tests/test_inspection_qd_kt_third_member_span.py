"""Prove exact two-member TT3Del body-level span deletion.

This is structural evidence only; does not approve Word list renumbering.
"""
from collections import Counter
from xml.etree import ElementTree as ET

import pytest

from backend.app.document.inspection_qd_kt_third_member_span import (
    QdKtThirdMemberSpanBlocked, remove_third_member_span_xml, W,
)


def _xml(*, adjacent=True, include_tt_ext=True):
    tag = W[1:-1]
    extras = f'<w:bookmarkStart w:id="7" w:name="TT_ext"/><w:bookmarkEnd w:id="7"/>' if include_tt_ext else ''
    between = '' if adjacent else '<w:p><w:r><w:t>Unexpected</w:t></w:r></w:p>'
    return (f'<w:document xmlns:w="{tag}"><w:body>'
        '<w:p><w:r><w:t>TT2</w:t></w:r></w:p>'
        '<w:p><w:bookmarkStart w:id="5" w:name="TT3x"/>'
        '<w:bookmarkStart w:id="6" w:name="TT3Del"/>'
        + extras +
        '<w:r><w:t>TT3 - Thành viên</w:t></w:r><w:bookmarkEnd w:id="5"/></w:p>'
        + between + '<w:bookmarkEnd w:id="6"/>'
        '<w:p><w:r><w:t>Next representative</w:t></w:r></w:p>'
        '</w:body></w:document>').encode()


def test_deletes_complete_span_and_preserves_siblings():
    result = remove_third_member_span_xml(_xml())
    root = ET.fromstring(result)
    paragraphs = [''.join(t.text or '' for t in p.iter(W+'t')) for p in root.iter(W+'p')]
    assert paragraphs == ['TT2', 'Next representative']
    assert not list(root.iter(W+'bookmarkStart'))
    assert not list(root.iter(W+'bookmarkEnd'))


@pytest.mark.parametrize('xml,error', [
    (b'invalid', 'QDKT_XML_INVALID'),
    (_xml(adjacent=False), 'QDKT_TT3DEL_END_NOT_ADJACENT'),
    (_xml(include_tt_ext=False), 'QDKT_TT3DEL_CONTEXT_UNPROVEN'),
    (_xml().replace(b'<w:bookmarkEnd w:id="6"/>', b''), 'QDKT_TT3DEL_END_NOT_ADJACENT'),
])
def test_rejects_unproven_shapes(xml, error):
    with pytest.raises(QdKtThirdMemberSpanBlocked, match=error):
        remove_third_member_span_xml(xml)


def test_unrelated_bookmark_survives_third_member_removal():
    xml = _xml().replace(
        b'<w:p><w:r><w:t>TT2</w:t></w:r></w:p>',
        b'<w:p><w:bookmarkStart w:id="19" w:name="Preceding"/><w:r><w:t>TT2</w:t></w:r><w:bookmarkEnd w:id="19"/></w:p>',
    )
    result = remove_third_member_span_xml(xml)
    root = ET.fromstring(result)
    assert [b.get(W + 'name') for b in root.iter(W + 'bookmarkStart')] == ['Preceding']
    assert [b.get(W + 'id') for b in root.iter(W + 'bookmarkEnd')] == ['19']


@pytest.mark.parametrize("unsafe", [
    '<w:ins w:id="8"><w:r><w:t>Tracked member</w:t></w:r></w:ins>',
    '<w:del w:id="9"><w:r><w:delText>Deleted member</w:delText></w:r></w:del>',
    '<w:fldSimple w:instr="MERGEFIELD Person"><w:r><w:t>Name</w:t></w:r></w:fldSimple>',
    '<w:r><w:fldChar w:fldCharType="begin"/></w:r>',
    '<w:sdt><w:sdtContent><w:r><w:t>Controlled member</w:t></w:r></w:sdtContent></w:sdt>',
])
def test_third_member_removal_refuses_unresolved_word_markup(unsafe):
    source = _xml()
    source = source.replace(
        b'<w:r><w:t>TT3 - ',
        unsafe.encode('utf-8') + b'<w:r><w:t>TT3 - ',
        1,
    )
    with pytest.raises(QdKtThirdMemberSpanBlocked, match='QDKT_TT3DEL_MARKUP_UNPROVEN'):
        remove_third_member_span_xml(source)


def test_revision_outside_target_paragraph_is_preserved():
    source = _xml().replace(
        b'<w:p><w:r><w:t>TT2</w:t></w:r></w:p>',
        b'<w:p><w:ins w:id="11"><w:r><w:t>TT2</w:t></w:r></w:ins></w:p>',
    )
    result = remove_third_member_span_xml(source)
    root = ET.fromstring(result)
    assert len(list(root.iter(W+'ins'))) == 1
    assert 'TT2' in result.decode('utf-8')
