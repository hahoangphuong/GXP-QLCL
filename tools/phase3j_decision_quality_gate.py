from __future__ import annotations

from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.phase3h_external_evidence import (
    PHASE3H_DECISIONS_PATH,
    build_phase3h_queue,
    build_queue_lookup,
    load_json,
    validate_decision,
)


TODAY = date(2026, 8, 13)
ALLOWED_EVIDENCE_SOURCES = {
    "synology_doc",
    "word_output",
    "signed_pdf",
    "business_chronology",
    "legacy_register",
    "email_confirmation",
}


def parse_reviewed_on(value: str) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        year, month, day = text.split("-")
        return date(int(year), int(month), int(day))
    except (ValueError, TypeError):
        return None


def validate_decision_quality(
    decision: dict[str, Any],
    queue_lookup: dict[str, dict[str, Any]],
) -> list[str]:
    errors = validate_decision(decision, queue_lookup)
    key = str(decision.get("review_key", "")).strip()
    if not key or key not in queue_lookup:
        return errors

    row = queue_lookup[key]
    action = str(decision.get("decision", "")).strip()
    reviewer = str(decision.get("reviewer", "")).strip()
    reviewed_on_text = str(decision.get("reviewed_on", "")).strip()
    rationale = str(decision.get("decision_rationale", "")).strip()
    evidence_source = str(decision.get("evidence_source", "")).strip()
    evidence_reference = str(decision.get("evidence_reference", "")).strip()
    selected_legacy_id = decision.get("selected_legacy_id")

    if action == "defer":
        if not rationale:
            errors.append(f"{key}: decision_rationale is required for defer")
        if not reviewer:
            errors.append(f"{key}: reviewer is required for defer")
        reviewed_on = parse_reviewed_on(reviewed_on_text)
        if reviewed_on is None:
            errors.append(f"{key}: reviewed_on must be ISO date YYYY-MM-DD")
        elif reviewed_on > TODAY:
            errors.append(f"{key}: reviewed_on cannot be in the future")
        return errors

    if evidence_source and evidence_source not in ALLOWED_EVIDENCE_SOURCES:
        errors.append(f"{key}: unsupported evidence_source '{evidence_source}'")

    if evidence_reference and len(evidence_reference) < 8:
        errors.append(f"{key}: evidence_reference is too short")

    reviewed_on = parse_reviewed_on(reviewed_on_text)
    if reviewed_on is None:
        errors.append(f"{key}: reviewed_on must be ISO date YYYY-MM-DD")
    elif reviewed_on > TODAY:
        errors.append(f"{key}: reviewed_on cannot be in the future")

    if len(rationale) and len(rationale) < 12:
        errors.append(f"{key}: decision_rationale is too short")

    if action == "approve_override":
        if row.get("candidate_count", 0) == 0:
            errors.append(f"{key}: approve_override is not allowed when candidate_count is 0")
        if selected_legacy_id is not None and int(selected_legacy_id) <= 0:
            errors.append(f"{key}: selected_legacy_id must be positive")

    if action in {"exclude_legacy_row", "legacy_only_record"} and not evidence_reference:
        errors.append(f"{key}: evidence_reference is required for '{action}'")

    return errors


def build_phase3j_gate_report() -> dict[str, Any]:
    queue_bundle = build_phase3h_queue()
    queue_rows = queue_bundle["queue"]
    queue_lookup = build_queue_lookup(queue_rows)

    if not PHASE3H_DECISIONS_PATH.exists():
        return {
            "status": "blocked",
            "reason": "missing_decision_file",
            "queue_actionable_count": queue_bundle["actionable_count"],
            "submitted_decision_count": 0,
            "coverage_ratio": 0.0,
            "can_rerun_phase3i": False,
            "validation_errors": ["external_evidence_decisions.json does not exist"],
            "quality_errors": [],
            "decision_counts": {},
        }

    decisions = load_json(PHASE3H_DECISIONS_PATH)
    review_keys = [str(item.get("review_key", "")).strip() for item in decisions]
    duplicate_keys = sorted(key for key, count in Counter(review_keys).items() if key and count > 1)

    validation_errors: list[str] = []
    quality_errors: list[str] = []
    for decision in decisions:
        validation_errors.extend(validate_decision(decision, queue_lookup))
        quality_errors.extend(validate_decision_quality(decision, queue_lookup))

    for key in duplicate_keys:
        quality_errors.append(f"{key}: duplicate decision rows are not allowed")

    decision_counts = Counter(str(item.get("decision", "")).strip() for item in decisions if item.get("decision"))
    decided_keys = {key for key in review_keys if key}
    actionable_count = queue_bundle["actionable_count"]
    coverage_ratio = round(len(decided_keys) / actionable_count, 4) if actionable_count else 1.0

    return {
        "status": "pass" if not validation_errors and not quality_errors else "blocked",
        "reason": None if not validation_errors and not quality_errors else "decision_quality_errors",
        "queue_actionable_count": actionable_count,
        "submitted_decision_count": len(decisions),
        "decided_review_key_count": len(decided_keys),
        "coverage_ratio": coverage_ratio,
        "can_rerun_phase3i": not validation_errors and not quality_errors,
        "validation_errors": validation_errors,
        "quality_errors": quality_errors,
        "duplicate_review_keys": duplicate_keys,
        "decision_counts": dict(decision_counts),
    }
