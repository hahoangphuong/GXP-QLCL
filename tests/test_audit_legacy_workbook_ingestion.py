from __future__ import annotations

from hashlib import sha256
import json

import pytest

import tools.audit_legacy_workbook_ingestion as audit
from tools.audit_legacy_workbook_ingestion import _column_profile, _header_terms, _sheet_kind


def test_unicode_header_analysis_preserves_vietnamese_identifier_cues():
    assert "mã" in _header_terms("Mã số cơ sở")
    column = _column_profile("Mã số", 1, ["1", "2"])
    assert column["stable_identifier_potential"] == "CANDIDATE"
    assert "mã" in column["header_terms_unicode_preserved"]


def test_sheet_classification_uses_approved_authority_not_static_ingestion_claims():
    assert _sheet_kind("TTviên") == "AUTHORITATIVE_SOURCE"
    assert _sheet_kind("Lịch sử TTV") == "REPORT_OR_DERIVED_ONLY"
    assert _sheet_kind("DsCB") == "REPORT_OR_DERIVED_ONLY"
    assert _sheet_kind("Nhóm 1c") == "OBSOLETE"
    assert _sheet_kind("Địa danh") == "REFERENCE"
    assert _sheet_kind("unclassified-sheet") == "UNKNOWN_REQUIRES_REVIEW"


class _Cell:
    def __init__(self, value: str):
        self.v = value


class _Sheet:
    def __init__(self, rows: list[list[str]]):
        self._rows = rows

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def rows(self):
        return [[_Cell(value) for value in row] for row in self._rows]


class _Workbook:
    def __init__(self):
        self.sheets = ["TTviên", "Lịch sử TTV", "Nhóm 1c", "Unknown"]

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def get_sheet(self, _name: str):
        return _Sheet([["Mã số", "Tên"], ["1", "Value"]])


def _snapshot_payload(workbook_sha256: str, sheet_names: list[str]) -> dict[str, object]:
    return {
        "schema_version": "legacy-workbook-snapshot/v2",
        "workbook": {
            "sha256": workbook_sha256,
            "total_sheet_count": len(sheet_names),
            "sheet_inventory": sheet_names,
        },
        "sheets": [{"sheet_name": name} for name in sheet_names],
    }


def test_inventory_keeps_source_classification_separate_from_observed_ingestion(monkeypatch, tmp_path):
    workbook = tmp_path / "workbook.xlsb"
    snapshot = tmp_path / "snapshot.json"
    workbook.write_bytes(b"workbook")
    snapshot.write_text(json.dumps(_snapshot_payload(sha256(b"workbook").hexdigest(), _Workbook().sheets)), encoding="utf-8")
    monkeypatch.setattr(audit, "open_workbook", lambda _path: _Workbook())
    report = audit.build_inventory(
        workbook, snapshot,
        expected_workbook_sha256=sha256(b"workbook").hexdigest(),
        expected_snapshot_sha256=sha256(snapshot.read_bytes()).hexdigest(),
    )
    kinds = {sheet["sheet_name"]: sheet["apparent_domain"] for sheet in report["sheets"]}
    assert kinds == {
        "TTviên": "AUTHORITATIVE_SOURCE",
        "Lịch sử TTV": "REPORT_OR_DERIVED_ONLY",
        "Nhóm 1c": "OBSOLETE",
        "Unknown": "UNKNOWN_REQUIRES_REVIEW",
    }
    assert all(sheet["observed_ingestion_coverage"] == "UNAVAILABLE_WITHOUT_EXPLICIT_EXECUTION_EVIDENCE" for sheet in report["sheets"])
    assert report["configured_import_plan"]["basis"].startswith("STATIC_CONFIGURATION")
    assert report["observed_ingestion_coverage"]["status"] == "UNAVAILABLE_WITHOUT_EXECUTION_EVIDENCE"
    assert report["provenance"]["read_only"] is True
    assert report["summary"]["snapshot_sheet_count"] == 4
    assert report["summary"]["sheets_absent_from_snapshot"] == []


