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
