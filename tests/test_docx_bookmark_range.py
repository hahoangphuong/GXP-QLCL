from __future__ import annotations

from xml.etree import ElementTree as ET

import pytest

from backend.app.document.docx_bookmark_range import (
    DocxBookmarkRangeError,
    delete_bookmark_ranges,
)

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W}


def _xml(body: str) -> ET.Element:
    return ET.fromstring(
        f'<w:document xmlns:w="{W}"><w:body>{body}</w:body></w:document>'
    )


def _text(root: ET.Element) -> list[str]:
    return ["".join(t.text or "" for t in p.findall(".//w:t", NS)) for p in root.findall(".//w:p", NS)]


def test_delete_range_removes_one_body_paragraph_and_preserves_next_member():
    root = _xml(
        '<w:p><w:pPr/><w:bookmarkStart w:id="1" w:name="TT3Del"/>'
        '<w:r><w:t>third member</w:t></w:r></w:p>'
        '<w:p><w:pPr/><w:bookmarkStart w:id="2" w:name="TT_VKNx"/>'
        '<w:bookmarkEnd w:id="1"/><w:r><w:t>institute member</w:t></w:r>'
        '<w:bookmarkEnd w:id="2"/></w:p>'
    )
    result = delete_bookmark_ranges(root, ("TT3Del",))
    assert result.deleted_paragraph_count == 1
    assert _text(root) == ["institute member"]
    assert [b.attrib[f"{{{W}}}name"] for b in root.findall(".//w:bookmarkStart", NS)] == ["TT_VKNx"]


def test_delete_range_with_cell_level_end_removes_only_selected_paragraphs():
    root = _xml(
        '<w:tbl><w:tr><w:tc><w:tcPr/>'
        '<w:p><w:r><w:t>keep before</w:t></w:r></w:p>'
        '<w:p><w:pPr/><w:bookmarkStart w:id="7" w:name="PVPeni1"/>'
        '<w:r><w:t>delete penicillin</w:t></w:r></w:p>'
        '<w:p><w:r><w:t>delete second line</w:t></w:r></w:p>'
        '<w:bookmarkEnd w:id="7"/>'
        '<w:p><w:r><w:t>keep after</w:t></w:r></w:p>'
        '</w:tc></w:tr></w:tbl>'
    )
    result = delete_bookmark_ranges(root, ("PVPeni1",))
    assert result.deleted_paragraph_count == 2
    assert _text(root) == ["keep before", "keep after"]


def test_overlapping_ranges_are_planned_before_mutation_and_delete_the_union():
    root = _xml(
        '<w:tbl><w:tr><w:tc><w:tcPr/>'
        '<w:p><w:bookmarkStart w:id="10" w:name="PVDuoclieu1"/>'
        '<w:r><w:t>delete herbal</w:t></w:r></w:p>'
        '<w:p><w:bookmarkStart w:id="20" w:name="PVCepha1"/>'
        '<w:bookmarkEnd w:id="10"/><w:r><w:t>delete cepha</w:t></w:r></w:p>'
        '<w:p><w:bookmarkEnd w:id="20"/><w:r><w:t>keep penicillin</w:t></w:r></w:p>'
        '</w:tc></w:tr></w:tbl>'
    )
    result = delete_bookmark_ranges(root, ("PVCepha1", "PVDuoclieu1"))
    assert result.planned_bookmarks == ("PVCepha1", "PVDuoclieu1")
    assert result.deleted_paragraph_count == 2
    assert _text(root) == ["keep penicillin"]
    assert root.findall(".//w:bookmarkStart", NS) == []
    assert root.findall(".//w:bookmarkEnd", NS) == []


def test_range_delete_fails_closed_when_range_crosses_cells():
    root = _xml(
        '<w:tbl><w:tr>'
        '<w:tc><w:p><w:bookmarkStart w:id="3" w:name="bad"/><w:r><w:t>x</w:t></w:r></w:p></w:tc>'
        '<w:tc><w:p><w:bookmarkEnd w:id="3"/><w:r><w:t>y</w:t></w:r></w:p></w:tc>'
        '</w:tr></w:tbl>'
    )
    with pytest.raises(DocxBookmarkRangeError, match="crosses table-cell boundaries"):
        delete_bookmark_ranges(root, ("bad",))


def test_range_delete_fails_closed_when_start_is_mid_paragraph():
    root = _xml(
        '<w:p><w:r><w:t>keep prefix</w:t></w:r>'
        '<w:bookmarkStart w:id="4" w:name="bad"/><w:r><w:t>delete</w:t></w:r></w:p>'
        '<w:p><w:bookmarkEnd w:id="4"/><w:r><w:t>keep next</w:t></w:r></w:p>'
    )
    with pytest.raises(DocxBookmarkRangeError, match="starts after visible paragraph text"):
        delete_bookmark_ranges(root, ("bad",))


def test_range_delete_missing_ok_matches_best_effort_legacy_contract():
    root = _xml('<w:p><w:r><w:t>keep</w:t></w:r></w:p>')
    result = delete_bookmark_ranges(root, ("missing",), missing_ok=True)
    assert result.planned_bookmarks == ()
    assert result.deleted_paragraph_count == 0
    with pytest.raises(DocxBookmarkRangeError, match="was not found"):
        delete_bookmark_ranges(root, ("missing",))
