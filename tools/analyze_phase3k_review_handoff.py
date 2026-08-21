from __future__ import annotations

from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.phase3k_review_handoff import build_phase3k_handoff, write_prioritized_csv


def main() -> None:
    handoff = build_phase3k_handoff()
    output_dir = ROOT / "artifacts" / "phase3k"
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_json_path = output_dir / "review_handoff_summary.json"
    summary_md_path = output_dir / "review_handoff_summary.md"
    prioritized_json_path = output_dir / "prioritized_review_queue.json"
    prioritized_csv_path = output_dir / "prioritized_review_queue.csv"
    reviewer_guide_path = output_dir / "reviewer_guide.md"

    prioritized_json_path.write_text(
        json.dumps(handoff["prioritized_queue"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_prioritized_csv(prioritized_csv_path, handoff["prioritized_queue"])

    summary = {
        "generated_on": handoff["generated_on"],
        "queue_actionable_count": handoff["queue_actionable_count"],
        "gate_status": handoff["gate_status"],
        "gate_reason": handoff["gate_reason"],
        "batch_counts": handoff["batch_counts"],
        "sheet_counts": handoff["sheet_counts"],
        "candidate_count_buckets": handoff["candidate_count_buckets"],
        "top_examples": handoff["top_examples"],
    }
    summary_json_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    summary_lines = [
        "# Phase 3k Review Handoff Summary",
        "",
        f"- Generated on: `{handoff['generated_on']}`",
        f"- Actionable queue rows: `{handoff['queue_actionable_count']}`",
        f"- Phase 3j gate status: `{handoff['gate_status']}`",
        f"- Gate reason: `{handoff['gate_reason']}`",
        "",
        "## Batch Counts",
    ]
    for key, value in sorted(handoff["batch_counts"].items()):
        summary_lines.append(f"- `{key}`: `{value}`")
    summary_lines.extend(["", "## Candidate Count Buckets"])
    for key, value in sorted(handoff["candidate_count_buckets"].items()):
        summary_lines.append(f"- `{key}`: `{value}`")
    summary_md_path.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    guide_lines = [
        "# Reviewer Guide",
        "",
        "## Goal",
        "Resolve the external evidence queue using file-backed business evidence without guessing.",
        "",
        "## Working Order",
        "1. Start with `B1-high-confidence-adjudication` rows.",
        "2. Then review `B2-multi-candidate-adjudication` rows.",
        "3. Leave `B3-hard-unresolved` for senior adjudication or explicit exclusion decisions.",
        "",
        "## Required Evidence",
        "- Use exact document or chronology references.",
        "- Do not use folder display names as business identity.",
        "- Prefer Synology documents, Word outputs, signed PDFs, or explicit business chronology.",
        "",
        "## First 10 Suggested Rows",
    ]
    for row in handoff["prioritized_queue"][:10]:
        legacy_context = row.get("legacy_context") or {}
        guide_lines.append(
            f"- `{row['review_key']}` | `{row['batch_label']}` | "
            f"{legacy_context.get('site_name') or '(unknown site)'} | "
            f"candidates `{row.get('candidate_count', 0)}`"
        )
    guide_lines.extend(["", "## Evidence Checklist"])
    guide_lines.append("- Certificates: locate DOCX/PDF/scan, confirm site identity, confirm chronology, record exact reference.")
    guide_lines.append("- Business eligibility: locate dossier/certificate evidence, verify stable site identity, record exact reference.")
    reviewer_guide_path.write_text("\n".join(guide_lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
