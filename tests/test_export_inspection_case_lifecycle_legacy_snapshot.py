from __future__ import annotations

from datetime import date
from hashlib import sha256
import inspect
import json
from pathlib import Path

import pytest

from tools import export_inspection_case_lifecycle_legacy_snapshot as exporter
from tools import plan_inspection_case_lifecycle_reconciliation as planner


def _source_rows() -> dict[str, list[dict[str, str]]]:
    return {
        "db.ktra": [
            {
                "ID": "41",
                "__excel_row_number": "12",
                "Q. định": "540/QD-KT 05/05/2026",
                "B. bản": "2026-05-05",
                "Ngày K.tra": "17-19/07/2026",
                "Ngày nộp": "14-01-2026",
                "Mã hồ sơ": "HS-41",
                "TIÊU CHUẨN ÁP DỤNG": "WHO-GMP",
                "LOẠI KIỂM TRA": "Tai",
            }
        ],
        "db.cc": [
            {
                "ID": "71",
                "__excel_row_number": "8",
                "ID ĐỢT KTRA": "41",
                "Ngày cấp CC": "2026-08-21",
                "Hết hạn CC": "2029-08-19",
                "THỜI HẠN HIỆU LỰC": "",
            },
            {
                "ID": "72",
                "__excel_row_number": "9",
                "ID ĐỢT KTRA": "",
                "Ngày cấp CC": "2020-01-01",
            },
        ],
    }


def _canonical_case() -> dict[str, object]:
    return {
        "id": "case-41",
        "legacy_inspection_id": 41,
        "gxp_type": "GMP",
        "applicable_standard": "WHO-GMP",
        "inspection_type": "Tai",
        "application": {"dossier_code": "HS-41", "submitted_on": date(2026, 1, 14)},
        "plan": {},
        "outcome": {"inspected_on": date(2026, 7, 17), "inspected_to_on": date(2026, 7, 19)},
        "certificate": {"issue_date": date(2026, 8, 21), "expiry_date": date(2029, 8, 19)},
    }


def _payload(tmp_path: Path) -> dict[str, object]:
    workbook = tmp_path / "legacy.xlsb"
    workbook.write_bytes(b"canonical-workbook-fixture")
    return exporter.build_snapshot_payload(workbook, _source_rows())


def test_exporter_uses_canonical_workbook_extraction_owner_and_writes_deterministic_payload(monkeypatch, tmp_path: Path):
    workbook = tmp_path / "legacy.xlsb"
    workbook.write_bytes(b"canonical-workbook-fixture")
    output = tmp_path / "snapshot.json"
    calls: list[Path] = []

    def read_owner(path: Path):
        calls.append(path)
        return _source_rows()

    monkeypatch.setattr(exporter, "read_core_sheet_rows", read_owner)
    monkeypatch.setattr(
        "sys.argv",
        ["export_inspection_case_lifecycle_legacy_snapshot.py", "--workbook", str(workbook), "--output", str(output)],
    )
    assert exporter.main() == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert calls == [workbook.resolve()]
    assert payload["extraction_owner"] == "backend.app.domain.legacy_snapshot.read_core_sheet_rows"
    assert payload["source_workbook_sha256"] == sha256(workbook.read_bytes()).hexdigest()
    assert payload["source_sheets"] == ["db.ktra", "db.cc"]
    assert payload["row_count"] == 2
    assert json.dumps(payload, ensure_ascii=False, sort_keys=True) == json.dumps(
        exporter.build_snapshot_payload(workbook, _source_rows()), ensure_ascii=False, sort_keys=True
    )


def test_snapshot_loader_preserves_db_cc_fk_linkage_and_matches_equivalent_in_memory_plan(tmp_path: Path):
    payload = _payload(tmp_path)
    loaded = planner.load_legacy_snapshot_payload(payload)
    report_from_snapshot = planner.build_reconciliation_plan(loaded["legacy_rows"], [_canonical_case()])
    ktra = payload["sections"]["db.ktra"]["rows"][0]
    certificate = payload["sections"]["db.cc"]["rows"][0]
    report_in_memory = planner.build_reconciliation_plan(
        [{"__source_ktra": ktra, "__certificate_source": certificate}], [_canonical_case()]
    )
    assert report_from_snapshot["summary"] == report_in_memory["summary"]
    assert report_from_snapshot["facts"] == report_in_memory["facts"]
    serialized = json.dumps(report_from_snapshot, default=str)
    assert "__certificate_source" not in serialized
    assert "HS-41" not in serialized
    assert "540/QD-KT" not in serialized


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda payload: payload.update(schema_version="wrong/v1"), "schema_version"),
        (lambda payload: payload["sections"].pop("db.cc"), "missing required section db.cc"),
        (lambda payload: payload["sections"]["db.ktra"]["rows"][0].pop("ID"), "missing required fields"),
        (lambda payload: payload["sections"]["db.cc"]["rows"].append(dict(payload["sections"]["db.cc"]["rows"][0])), "row_count does not match"),
    ],
)
def test_snapshot_loader_fails_closed_on_malformed_content(tmp_path: Path, mutate, message: str):
    payload = _payload(tmp_path)
    mutate(payload)
    with pytest.raises(RuntimeError, match=message):
        planner.load_legacy_snapshot_payload(payload)


def test_snapshot_loader_fails_closed_on_duplicate_case_certificate_and_expected_sha_mismatch(tmp_path: Path):
    payload = _payload(tmp_path)
    duplicate = dict(payload["sections"]["db.cc"]["rows"][0])
    duplicate["ID"] = "73"
    duplicate["__excel_row_number"] = "10"
    payload["sections"]["db.cc"]["rows"].append(duplicate)
    payload["sections"]["db.cc"]["row_count"] += 1
    payload["row_count"] += 1
    with pytest.raises(RuntimeError, match="multiple db.cc certificate rows"):
        planner.load_legacy_snapshot_payload(payload)

    with pytest.raises(RuntimeError, match="does not match"):
        planner.load_legacy_snapshot_payload(_payload(tmp_path), expected_workbook_sha256="f" * 64)


def test_snapshot_mode_is_platform_independent_and_does_not_import_workbook_reader(tmp_path: Path):
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text(json.dumps(_payload(tmp_path)), encoding="utf-8")
    loaded = planner.load_legacy_snapshot_json(snapshot_path)
    assert loaded["validation_counts"] == {"db_ktra_rows": 1, "db_cc_rows": 1, "linked_certificate_rows": 1}
    source = inspect.getsource(planner)
    assert "from backend.app.domain.legacy_snapshot import read_core_sheet_rows" not in source.split("def run_read_only_plan(", 1)[0]
    assert "pywin32" not in source
