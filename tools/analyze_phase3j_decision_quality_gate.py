from __future__ import annotations

from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.phase3j_decision_quality_gate import build_phase3j_gate_report


def main() -> None:
    report = build_phase3j_gate_report()
    output_dir = ROOT / "artifacts" / "phase3j"
    output_dir.mkdir(parents=True, exist_ok=True)

    report_json_path = output_dir / "decision_quality_gate.json"
    report_md_path = output_dir / "decision_quality_gate.md"

    report_json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    lines = [
        "# Phase 3j Decision Quality Gate",
        "",
        f"- Status: `{report['status']}`",
        f"- Can rerun Phase 3i: `{report['can_rerun_phase3i']}`",
        f"- Actionable queue rows: `{report['queue_actionable_count']}`",
        f"- Submitted decisions: `{report['submitted_decision_count']}`",
        f"- Coverage ratio: `{report['coverage_ratio']}`",
        "",
        "## Decision Counts",
    ]
    if report["decision_counts"]:
        for key, value in sorted(report["decision_counts"].items()):
            lines.append(f"- `{key}`: `{value}`")
    else:
        lines.append("- none")

    lines.extend(["", "## Validation Errors"])
    if report["validation_errors"]:
        lines.extend(f"- {item}" for item in report["validation_errors"])
    else:
        lines.append("- none")

    lines.extend(["", "## Quality Errors"])
    if report["quality_errors"]:
        lines.extend(f"- {item}" for item in report["quality_errors"])
    else:
        lines.append("- none")

    report_md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
