from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import sys

from backend.app.project_paths import artifacts_root, phase_artifact_path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.phase3h_external_evidence import PHASE3H_TEMPLATE_PATH, load_json


def _phase3l_tracker_template_path() -> Path:
    return phase_artifact_path("phase3l", "review_progress_tracker.template.json")


def _phase3l_tracker_live_path() -> Path:
    return phase_artifact_path("phase3l", "review_progress_tracker.json")


def _phase3k_summary_path() -> Path:
    return phase_artifact_path("phase3k", "review_handoff_summary.json")


def _phase3l_assignment_summary_path() -> Path:
    return phase_artifact_path("phase3l", "review_assignment_summary.json")


def _phase3n_dir() -> Path:
    return artifacts_root() / "phase3n"


def build_live_tracker_seed() -> list[dict[str, Any]]:
    tracker_rows = load_json(_phase3l_tracker_template_path())
    seeded_rows = []
    for row in tracker_rows:
        seeded = dict(row)
        seeded["notes"] = str(row.get("notes", "") or "")
        seeded_rows.append(seeded)
    return seeded_rows


def build_submission_checklist() -> list[dict[str, str]]:
    return [
        {
            "step_id": "S1",
            "title": "Assign reviewers to live tracker",
            "owner": "review coordinator",
            "done_when": "Each lane bundle has an assignee or an explicit pending note in review_progress_tracker.json.",
        },
        {
            "step_id": "S2",
            "title": "Execute review with file-backed evidence",
            "owner": "reviewers",
            "done_when": "Review rows move from not_started to in_progress or completed with exact evidence references.",
        },
        {
            "step_id": "S3",
            "title": "Update external decision file",
            "owner": "reviewers",
            "done_when": "Reviewed rows are reflected in external_evidence_decisions.json and completed tracker rows set decision_file_updated=true.",
        },
        {
            "step_id": "S4",
            "title": "Run Phase 3m progress monitor",
            "owner": "review coordinator",
            "done_when": "review_progress_summary.json shows current lane progress without validation errors.",
        },
        {
            "step_id": "S5",
            "title": "Run Phase 3j decision quality gate",
            "owner": "migration operator",
            "done_when": "decision_quality_gate.json returns status=pass.",
        },
        {
            "step_id": "S6",
            "title": "Run adjudicated rerun",
            "owner": "migration operator",
            "done_when": "Phase 3h and Phase 3i reruns complete with updated merged overrides and reconciliation output.",
        },
    ]


def build_phase3n_pack() -> dict[str, Any]:
    handoff_summary = load_json(_phase3k_summary_path())
    assignment_summary = load_json(_phase3l_assignment_summary_path())
    decision_template = load_json(PHASE3H_TEMPLATE_PATH)
    tracker_seed = build_live_tracker_seed()

    first_day_actions = [
        "Copy reviewer names into artifacts/phase3l/review_progress_tracker.json.",
        "Start with B1-high-confidence-adjudication bundles before B2 and B3.",
        "Use exact Synology/Word/PDF references in external_evidence_decisions.json.",
        "Run Phase 3m at least once before attempting Phase 3j.",
    ]

    return {
        "generated_on": "2026-08-13",
        "queue_actionable_count": handoff_summary["queue_actionable_count"],
        "batch_counts": handoff_summary["batch_counts"],
        "lane_summaries": assignment_summary["lane_summaries"],
        "decision_template_row_count": len(decision_template),
        "tracker_seed_row_count": len(tracker_seed),
        "first_day_actions": first_day_actions,
        "submission_checklist": build_submission_checklist(),
        "review_progress_tracker_seed": tracker_seed,
    }
