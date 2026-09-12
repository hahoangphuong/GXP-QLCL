"""Read-only morphology profile for the source-owned legacy inspection periods."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
from typing import Any

from backend.app.domain.inspection_periods import (
    InspectionPeriodSourceState,
    parse_legacy_inspection_periods,
)
from backend.app.domain.phase2_import import normalize_row, parse_int


def _shape(value: str) -> str:
    return re.sub(r"\d", "9", value.strip())


def profile(rows: list[dict[str, str]]) -> dict[str, Any]:
    state_counts: Counter[str] = Counter()
    segment_counts: Counter[str] = Counter()
    shapes: Counter[str] = Counter()
    unresolved: Counter[str] = Counter()
    non_date_values: Counter[str] = Counter()
    semantic_shapes: Counter[str] = Counter()
    examples: dict[str, list[int]] = defaultdict(list)
    valid_rows = 0
    max_segments = 0
    for raw_row in rows:
        row = normalize_row(raw_row)
        legacy_id = parse_int(row.get("ID", ""))
        if legacy_id is None:
            continue
        valid_rows += 1
        value = row.get("inspected_at", "")
        result = parse_legacy_inspection_periods(value)
        state_counts[result.state.value] += 1
        shapes[_shape(value)] += 1
        if result.state == InspectionPeriodSourceState.KNOWN:
            count = len(result.segments)
            max_segments = max(max_segments, count)
            segment_counts["4+" if count >= 4 else str(count)] += 1
            ranges = sum(segment.started_on != segment.ended_on for segment in result.segments)
            if count == 1:
                semantic_shapes["ONE_CONTINUOUS_RANGE" if ranges else "ONE_SINGLE_DAY"] += 1
            elif ranges == 0:
                semantic_shapes["MULTIPLE_ISOLATED_SINGLE_DAYS"] += 1
            elif ranges == count:
                semantic_shapes["MULTIPLE_RANGES"] += 1
            else:
                semantic_shapes["MIXED_SINGLE_AND_RANGE"] += 1
        elif result.state == InspectionPeriodSourceState.UNRESOLVED:
            unresolved[f"{_shape(value)}|{result.diagnostic or 'unknown'}"] += 1
        elif result.state == InspectionPeriodSourceState.NON_DATE_EXPRESSION:
            non_date_values[value.strip()] += 1
        bucket = result.state.value
        if len(examples[bucket]) < 5:
            examples[bucket].append(legacy_id)
    return {
        "valid_id_rows": valid_rows,
        "source_field": "db.ktra Ngày K.tra",
        "state_counts": dict(sorted(state_counts.items())),
        "known_segment_count_distribution": dict(sorted(segment_counts.items())),
        "known_semantic_shape_counts": dict(sorted(semantic_shapes.items())),
        "max_segments": max_segments,
        "source_shapes": dict(sorted(shapes.items())),
        "example_legacy_ids_by_state": dict(sorted(examples.items())),
        "unresolved_morphology": dict(sorted(unresolved.items())),
        "non_date_expression_values": dict(sorted(non_date_values.items())),
        "sentinel_counts": {
            "pending_input": state_counts[InspectionPeriodSourceState.PENDING_INPUT.value],
            "not_applicable": state_counts[InspectionPeriodSourceState.NOT_APPLICABLE.value],
            "missing": state_counts[InspectionPeriodSourceState.MISSING.value],
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    args = parser.parse_args(argv)
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    rows = snapshot.get("db.ktra") or snapshot.get("sheets", {}).get("db.ktra") or snapshot.get("sections", {}).get("db.ktra", {}).get("rows")
    if not isinstance(rows, list):
        raise RuntimeError("snapshot does not contain db.ktra rows")
    # Keep the CLI portable to the Windows legacy console without changing data.
    print(json.dumps(profile(rows), ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
