from __future__ import annotations

from pathlib import Path
import json

from phase3c_remediation import ROOT, build_phase3c_analysis


OUT_DIR = ROOT / "artifacts" / "phase3c"
ANALYSIS_PATH = OUT_DIR / "remediation_analysis.json"
OVERRIDES_PATH = OUT_DIR / "remediation_overrides.auto.json"
REPORT_PATH = OUT_DIR / "remediation_analysis.md"


def main() -> int:
    analysis = build_phase3c_analysis()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ANALYSIS_PATH.write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")
    OVERRIDES_PATH.write_text(json.dumps(analysis["auto_overrides"], ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Phase 3c Remediation Analysis",
        "",
        f"- Baseline anomalies: `{analysis['baseline_anomaly_count']}`",
        f"- Auto-resolvable suggestions: `{analysis['auto_resolvable_count']}`",
        "",
        "## Placeholder-like anomaly rows",
        "",
    ]
    if analysis["placeholder_counts"]:
        for sheet, count in sorted(analysis["placeholder_counts"].items()):
            lines.append(f"- `{sheet}`: `{count}`")
    else:
        lines.append("- none")

    lines.extend(["", "## Auto-resolvable suggestions", ""])
    if analysis["auto_resolvable_suggestions"]:
        for item in analysis["auto_resolvable_suggestions"]:
            lines.append(
                f"- `{item['source_sheet']}` row `{item['legacy_row_id']}` -> "
                f"`{json.dumps(item['override'], ensure_ascii=False)}` via `{item['rule']}`"
            )
    else:
        lines.append("- none")

    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {ANALYSIS_PATH}")
    print(f"Wrote {OVERRIDES_PATH}")
    print(f"Wrote {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
