from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.domain.phase2_import import normalize_row


SNAPSHOT_PATH = ROOT / "artifacts" / "phase3c" / "legacy_snapshot.json"
RECONCILIATION_PATH = ROOT / "artifacts" / "phase2" / "reconciliation.json"
SITE_EXPORT_PATH = ROOT / "artifacts" / "phase3" / "site.json"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def canonicalize_snapshot(snapshot: dict[str, list[dict[str, str]]]) -> dict[str, list[dict[str, str]]]:
    return {
        sheet: [normalize_row(row) for row in rows]
        for sheet, rows in snapshot.items()
    }


def has_meaningful_payload(row: dict[str, str]) -> bool:
    for key, value in row.items():
        if key == "ID":
            continue
        if str(value or "").strip() not in {"", "-"}:
            return True
    return False


def _anomaly_index(anomalies: list[dict[str, Any]]) -> dict[str, set[str]]:
    index: dict[str, set[str]] = defaultdict(set)
    for row in anomalies:
        legacy_row_id = row.get("legacy_row_id")
        if legacy_row_id:
            index[row["source_sheet"]].add(legacy_row_id)
    return index


def build_phase3c_analysis() -> dict[str, Any]:
    snapshot = canonicalize_snapshot(load_json(SNAPSHOT_PATH))
    reconciliation = load_json(RECONCILIATION_PATH)
    site_rows = load_json(SITE_EXPORT_PATH)
    anomalies = reconciliation["anomaly_rows"]
    anomaly_index = _anomaly_index(anomalies)

    site_by_legacy_id = {
        str(row["legacy_site_id"]): row
        for row in site_rows
        if row.get("legacy_site_id") is not None
    }

    placeholder_rows: dict[str, list[str]] = defaultdict(list)
    for sheet, row_ids in anomaly_index.items():
        for row in snapshot[sheet]:
            legacy_id = str(row.get("ID", "")).strip()
            if legacy_id and legacy_id in row_ids and not has_meaningful_payload(row):
                placeholder_rows[sheet].append(legacy_id)

    suggestions: list[dict[str, Any]] = []
    overrides: dict[str, dict[str, dict[str, int]]] = defaultdict(dict)

    missing_ktra_ids = anomaly_index.get("db.ktra", set())
    certificate_rows = snapshot["db.cc"]
    inferred_ktra_sites: dict[str, Counter[str]] = defaultdict(Counter)
    for row in certificate_rows:
        case_legacy_id = str(row.get("inspection_case_legacy_id_ref", "")).strip()
        site_legacy_id = str(row.get("site_legacy_id_ref", "")).strip()
        if case_legacy_id in missing_ktra_ids and site_legacy_id:
            inferred_ktra_sites[case_legacy_id][site_legacy_id] += 1

    for legacy_row_id, site_counts in sorted(inferred_ktra_sites.items(), key=lambda item: int(item[0])):
        if len(site_counts) != 1:
            continue
        site_legacy_id = next(iter(site_counts))
        supporting_cert_ids = [
            str(row.get("ID", "")).strip()
            for row in certificate_rows
            if str(row.get("inspection_case_legacy_id_ref", "")).strip() == legacy_row_id
            and str(row.get("site_legacy_id_ref", "")).strip() == site_legacy_id
        ]
        suggestion = {
            "source_sheet": "db.ktra",
            "legacy_row_id": legacy_row_id,
            "override": {"site_legacy_id": int(site_legacy_id)},
            "rule": "certificate_site_backfill",
            "evidence": {
                "supporting_certificate_legacy_ids": supporting_cert_ids,
                "supporting_site_legacy_id": int(site_legacy_id),
                "supporting_site_name": site_by_legacy_id.get(site_legacy_id, {}).get("site_name"),
                "supporting_site_address": site_by_legacy_id.get(site_legacy_id, {}).get("site_address"),
                "support_count": site_counts[site_legacy_id],
            },
        }
        suggestions.append(suggestion)
        overrides["db.ktra"][legacy_row_id] = suggestion["override"]

    return {
        "source_snapshot_path": str(SNAPSHOT_PATH),
        "source_reconciliation_path": str(RECONCILIATION_PATH),
        "baseline_anomaly_count": len(anomalies),
        "placeholder_rows": {sheet: sorted(row_ids, key=int) for sheet, row_ids in placeholder_rows.items()},
        "placeholder_counts": {sheet: len(row_ids) for sheet, row_ids in placeholder_rows.items()},
        "auto_resolvable_suggestions": suggestions,
        "auto_resolvable_count": len(suggestions),
        "auto_overrides": overrides,
    }
