"""Pure isolated Word XML transformation for QĐKT draft issuance year.

Never called by runtime document generation. Operates on bytes in memory only.
"""
from __future__ import annotations

import re
from lxml import etree as ET

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
ISSUE = re.compile(r'\bnăm\s+((?:19|20)\d{2})\b')


class QdKtIssuanceDateBlocked(ValueError):
    pass


def blank_issuance_year_xml(xml: bytes) -> tuple[bytes, str]:
    """Clear the uniquely identified fixed year, preserving other paragraph text.

    Does not approve visual layout or authorize document creation.
    """
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise QdKtIssuanceDateBlocked('DOCUMENT_XML_INVALID') from exc
    candidates = []
    for para in root.iter(W+'p'):
        nodes = list(para.iter(W+'t'))
        text = ''.join(node.text or '' for node in nodes)
        if 'Hà Nội,' in text and all(token in text for token in ('ngày', 'tháng', 'năm')):
            candidates.append((nodes,text))
    if len(candidates) != 1:
        raise QdKtIssuanceDateBlocked('ISSUANCE_PARAGRAPH_NOT_UNIQUE')
    nodes, text = candidates[0]
    # Field instructions, revisions and content controls have distinct Word
    # display/acceptance semantics. Plain w:t concatenation does not prove
    # which value Word will display, so never rewrite these candidate dates.
    paragraph = nodes[0]
    while paragraph is not None and paragraph.tag != W + 'p':
        paragraph = paragraph.getparent()
    unsafe = {
        W + name for name in (
            'fldChar', 'fldSimple', 'instrText', 'del', 'delText',
            'ins', 'moveFrom', 'moveTo', 'sdt',
        )
    }
    if paragraph is None or any(node.tag in unsafe for node in paragraph.iter()):
        raise QdKtIssuanceDateBlocked('ISSUANCE_DATE_MARKUP_UNPROVEN')
    # Block-level revisions/content controls can wrap an entire paragraph.
    # The paragraph itself may contain only innocuous w:t descendants.
    for ancestor in paragraph.iterancestors():
        if ancestor.tag in unsafe:
            raise QdKtIssuanceDateBlocked('ISSUANCE_DATE_MARKUP_UNPROVEN')
    matches = list(ISSUE.finditer(text))
    if len(matches) != 1:
        raise QdKtIssuanceDateBlocked('ISSUANCE_YEAR_NOT_UNIQUE')
    match = matches[0]
    start, end = match.span(1)
    before = text[:start]
    after = text[end:]
    if re.search(r'\d', before + after):
        raise QdKtIssuanceDateBlocked('ISSUANCE_DATE_HAS_OTHER_NUMERALS')
    pos = 0
    for node in nodes:
        value = node.text or ''
        node.text = ''.join(c for index, c in enumerate(value, pos) if not start <= index < end)
        pos += len(value)
    cleaned = ''.join(node.text or '' for node in nodes)
    if cleaned != before+after or re.search(r'\d', cleaned):
        raise QdKtIssuanceDateBlocked('ISSUANCE_DATE_OUTPUT_INVALID')
    return ET.tostring(root, encoding='utf-8', xml_declaration=True), match.group(1)
