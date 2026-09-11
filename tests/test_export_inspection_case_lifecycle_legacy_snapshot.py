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
    assert payload["row_count"] == 3
    assert payload["row_eligibility_counts"] == {
        "db_ktra_rows_emitted": 1,
        "db_ktra_structural_blank_rows_skipped": 0,
        "db_cc_rows_emitted": 2,
        "db_cc_linked_rows": 1,
        "db_cc_unlinked_rows": 1,
        "db_cc_unlinked_rows_with_business_payload": 1,
        "db_cc_invalid_link_rows": 0,
        "db_cc_structural_blank_rows_skipped": 0,
    }
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
        [{"__source_ktra": ktra, "__certificate_sources": [certificate]}], [_canonical_case()]
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


def test_snapshot_loader_preserves_multiple_case_certificates_without_selecting_one_and_expected_sha_mismatch(tmp_path: Path):
    payload = _payload(tmp_path)
    duplicate = dict(payload["sections"]["db.cc"]["rows"][0])
    duplicate["ID"] = "73"
    duplicate["__excel_row_number"] = "10"
    payload["sections"]["db.cc"]["rows"].append(duplicate)
    payload["sections"]["db.cc"]["row_count"] += 1
    payload["row_count"] += 1
    payload["row_eligibility_counts"]["db_cc_rows_emitted"] += 1
    payload["row_eligibility_counts"]["db_cc_linked_rows"] += 1
    loaded = planner.load_legacy_snapshot_payload(payload)
    assert len(loaded["legacy_rows"][0]["__certificate_sources"]) == 2
    report = planner.build_reconciliation_plan(loaded["legacy_rows"], [_canonical_case()])
    facts = {fact["canonical_fact"]: fact for fact in report["facts"]}
    assert facts["certificate_issue_date"]["reconciliation_status"] == "BLOCKED_CERTIFICATE_SOURCE_AMBIGUOUS"
    assert facts["certificate_expiry_date"]["legacy_certificate_candidate_count"] == 2
    assert facts["dossier_code"]["reconciliation_status"] == "ALREADY_MATCHES"

    with pytest.raises(RuntimeError, match="does not match"):
        planner.load_legacy_snapshot_payload(_payload(tmp_path), expected_workbook_sha256="f" * 64)


def test_snapshot_mode_is_platform_independent_and_does_not_import_workbook_reader(tmp_path: Path):
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text(json.dumps(_payload(tmp_path)), encoding="utf-8")
    loaded = planner.load_legacy_snapshot_json(snapshot_path)
    assert loaded["validation_counts"] == {
        "db_ktra_rows": 1,
        "db_cc_rows": 2,
        "linked_certificate_rows": 1,
        "unlinked_certificate_rows": 1,
        "cases_with_multiple_linked_certificates": 0,
    }
    source = inspect.getsource(planner)
    assert "from backend.app.domain.legacy_snapshot import read_core_sheet_rows" not in source.split("def run_read_only_plan(", 1)[0]
    assert "pywin32" not in source


def test_ktra_structural_blank_rows_are_skipped_but_invalid_identity_with_business_payload_fails_closed(tmp_path: Path):
    source_rows = _source_rows()
    source_rows["db.ktra"].append({"ID": "", "__excel_row_number": "13"})
    workbook = tmp_path / "legacy.xlsb"
    workbook.write_bytes(b"fixture")
    payload = exporter.build_snapshot_payload(workbook, source_rows)
    assert payload["sections"]["db.ktra"]["row_count"] == 1
    assert payload["row_eligibility_counts"]["db_ktra_structural_blank_rows_skipped"] == 1

    source_rows["db.ktra"][-1]["Mã hồ sơ"] = "unexpected-payload"
    with pytest.raises(RuntimeError, match="db.ktra row 13 has invalid required ID"):
        exporter.build_snapshot_payload(workbook, source_rows)


