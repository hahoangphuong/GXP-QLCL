from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from pathlib import Path

from tools.trace_inspection_qd_kt_vba import EXPECTED_SHA256, _branch_context, _decode, build_trace

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "legacy" / "GXP-VBA code.zip"


def _variant(tmp_path: Path, transform, module_transform=None) -> Path:
    target = tmp_path / "variant.zip"
    with zipfile.ZipFile(SOURCE) as source, zipfile.ZipFile(target, "w") as output:
        for info in source.infolist():
            payload = source.read(info.filename)
            if info.filename == "Module1.bas" and module_transform:
                payload = module_transform(_decode(payload)).encode("utf-8")
            if info.filename == "RecordForm.frm":
                payload = transform(_decode(payload)).encode("utf-8")
            output.writestr(info, payload)
    return target


def _without_coordinates(report):
    value = json.loads(json.dumps(report))
    value.pop("source_zip_sha256", None)
    def strip_lines(item):
        if isinstance(item, dict):
            item.pop("line", None)
            item.pop("start_line", None)
            item.pop("end_line", None)
            for child in item.values():
                strip_lines(child)
        elif isinstance(item, list):
            for child in item:
                strip_lines(child)
    strip_lines(value)
    return value


def _semantic_operations(report):
    return [
        {key: operation.get(key) for key in ("physical_bookmark", "physical_bookmark_expression", "operation_type", "expression", "branch_predicates", "reachability_i2")}
        for operation in report["physical_bookmark_operations"]
    ]


def test_real_trace_is_source_derived_and_classifies_tt3del():
    report = build_trace(SOURCE)
    assert report["source_zip_sha256"] == EXPECTED_SHA256
    assert report["logical_field_disposition"]["QDKT"]["status"] == "PROVEN_WRITE_I2"
    assert report["logical_field_disposition"]["TT3Del"]["status"] == "PROVEN_CONDITIONAL_DELETE_I2"
    assert report["logical_field_disposition"]["TT3x"]["status"] == "PROVEN_CONDITIONAL_WRITE_I2"
    assert report["logical_field_disposition"]["TT1"]["status"] == "UNRESOLVED_MAPPING"
    assert report["logical_field_disposition"]["TT2"]["status"] == "UNRESOLVED_MAPPING"
    assert all("commented" not in op["branch_predicates"].lower() for op in report["physical_bookmark_operations"])


def test_source_mutations_change_or_fail_trace(tmp_path):
    missing = _variant(tmp_path, lambda text: text.replace('Replace_Bookmark wdDoc, "QDKT", QDKT', "' removed", 1))
    changed = build_trace(missing, expected_sha256=None)
    assert changed["logical_field_disposition"]["QDKT"]["status"] == "PROVEN_NO_ACTIVE_OPERATION_I2"

    branch = _variant(tmp_path, lambda text: text.replace("If i = 2 Then Replace_Bookmark wdDoc, \"VKN\"", "If i = 3 Then Replace_Bookmark wdDoc, \"VKN\"", 1))
    branch_report = build_trace(branch, expected_sha256=None)
    assert branch_report["logical_field_disposition"]["VKN"]["status"] == "UNRESOLVED_MAPPING"


def test_comments_are_ignored_and_line_shifts_only_change_coordinates(tmp_path):
    commented = _variant(tmp_path, lambda text: text.replace('Replace_Bookmark wdDoc, "QDKT", QDKT', "' Replace_Bookmark wdDoc, \"QDKT\", QDKT", 1))
    report = build_trace(commented, expected_sha256=None)
    assert report["logical_field_disposition"]["QDKT"]["status"] == "PROVEN_NO_ACTIVE_OPERATION_I2"

    shifted = _variant(tmp_path, lambda text: "' harmless\n\n" + text)
    shifted_report = build_trace(shifted, expected_sha256=None)
    assert _semantic_operations(build_trace(SOURCE)) == _semantic_operations(shifted_report)


def test_duplicate_required_call_fails_closed(tmp_path):
    duplicate = _variant(tmp_path, lambda text: text.replace("If Not Get_Tpl(i, syear, tpl, fname, iFName) Then GoTo Quit0", "If Not Get_Tpl(i, syear, tpl, fname, iFName) Then GoTo Quit0\n    If Not Get_Tpl(i, syear, tpl, fname, iFName) Then GoTo Quit0", 1))
    try:
        build_trace(duplicate, expected_sha256=None)
    except RuntimeError as exc:
        assert "exactly one Get_Tpl call" in str(exc)
    else:
        raise AssertionError("duplicate required call was accepted")


