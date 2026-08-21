from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


PHASE3F_RECONCILIATION_PATH = ROOT / "artifacts" / "phase3f" / "reconciliation_final.json"
PHASE3F_OVERRIDES_PATH = ROOT / "artifacts" / "phase3f" / "final_merged_overrides.json"
PHASE3C_ANALYSIS_PATH = ROOT / "artifacts" / "phase3c" / "remediation_analysis.json"
PHASE3D_QUEUE_PATH = ROOT / "artifacts" / "phase3d" / "manual_review_queue.json"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def classify_unresolved_row(
    row: dict[str, Any],
    placeholder_rows: dict[str, set[str]],
    queue_lookup: dict[tuple[str, str], dict[str, Any]],
) -> str:
    legacy_row_id = row.get("legacy_row_id")
    source_sheet = row["source_sheet"]

    if legacy_row_id is None or legacy_row_id in placeholder_rows.get(source_sheet, set()):
        return "archival_placeholder"

    queue_item = queue_lookup.get((source_sheet, legacy_row_id))
    if queue_item and queue_item.get("candidate_cases"):
        return "needs_external_evidence"

    return "hard_unresolved"


def build_phase3g_closeout() -> dict[str, Any]:
    reconciliation = load_json(PHASE3F_RECONCILIATION_PATH)
    accepted_overrides = load_json(PHASE3F_OVERRIDES_PATH)
    phase3c_analysis = load_json(PHASE3C_ANALYSIS_PATH)
    manual_queue = load_json(PHASE3D_QUEUE_PATH)

    placeholder_rows = {
        sheet: set(row_ids)
        for sheet, row_ids in phase3c_analysis["placeholder_rows"].items()
    }
    queue_lookup = {
        (item["source_sheet"], item["legacy_row_id"]): item
        for item in manual_queue
    }

    open_rows = [row for row in reconciliation["anomaly_rows"] if row["status"] == "open"]
    unresolved_review_pack: list[dict[str, Any]] = []
    classification_counts: dict[str, int] = {
        "archival_placeholder": 0,
        "needs_external_evidence": 0,
        "hard_unresolved": 0,
    }
    source_classification_counts: dict[str, dict[str, int]] = {}

    for row in open_rows:
        classification = classify_unresolved_row(row, placeholder_rows, queue_lookup)
        classification_counts[classification] += 1
        source_classification_counts.setdefault(row["source_sheet"], {}).setdefault(classification, 0)
        source_classification_counts[row["source_sheet"]][classification] += 1

        legacy_row_id = row.get("legacy_row_id")
        queue_item = queue_lookup.get((row["source_sheet"], legacy_row_id)) if legacy_row_id else None
        unresolved_review_pack.append(
            {
                "source_sheet": row["source_sheet"],
                "legacy_row_id": legacy_row_id,
                "reason": row["reason"],
                "required_field": row.get("required_field"),
                "raw_fk_value": row.get("raw_fk_value"),
                "classification": classification,
                "review_context": queue_item,
            }
        )

    unresolved_review_pack.sort(
        key=lambda item: (
            item["classification"] != "needs_external_evidence",
            item["classification"] != "hard_unresolved",
            item["source_sheet"],
            -1 if item["legacy_row_id"] is None else int(item["legacy_row_id"]),
        )
    )

    return {
        "accepted_override_count": sum(len(rows) for rows in accepted_overrides.values()),
        "accepted_overrides": accepted_overrides,
        "open_anomaly_count": len(open_rows),
        "classification_counts": classification_counts,
        "source_classification_counts": source_classification_counts,
        "unresolved_review_pack": unresolved_review_pack,
    }
