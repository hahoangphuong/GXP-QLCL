from __future__ import annotations

from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.phase3m_review_progress_monitor import (
    build_phase3m_monitor,
    tracker_source_path,
    write_monitor_csv,
)


def main() -> None:
    monitor = build_phase3m_monitor()
    tracker_rows = json.loads(tracker_source_path().read_text(encoding="utf-8"))

    output_dir = ROOT / "artifacts" / "phase3m"
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_json_path = output_dir / "review_progress_summary.json"
    summary_md_path = output_dir / "review_progress_summary.md"
    snapshot_csv_path = output_dir / "review_progress_snapshot.csv"

    summary_json_path.write_text(
        json.dumps(monitor, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_monitor_csv(snapshot_csv_path, tracker_rows)

    lines = [
        "# Phase 3m Review Progress Summary",
        "",
        f"- Generated on: `{monitor['generated_on']}`",
        f"- Tracker source: `{monitor['tracker_source']}`",
        f"- Queue actionable rows: `{monitor['queue_actionable_count']}`",
        f"- Completed review keys: `{monitor['completed_review_keys']}`",
        f"- In-progress review keys: `{monitor['in_progress_review_keys']}`",
        f"- Blocked review keys: `{monitor['blocked_review_keys']}`",
        f"- Completion ratio: `{monitor['completion_ratio']}`",
        f"- Can submit Phase 3j: `{monitor['can_submit_phase3j']}`",
        "",
        "## Lane Progress",
    ]
    for lane, lane_progress in monitor["lane_progress"].items():
        lines.append(
            f"- `{lane}`: completed `{lane_progress['completed_review_keys']}` / `{lane_progress['row_count']}`, "
            f"in-progress `{lane_progress['in_progress_review_keys']}`, blocked `{lane_progress['blocked_review_keys']}`"
        )
    lines.extend(["", "## Validation Errors"])
    if monitor["validation_errors"]:
        lines.extend(f"- {item}" for item in monitor["validation_errors"])
    else:
        lines.append("- none")
    lines.extend(["", "## Stale Flags"])
    if monitor["stale_flags"]:
        lines.extend(f"- {item}" for item in monitor["stale_flags"])
    else:
        lines.append("- none")
    summary_md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
