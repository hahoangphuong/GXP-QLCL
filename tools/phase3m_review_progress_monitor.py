from __future__ import annotations

from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any
import csv
import json
import sys

from backend.app.project_paths import phase_artifact_path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _phase3l_template_json_path() -> Path:
    return phase_artifact_path("phase3l", "review_progress_tracker.template.json")


def _phase3l_tracker_json_path() -> Path:
    return phase_artifact_path("phase3l", "review_progress_tracker.json")


def _phase3l_summary_path() -> Path:
    return phase_artifact_path("phase3l", "review_assignment_summary.json")
TODAY = date(2026, 8, 13)
ALLOWED_STATUSES = {"not_started", "in_progress", "completed", "blocked"}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_iso_date(value: str) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        year, month, day = text.split("-")
        return date(int(year), int(month), int(day))
    except (TypeError, ValueError):
        return None


def tracker_source_path() -> Path:
    tracker_path = _phase3l_tracker_json_path()
    if tracker_path.exists():
        return tracker_path
    return _phase3l_template_json_path()


def validate_tracker_row(row: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    lane = str(row.get("lane", "")).strip()
    group_key = str(row.get("group_key", "")).strip()
    status = str(row.get("status", "")).strip()
    assignee = str(row.get("assignee", "")).strip()
    started_on = str(row.get("started_on", "")).strip()
    completed_on = str(row.get("completed_on", "")).strip()
    review_keys = row.get("review_keys") or []

    row_label = f"{lane}:{group_key}" if lane or group_key else "(unknown tracker row)"

    if not lane:
        errors.append(f"{row_label}: lane is required")
    if not group_key:
        errors.append(f"{row_label}: group_key is required")
    if status not in ALLOWED_STATUSES:
        errors.append(f"{row_label}: unsupported status '{status}'")
        return errors
    if not isinstance(review_keys, list) or not review_keys:
        errors.append(f"{row_label}: review_keys must be a non-empty list")

    started_dt = parse_iso_date(started_on)
    completed_dt = parse_iso_date(completed_on)
    if started_on and started_dt is None:
        errors.append(f"{row_label}: started_on must be ISO date YYYY-MM-DD")
    if completed_on and completed_dt is None:
        errors.append(f"{row_label}: completed_on must be ISO date YYYY-MM-DD")
    if started_dt and started_dt > TODAY:
        errors.append(f"{row_label}: started_on cannot be in the future")
    if completed_dt and completed_dt > TODAY:
        errors.append(f"{row_label}: completed_on cannot be in the future")
    if started_dt and completed_dt and completed_dt < started_dt:
        errors.append(f"{row_label}: completed_on cannot be before started_on")

    if status == "not_started":
        if started_on or completed_on:
            errors.append(f"{row_label}: not_started rows cannot have started_on or completed_on")
        if assignee and not str(row.get("notes", "")).strip():
            errors.append(f"{row_label}: assigned not_started rows should explain pending notes")
    elif status == "in_progress":
        if not assignee:
            errors.append(f"{row_label}: in_progress rows require assignee")
        if not started_on:
            errors.append(f"{row_label}: in_progress rows require started_on")
        if completed_on:
            errors.append(f"{row_label}: in_progress rows cannot have completed_on")
    elif status == "completed":
        if not assignee:
            errors.append(f"{row_label}: completed rows require assignee")
        if not started_on:
            errors.append(f"{row_label}: completed rows require started_on")
        if not completed_on:
            errors.append(f"{row_label}: completed rows require completed_on")
    elif status == "blocked":
        if not assignee:
            errors.append(f"{row_label}: blocked rows require assignee")
        if not started_on:
            errors.append(f"{row_label}: blocked rows require started_on")
        if not str(row.get("notes", "")).strip():
            errors.append(f"{row_label}: blocked rows require notes")

    return errors


def build_phase3m_monitor() -> dict[str, Any]:
    assignment_summary = load_json(_phase3l_summary_path())
    tracker_path = tracker_source_path()
    tracker_rows = load_json(tracker_path)

    validation_errors: list[str] = []
    for row in tracker_rows:
        validation_errors.extend(validate_tracker_row(row))

    lane_status_counts: dict[str, dict[str, int]] = {}
    lane_review_key_counts: dict[str, int] = {}
    lane_decision_file_updates: dict[str, int] = {}
    stale_flags: list[str] = []
    status_counts = Counter()

    for row in tracker_rows:
        lane = row["lane"]
        status = row["status"]
        review_key_count = len(row.get("review_keys") or [])
        status_counts[status] += 1
        lane_status_counts.setdefault(lane, {})
        lane_status_counts[lane][status] = lane_status_counts[lane].get(status, 0) + 1
        lane_review_key_counts[lane] = lane_review_key_counts.get(lane, 0) + review_key_count
        if row.get("decision_file_updated"):
            lane_decision_file_updates[lane] = lane_decision_file_updates.get(lane, 0) + 1

        row_label = f"{lane}:{row['group_key']}"
        if status == "completed" and not row.get("decision_file_updated"):
            stale_flags.append(f"{row_label}: completed but decision_file_updated=false")
        if status == "blocked" and not str(row.get("notes", "")).strip():
            stale_flags.append(f"{row_label}: blocked without notes")

    queue_actionable_count = assignment_summary["queue_actionable_count"]
    completed_review_keys = sum(
        len(row.get("review_keys") or [])
        for row in tracker_rows
        if row.get("status") == "completed"
    )
    in_progress_review_keys = sum(
        len(row.get("review_keys") or [])
        for row in tracker_rows
        if row.get("status") == "in_progress"
    )
    blocked_review_keys = sum(
        len(row.get("review_keys") or [])
        for row in tracker_rows
        if row.get("status") == "blocked"
    )

    lane_progress = {}
    for lane, lane_summary in assignment_summary["lane_summaries"].items():
        lane_total = lane_summary["row_count"]
        lane_completed = sum(
            len(row.get("review_keys") or [])
            for row in tracker_rows
            if row.get("lane") == lane and row.get("status") == "completed"
        )
        lane_in_progress = sum(
            len(row.get("review_keys") or [])
            for row in tracker_rows
            if row.get("lane") == lane and row.get("status") == "in_progress"
        )
        lane_blocked = sum(
            len(row.get("review_keys") or [])
            for row in tracker_rows
            if row.get("lane") == lane and row.get("status") == "blocked"
        )
        lane_progress[lane] = {
            "row_count": lane_total,
            "completed_review_keys": lane_completed,
            "in_progress_review_keys": lane_in_progress,
            "blocked_review_keys": lane_blocked,
            "completion_ratio": round(lane_completed / lane_total, 4) if lane_total else 1.0,
        }

    return {
        "generated_on": "2026-08-13",
        "tracker_source": str(tracker_path.relative_to(ROOT)),
        "queue_actionable_count": queue_actionable_count,
        "completed_review_keys": completed_review_keys,
        "in_progress_review_keys": in_progress_review_keys,
        "blocked_review_keys": blocked_review_keys,
        "completion_ratio": round(completed_review_keys / queue_actionable_count, 4)
        if queue_actionable_count
        else 1.0,
        "status_counts": dict(status_counts),
        "lane_status_counts": lane_status_counts,
        "lane_progress": lane_progress,
        "lane_decision_file_updates": lane_decision_file_updates,
        "validation_errors": validation_errors,
        "stale_flags": stale_flags,
        "can_submit_phase3j": not validation_errors and not stale_flags and completed_review_keys > 0,
    }


def write_monitor_csv(path: Path, tracker_rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "lane",
                "group_key",
                "status",
                "assignee",
                "started_on",
                "completed_on",
                "decision_file_updated",
                "review_key_count",
                "notes",
            ],
        )
        writer.writeheader()
        for row in tracker_rows:
            writer.writerow(
                {
                    "lane": row.get("lane"),
                    "group_key": row.get("group_key"),
                    "status": row.get("status"),
                    "assignee": row.get("assignee"),
                    "started_on": row.get("started_on"),
                    "completed_on": row.get("completed_on"),
                    "decision_file_updated": row.get("decision_file_updated"),
                    "review_key_count": len(row.get("review_keys") or []),
                    "notes": row.get("notes"),
                }
            )
