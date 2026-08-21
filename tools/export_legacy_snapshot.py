from __future__ import annotations

from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.domain.legacy_snapshot import read_core_sheet_rows


def main() -> int:
    workbook_path = next((ROOT / "legacy").glob("*.xlsb"))
    out_path = ROOT / "artifacts" / "phase3c" / "legacy_snapshot.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot = read_core_sheet_rows(workbook_path)
    out_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote raw legacy snapshot to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
