from __future__ import annotations

import json
from pathlib import Path

from tools.audit_c5e_certificate_detail_semantics import _active_lines, _strip_comment

ROOT = Path(__file__).resolve().parents[1]


def test_strip_comment_does_not_strip_apostrophe_inside_vba_string():
    assert _strip_comment("x = \"a'b\" ' comment") == "x = \"a'b\""


def test_active_lines_excludes_commented_vba():
    lines = _active_lines("""
' Bookmarks("OLD")
x = Key2Bookmark(k)
' y.Copy
z.Copy
""")
    text = "\n".join(code for _, code in lines)
    assert "OLD" not in text
    assert "Key2Bookmark" in text
    assert "z.Copy" in text


def test_semantic_extraction_uses_only_captured_fixtures_when_available():
    from tools.audit_c5e_certificate_detail_semantics import audit, ACTIVE_VBA

    if not ACTIVE_VBA.is_file():
        return
    report = audit()
    assert report["active_procedure_fixture"].endswith("Input_DC_to_CC.active.bas")
    assert report["invariants"]["commented_code_used"] is False
    assert report["invariants"]["unkeyed_entries_used"] is False
    assert report["invariants"]["production_code_modified"] is False
    assert len(report["templates"]) >= 1
