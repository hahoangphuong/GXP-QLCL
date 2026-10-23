"""Offline-only physical removal of TT3Del span in legacy QĐKT templates.

This handles ONLY the physical two-member branch, not semantic mapping,
numbering approval, rendering authorization, or document storage.
"""
from __future__ import annotations

from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class QdKtThirdMemberSpanBlocked(ValueError):
    pass


def remove_third_member_span_xml(xml: bytes) -> bytes:
    """Delete one proven TT3Del paragraph AND its body-level bookmarkEnd.

    Rejects nonstandard shapes and ensures no orphaned bookmark endpoints.
    Remaining numbering must still undergo visual QA before any runtime use.
    """
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise QdKtThirdMemberSpanBlocked("QDKT_XML_INVALID") from exc
    body = root.find(W + "body")
    if body is None:
        raise QdKtThirdMemberSpanBlocked("QDKT_BODY_MISSING")
    children = list(body)
    spans = []
    for index, node in enumerate(children):
        starts = [b for b in node.iter(W + "bookmarkStart") if b.get(W + "name") == "TT3Del"]
        if starts:
            spans.append((index, node, starts))
    if len(spans) != 1:
        raise QdKtThirdMemberSpanBlocked("QDKT_TT3DEL_START_NOT_UNIQUE")
    index, para, starts = spans[0]
    if para.tag != W + "p" or len(starts) != 1:
        raise QdKtThirdMemberSpanBlocked("QDKT_TT3DEL_NOT_PARAGRAPH")
    identifier = starts[0].get(W + "id")
    names = [b.get(W + "name") for b in para.iter(W + "bookmarkStart")]
    if not identifier or not {"TT3Del", "TT3x", "TT_ext"}.issubset(names):
        raise QdKtThirdMemberSpanBlocked("QDKT_TT3DEL_CONTEXT_UNPROVEN")
    if index + 1 >= len(children):
        raise QdKtThirdMemberSpanBlocked("QDKT_TT3DEL_END_MISSING")
    end_node = children[index + 1]
    if end_node.tag != W + "bookmarkEnd" or end_node.get(W + "id") != identifier:
        raise QdKtThirdMemberSpanBlocked("QDKT_TT3DEL_END_NOT_ADJACENT")
    for b in para.iter(W + "bookmarkStart"):
        b_id = b.get(W + "id")
        if b_id == identifier:
            continue
        paired = [e for e in para.iter(W + "bookmarkEnd") if e.get(W + "id") == b_id]
        if len(paired) != 1:
            raise QdKtThirdMemberSpanBlocked("QDKT_NESTED_BOOKMARK_ESCAPES_PARAGRAPH")
    if any(e.get(W + "id") == identifier for e in para.iter(W + "bookmarkEnd")):
        raise QdKtThirdMemberSpanBlocked("QDKT_TT3DEL_EARLY_END")
    body.remove(end_node)
    body.remove(para)
    all_starts = [b.get(W + "id") for b in root.iter(W + "bookmarkStart")]
    all_ends = [b.get(W + "id") for b in root.iter(W + "bookmarkEnd")]
    if sorted(all_starts) != sorted(all_ends) or len(all_starts) != len(set(all_starts)):
        raise QdKtThirdMemberSpanBlocked("QDKT_BOOKMARK_PAIRING_INVALID")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)
