from __future__ import annotations

from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.phase3h_external_evidence import (
    PHASE3H_DIR,
    PHASE3H_TEMPLATE_PATH,
    build_phase3h_analysis,
    write_queue_csv,
)


def main() -> None:
    analysis = build_phase3h_analysis()
    PHASE3H_DIR.mkdir(parents=True, exist_ok=True)

    queue_json_path = PHASE3H_DIR / "external_evidence_queue.json"
    queue_csv_path = PHASE3H_DIR / "external_evidence_queue.csv"
    summary_json_path = PHASE3H_DIR / "external_evidence_summary.json"
    summary_md_path = PHASE3H_DIR / "external_evidence_summary.md"
    approved_overrides_path = PHASE3H_DIR / "adjudicated_overrides.external.json"
    merged_overrides_path = PHASE3H_DIR / "merged_overrides.external.json"

    queue_json_path.write_text(
        json.dumps(analysis["queue"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_queue_csv(queue_csv_path, analysis["queue"])
    PHASE3H_TEMPLATE_PATH.write_text(
        json.dumps(analysis["decision_template"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    approved_overrides_path.write_text(
        json.dumps(analysis["approved_overrides"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    merged_overrides_path.write_text(
        json.dumps(analysis["merged_overrides"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    summary = {
        "accepted_override_count": analysis["accepted_override_count"],
        "actionable_count": analysis["queue_summary"]["actionable_count"],
        "classification_counts": analysis["queue_summary"]["classification_counts"],
        "sheet_counts": analysis["queue_summary"]["sheet_counts"],
        "submitted_decision_count": analysis["submitted_decision_count"],
        "decision_summary": analysis["decision_summary"],
        "validation_errors": analysis["validation_errors"],
        "approved_override_count": sum(
            len(rows) for rows in analysis["approved_overrides"].values()
        ),
        "queue_json_path": str(queue_json_path.relative_to(Path.cwd())),
        "queue_csv_path": str(queue_csv_path.relative_to(Path.cwd())),
        "template_path": str(PHASE3H_TEMPLATE_PATH.relative_to(Path.cwd())),
    }
    summary_json_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    md_lines = [
        "# Phase 3h External Evidence Summary",
        "",
        f"- Accepted override baseline: `{analysis['accepted_override_count']}`",
        f"- Actionable rows for external adjudication: `{analysis['queue_summary']['actionable_count']}`",
        f"- Submitted decisions: `{analysis['submitted_decision_count']}`",
        f"- Approved overrides from submitted decisions: `{summary['approved_override_count']}`",
        "",
        "## Classification Counts",
    ]
    for label, count in analysis["queue_summary"]["classification_counts"].items():
        md_lines.append(f"- `{label}`: `{count}`")
    md_lines.extend(["", "## Validation"])
    if analysis["validation_errors"]:
        md_lines.extend(f"- {error}" for error in analysis["validation_errors"])
    else:
        md_lines.append("- No validation errors.")
    summary_md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
