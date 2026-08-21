from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any
import csv
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.phase3h_external_evidence import build_phase3h_queue
from tools.phase3j_decision_quality_gate import build_phase3j_gate_report


def urgency_rank(row: dict[str, Any]) -> int:
    if row["classification"] == "hard_unresolved":
        return 0
    if row.get("priority") == "high":
        return 1
    return 2


def evidence_complexity_rank(row: dict[str, Any]) -> int:
    candidate_count = int(row.get("candidate_count") or 0)
    if candidate_count == 0:
        return 2
    if candidate_count <= 3:
        return 0
    return 1


def review_batch_label(row: dict[str, Any]) -> str:
    if row["classification"] == "hard_unresolved":
        return "B3-hard-unresolved"
    if int(row.get("candidate_count") or 0) <= 3:
        return "B1-high-confidence-adjudication"
    return "B2-multi-candidate-adjudication"


def build_reviewer_prompt(row: dict[str, Any]) -> str:
    legacy_context = row.get("legacy_context") or {}
    certificate_number = legacy_context.get("certificate_number") or "(unknown certificate number)"
    site_name = legacy_context.get("site_name") or "(unknown site)"
    if row["source_sheet"] == "db.cc":
        return (
            f"Locate certificate or Word/PDF evidence for {site_name}, certificate {certificate_number}, "
            "then confirm which candidate inspection case matches the chronology."
        )
    return (
        "Locate business-eligibility or site identity evidence that can prove whether this row should link "
        "to an existing site, remain legacy-only, or be excluded."
    )


def build_evidence_checklist(row: dict[str, Any]) -> list[str]:
    if row["source_sheet"] == "db.cc":
        return [
            "Find certificate DOCX/PDF or signed scan on Synology.",
            "Confirm site identity using stable site ID context, not folder display name.",
            "Compare issuance chronology against candidate case years and inspection artifacts.",
            "Record exact path or document reference in evidence_reference.",
        ]
    return [
        "Find business eligibility certificate, site dossier, or equivalent Synology evidence.",
        "Verify whether the address maps to an existing stable site identity.",
        "If no safe site match exists, choose legacy_only_record or exclude_legacy_row with rationale.",
        "Record exact path or document reference in evidence_reference.",
    ]


def build_phase3k_handoff() -> dict[str, Any]:
    queue_bundle = build_phase3h_queue()
    gate_report = build_phase3j_gate_report()
    queue_rows = queue_bundle["queue"]

    prioritized_rows = []
    for row in queue_rows:
        prioritized_rows.append(
            {
                **row,
                "batch_label": review_batch_label(row),
                "reviewer_prompt": build_reviewer_prompt(row),
                "evidence_checklist": build_evidence_checklist(row),
                "urgency_rank": urgency_rank(row),
                "evidence_complexity_rank": evidence_complexity_rank(row),
            }
        )

    prioritized_rows.sort(
        key=lambda row: (
            row["urgency_rank"],
            row["evidence_complexity_rank"],
            row["source_sheet"],
            str(row["legacy_row_id"]),
        )
    )

    batch_counts = Counter(row["batch_label"] for row in prioritized_rows)
    sheet_counts = Counter(row["source_sheet"] for row in prioritized_rows)
    candidate_count_buckets = Counter()
    for row in prioritized_rows:
        count = int(row.get("candidate_count") or 0)
        if count == 0:
            bucket = "0"
        elif count <= 3:
            bucket = "1-3"
        elif count <= 6:
            bucket = "4-6"
        else:
            bucket = "7+"
        candidate_count_buckets[bucket] += 1

    top_examples = [
        {
            "review_key": row["review_key"],
            "source_sheet": row["source_sheet"],
            "classification": row["classification"],
            "batch_label": row["batch_label"],
            "candidate_count": row["candidate_count"],
            "site_name": (row.get("legacy_context") or {}).get("site_name"),
            "certificate_number": (row.get("legacy_context") or {}).get("certificate_number"),
        }
        for row in prioritized_rows[:15]
    ]

    return {
        "generated_on": "2026-08-13",
        "queue_actionable_count": queue_bundle["actionable_count"],
        "gate_status": gate_report["status"],
        "gate_reason": gate_report["reason"],
        "batch_counts": dict(batch_counts),
        "sheet_counts": dict(sheet_counts),
        "candidate_count_buckets": dict(candidate_count_buckets),
        "top_examples": top_examples,
        "prioritized_queue": prioritized_rows,
    }


def write_prioritized_csv(path: Path, prioritized_rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "batch_label",
                "review_key",
                "source_sheet",
                "legacy_row_id",
                "classification",
                "priority",
                "candidate_count",
                "site_name",
                "certificate_number",
                "reviewer_prompt",
            ],
        )
        writer.writeheader()
        for row in prioritized_rows:
            legacy_context = row.get("legacy_context") or {}
            writer.writerow(
                {
                    "batch_label": row["batch_label"],
                    "review_key": row["review_key"],
                    "source_sheet": row["source_sheet"],
                    "legacy_row_id": row["legacy_row_id"],
                    "classification": row["classification"],
                    "priority": row.get("priority"),
                    "candidate_count": row.get("candidate_count"),
                    "site_name": legacy_context.get("site_name"),
                    "certificate_number": legacy_context.get("certificate_number"),
                    "reviewer_prompt": row["reviewer_prompt"],
                }
            )
