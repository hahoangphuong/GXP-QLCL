from __future__ import annotations

from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.phase3n_review_starter_pack import (
    PHASE3L_TRACKER_LIVE_PATH,
    PHASE3N_DIR,
    build_phase3n_pack,
)


def main() -> None:
    pack = build_phase3n_pack()
    PHASE3N_DIR.mkdir(parents=True, exist_ok=True)

    starter_summary_path = PHASE3N_DIR / "review_starter_pack_summary.json"
    starter_md_path = PHASE3N_DIR / "review_starter_pack_summary.md"
    checklist_path = PHASE3N_DIR / "submission_checklist.json"
    quickstart_path = PHASE3N_DIR / "review_quickstart.md"

    starter_summary_path.write_text(
        json.dumps({k: v for k, v in pack.items() if k != "review_progress_tracker_seed"}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    checklist_path.write_text(
        json.dumps(pack["submission_checklist"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    PHASE3L_TRACKER_LIVE_PATH.write_text(
        json.dumps(pack["review_progress_tracker_seed"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    lines = [
        "# Phase 3n Review Starter Pack",
        "",
        f"- Generated on: `{pack['generated_on']}`",
        f"- Actionable queue rows: `{pack['queue_actionable_count']}`",
        f"- Decision template rows: `{pack['decision_template_row_count']}`",
        f"- Live tracker rows seeded: `{pack['tracker_seed_row_count']}`",
        "",
        "## First-Day Actions",
    ]
    lines.extend(f"- {item}" for item in pack["first_day_actions"])
    starter_md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    quickstart_lines = [
        "# Review Quickstart",
        "",
        "## Start Today",
        "1. Open `artifacts/phase3l/review_progress_tracker.json` and assign reviewers by lane.",
        "2. Review B1 bundles first.",
        "3. Record decisions in `artifacts/phase3h/external_evidence_decisions.json`.",
        "4. Mark `decision_file_updated=true` only after the decision file reflects the completed work.",
        "5. Run Phase 3m, then Phase 3j.",
        "",
        "## Guardrails",
        "- Do not use display folder names as business identity.",
        "- Do not approve overrides without exact evidence.",
        "- Keep hard-unresolved rows for senior adjudication or explicit exclusion.",
    ]
    quickstart_path.write_text("\n".join(quickstart_lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
