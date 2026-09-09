from __future__ import annotations

from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.domain.legacy_inspection_storage_anchor import (
    projection_artifact_payload,
    read_legacy_inspection_storage_anchor_rows,
)
from backend.app.domain.legacy_snapshot import read_core_sheet_rows, read_evaluation_scope_taxonomy


def main() -> int:
    parser = argparse.ArgumentParser(description="Export legacy snapshot and authoritative evaluation-scope taxonomy on Windows.")
    parser.add_argument("--workbook", type=Path, default=next((ROOT / "legacy").glob("*.xlsb"), None))
    parser.add_argument("--snapshot-output", type=Path, default=ROOT / "artifacts" / "phase3c" / "legacy_snapshot.json")
    parser.add_argument(
        "--inspection-storage-anchor-output",
        type=Path,
        default=ROOT / "artifacts" / "phase3c" / "legacy_inspection_storage_anchor.json",
    )
    parser.add_argument("--taxonomy-output", type=Path, default=ROOT / "artifacts" / "legacy_snapshot" / "evaluation_scope_taxonomy.json")
    args = parser.parse_args()
    if args.workbook is None:
        raise RuntimeError("No legacy .xlsb workbook was found; pass --workbook explicitly.")
    out_path = args.snapshot_output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot = read_core_sheet_rows(args.workbook)
    out_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    anchor_rows, anchor_source_version = read_legacy_inspection_storage_anchor_rows(args.workbook)
    anchor_path = args.inspection_storage_anchor_output
    anchor_path.parent.mkdir(parents=True, exist_ok=True)
    anchor_path.write_text(
        json.dumps(
            projection_artifact_payload(anchor_rows, source_version=anchor_source_version),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    taxonomy_path = args.taxonomy_output
    taxonomy_path.parent.mkdir(parents=True, exist_ok=True)
    taxonomy = read_evaluation_scope_taxonomy(args.workbook)
    taxonomy_path.write_text(json.dumps(taxonomy, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"Wrote raw legacy snapshot to {out_path}")
    print(f"Wrote inspection storage anchor projection to {anchor_path} (source_version={anchor_source_version}, count={len(anchor_rows)})")
    print(f"Wrote evaluation-scope taxonomy to {taxonomy_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
