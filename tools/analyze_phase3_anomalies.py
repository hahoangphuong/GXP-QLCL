from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any
import json

from backend.app.project_paths import phase_artifact_path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = phase_artifact_path("phase2", "reconciliation.json")
OUT = phase_artifact_path("phase3", "anomaly_summary.json")


def build_summary(data: dict[str, Any]) -> dict[str, Any]:
    anomalies = data.get("anomaly_rows", [])
    counts = data.get("skipped_rows", {})

    by_reason = Counter()
    by_status = Counter()
    by_sheet: dict[str, dict[str, Any]] = {}

    for row in anomalies:
        sheet = row["source_sheet"]
        reason = row["reason"]
        status = row.get("status", "open")
        by_reason[reason] += 1
        by_status[status] += 1

        sheet_summary = by_sheet.setdefault(
            sheet,
            {
                "skipped_count": counts.get(sheet, 0),
                "reason_breakdown": Counter(),
                "status_breakdown": Counter(),
                "sample_rows": [],
            },
        )
        sheet_summary["reason_breakdown"][reason] += 1
        sheet_summary["status_breakdown"][status] += 1
        if len(sheet_summary["sample_rows"]) < 10:
            sheet_summary["sample_rows"].append(
                {
                    "legacy_row_id": row.get("legacy_row_id"),
                    "reason": reason,
                    "required_field": row.get("required_field"),
                    "raw_fk_value": row.get("raw_fk_value"),
                    "status": status,
                }
            )

    normalized_by_sheet = {
        sheet: {
            "skipped_count": payload["skipped_count"],
            "reason_breakdown": dict(payload["reason_breakdown"]),
            "status_breakdown": dict(payload["status_breakdown"]),
            "sample_rows": payload["sample_rows"],
        }
        for sheet, payload in by_sheet.items()
    }

    return {
        "skipped_rows": counts,
        "total_anomalies": len(anomalies),
        "open_anomalies": by_status.get("open", 0),
        "overridden_anomalies": by_status.get("overridden", 0),
        "excluded_confirmed_blanked_anomalies": by_status.get("excluded_confirmed_blanked", 0),
        "by_reason": dict(by_reason),
        "by_status": dict(by_status),
        "by_sheet": normalized_by_sheet,
    }


def main() -> int:
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    payload = build_summary(data)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
