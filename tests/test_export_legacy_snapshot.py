from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

from backend.app.domain import legacy_snapshot
from backend.app.domain.legacy_inspection_storage_anchor import (
    LegacyInspectionStorageAnchorSourceRow,
    SourceYear,
)
from tools import export_legacy_snapshot


def test_exporter_writes_snapshot_and_authoritative_taxonomy_artifact(monkeypatch, tmp_path: Path):
    workbook = tmp_path / "GPs.xlsb"
    snapshot_path = tmp_path / "snapshot.json"
    taxonomy_path = tmp_path / "taxonomy.json"
    anchor_path = tmp_path / "anchors.json"
    snapshot = {"db.ktra": [{"ID": "KT-1"}]}
    taxonomy = {
        "schema_version": "evaluation-scope-taxonomy/v1",
        "named_ranges": {"PVCN_GMP": {"gxp_type": "GMP", "rows": []}},
    }
    monkeypatch.setattr(export_legacy_snapshot, "read_core_sheet_rows", lambda path: snapshot)
    monkeypatch.setattr(export_legacy_snapshot, "read_evaluation_scope_taxonomy", lambda path: taxonomy)
    monkeypatch.setattr(
        export_legacy_snapshot,
        "read_legacy_inspection_storage_anchor_rows",
        lambda path: (
            [
                LegacyInspectionStorageAnchorSourceRow(
                    legacy_inspection_id=1,
                    source_sheet="db.ktra",
                    source_row=5,
                    registration_submission=SourceYear(raw="2024", year=2024, status="usable"),
                    inspection_date=SourceYear(raw="2024", year=2024, status="usable"),
                    source_hash="a" * 64,
                )
            ],
            "b" * 64,
        ),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "export_legacy_snapshot.py",
            "--workbook",
            str(workbook),
            "--snapshot-output",
            str(snapshot_path),
            "--taxonomy-output",
            str(taxonomy_path),
            "--inspection-storage-anchor-output",
            str(anchor_path),
        ],
    )

    assert export_legacy_snapshot.main() == 0
    assert json.loads(snapshot_path.read_text(encoding="utf-8")) == snapshot
    assert json.loads(taxonomy_path.read_text(encoding="utf-8")) == taxonomy
    anchor = json.loads(anchor_path.read_text(encoding="utf-8"))
    assert anchor["schema_version"] == "legacy-inspection-storage-anchor/v1"
    assert anchor["source_version"] == "b" * 64
    assert len(anchor["snapshot_sha256"]) == 64
    assert set(anchor["rows"][0]) == {
        "legacy_inspection_id", "source_sheet", "source_row", "registration_submission_raw",
        "registration_submission_year", "registration_submission_status", "inspection_date_raw",
        "inspection_year", "inspection_year_status", "source_hash", "source_version",
    }
    assert b"\r\n" not in anchor_path.read_bytes()


def test_named_range_reader_exports_real_required_ranges_without_fake_gdp(monkeypatch, tmp_path: Path):
    class FakeComError(Exception):
        pass

    class FakeRange:
        def __init__(self, row: int, value: tuple[tuple[str, ...], ...]):
            self.Worksheet = SimpleNamespace(Name="Phạm vi CN")
            self.Row = row
            self.Value = value

    class FakeNames:
        def __init__(self):
            self.values = {
                "PVCN_GMP": FakeRange(4, (("1", "GMP", "", "", "", "", "", ""),)),
                "PVCN_GLP": FakeRange(124, (("1", "GLP", "", "", "", "", "", ""),)),
                "PVCN_GSP": FakeRange(370, (("1", "GSP", "", "", "", "", "", ""),)),
            }

        def __call__(self, name: str):
            if name not in self.values:
                raise FakeComError(name)
            return SimpleNamespace(RefersToRange=self.values[name])

    class FakeWorkbook:
        def __init__(self):
            self.Names = FakeNames()

        def Close(self, save_changes: bool):
            assert save_changes is False

    workbook = FakeWorkbook()
    app = SimpleNamespace(Workbooks=SimpleNamespace(Open=lambda path: workbook), Quit=lambda: None)
    workbook_path = tmp_path / "GPs.xlsb"
    workbook_path.write_bytes(b"fixture workbook")
    monkeypatch.setitem(sys.modules, "pywintypes", SimpleNamespace(com_error=FakeComError))
    monkeypatch.setattr(legacy_snapshot, "_excel_app", lambda: app)

    artifact = legacy_snapshot.read_evaluation_scope_taxonomy(workbook_path)

    assert set(artifact["named_ranges"]) == {"PVCN_GMP", "PVCN_GLP", "PVCN_GSP"}
    assert artifact["taxonomy_availability"]["GDP"]["status"] == "unavailable"


def test_repeated_excel_headers_preserve_every_physical_column_without_guessing_gxp():
    headers = ["ID", "ID CC", "ID CC", "ID CC", "ID CC", "Mã số CC"]
    plan = legacy_snapshot._core_header_plan(headers)
    assert plan[1] == [{"header": "ID CC", "column_ordinals": [2, 3, 4, 5]}]
    result = legacy_snapshot._core_source_row(
        headers, ["400", "101", "", "303", "404", "DDK-400"], 91, plan=plan,
    )
    assert result == {
        "ID": "400",
        "ID CC [excel_column=2]": "101",
        "ID CC [excel_column=3]": "",
        "ID CC [excel_column=4]": "303",
        "ID CC [excel_column=5]": "404",
        "Mã số CC": "DDK-400",
        "__excel_row_number": "91",
        "__excel_duplicate_headers": '[{"header":"ID CC","column_ordinals":[2,3,4,5]}]',
    }
    assert "ID CC" not in result
    assert "linked_certificate_ids" not in result


def test_distinct_excel_headers_preserve_existing_v1_source_shape():
    headers = ["ID", "ID CC", "Mã số CC"]
    plan = legacy_snapshot._core_header_plan(headers)
    assert plan[1] == []
    assert legacy_snapshot._core_source_row(
        headers, ["400", "101", "DDK-400"], 91, plan=plan,
    ) == {
        "ID": "400", "ID CC": "101", "Mã số CC": "DDK-400",
        "__excel_row_number": "91",
    }


def test_repeated_source_header_with_blank_cells_does_not_drop_other_values():
    headers = ["ID", "ID CC", "ID CC", "ID CC", "ID CC"]
    value = legacy_snapshot._core_source_row(
        headers, ["400", "", "202", "", ""], 55
    )
    assert value["ID CC [excel_column=3]"] == "202"
    assert len([key for key in value if key.startswith("ID CC [excel_column=")]) == 4
