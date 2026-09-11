from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from pathlib import Path

from tools.trace_inspection_qd_kt_vba import EXPECTED_SHA256, _decode, build_trace

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "legacy" / "GXP-VBA code.zip"


def _variant(tmp_path: Path, transform) -> Path:
    target = tmp_path / "variant.zip"
    with zipfile.ZipFile(SOURCE) as source, zipfile.ZipFile(target, "w") as output:
        for info in source.infolist():
            payload = source.read(info.filename)
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


def test_missing_source_and_hash_mismatch_fail_closed(tmp_path):
    missing = subprocess.run([sys.executable, "tools/trace_inspection_qd_kt_vba.py", "--vba-zip", str(tmp_path / "missing.zip")], cwd=ROOT, capture_output=True, text=True)
    assert missing.returncode == 2 and "not found" in missing.stdout
    copy = tmp_path / "copy.zip"
    copy.write_bytes(SOURCE.read_bytes())
    mismatch = subprocess.run([sys.executable, "tools/trace_inspection_qd_kt_vba.py", "--vba-zip", str(copy), "--expected-sha256", "0" * 64], cwd=ROOT, capture_output=True, text=True)
    assert mismatch.returncode == 2 and "SHA256 mismatch" in mismatch.stdout
