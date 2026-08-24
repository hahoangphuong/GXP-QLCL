from __future__ import annotations

from pathlib import Path
import json

from tools import run_phase2_import as runner


def sample_snapshot() -> dict[str, list[dict[str, str]]]:
    return {
        "db.cty": [{"ID": "1", "TÊN CÔNG TY": "Company A"}],
        "db.cso": [{"ID": "10", "ID Cty": "1", "TÊN CƠ SỞ": "Site A"}],
        "db.ktra": [{"ID": "100", "ID CƠ SỞ": "10", "LOẠI KT": "GMP"}],
        "db.cc": [{"ID": "200", "ID ĐỢT KTRA": "100", "ID CƠ SỞ": "10", "LOẠI CC": "GMP"}],
        "db.dkkd": [{"ID": "300", "ID CƠ SỞ": "10", "ID CTY": "1"}],
        "db.Tdoi": [{"ID": "400", "ID CƠ SỞ": "10"}],
        "db.Tdoi2": [{"ID": "500", "ID Gốc": "400"}],
    }


def test_run_phase2_import_uses_snapshot_when_workbook_is_missing(tmp_path: Path, monkeypatch) -> None:
    artifacts_root = tmp_path / "artifacts"
    snapshot_path = artifacts_root / "phase3c" / "legacy_snapshot.json"
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(json.dumps(sample_snapshot(), ensure_ascii=False, indent=2), encoding="utf-8")

    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "SNAPSHOT_FALLBACK_PATH", snapshot_path)

    code = runner.main()

    reconciliation_json = artifacts_root / "phase2" / "reconciliation.json"
    assert code == 0
    assert reconciliation_json.exists()
    data = json.loads(reconciliation_json.read_text(encoding="utf-8"))
    assert data["source_counts"]["db.cty"] == 1
