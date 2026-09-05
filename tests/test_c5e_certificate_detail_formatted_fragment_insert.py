from __future__ import annotations

from xml.etree import ElementTree as ET

import pytest

from backend.app.document.formatted_fragment_insert import (
    FormattedFragmentInsertError,
    insert_table_fragment_xml_at_empty_bookmark,
)

WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": WORD_NS}


def _destination_xml(*, suffix_runs: str, prefix_run: str = "") -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="{WORD_NS}">
  <w:body>
    <w:p>
      <w:pPr><w:pStyle w:val="Heading"/></w:pPr>
      {prefix_run}
      <w:bookmarkStart w:id="20" w:name="Pvi"/>
      <w:bookmarkEnd w:id="20"/>
      {suffix_runs}
    </w:p>
  </w:body>
</w:document>""".encode("utf-8")


def _fragment_xml() -> str:
    return f"""<w:tbl xmlns:w="{WORD_NS}">
  <w:tr><w:tc><w:p><w:r><w:t>Copied scope row</w:t></w:r></w:p></w:tc></w:tr>
</w:tbl>"""


def test_inserts_table_before_heading_and_preserves_suffix_text():
    document_xml = _destination_xml(
        suffix_runs=(
            '<w:r><w:t xml:space="preserve">1. </w:t></w:r>'
            '<w:r><w:t>Nội dung hạn chế hoặc làm rõ liên quan đến phạm vi chứng nhận :</w:t></w:r>'
        )
    )
    rendered, result = insert_table_fragment_xml_at_empty_bookmark(
        document_xml,
        bookmark_name="Pvi",
        fragment_xml=_fragment_xml(),
    )

    root = ET.fromstring(rendered)
    body = root.find("./w:body", NS)
    assert body is not None
    children = list(body)
    assert [child.tag.rsplit("}", 1)[-1] for child in children] == ["tbl", "p"]

    table_text = "".join(t.text or "" for t in children[0].findall(".//w:t", NS))
    heading_text = "".join(t.text or "" for t in children[1].findall(".//w:t", NS))
    assert table_text == "Copied scope row"
    assert heading_text == "1. Nội dung hạn chế hoặc làm rõ liên quan đến phạm vi chứng nhận :"

    assert not root.findall(".//w:bookmarkStart", NS)
    assert not root.findall(".//w:bookmarkEnd", NS)
    assert result.inserted_root_tag == "tbl"
    assert result.destination_parent_tag == "body"
    assert result.destination_child_index == 0


def test_preserves_single_run_heading_variant():
    document_xml = _destination_xml(
        suffix_runs='<w:r><w:t>Nội dung hạn chế hoặc làm rõ liên quan đến phạm vi chứng nhận:</w:t></w:r>'
    )
    rendered, _ = insert_table_fragment_xml_at_empty_bookmark(
        document_xml,
        bookmark_name="Pvi",
        fragment_xml=_fragment_xml(),
    )
    root = ET.fromstring(rendered)
    paragraphs = root.findall("./w:body/w:p", NS)
    assert len(paragraphs) == 1
    assert "".join(t.text or "" for t in paragraphs[0].findall(".//w:t", NS)).startswith(
        "Nội dung hạn chế"
    )


def test_semantic_content_before_bookmark_fails_closed():
    document_xml = _destination_xml(
        prefix_run='<w:r><w:t>must stay before bookmark</w:t></w:r>',
        suffix_runs='<w:r><w:t>heading</w:t></w:r>',
    )
    with pytest.raises(FormattedFragmentInsertError, match="semantic content exists before"):
        insert_table_fragment_xml_at_empty_bookmark(
            document_xml,
            bookmark_name="Pvi",
            fragment_xml=_fragment_xml(),
        )


def test_nonempty_bookmark_fails_closed():
    document_xml = f"""<?xml version="1.0"?>
<w:document xmlns:w="{WORD_NS}"><w:body><w:p>
<w:pPr/>
<w:bookmarkStart w:id="20" w:name="Pvi"/>
<w:r><w:t>inside bookmark</w:t></w:r>
<w:bookmarkEnd w:id="20"/>
<w:r><w:t>heading</w:t></w:r>
</w:p></w:body></w:document>""".encode()
    with pytest.raises(FormattedFragmentInsertError, match="empty/adjacent"):
        insert_table_fragment_xml_at_empty_bookmark(
            document_xml,
            bookmark_name="Pvi",
            fragment_xml=_fragment_xml(),
        )


def test_fragment_with_bookmark_markup_fails_closed():
    fragment = f"""<w:tbl xmlns:w="{WORD_NS}">
<w:tr><w:tc><w:p>
<w:bookmarkStart w:id="1" w:name="L1"/>
<w:bookmarkEnd w:id="1"/>
</w:p></w:tc></w:tr>
</w:tbl>"""
    with pytest.raises(FormattedFragmentInsertError, match="must not contain bookmark markup"):
        insert_table_fragment_xml_at_empty_bookmark(
            _destination_xml(suffix_runs='<w:r><w:t>heading</w:t></w:r>'),
            bookmark_name="Pvi",
            fragment_xml=fragment,
        )
