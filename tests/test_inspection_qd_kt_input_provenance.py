from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from tools.trace_inspection_qd_kt_input_provenance import build_provenance
from tools.trace_inspection_qd_kt_vba import EXPECTED_SHA256, _decode

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


def _without_coordinates(value):
    result = json.loads(json.dumps(value))

    def strip(item):
        if isinstance(item, dict):
            item.pop("line", None)
            for child in item.values():
                strip(child)
        elif isinstance(item, list):
            for child in item:
                strip(child)

    strip(result)
    result.pop("source_zip_sha256", None)
    return result


def test_real_provenance_captures_all_active_inputs_and_remains_fail_closed():
    report = build_provenance(SOURCE)
    assert report["source_zip_sha256"] == EXPECTED_SHA256
    assert set(report["fields"]) == {
        "Fulldate", "Tencoso", "Diadiem", "Diadiemx", "Diachicoso", "HsDK",
        "NgaynopHsDK", "QDKT", "NgayQDKT", "VKNx", "VKN", "TT3x", "TT3Del", "TTx",
    }
    assert report["classification_counts"] == {"OWNER_PROVEN": 0, "OWNER_PARTIAL": 6, "OWNER_BLOCKED": 8}
    assert report["decision"]["typed_qd_kt_input_contract"] == "BUSINESS_INPUT_CONTRACT_MISSING"
    assert report["invariants"]["display_prose_parsed_as_truth"] is False


def test_assignment_source_mutation_changes_provenance(tmp_path):
    original = build_provenance(SOURCE)
    changed_zip = _variant(tmp_path, lambda text: text.replace("s_MaHsDk = Rg3.Cells(1, ColDB_HSDK_Ktra + 1).Value", "s_MaHsDk = Rg3.Cells(1, ColDB_HSDK_Ktra + 2).Value", 1))
    changed = build_provenance(changed_zip, trace_path=ROOT / "artifacts/legacy_audit/inspection_qd_kt_vba_trace.json", expected_sha256=None)
    assert _without_coordinates(changed["fields"]["HsDK"]) != _without_coordinates(original["fields"]["HsDK"])


def test_commenting_required_assignment_fails_closed(tmp_path):
    commented = _variant(tmp_path, lambda text: text.replace("s_MaHsDk = Rg3.Cells(1, ColDB_HSDK_Ktra + 1).Value", "' s_MaHsDk = Rg3.Cells(1, ColDB_HSDK_Ktra + 1).Value", 1))
    with pytest.raises(RuntimeError, match="source assignment missing"):
        build_provenance(commented, trace_path=ROOT / "artifacts/legacy_audit/inspection_qd_kt_vba_trace.json", expected_sha256=None)


def test_harmless_line_shift_preserves_semantic_provenance(tmp_path):
    shifted = _variant(tmp_path, lambda text: "' harmless\n\n" + text)
    shifted_report = build_provenance(shifted, trace_path=ROOT / "artifacts/legacy_audit/inspection_qd_kt_vba_trace.json", expected_sha256=None)
    assert _without_coordinates(shifted_report) == _without_coordinates(build_provenance(SOURCE))
