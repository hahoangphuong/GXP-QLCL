from __future__ import annotations

from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.phase3i_external_reimport import build_phase3i_summary


def main() -> None:
    summary = build_phase3i_summary()
    output_dir = ROOT / "artifacts" / "phase3i"
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_json_path = output_dir / "external_reimport_summary.json"
    summary_md_path = output_dir / "external_reimport_summary.md"

    summary_json_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    lines = [
        "# Phase 3i External Reimport Summary",
        "",
        f"- Submitted decisions: `{summary['submitted_decision_count']}`",
        f"- Approved overrides from external adjudication: `{summary['approved_override_count']}`",
        f"- Phase 3f applied overrides: `{summary['phase3f_applied_override_count']}`",
        f"- Phase 3i applied overrides: `{summary['phase3i_applied_override_count']}`",
        f"- Phase 3f open anomalies: `{summary['phase3f_open_anomaly_count']}`",
        f"- Phase 3i open anomalies: `{summary['phase3i_open_anomaly_count']}`",
        "",
        "## Target Count Deltas",
    ]
    if summary["target_count_deltas"]:
        for key, value in summary["target_count_deltas"].items():
            lines.append(
                f"- `{key}`: baseline `{value['baseline']}`, current `{value['current']}`, delta `{value['delta']}`"
            )
    else:
        lines.append("- none")

    lines.extend(["", "## Skipped Row Deltas"])
    if summary["skipped_row_deltas"]:
        for key, value in summary["skipped_row_deltas"].items():
            lines.append(
                f"- `{key}`: baseline `{value['baseline']}`, current `{value['current']}`, delta `{value['delta']}`"
            )
    else:
        lines.append("- none")

    lines.extend(["", "## Derived Count Deltas"])
    if summary["derived_count_deltas"]:
        for key, value in summary["derived_count_deltas"].items():
            lines.append(
                f"- `{key}`: baseline `{value['baseline']}`, current `{value['current']}`, delta `{value['delta']}`"
            )
    else:
        lines.append("- none")

    summary_md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
