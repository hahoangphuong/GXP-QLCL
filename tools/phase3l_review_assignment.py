from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any
import csv
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.phase3k_review_handoff import build_phase3k_handoff


DEFAULT_LANES = ["lane_alpha", "lane_bravo", "lane_charlie"]


def estimate_effort_points(row: dict[str, Any]) -> int:
    points = 1
    candidate_count = int(row.get("candidate_count") or 0)
    if row["classification"] == "hard_unresolved":
        points += 5
    elif candidate_count <= 3:
        points += 1
    elif candidate_count <= 6:
        points += 2
    else:
        points += 3
    if row.get("priority") == "high":
        points += 1
    return points


def build_site_group_key(row: dict[str, Any]) -> str:
    legacy_context = row.get("legacy_context") or {}
    site_legacy_id = legacy_context.get("site_legacy_id")
    site_name = legacy_context.get("site_name")
    if site_legacy_id:
        return f"site:{site_legacy_id}"
    if site_name:
        return f"site_name:{site_name.strip().lower()}"
    return f"review_key:{row['review_key']}"


def group_rows_for_assignment(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(build_site_group_key(row), []).append(row)

    bundles = []
    for key, items in grouped.items():
        items = sorted(items, key=lambda item: item["review_key"])
        bundles.append(
            {
                "group_key": key,
                "review_keys": [item["review_key"] for item in items],
                "batch_labels": sorted({item["batch_label"] for item in items}),
                "site_names": sorted(
                    {
                        (item.get("legacy_context") or {}).get("site_name")
                        for item in items
                        if (item.get("legacy_context") or {}).get("site_name")
                    }
                ),
                "row_count": len(items),
                "effort_points": sum(estimate_effort_points(item) for item in items),
                "rows": items,
            }
        )
    bundles.sort(
        key=lambda bundle: (
            -bundle["effort_points"],
            -bundle["row_count"],
            bundle["group_key"],
        )
    )
    return bundles


def assign_bundles_to_lanes(
    bundles: list[dict[str, Any]],
    lanes: list[str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    lane_names = lanes or DEFAULT_LANES
    assignments = {lane: [] for lane in lane_names}
    lane_points = {lane: 0 for lane in lane_names}

    for bundle in bundles:
        target_lane = min(lane_names, key=lambda lane: (lane_points[lane], len(assignments[lane]), lane))
        assignments[target_lane].append(bundle)
        lane_points[target_lane] += bundle["effort_points"]

    return assignments


def build_phase3l_assignment() -> dict[str, Any]:
    handoff = build_phase3k_handoff()
    prioritized_rows = handoff["prioritized_queue"]
    bundles = group_rows_for_assignment(prioritized_rows)
    assignments = assign_bundles_to_lanes(bundles, DEFAULT_LANES)

    lane_summaries = {}
    for lane, lane_bundles in assignments.items():
        batch_counts = Counter()
        row_count = 0
        effort_points = 0
        for bundle in lane_bundles:
            row_count += bundle["row_count"]
            effort_points += bundle["effort_points"]
            for row in bundle["rows"]:
                batch_counts[row["batch_label"]] += 1
        lane_summaries[lane] = {
            "bundle_count": len(lane_bundles),
            "row_count": row_count,
            "effort_points": effort_points,
            "batch_counts": dict(batch_counts),
            "review_keys": [review_key for bundle in lane_bundles for review_key in bundle["review_keys"]],
        }

    progress_template = []
    for lane, lane_bundles in assignments.items():
        for bundle in lane_bundles:
            progress_template.append(
                {
                    "lane": lane,
                    "group_key": bundle["group_key"],
                    "review_keys": bundle["review_keys"],
                    "status": "not_started",
                    "assignee": "",
                    "started_on": "",
                    "completed_on": "",
                    "decision_file_updated": False,
                    "notes": "",
                }
            )

    return {
        "generated_on": "2026-08-13",
        "queue_actionable_count": handoff["queue_actionable_count"],
        "lane_summaries": lane_summaries,
        "bundles": bundles,
        "assignments": assignments,
        "progress_template": progress_template,
    }


def write_assignment_csv(path: Path, assignments: dict[str, list[dict[str, Any]]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "lane",
                "group_key",
                "row_count",
                "effort_points",
                "site_names",
                "batch_labels",
                "review_keys",
            ],
        )
        writer.writeheader()
        for lane, bundles in assignments.items():
            for bundle in bundles:
                writer.writerow(
                    {
                        "lane": lane,
                        "group_key": bundle["group_key"],
                        "row_count": bundle["row_count"],
                        "effort_points": bundle["effort_points"],
                        "site_names": "; ".join(bundle["site_names"]),
                        "batch_labels": "; ".join(bundle["batch_labels"]),
                        "review_keys": "; ".join(bundle["review_keys"]),
                    }
                )


def write_progress_tracker_csv(path: Path, progress_template: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "lane",
                "group_key",
                "review_keys",
                "status",
                "assignee",
                "started_on",
                "completed_on",
                "decision_file_updated",
                "notes",
            ],
        )
        writer.writeheader()
        for row in progress_template:
            writer.writerow(
                {
                    **row,
                    "review_keys": "; ".join(row["review_keys"]),
                }
            )
