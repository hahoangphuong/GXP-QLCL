from __future__ import annotations

from pathlib import Path
import json

from phase3e_curated_review import ROOT, build_phase3e_analysis


OUT_DIR = ROOT / "artifacts" / "phase3e"
ANALYSIS_PATH = OUT_DIR / "curated_review_analysis.json"
CURATED_OVERRIDES_PATH = OUT_DIR / "curated_overrides.json"
MERGED_OVERRIDES_PATH = OUT_DIR / "merged_overrides.json"
REPORT_PATH = OUT_DIR / "curated_review_analysis.md"


def main() -> int:
    analysis = build_phase3e_analysis()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ANALYSIS_PATH.write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")
    CURATED_OVERRIDES_PATH.write_text(json.dumps(analysis["curated_overrides"], ensure_ascii=False, indent=2), encoding="utf-8")
    MERGED_OVERRIDES_PATH.write_text(json.dumps(analysis["merged_overrides"], ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Phase 3e Curated Review Analysis",
        "",
        f"- Phase 3d high-confidence overrides: `{analysis['phase3d_override_count']}`",
        f"- Phase 3e curated suggestions: `{analysis['curated_suggestion_count']}`",
        "",
        "## Curated suggestions",
        "",
    ]
    if analysis["curated_suggestions"]:
        for item in analysis["curated_suggestions"]:
            lines.append(
                f"- `db.cc` row `{item['legacy_row_id']}` -> "
                f"`{json.dumps(item['override'], ensure_ascii=False)}` via `{item['evidence']['match_kind']}`"
            )
    else:
        lines.append("- none")

    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {ANALYSIS_PATH}")
    print(f"Wrote {CURATED_OVERRIDES_PATH}")
    print(f"Wrote {MERGED_OVERRIDES_PATH}")
    print(f"Wrote {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