def test_cc_unlinked_and_structural_rows_are_explicit_and_malformed_link_fails_closed(tmp_path: Path):
    source_rows = _source_rows()
    source_rows["db.cc"].append({"ID": "73", "__excel_row_number": "10", "ID ĐỢT KTRA": ""})
    workbook = tmp_path / "legacy.xlsb"
    workbook.write_bytes(b"fixture")
    payload = exporter.build_snapshot_payload(workbook, source_rows)
    assert payload["sections"]["db.cc"]["row_count"] == 2
    assert payload["row_eligibility_counts"]["db_cc_unlinked_rows_with_business_payload"] == 1
    assert payload["row_eligibility_counts"]["db_cc_structural_blank_rows_skipped"] == 1

    source_rows["db.cc"][-1]["ID ĐỢT KTRA"] = "not-a-case-id"
    with pytest.raises(RuntimeError, match="inspection_case_legacy_id_ref"):
        exporter.build_snapshot_payload(workbook, source_rows)


def test_cc_link_to_missing_ktra_fails_closed_and_multiple_case_a_does_not_block_case_b(tmp_path: Path):
    payload = _payload(tmp_path)
    linked = dict(payload["sections"]["db.cc"]["rows"][0])
    linked["inspection_case_legacy_id_ref"] = "999"
    payload["sections"]["db.cc"]["rows"][0] = linked
    with pytest.raises(RuntimeError, match="references missing db.ktra ID 999"):
        planner.load_legacy_snapshot_payload(payload)

    source_rows = _source_rows()
    source_rows["db.ktra"].append(
        {
            "ID": "42", "__excel_row_number": "14", "Mã hồ sơ": "HS-42", "Ngày nộp": "14-01-2026",
            "Ngày K.tra": "17-19/07/2026", "TIÊU CHUẨN ÁP DỤNG": "WHO-GMP", "LOẠI KIỂM TRA": "Tai",
        }
    )
    source_rows["db.cc"].append(
        {"ID": "73", "__excel_row_number": "10", "ID ĐỢT KTRA": "41", "Ngày cấp CC": "2027-08-21"}
    )
    source_rows["db.cc"].append(
        {"ID": "74", "__excel_row_number": "11", "ID ĐỢT KTRA": "42", "Ngày cấp CC": "2026-08-21", "Hết hạn CC": "2029-08-19"}
    )
    workbook = tmp_path / "two-cases.xlsb"
    workbook.write_bytes(b"fixture")
    loaded = planner.load_legacy_snapshot_payload(exporter.build_snapshot_payload(workbook, source_rows))
    case_b = dict(_canonical_case(), id="case-42", legacy_inspection_id=42, application={"dossier_code": "HS-42", "submitted_on": date(2026, 1, 14)})
    report = planner.build_reconciliation_plan(loaded["legacy_rows"], [_canonical_case(), case_b])
    b_facts = [fact for fact in report["facts"] if fact["legacy_inspection_id"] == 42]
    assert next(fact for fact in b_facts if fact["canonical_fact"] == "certificate_issue_date")["reconciliation_status"] == "ALREADY_MATCHES"
    assert next(fact for fact in b_facts if fact["canonical_fact"] == "dossier_code")["reconciliation_status"] == "ALREADY_MATCHES"


def test_case_with_no_linked_certificate_blocks_only_certificate_facts(tmp_path: Path):
    source_rows = _source_rows()
    source_rows["db.cc"] = [source_rows["db.cc"][1]]  # Retain only valid unlinked certificate evidence.
    workbook = tmp_path / "unlinked-only.xlsb"
    workbook.write_bytes(b"fixture")
    loaded = planner.load_legacy_snapshot_payload(exporter.build_snapshot_payload(workbook, source_rows))
    report = planner.build_reconciliation_plan(loaded["legacy_rows"], [_canonical_case()])
    facts = {fact["canonical_fact"]: fact for fact in report["facts"]}
    assert facts["certificate_issue_date"]["reconciliation_status"] == "BLOCKED_CERTIFICATE_SOURCE_MISSING"
    assert facts["certificate_expiry_date"]["legacy_certificate_candidate_count"] == 0
    assert facts["actual_inspection_period"]["reconciliation_status"] == "ALREADY_MATCHES"
