from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import sys

from backend.app.project_paths import phase_artifact_path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _phase3e_merged_overrides_path() -> Path:
    return phase_artifact_path("phase3e", "merged_overrides.json")


def _snapshot_path() -> Path:
    return phase_artifact_path("phase3c", "legacy_snapshot.json")


def _site_export_path() -> Path:
    return phase_artifact_path("phase3", "site.json")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_address(text: str | None) -> str:
    normalized = " ".join(str(text or "").strip().lower().split())
    for suffix in [", việt nam", ", vietnam", " việt nam", " vietnam"]:
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)].rstrip(", ")
    return normalized.strip(" ,")


def build_phase3f_analysis() -> dict[str, Any]:
    merged_overrides = load_json(_phase3e_merged_overrides_path())
    snapshot = load_json(_snapshot_path())
    sites = load_json(_site_export_path())

    detail_155 = next(row for row in snapshot["db.Tdoi2"] if str(row.get("ID", "")).strip() == "155")
    new_address = str(detail_155.get("THÔNG TIN MỚI", "")).strip()
    normalized_new_address = normalize_address(new_address)

    matching_sites = [
        {
            "legacy_site_id": site["legacy_site_id"],
            "site_name": site.get("site_name"),
            "site_address": site.get("site_address"),
            "site_address_en": site.get("site_address_en"),
        }
        for site in sites
        if normalized_new_address
        and any(
            normalized_new_address == candidate
            or normalized_new_address in candidate
            or candidate in normalized_new_address
            for candidate in [
                normalize_address(site.get("site_address")),
                normalize_address(site.get("site_address_en")),
            ]
            if candidate
        )
    ]

    adjudicated_suggestions: list[dict[str, Any]] = []
    adjudicated_overrides: dict[str, dict[str, dict[str, int]]] = {}

    if len(matching_sites) == 1:
        match = matching_sites[0]
        suggestion = {
            "source_sheet": "db.Tdoi",
            "legacy_row_id": "187",
            "override": {"site_legacy_id": int(match["legacy_site_id"])},
            "rule": "address_change_detail_exact_site_match",
            "evidence": {
                "change_detail_legacy_id": 155,
                "classification_label": detail_155.get("PHÂN LOẠI"),
                "old_value": detail_155.get("THÔNG TIN CŨ"),
                "new_value": new_address,
                "matched_site": match,
            },
        }
        adjudicated_suggestions.append(suggestion)
        adjudicated_overrides = {"db.Tdoi": {"187": suggestion["override"]}}

    final_merged_overrides = json.loads(json.dumps(merged_overrides))
    for sheet, rows in adjudicated_overrides.items():
        final_merged_overrides.setdefault(sheet, {}).update(rows)

    return {
        "phase3e_override_count": sum(len(rows) for rows in merged_overrides.values()),
        "adjudicated_suggestions": adjudicated_suggestions,
        "adjudicated_suggestion_count": len(adjudicated_suggestions),
        "adjudicated_overrides": adjudicated_overrides,
        "final_merged_overrides": final_merged_overrides,
    }
