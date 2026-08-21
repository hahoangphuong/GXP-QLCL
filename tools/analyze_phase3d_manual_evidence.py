from __future__ import annotations

from pathlib import Path
import json

from phase3d_manual_evidence import ROOT, build_phase3d_analysis


OUT_DIR = ROOT / "artifacts" / "phase3d"
ANALYSIS_PATH = OUT_DIR / "manual_evidence_analysis.json"
OVERRIDES_PATH = OUT_DIR / "high_confidence_overrides.json"
QUEUE_PATH = OUT_DIR / "manual_review_queue.json"
REPORT_PATH = OUT_DIR / "manual_evidence_analysis.md"


def main() -> int:
    analysis = build_phase3d_analysis()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ANALYSIS_PATH.write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")
    OVERRIDES_PATH.write_text(json.dumps(analysis["high_confidence_overrides"], ensure_ascii=False, indent=2), encoding="utf-8")
    QUEUE_PATH.write_text(json.dumps(analysis["manual_review_queue"], ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Phase 3d Manual Evidence Analysis",
        "",
        f"- Baseline anomalies: `{analysis['baseline_anomaly_count']}`",
        f"- High-confidence suggestions: `{analysis['high_confidence_count']}`",
        f"- Manual review queue: `{analysis['manual_review_count']}`",
        "",
        "## High-confidence suggestions",
        "",
    ]
    if analysis["high_confidence_suggestions"]:
        for item in analysis["high_confidence_suggestions"]:
            lines.append(
                f"- `{item['source_sheet']}` row `{item['legacy_row_id']}` -> "
                f"`{json.dumps(item['override'], ensure_ascii=False)}` via `{item['rule']}`"
            )
    else:
        lines.append("- none")

    lines.extend(["", "## Manual review queue", ""])
    if analysis["manual_review_queue"]:
        for item in analysis["manual_review_queue"][:25]:
            lines.append(
                f"- `{item['source_sheet']}` row `{item['legacy_row_id']}` "
                f"[{item['priority']}] {item['summary']}"
            )
    else:
        lines.append("- none")

    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {ANALYSIS_PATH}")
    print(f"Wrote {OVERRIDES_PATH}")
    print(f"Wrote {QUEUE_PATH}")
    print(f"Wrote {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
