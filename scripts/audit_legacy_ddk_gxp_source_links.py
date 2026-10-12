"""Print the independent, source-only DDK/GxP audit (never import/repair)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.app.domain.legacy_ddk_gxp_source_audit import audit_ddk_gxp_source_links

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--snapshot", type=Path,
        default=ROOT / "artifacts/phase3c/legacy_snapshot.json",
    )
    parser.add_argument(
        "--confirmed-blanked", type=Path,
        default=ROOT / "artifacts/phase3q/confirmed_blanked_rows.json",
    )
    args = parser.parse_args()
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    contract = json.loads(args.confirmed_blanked.read_text(encoding="utf-8"))
    exclusions = {
        (str(row["source_sheet"]).strip(), str(row["source_row_key"]).strip())
        for row in contract["rows"]
    }
    report = audit_ddk_gxp_source_links(
        snapshot,
        confirmed_blanked_row_keys=exclusions,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