def test_inventory_fails_closed_when_provenance_hash_does_not_match(tmp_path):
    workbook = tmp_path / "workbook.xlsb"
    snapshot = tmp_path / "snapshot.json"
    workbook.write_bytes(b"workbook")
    snapshot.write_text(json.dumps(_snapshot_payload(sha256(b"workbook").hexdigest(), [])), encoding="utf-8")
    with pytest.raises(ValueError, match="workbook SHA256"):
        audit.build_inventory(
            workbook, snapshot,
            expected_workbook_sha256="0" * 64,
            expected_snapshot_sha256=sha256(snapshot.read_bytes()).hexdigest(),
        )


def test_inventory_rejects_legacy_snapshot_shape_even_when_hash_matches(monkeypatch, tmp_path):
    workbook = tmp_path / "workbook.xlsb"; snapshot = tmp_path / "snapshot.json"
    workbook.write_bytes(b"workbook"); snapshot.write_text(json.dumps({"db.ktra": []}), encoding="utf-8")
    monkeypatch.setattr(audit, "open_workbook", lambda _path: _Workbook())
    with pytest.raises(ValueError, match="Snapshot V2 schema"):
        audit.build_inventory(workbook, snapshot, expected_workbook_sha256=sha256(b"workbook").hexdigest(), expected_snapshot_sha256=sha256(snapshot.read_bytes()).hexdigest())


def test_inventory_fails_closed_for_snapshot_lineage_or_actual_inventory_mismatch(monkeypatch, tmp_path):
    workbook = tmp_path / "workbook.xlsb"; snapshot = tmp_path / "snapshot.json"
    workbook.write_bytes(b"workbook")
    monkeypatch.setattr(audit, "open_workbook", lambda _path: _Workbook())
    payload = _snapshot_payload("0" * 64, _Workbook().sheets)
    snapshot.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="lineage"):
        audit.build_inventory(workbook, snapshot, expected_workbook_sha256=sha256(b"workbook").hexdigest(), expected_snapshot_sha256=sha256(snapshot.read_bytes()).hexdigest())
    payload = _snapshot_payload(sha256(b"workbook").hexdigest(), ["TTviên"])
    snapshot.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="does not match"):
        audit.build_inventory(workbook, snapshot, expected_workbook_sha256=sha256(b"workbook").hexdigest(), expected_snapshot_sha256=sha256(snapshot.read_bytes()).hexdigest())
    payload = _snapshot_payload(sha256(b"workbook").hexdigest(), [*_Workbook().sheets, "Unexpected snapshot sheet"])
    snapshot.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="does not match"):
        audit.build_inventory(workbook, snapshot, expected_workbook_sha256=sha256(b"workbook").hexdigest(), expected_snapshot_sha256=sha256(snapshot.read_bytes()).hexdigest())
    payload = _snapshot_payload(sha256(b"workbook").hexdigest(), _Workbook().sheets)
    payload["sheets"] = [{"sheet_name": "TTviên"}]
    snapshot.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="internal sheet inventory"):
        audit.build_inventory(workbook, snapshot, expected_workbook_sha256=sha256(b"workbook").hexdigest(), expected_snapshot_sha256=sha256(snapshot.read_bytes()).hexdigest())
    payload = _snapshot_payload(sha256(b"workbook").hexdigest(), _Workbook().sheets)
    payload["sheets"].append({"sheet_name": "TTviên"})
    snapshot.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="sheet inventory is duplicated"):
        audit.build_inventory(workbook, snapshot, expected_workbook_sha256=sha256(b"workbook").hexdigest(), expected_snapshot_sha256=sha256(snapshot.read_bytes()).hexdigest())
    payload = _snapshot_payload(sha256(b"workbook").hexdigest(), ["TTviên", "TTviên"])
    snapshot.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="lineage or inventory"):
        audit.build_inventory(workbook, snapshot, expected_workbook_sha256=sha256(b"workbook").hexdigest(), expected_snapshot_sha256=sha256(snapshot.read_bytes()).hexdigest())
