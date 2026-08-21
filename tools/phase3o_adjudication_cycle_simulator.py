from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any
import json
import sys

from backend.app.project_paths import artifacts_root, legacy_root, phase_artifact_path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.db.session import session_scope
from backend.app.domain.phase2_import import import_workbook_to_database
from backend.app.project_paths import phase_artifact_path
from tools.phase3h_external_evidence import (
    build_approved_overrides,
    build_phase3h_queue,
    build_queue_lookup,
    load_json,
    merge_overrides,
    validate_decision,
)
from tools.phase3i_external_reimport import compare_counts
from tools.phase3j_decision_quality_gate import validate_decision_quality
from tools.phase3m_review_progress_monitor import validate_tracker_row


def _phase3f_reconciliation_path() -> Path:
    return phase_artifact_path("phase3f", "reconciliation_final.json")


def _phase3l_tracker_path() -> Path:
    return phase_artifact_path("phase3l", "review_progress_tracker.json")


def _phase3o_dir() -> Path:
    return artifacts_root() / "phase3o"


def choose_simulation_rows(limit: int = 3) -> list[dict[str, Any]]:
    queue_rows = build_phase3h_queue()["queue"]
    b1_rows = [
        row
        for row in queue_rows
        if row["classification"] == "needs_external_evidence" and 1 <= row.get("candidate_count", 0) <= 3
    ]
    b1_rows.sort(key=lambda row: (row.get("candidate_count", 0), row["review_key"]))
    selected: list[dict[str, Any]] = []
    seen_site_keys: set[str] = set()
    for row in b1_rows:
        legacy_context = row.get("legacy_context") or {}
        site_key = str(legacy_context.get("site_legacy_id") or legacy_context.get("site_name") or row["review_key"])
        if site_key in seen_site_keys:
            continue
        selected.append(row)
        seen_site_keys.add(site_key)
        if len(selected) >= limit:
            break
    return selected


def build_simulated_decisions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    decisions = []
    for index, row in enumerate(rows, start=1):
        selected_legacy_id = row["candidate_legacy_ids"][0]
        legacy_context = row.get("legacy_context") or {}
        certificate_number = legacy_context.get("certificate_number") or f"sim-{index}"
        decisions.append(
            {
                "review_key": row["review_key"],
                "source_sheet": row["source_sheet"],
                "legacy_row_id": row["legacy_row_id"],
                "decision": "approve_override",
                "selected_legacy_id": selected_legacy_id,
                "evidence_source": "synology_doc",
                "evidence_reference": rf"SIMULATED\{row['source_sheet']}\{certificate_number}.docx",
                "decision_rationale": "Synthetic dry-run decision for end-to-end adjudication pipeline verification.",
                "reviewer": f"sim.reviewer{index}",
                "reviewed_on": "2026-08-13",
            }
        )
    return decisions


def build_simulated_tracker_rows(
    live_tracker_rows: list[dict[str, Any]],
    selected_review_keys: set[str],
) -> list[dict[str, Any]]:
    tracker_rows = json.loads(json.dumps(live_tracker_rows))
    for row in tracker_rows:
        review_keys = set(row.get("review_keys") or [])
        if not review_keys.intersection(selected_review_keys):
            continue
        row["status"] = "completed"
        row["assignee"] = "sim.reviewer"
        row["started_on"] = "2026-08-12"
        row["completed_on"] = "2026-08-13"
        row["decision_file_updated"] = True
        row["notes"] = "Synthetic dry-run completion for simulator."
    return tracker_rows


def summarize_tracker_rows(tracker_rows: list[dict[str, Any]]) -> dict[str, Any]:
    validation_errors: list[str] = []
    status_counts = Counter()
    completed_review_keys = 0
    for row in tracker_rows:
        validation_errors.extend(validate_tracker_row(row))
        status = str(row.get("status", "")).strip()
        if status:
            status_counts[status] += 1
        if status == "completed":
            completed_review_keys += len(row.get("review_keys") or [])
    return {
        "status_counts": dict(status_counts),
        "validation_errors": validation_errors,
        "completed_review_keys": completed_review_keys,
    }


