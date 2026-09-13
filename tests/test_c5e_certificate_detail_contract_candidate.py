from __future__ import annotations

from tools.build_c5e_certificate_detail_contract_candidate import (
    active_lines,
    build_control_context,
    derive_contract,
    strip_comment,
)


def test_comment_stripping_preserves_string_apostrophe_and_drops_vba_comment():
    line = "x = \"a'b\" ' tail"
    assert strip_comment(line) == 'x = "a\'b"'


def test_contract_detects_formatted_bookmark_copy_and_key_transform():
    text = """
Private Sub Input_DC_to_CC()
For j = 1 To 2
If PV_map(j) <> 0 Then
.ActiveWindow.Selection.FormattedText = wdDoc2.Bookmarks(Key2Bookmark(DCForm.PVCN_GxP(j, PVCN_colKey))).Range.FormattedText
If Trim$(PV_Desc(PV_map(j))) <> vbNullString Then
If EngPart Then
End If
End If
End If
Next j
End Sub
"""
    rows = build_control_context(active_lines(text))
    contract = derive_contract(rows)
    assert contract["render_primitive_candidate"] == "formatted_bookmark_fragment_copy_plus_text_append"
    assert contract["table_row_clone_is_primary_primitive"] is False
    assert len(contract["dynamic_formatted_bookmark_copies"]) == 1
    item = contract["dynamic_formatted_bookmark_copies"][0]
    assert "PVCN_colKey" in item["source_bookmark_key_expression"]
    assert item["copy_mode"] == "Range.FormattedText -> Selection.FormattedText"


def test_contract_marks_unkeyed_and_summary_substitution_forbidden():
    rows = build_control_context(active_lines("""
Private Sub Input_DC_to_CC()
DCForm.Load_DC_Nodes(s_D, PV_map, PV_Desc, ncount)
If EngPart Then
End If
End Sub
"""))
    contract = derive_contract(rows)
    assert contract["explicit_invariants"]["unkeyed_entries_allowed"] is False
    assert contract["explicit_invariants"]["compact_summary_allowed"] is False
    assert contract["explicit_invariants"]["historical_prose_allowed"] is False
