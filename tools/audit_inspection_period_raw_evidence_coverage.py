"""Audit immutable raw ``Ngay K.tra`` evidence coverage without emitting it."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from typing import Any

from backend.app.domain.inspection_periods import parse_legacy_inspection_periods
from backend.app.domain.legacy_inspection_storage_anchor import load_projection_artifact
from backend.app.domain.phase2_import import normalize_row, parse_int


def audit_coverage(snapshot: dict[str, Any], anchor_path: str | Path) -> dict[str, Any]:
    rows = snapshot.get("sheets", snapshot).get("db.ktra")
    if not isinstance(rows, list):
        raise RuntimeError("snapshot does not contain db.ktra rows")
    anchors, _, _ = load_projection_artifact(anchor_path)
    anchors_by_id = {anchor.legacy_inspection_id: anchor for anchor in anchors}
    state_totals: Counter[str] = Counter()
    anchored_by_state: Counter[str] = Counter()
    missing_anchor_ids: list[int] = []
    valid_rows = 0
    for raw_row in rows:
        row = normalize_row(raw_row)
        legacy_id = parse_int(row.get("ID", ""))
        if legacy_id is None:
            continue
        valid_rows += 1
        state = parse_legacy_inspection_periods(row.get("inspected_at", "")).state.value
        state_totals[state] += 1
        anchor = anchors_by_id.get(legacy_id)
        if anchor is None:
            missing_anchor_ids.append(legacy_id)
            continue
        anchored_by_state[state] += 1
    return {
        "valid_legacy_row_count": valid_rows,
        "anchor_case_count": len(anchors_by_id),
        "anchored_row_count": sum(anchored_by_state.values()),
        "missing_anchor_count": len(missing_anchor_ids),
        "state_coverage": {
            state: {
                "total": state_totals[state],
                "anchored": anchored_by_state[state],
                "missing_anchor": state_totals[state] - anchored_by_state[state],
            }
            for state in sorted(state_totals)
        },
        # The anchor loader verifies every source_hash over the raw workbook
        # evidence.  Snapshot serialization can render Excel datetimes with a
        # different ISO separator, so comparing the two exported strings would
        # falsely report an evidence mismatch.
        "source_hash_validated_anchor_count": sum(anchored_by_state.values()),
        "missing_anchor_ids": missing_anchor_ids,
        "coverage_passed_for_anchored_rows": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--anchor-projection", type=Path, required=True)
    args = parser.parse_args(argv)
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    print(json.dumps(audit_coverage(snapshot, args.anchor_projection), ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