def build_simulated_gate_report(
    decisions: list[dict[str, Any]],
    queue_lookup: dict[str, dict[str, Any]],
    actionable_count: int,
) -> dict[str, Any]:
    validation_errors: list[str] = []
    quality_errors: list[str] = []
    for decision in decisions:
        validation_errors.extend(validate_decision(decision, queue_lookup))
        quality_errors.extend(validate_decision_quality(decision, queue_lookup))
    return {
        "status": "pass" if not validation_errors and not quality_errors else "blocked",
        "submitted_decision_count": len(decisions),
        "decided_review_key_count": len({decision["review_key"] for decision in decisions}),
        "coverage_ratio": round(len({decision["review_key"] for decision in decisions}) / actionable_count, 4)
        if actionable_count
        else 1.0,
        "validation_errors": validation_errors,
        "quality_errors": quality_errors,
    }


def run_simulated_reimport(merged_overrides: dict[str, dict[str, dict[str, int]]]) -> dict[str, Any]:
    workbook_path = next(legacy_root().glob("*.xlsb"))
    phase3o_dir = _phase3o_dir()
    database_path = phase3o_dir / "staging_simulated.db"
    report_path = phase3o_dir / "reconciliation_simulated.md"
    json_path = phase3o_dir / "reconciliation_simulated.json"

    phase3o_dir.mkdir(parents=True, exist_ok=True)
    if database_path.exists():
        database_path.unlink()

    database_url = f"sqlite:///{database_path.as_posix()}"
    with session_scope(database_url) as session:
        result = import_workbook_to_database(
            session,
            workbook_path,
            report_path,
            remediation_overrides=merged_overrides,
        )

    reconciliation = result.reconciliation
    json_path.write_text(json.dumps(reconciliation, ensure_ascii=False, indent=2), encoding="utf-8")
    baseline = load_json(_phase3f_reconciliation_path())
    baseline_open = sum(1 for row in baseline.get("anomaly_rows", []) if row.get("status") == "open")
    current_open = sum(1 for row in reconciliation.get("anomaly_rows", []) if row.get("status") == "open")
    return {
        "database_path": str(database_path.relative_to(ROOT)),
        "report_path": str(report_path.relative_to(ROOT)),
        "json_path": str(json_path.relative_to(ROOT)),
        "applied_override_count": reconciliation.get("applied_override_count", 0),
        "open_anomaly_count": current_open,
        "open_anomaly_delta": current_open - baseline_open,
        "target_count_deltas": compare_counts(
            baseline.get("target_counts", {}),
            reconciliation.get("target_counts", {}),
        ),
        "skipped_row_deltas": compare_counts(
            baseline.get("skipped_rows", {}),
            reconciliation.get("skipped_rows", {}),
        ),
        "derived_count_deltas": compare_counts(
            baseline.get("derived_counts", {}),
            reconciliation.get("derived_counts", {}),
        ),
    }


def build_phase3o_simulation() -> dict[str, Any]:
    queue_bundle = build_phase3h_queue()
    queue_lookup = build_queue_lookup(queue_bundle["queue"])
    accepted_overrides = load_json(phase_artifact_path("phase3g", "accepted_overrides_baseline.json"))
    live_tracker_rows = load_json(_phase3l_tracker_path())

    selected_rows = choose_simulation_rows(limit=3)
    simulated_decisions = build_simulated_decisions(selected_rows)
    selected_review_keys = {row["review_key"] for row in selected_rows}
    simulated_tracker_rows = build_simulated_tracker_rows(live_tracker_rows, selected_review_keys)

    tracker_summary = summarize_tracker_rows(simulated_tracker_rows)
    gate_report = build_simulated_gate_report(
        simulated_decisions,
        queue_lookup,
        queue_bundle["actionable_count"],
    )

    approved_overrides = build_approved_overrides(simulated_decisions, queue_lookup)
    merged_overrides = merge_overrides(accepted_overrides, approved_overrides)
    reimport_summary = run_simulated_reimport(merged_overrides)

    return {
        "generated_on": "2026-08-13",
        "selected_review_keys": sorted(selected_review_keys),
        "simulated_decision_count": len(simulated_decisions),
        "tracker_summary": tracker_summary,
        "gate_report": gate_report,
        "approved_overrides": approved_overrides,
        "merged_override_count": sum(len(rows) for rows in merged_overrides.values()),
        "reimport_summary": reimport_summary,
        "decisions": simulated_decisions,
        "tracker_rows": simulated_tracker_rows,
    }
