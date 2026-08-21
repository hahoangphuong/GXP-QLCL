from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.phase3c_remediation import canonicalize_snapshot, has_meaningful_payload


PHASE2_RECONCILIATION_PATH = ROOT / "artifacts" / "phase2" / "reconciliation.json"
PHASE3C_ANALYSIS_PATH = ROOT / "artifacts" / "phase3c" / "remediation_analysis.json"
SNAPSHOT_PATH = ROOT / "artifacts" / "phase3c" / "legacy_snapshot.json"
CASE_EXPORT_PATH = ROOT / "artifacts" / "phase3" / "case.json"
SITE_EXPORT_PATH = ROOT / "artifacts" / "phase3" / "site.json"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _build_anomaly_lookup(anomalies: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    lookup: dict[tuple[str, str], dict[str, Any]] = {}
    for row in anomalies:
        legacy_row_id = row.get("legacy_row_id")
        if legacy_row_id:
            lookup[(row["source_sheet"], legacy_row_id)] = row
    return lookup


def _rank_cc_candidate(
    row: dict[str, str],
    candidate: dict[str, Any],
    site_uuid_by_legacy: dict[str, str],
) -> int:
    score = 0
    if row.get("scope_code") and candidate.get("scope_code") == row.get("scope_code"):
        score += 3
    if row.get("certificate_type") and candidate.get("gxp_type") == row.get("certificate_type"):
        score += 3
    site_legacy_id = str(row.get("site_legacy_id_ref", "")).strip()
    if site_legacy_id and site_uuid_by_legacy.get(site_legacy_id) == candidate.get("site_id"):
        score += 4
    return score


def build_phase3d_analysis() -> dict[str, Any]:
    reconciliation = load_json(PHASE2_RECONCILIATION_PATH)
    phase3c_analysis = load_json(PHASE3C_ANALYSIS_PATH)
    snapshot = canonicalize_snapshot(load_json(SNAPSHOT_PATH))
    cases = load_json(CASE_EXPORT_PATH)
    sites = load_json(SITE_EXPORT_PATH)

    anomaly_lookup = _build_anomaly_lookup(reconciliation["anomaly_rows"])
    placeholder_rows = {
        sheet: set(row_ids)
        for sheet, row_ids in phase3c_analysis["placeholder_rows"].items()
    }
    site_uuid_by_legacy = {
        str(row["legacy_site_id"]): row["id"]
        for row in sites
        if row.get("legacy_site_id") is not None
    }
    site_by_legacy = {
        str(row["legacy_site_id"]): row
        for row in sites
        if row.get("legacy_site_id") is not None
    }

    cases_by_site: dict[str, list[dict[str, Any]]] = defaultdict(list)
    case_by_legacy_id: dict[str, dict[str, Any]] = {}
    for case in cases:
        cases_by_site[str(case["site_id"])].append(case)
        if case.get("legacy_inspection_id") is not None:
            case_by_legacy_id[str(case["legacy_inspection_id"])] = case

    high_confidence_suggestions: list[dict[str, Any]] = []
    high_confidence_overrides: dict[str, dict[str, dict[str, int]]] = defaultdict(dict)
    manual_review_queue: list[dict[str, Any]] = []

    # Focus Phase 3d on non-placeholder anomalies that still carry business payload.
    for row in snapshot["db.cc"]:
        legacy_row_id = str(row.get("ID", "")).strip()
        if not legacy_row_id or ("db.cc", legacy_row_id) not in anomaly_lookup:
            continue
        if legacy_row_id in placeholder_rows.get("db.cc", set()):
            continue
        if not has_meaningful_payload(row):
            continue

        site_legacy_id = str(row.get("site_legacy_id_ref", "")).strip()
        site_uuid = site_uuid_by_legacy.get(site_legacy_id)
        site_candidates = cases_by_site.get(site_uuid or "", [])
        scored_candidates = []
        for candidate in site_candidates:
            score = _rank_cc_candidate(row, candidate, site_uuid_by_legacy)
            if score > 0:
                scored_candidates.append(
                    {
                        "legacy_case_id": candidate["legacy_inspection_id"],
                        "site_id": candidate["site_id"],
                        "gxp_type": candidate.get("gxp_type"),
                        "scope_code": candidate.get("scope_code"),
                        "opened_year": candidate.get("opened_year"),
                        "score": score,
                    }
                )
        scored_candidates.sort(key=lambda item: (-item["score"], item["legacy_case_id"]))

        if len(scored_candidates) == 1:
            suggestion = {
                "source_sheet": "db.cc",
                "legacy_row_id": legacy_row_id,
                "override": {"case_legacy_id": int(scored_candidates[0]["legacy_case_id"])},
                "rule": "unique_site_scope_case_match",
                "evidence": {
                    "site_legacy_id": int(site_legacy_id) if site_legacy_id else None,
                    "site_name": row.get("site_name"),
                    "scope_code": row.get("scope_code"),
                    "certificate_type": row.get("certificate_type"),
                    "candidate_case": scored_candidates[0],
                    "legacy_certificate_note": row.get("note"),
                    "legacy_certificate_number": row.get("Mã số CC"),
                },
            }
            high_confidence_suggestions.append(suggestion)
            high_confidence_overrides["db.cc"][legacy_row_id] = suggestion["override"]
            continue

        queue_item = {
            "priority": "high" if scored_candidates else "medium",
            "source_sheet": "db.cc",
            "legacy_row_id": legacy_row_id,
            "anomaly_reason": anomaly_lookup[("db.cc", legacy_row_id)]["reason"],
            "summary": "Certificate row has site/type payload but missing case linkage.",
            "legacy_context": {
                "certificate_type": row.get("certificate_type"),
                "site_legacy_id": site_legacy_id or None,
                "site_name": row.get("site_name") or None,
                "site_address": row.get("site_address") or None,
                "scope_code": row.get("scope_code") or None,
                "certificate_number": row.get("Mã số CC") or None,
                "note": row.get("note") or None,
                "alt_case_ref": row.get("ID TĐ KHÁC") or None,
            },
            "candidate_cases": scored_candidates[:10],
            "decision_hint": "Select case_legacy_id only if supporting documents or chronology confirm the candidate.",
        }
        manual_review_queue.append(queue_item)

    for row in snapshot["db.Tdoi2"]:
        legacy_row_id = str(row.get("ID", "")).strip()
        if not legacy_row_id or ("db.Tdoi2", legacy_row_id) not in anomaly_lookup:
            continue
        if legacy_row_id in placeholder_rows.get("db.Tdoi2", set()):
            continue
        manual_review_queue.append(
            {
                "priority": "high",
                "source_sheet": "db.Tdoi2",
                "legacy_row_id": legacy_row_id,
                "anomaly_reason": anomaly_lookup[("db.Tdoi2", legacy_row_id)]["reason"],
                "summary": "Change detail points to missing root change request.",
                "legacy_context": {
                    "change_request_legacy_id_ref": row.get("change_request_legacy_id_ref") or None,
                    "classification_label": row.get("classification_label") or None,
                    "old_value": row.get("old_value") or None,
                    "new_value": row.get("new_value") or None,
                },
                "candidate_cases": [],
                "decision_hint": "Needs external evidence or explicit archival rule because root db.Tdoi row is placeholder-only.",
            }
        )

    for row in snapshot["db.dkkd"]:
        legacy_row_id = str(row.get("ID", "")).strip()
        if not legacy_row_id or ("db.dkkd", legacy_row_id) not in anomaly_lookup:
            continue
        if legacy_row_id in placeholder_rows.get("db.dkkd", set()):
            continue
        site_matches = [
            {
                "legacy_site_id": site["legacy_site_id"],
                "site_name": site.get("site_name"),
                "site_address": site.get("site_address"),
                "site_address_en": site.get("site_address_en"),
            }
            for site in sites
            if row.get("SITE ADDRESS")
            and row.get("SITE ADDRESS") in {(site.get("site_address_en") or "").strip(), (site.get("site_address") or "").strip()}
        ]
        manual_review_queue.append(
            {
                "priority": "medium",
                "source_sheet": "db.dkkd",
                "legacy_row_id": legacy_row_id,
                "anomaly_reason": anomaly_lookup[("db.dkkd", legacy_row_id)]["reason"],
                "summary": "Business eligibility row carries address payload but missing site linkage.",
                "legacy_context": {
                    "site_address_en": row.get("SITE ADDRESS") or None,
                    "legal_address_en": row.get("LEGAL ADDRESS") or None,
                },
                "candidate_sites": site_matches[:10],
                "decision_hint": "No exact imported site match found in current export; keep open unless separate evidence exists.",
            }
        )

    manual_review_queue.sort(key=lambda item: (item["priority"] != "high", item["source_sheet"], int(item["legacy_row_id"])))
    high_confidence_suggestions.sort(key=lambda item: (item["source_sheet"], int(item["legacy_row_id"])))

    return {
        "baseline_anomaly_count": len(reconciliation["anomaly_rows"]),
        "phase3c_placeholder_counts": phase3c_analysis["placeholder_counts"],
        "high_confidence_suggestions": high_confidence_suggestions,
        "high_confidence_count": len(high_confidence_suggestions),
        "high_confidence_overrides": high_confidence_overrides,
        "manual_review_queue": manual_review_queue,
        "manual_review_count": len(manual_review_queue),
    }