def test_duplicate_procedure_names_fail_closed_in_each_source_module(tmp_path):
    duplicate_module = _variant(
        tmp_path,
        lambda text: text,
        module_transform=lambda text: text + "\nSub TaoQDKT_KHKT()\nEnd Sub\n",
    )
    try:
        build_trace(duplicate_module, expected_sha256=None)
    except RuntimeError as exc:
        assert "duplicate procedure" in str(exc)
        assert "TaoQDKT_KHKT" in str(exc)
        assert "ranges=" in str(exc) and "count=2" in str(exc)
    else:
        raise AssertionError("duplicate Module1 procedure was accepted")

    duplicate_record = _variant(
        tmp_path,
        lambda text: text + "\nPrivate Sub CreateFile()\nEnd Sub\n",
    )
    try:
        build_trace(duplicate_record, expected_sha256=None)
    except RuntimeError as exc:
        assert "duplicate procedure" in str(exc)
        assert "CreateFile" in str(exc)
        assert "count=2" in str(exc)
    else:
        raise AssertionError("duplicate RecordForm procedure was accepted")


def test_get_tpl_case_2_is_bounded_and_requires_one_assignment(tmp_path):
    original = 'tpl = "2. QD KT - " & S_GPs & ".dotx"'
    missing = _variant(tmp_path, lambda text: text.replace(original, "' removed", 1))
    try:
        build_trace(missing, expected_sha256=None)
    except RuntimeError as exc:
        assert "Case 2 requires exactly one tpl assignment, found 0" in str(exc)
    else:
        raise AssertionError("Case 2 accepted an assignment from another case")

    duplicate = _variant(tmp_path, lambda text: text.replace(original, original + "\n        " + original, 1))
    try:
        build_trace(duplicate, expected_sha256=None)
    except RuntimeError as exc:
        assert "Case 2 requires exactly one tpl assignment, found 2" in str(exc)
    else:
        raise AssertionError("duplicate Case 2 assignments were accepted")


def test_branch_context_preserves_elseif_else_negation_and_unknowns():
    first = ["If i = 2 Then", "Replace_Bookmark wdDoc, \"A\", value", "ElseIf i = 3 Then", "Replace_Bookmark wdDoc, \"B\", value", "Else", "Replace_Bookmark wdDoc, \"C\", value", "End If"]
    assert _branch_context(first, 1)[1] == "REACHABLE_I2"
    assert _branch_context(first, 3)[1] == "UNREACHABLE_I2"
    assert _branch_context(first, 5)[1] == "UNREACHABLE_I2"

    second = ["If i = 3 Then", "x", "ElseIf i = 2 Then", "x", "Else", "x", "End If"]
    assert _branch_context(second, 3)[1] == "REACHABLE_I2"
    assert _branch_context(second, 5)[1] == "UNREACHABLE_I2"

    greater = ["If i > 2 Then", "x", "Else", "x", "End If"]
    assert _branch_context(greater, 1)[1] == "UNREACHABLE_I2"
    assert _branch_context(greater, 3)[1] == "REACHABLE_I2"

    nested = ["If Sel_GPs = 1 Then", "If i = 2 Then", "x", "End If", "End If"]
    assert _branch_context(nested, 2)[1] == "CONDITIONAL_I2"
    unknown = ["If Sel_GPs = 1 Then", "x", "End If"]
    assert _branch_context(unknown, 1)[1] == "CONDITIONAL_I2"


def test_missing_source_and_hash_mismatch_fail_closed(tmp_path):
    missing = subprocess.run([sys.executable, "tools/trace_inspection_qd_kt_vba.py", "--vba-zip", str(tmp_path / "missing.zip")], cwd=ROOT, capture_output=True, text=True)
    assert missing.returncode == 2 and "not found" in missing.stdout
    copy = tmp_path / "copy.zip"
    copy.write_bytes(SOURCE.read_bytes())
    mismatch = subprocess.run([sys.executable, "tools/trace_inspection_qd_kt_vba.py", "--vba-zip", str(copy), "--expected-sha256", "0" * 64], cwd=ROOT, capture_output=True, text=True)
    assert mismatch.returncode == 2 and "SHA256 mismatch" in mismatch.stdout
