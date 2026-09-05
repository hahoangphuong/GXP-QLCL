from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

TOOL = (
    ROOT
    / "tools"
    / "audit_c5e_certificate_detail_selection_geometry.py"
)


def _load_tool():
    spec = (
        importlib.util.spec_from_file_location(
            "c5e_selection_geometry",
            TOOL,
        )
    )

    assert spec is not None
    assert spec.loader is not None

    module = (
        importlib.util.module_from_spec(
            spec
        )
    )

    spec.loader.exec_module(
        module
    )

    return module


def test_known_sequence_is_profiled_without_blocker():
    module = _load_tool()

    source = """
Selection.TypeText Text:="Heading"
Selection.FormattedText = wdDoc2.Bookmarks(Key2Bookmark("1.1")).Range.FormattedText
Selection.EndKey Unit:=wdLine
Selection.MoveRight Unit:=wdCharacter, Count:=1
Selection.TypeText Text:="Description"
"""

    report = (
        module.audit_selection_geometry(
            source
        )
    )

    assert (
        report["status"]
        == "SELECTION_GEOMETRY_PROFILED"
    )

    assert (
        report["summary"][
            "operation_count"
        ]
        == 5
    )

    assert (
        report["summary"][
            "mutating_operation_count"
        ]
        == 5
    )

    assert (
        report["summary"][
            "unknown_member_count"
        ]
        == 0
    )

    assert [
        item["member"]
        for item in report[
            "operations"
        ]
    ] == [
        "TypeText",
        "FormattedText",
        "EndKey",
        "MoveRight",
        "TypeText",
    ]


def test_bookmarks_range_and_terminal_formattedtext_are_queries():
    module = _load_tool()

    source = """
Selection.TypeText Text:="Heading"
Selection.FormattedText = Selection.Bookmarks("Pvi").Range.FormattedText
"""

    report = (
        module.audit_selection_geometry(
            source
        )
    )

    assert (
        report["status"]
        == "SELECTION_GEOMETRY_PROFILED"
    )

    #
    # LHS Selection.FormattedText is a write.
    #
    # RHS:
    #
    # Selection.Bookmarks(...).Range.FormattedText
    #
    # is a read chain.
    #
    assert (
        report["member_counts"][
            "Bookmarks"
        ]
        == 1
    )

    assert (
        report["member_counts"][
            "Range"
        ]
        == 1
    )

    assert (
        report["member_counts"][
            "FormattedText"
        ]
        == 2
    )

    assert (
        report["summary"][
            "mutating_operation_count"
        ]
        == 2
    )

    assert (
        report["summary"][
            "query_operation_count"
        ]
        == 3
    )

    formatted = [
        item
        for item in report[
            "operations"
        ]
        if (
            item["member"]
            == "FormattedText"
        )
    ]

    assert [
        item[
            "classification"
        ]
        for item in formatted
    ] == [
        "mutating",
        "query",
    ]


def test_unknown_member_fails_closed():
    module = _load_tool()

    source = """
Selection.TypeText Text:="Heading"
Selection.FormattedText = wdDoc2.Bookmarks("L1").Range.FormattedText
Selection.MysteryCursorOperation Unit:=wdLine
"""

    report = (
        module.audit_selection_geometry(
            source
        )
    )

    assert (
        report["status"]
        == "SELECTION_GEOMETRY_BLOCKED"
    )

    assert (
        report["summary"][
            "unknown_member_count"
        ]
        == 1
    )

    assert (
        report[
            "unknown_members"
        ]
        == [
            "MysteryCursorOperation"
        ]
    )

    assert (
        report["blockers"][0][
            "code"
        ]
        == "UNKNOWN_SELECTION_MEMBER"
    )


def test_comments_and_strings_do_not_create_false_operations():
    module = _load_tool()

    source = """
' Selection.MoveLeft Unit:=wdCharacter
Selection.TypeText Text:="Selection.Delete inside string"
Selection.FormattedText = wdDoc2.Bookmarks("L1").Range.FormattedText ' Selection.MoveDown
"""

    report = (
        module.audit_selection_geometry(
            source
        )
    )

    assert (
        report["status"]
        == "SELECTION_GEOMETRY_PROFILED"
    )

    assert [
        item["member"]
        for item in report[
            "operations"
        ]
    ] == [
        "TypeText",
        "FormattedText",
    ]

    assert (
        "Delete"
        not in report[
            "member_counts"
        ]
    )

    assert (
        "MoveDown"
        not in report[
            "member_counts"
        ]
    )

    assert (
        "MoveLeft"
        not in report[
            "member_counts"
        ]
    )


def test_vba_continuation_preserves_line_span():
    module = _load_tool()

    source = """
Selection.TypeText _
    Text:="Heading"
Selection.FormattedText = wdDoc2.Bookmarks("L1").Range.FormattedText
"""

    report = (
        module.audit_selection_geometry(
            source
        )
    )

    assert (
        report["status"]
        == "SELECTION_GEOMETRY_PROFILED"
    )

    first = report[
        "operations"
    ][0]

    assert (
        first["member"]
        == "TypeText"
    )

    assert (
        first["start_line"]
        == 2
    )

    assert (
        first["end_line"]
        == 3
    )


def test_formattedtext_read_vs_write_is_context_sensitive():
    module = _load_tool()

    source = """
Selection.FormattedText = sourceRange.FormattedText
x = Selection.Range.FormattedText
"""

    report = (
        module.audit_selection_geometry(
            source
        )
    )

    assert (
        report["status"]
        == "SELECTION_GEOMETRY_PROFILED"
    )

    operations = report[
        "operations"
    ]

    assert [
        (
            item["member"],
            item[
                "classification"
            ],
        )
        for item in operations
    ] == [
        (
            "FormattedText",
            "mutating",
        ),
        (
            "Range",
            "query",
        ),
        (
            "FormattedText",
            "query",
        ),
    ]


def test_formatting_properties_are_not_cursor_blockers():
    module = _load_tool()

    source = """
Selection.Font.Bold = True
Selection.Font.Italic = True
Selection.Font.Color = wdColorBlack
Selection.ParagraphFormat.SpaceBefore = 0
Selection.ParagraphFormat.SpaceAfter = 6
Selection.TypeText Text:="A"
Selection.FormattedText = sourceRange.FormattedText
"""

    report = (
        module.audit_selection_geometry(
            source
        )
    )

    assert (
        report["status"]
        == "SELECTION_GEOMETRY_PROFILED"
    )

    assert (
        report["summary"][
            "unknown_member_count"
        ]
        == 0
    )

    assert set(
        report[
            "formatting_members"
        ]
    ) == {
        "Bold",
        "Color",
        "Font",
        "Italic",
        "ParagraphFormat",
        "SpaceAfter",
        "SpaceBefore",
    }

    assert set(
        report[
            "mutating_members"
        ]
    ) == {
        "FormattedText",
        "TypeText",
    }