from __future__ import annotations

from pathlib import Path
import json

from phase3g_closeout import ROOT, build_phase3g_closeout


OUT_DIR = ROOT / "artifacts" / "phase3g"
SUMMARY_PATH = OUT_DIR / "closeout_summary.json"
BASELINE_OVERRIDES_PATH = OUT_DIR / "accepted_overrides_baseline.json"
REVIEW_PACK_PATH = OUT_DIR / "unresolved_review_pack.json"
REPORT_PATH = OUT_DIR / "closeout_summary.md"


def main() -> int:
    summary = build_phase3g_closeout()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    BASELINE_OVERRIDES_PATH.write_text(json.dumps(summary["accepted_overrides"], ensure_ascii=False, indent=2), encoding="utf-8")
    REVIEW_PACK_PATH.write_text(json.dumps(summary["unresolved_review_pack"], ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Phase 3g Closeout Summary",
        "",
        f"- Accepted override count: `{summary['accepted_override_count']}`",
        f"- Open anomaly count: `{summary['open_anomaly_count']}`",
        "",
        "## Classification counts",
        "",
    ]
    for key, value in summary["classification_counts"].items():
        lines.append(f"- `{key}`: `{value}`")

    lines.extend(["", "## Remaining by source sheet", ""])
    for sheet, counts in sorted(summary["source_classification_counts"].items()):
        lines.append(f"- `{sheet}`: `{json.dumps(counts, ensure_ascii=False)}`")

    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {SUMMARY_PATH}")
    print(f"Wrote {BASELINE_OVERRIDES_PATH}")
    print(f"Wrote {REVIEW_PACK_PATH}")
    print(f"Wrote {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
