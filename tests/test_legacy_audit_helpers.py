from tools.legacy_audit_helpers import (
    detect_file_ops,
    detect_header_row,
    detect_word_ops,
    extract_procedure_defs,
    find_application_run_targets,
    split_procedure_blocks,
)


def test_extract_procedure_defs_finds_sub_and_function():
    source = """
    Public Sub Main()
    End Sub

    Private Function Load_Lib() As Boolean
    End Function
    """
    procs = extract_procedure_defs(source)
    assert [(p.kind, p.name) for p in procs] == [("Sub", "Main"), ("Function", "Load_Lib")]


def test_find_application_run_targets_parses_cross_workbook_call():
    source = 'If Load_Lib Then Application.Run "GPs.xlam!ReFilter"'
    targets = find_application_run_targets(source)
    assert targets == [{"workbook": "GPs.xlam", "procedure": "ReFilter"}]


def test_detect_word_and_file_ops():
    source = """
    Set wd = CreateObject("Word.Application")
    Set fso = CreateObject("Scripting.FileSystemObject")
    ShellExecute 0, "open", path, "", "", 1
    doc.SaveAs fileName
    """
    assert detect_word_ops(source) is True
    assert detect_file_ops(source) == ["fso", "save_as", "shell"]


def test_detect_header_row_chooses_densest_row():
    rows = [
        ["", "", ""],
        ["Title", "", ""],
        ["ID", "Name", "Address"],
        ["1", "A", "X"],
    ]
    assert detect_header_row(rows) == 2


def test_split_procedure_blocks_returns_individual_bodies():
    source = """
    Public Sub A()
        Call B
    End Sub

    Private Function B() As Boolean
        B = True
    End Function
    """
    blocks = split_procedure_blocks(source)
    assert set(blocks) == {"A", "B"}
    assert "Call B" in blocks["A"]
