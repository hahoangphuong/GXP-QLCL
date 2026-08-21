from __future__ import annotations

from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.phase3l_review_assignment import (
    build_phase3l_assignment,
    write_assignment_csv,
    write_progress_tracker_csv,
)


def main() -> None:
    assignment = build_phase3l_assignment()
    output_dir = ROOT / "artifacts" / "phase3l"
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_json_path = output_dir / "review_assignment_summary.json"
    summary_md_path = output_dir / "review_assignment_summary.md"
    assignments_json_path = output_dir / "review_lane_assignments.json"
    assignments_csv_path = output_dir / "review_lane_assignments.csv"
    tracker_json_path = output_dir / "review_progress_tracker.template.json"
    tracker_csv_path = output_dir / "review_progress_tracker.template.csv"

    assignments_json_path.write_text(
        json.dumps(assignment["assignments"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_assignment_csv(assignments_csv_path, assignment["assignments"])
    tracker_json_path.write_text(
        json.dumps(assignment["progress_template"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_progress_tracker_csv(tracker_csv_path, assignment["progress_template"])

    summary = {
        "generated_on": assignment["generated_on"],
        "queue_actionable_count": assignment["queue_actionable_count"],
        "lane_summaries": assignment["lane_summaries"],
    }
    summary_json_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    lines = [
        "# Phase 3l Review Assignment Summary",
        "",
        f"- Generated on: `{assignment['generated_on']}`",
        f"- Actionable rows: `{assignment['queue_actionable_count']}`",
        "",
        "## Lane Summaries",
    ]
    for lane, lane_summary in assignment["lane_summaries"].items():
        lines.append(
            f"- `{lane}`: rows `{lane_summary['row_count']}`, bundles `{lane_summary['bundle_count']}`, effort `{lane_summary['effort_points']}`"
        )
    summary_md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
