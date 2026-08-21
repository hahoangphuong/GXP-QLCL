from __future__ import annotations

from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.db.session import session_scope
from backend.app.domain.phase2_import import import_workbook_to_database


def main() -> int:
    workbook_path = next((ROOT / "legacy").glob("*.xlsb"))
    database_path = ROOT / "artifacts" / "phase3d" / "staging_high_confidence.db"
    report_path = ROOT / "artifacts" / "phase3d" / "reconciliation_high_confidence.md"
    json_path = ROOT / "artifacts" / "phase3d" / "reconciliation_high_confidence.json"
    override_path = ROOT / "artifacts" / "phase3d" / "high_confidence_overrides.json"

    database_path.parent.mkdir(parents=True, exist_ok=True)
    if database_path.exists():
        database_path.unlink()

    overrides = {}
    if override_path.exists():
        overrides = json.loads(override_path.read_text(encoding="utf-8"))

    database_url = f"sqlite:///{database_path.as_posix()}"
    with session_scope(database_url) as session:
        result = import_workbook_to_database(
            session,
            workbook_path,
            report_path,
            remediation_overrides=overrides,
        )

    json_path.write_text(json.dumps(result.reconciliation, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Imported workbook snapshot into {result.database_url}")
    print(f"Wrote reconciliation report to {result.report_path}")
    print(f"Wrote reconciliation json to {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
