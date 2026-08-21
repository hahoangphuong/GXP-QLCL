from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import sys

from backend.app.project_paths import phase_artifact_path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _phase3f_reconciliation_path() -> Path:
    return phase_artifact_path("phase3f", "reconciliation_final.json")


def _phase3h_summary_path() -> Path:
    return phase_artifact_path("phase3h", "external_evidence_summary.json")


def _phase3i_reconciliation_path() -> Path:
    return phase_artifact_path("phase3i", "reconciliation_external.json")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def compare_counts(
    baseline: dict[str, int],
    current: dict[str, int],
) -> dict[str, dict[str, int]]:
    keys = sorted(set(baseline) | set(current))
    deltas: dict[str, dict[str, int]] = {}
    for key in keys:
        baseline_value = int(baseline.get(key, 0))
        current_value = int(current.get(key, 0))
        if baseline_value != current_value:
            deltas[key] = {
                "baseline": baseline_value,
                "current": current_value,
                "delta": current_value - baseline_value,
            }
    return deltas


def build_phase3i_summary() -> dict[str, Any]:
    baseline = load_json(_phase3f_reconciliation_path())
    current = load_json(_phase3i_reconciliation_path())
    external_summary = load_json(_phase3h_summary_path())

    baseline_open = sum(1 for row in baseline.get("anomaly_rows", []) if row.get("status") == "open")
    current_open = sum(1 for row in current.get("anomaly_rows", []) if row.get("status") == "open")

    return {
        "submitted_decision_count": external_summary.get("submitted_decision_count", 0),
        "approved_override_count": external_summary.get("approved_override_count", 0),
        "phase3f_applied_override_count": baseline.get("applied_override_count", 0),
        "phase3i_applied_override_count": current.get("applied_override_count", 0),
        "phase3f_open_anomaly_count": baseline_open,
        "phase3i_open_anomaly_count": current_open,
        "target_count_deltas": compare_counts(
            baseline.get("target_counts", {}),
            current.get("target_counts", {}),
        ),
        "skipped_row_deltas": compare_counts(
            baseline.get("skipped_rows", {}),
            current.get("skipped_rows", {}),
        ),
        "derived_count_deltas": compare_counts(
            baseline.get("derived_counts", {}),
            current.get("derived_counts", {}),
        ),
    }
