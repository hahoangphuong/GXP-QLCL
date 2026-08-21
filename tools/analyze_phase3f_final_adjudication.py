from __future__ import annotations

from pathlib import Path
import json

from phase3f_final_adjudication import ROOT, build_phase3f_analysis


OUT_DIR = ROOT / "artifacts" / "phase3f"
ANALYSIS_PATH = OUT_DIR / "final_adjudication_analysis.json"
ADJUDICATED_OVERRIDES_PATH = OUT_DIR / "adjudicated_overrides.json"
FINAL_MERGED_OVERRIDES_PATH = OUT_DIR / "final_merged_overrides.json"
REPORT_PATH = OUT_DIR / "final_adjudication_analysis.md"


def main() -> int:
    analysis = build_phase3f_analysis()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ANALYSIS_PATH.write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")
    ADJUDICATED_OVERRIDES_PATH.write_text(json.dumps(analysis["adjudicated_overrides"], ensure_ascii=False, indent=2), encoding="utf-8")
    FINAL_MERGED_OVERRIDES_PATH.write_text(json.dumps(analysis["final_merged_overrides"], ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Phase 3f Final Adjudication Analysis",
        "",
        f"- Phase 3e merged overrides carried forward: `{analysis['phase3e_override_count']}`",
        f"- New adjudicated suggestions: `{analysis['adjudicated_suggestion_count']}`",
        "",
        "## Adjudicated suggestions",
        "",
    ]
    if analysis["adjudicated_suggestions"]:
        for item in analysis["adjudicated_suggestions"]:
            lines.append(
                f"- `{item['source_sheet']}` row `{item['legacy_row_id']}` -> "
                f"`{json.dumps(item['override'], ensure_ascii=False)}` via `{item['rule']}`"
            )
    else:
        lines.append("- none")

    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {ANALYSIS_PATH}")
    print(f"Wrote {ADJUDICATED_OVERRIDES_PATH}")
    print(f"Wrote {FINAL_MERGED_OVERRIDES_PATH}")
    print(f"Wrote {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
