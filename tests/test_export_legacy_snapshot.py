from __future__ import annotations

import json
import sys
from pathlib import Path

from tools import export_legacy_snapshot


def test_exporter_writes_snapshot_and_authoritative_taxonomy_artifact(monkeypatch, tmp_path: Path):
    workbook = tmp_path / "GPs.xlsb"
    snapshot_path = tmp_path / "snapshot.json"
    taxonomy_path = tmp_path / "taxonomy.json"
    snapshot = {"db.ktra": [{"ID": "KT-1"}]}
    taxonomy = {
        "schema_version": "evaluation-scope-taxonomy/v1",
        "named_ranges": {"PVCN_GMP": {"gxp_type": "GMP", "rows": []}},
    }
    monkeypatch.setattr(export_legacy_snapshot, "read_core_sheet_rows", lambda path: snapshot)
    monkeypatch.setattr(export_legacy_snapshot, "read_evaluation_scope_taxonomy", lambda path: taxonomy)
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
        ],
    )

    assert export_legacy_snapshot.main() == 0
    assert json.loads(snapshot_path.read_text(encoding="utf-8")) == snapshot
    assert json.loads(taxonomy_path.read_text(encoding="utf-8")) == taxonomy
