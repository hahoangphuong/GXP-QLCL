from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.domain.legacy_inspection_storage_anchor import (
    LegacyInspectionStorageAnchorSourceRow,
    audit_projection_rows,
    read_legacy_inspection_storage_anchor_rows,
)


def audit(
    source_rows: Iterable[LegacyInspectionStorageAnchorSourceRow],
    *,
    source_version: str,
    projection_rows: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    return audit_projection_rows(
        source_rows,
        source_version=source_version,
        projection_rows=projection_rows,
    )


def _load_projection_rows(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("rows", payload) if isinstance(payload, dict) else payload
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError("Projection JSON must be a list of projection row objects or an object containing rows.")
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only parity audit for source-faithful legacy inspection storage anchors."
    )
    parser.add_argument("--workbook", type=Path, required=True)
    parser.add_argument("--projection-json", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    source_rows, source_version = read_legacy_inspection_storage_anchor_rows(args.workbook)
    report = audit(
        source_rows,
        source_version=source_version,
        projection_rows=_load_projection_rows(args.projection_json),
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8", newline="\n")
    else:
        print(rendered, end="")
    return 0 if report["parity_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
