from __future__ import annotations

from pathlib import Path
from typing import Any
import csv
import json
import sys

from backend.app.project_paths import artifacts_root, phase_artifact_path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _phase3g_accepted_overrides_path() -> Path:
    return phase_artifact_path("phase3g", "accepted_overrides_baseline.json")


def _phase3g_unresolved_pack_path() -> Path:
    return phase_artifact_path("phase3g", "unresolved_review_pack.json")


def _phase3h_dir() -> Path:
    return artifacts_root() / "phase3h"


PHASE3H_TEMPLATE_PATH = _phase3h_dir() / "external_evidence_decisions.template.json"
PHASE3H_DECISIONS_PATH = _phase3h_dir() / "external_evidence_decisions.json"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def review_key(source_sheet: str, legacy_row_id: str | None) -> str:
    return f"{source_sheet}:{legacy_row_id if legacy_row_id is not None else 'null'}"


def infer_override_field(row: dict[str, Any]) -> str | None:
    if row["reason"] == "missing_case_fk":
        return "case_legacy_id"
    if row["reason"] == "missing_site_fk":
        return "site_legacy_id"
    return None


def candidate_legacy_ids(row: dict[str, Any]) -> list[int]:
    review_context = row.get("review_context") or {}
    candidates = review_context.get("candidate_cases") or []
    values: list[int] = []
    for candidate in candidates:
        legacy_id = candidate.get("legacy_case_id")
        if legacy_id is not None:
            values.append(int(legacy_id))
    return values


def build_phase3h_queue() -> dict[str, Any]:
    unresolved_pack = load_json(_phase3g_unresolved_pack_path())

    actionable_rows = [
        row
        for row in unresolved_pack
        if row["classification"] in {"needs_external_evidence", "hard_unresolved"}
    ]

    queue_rows = []
    for row in actionable_rows:
        review_context = row.get("review_context") or {}
        legacy_context = review_context.get("legacy_context") or {}
        candidates = review_context.get("candidate_cases") or []
        queue_rows.append(
            {
                "review_key": review_key(row["source_sheet"], row["legacy_row_id"]),
                "source_sheet": row["source_sheet"],
                "legacy_row_id": row["legacy_row_id"],
                "classification": row["classification"],
                "reason": row["reason"],
                "required_field": row["required_field"],
                "override_field": infer_override_field(row),
                "summary": review_context.get("summary"),
                "priority": review_context.get("priority"),
                "decision_hint": review_context.get("decision_hint"),
                "candidate_legacy_ids": candidate_legacy_ids(row),
                "candidate_count": len(candidates),
                "legacy_context": legacy_context,
                "review_context": review_context,
            }
        )

    queue_rows.sort(key=lambda item: (item["source_sheet"], str(item["legacy_row_id"])))

    by_classification: dict[str, int] = {}
    by_sheet: dict[str, int] = {}
    for row in queue_rows:
        by_classification[row["classification"]] = by_classification.get(row["classification"], 0) + 1
        by_sheet[row["source_sheet"]] = by_sheet.get(row["source_sheet"], 0) + 1

    return {
        "actionable_count": len(queue_rows),
        "classification_counts": by_classification,
        "sheet_counts": by_sheet,
        "queue": queue_rows,
    }


def build_decision_template(queue_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    template = []
    for row in queue_rows:
        template.append(
            {
                "review_key": row["review_key"],
                "source_sheet": row["source_sheet"],
                "legacy_row_id": row["legacy_row_id"],
                "classification": row["classification"],
                "reason": row["reason"],
                "override_field": row["override_field"],
                "candidate_legacy_ids": row["candidate_legacy_ids"],
                "decision": "",
                "selected_legacy_id": None,
                "evidence_source": "",
                "evidence_reference": "",
                "decision_rationale": "",
                "reviewer": "",
                "reviewed_on": "",
            }
        )
    return template


def build_queue_lookup(queue_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {row["review_key"]: row for row in queue_rows}


def validate_decision(decision: dict[str, Any], queue_lookup: dict[str, dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    key = decision.get("review_key")
    if not key or key not in queue_lookup:
        return [f"unknown review_key: {key}"]

    row = queue_lookup[key]
    action = str(decision.get("decision", "")).strip()
    if action not in {"approve_override", "exclude_legacy_row", "legacy_only_record", "defer"}:
        errors.append(f"{key}: unsupported decision '{action}'")
        return errors

    if action == "defer":
        return errors

    evidence_source = str(decision.get("evidence_source", "")).strip()
    evidence_reference = str(decision.get("evidence_reference", "")).strip()
    rationale = str(decision.get("decision_rationale", "")).strip()
    reviewer = str(decision.get("reviewer", "")).strip()
    reviewed_on = str(decision.get("reviewed_on", "")).strip()

    if not evidence_source:
        errors.append(f"{key}: evidence_source is required")
    if not evidence_reference:
        errors.append(f"{key}: evidence_reference is required")
    if not rationale:
        errors.append(f"{key}: decision_rationale is required")
    if not reviewer:
        errors.append(f"{key}: reviewer is required")
    if not reviewed_on:
        errors.append(f"{key}: reviewed_on is required")

    selected_legacy_id = decision.get("selected_legacy_id")
    if action == "approve_override":
        if row["override_field"] is None:
            errors.append(f"{key}: no override_field available for approve_override")
        if selected_legacy_id is None:
            errors.append(f"{key}: selected_legacy_id is required for approve_override")
        else:
            candidate_ids = set(row["candidate_legacy_ids"])
            if candidate_ids and int(selected_legacy_id) not in candidate_ids:
                errors.append(
                    f"{key}: selected_legacy_id {selected_legacy_id} is not in candidate_legacy_ids"
                )
    else:
        if selected_legacy_id is not None:
            errors.append(f"{key}: selected_legacy_id must be null for decision '{action}'")

    return errors


def build_approved_overrides(
    decisions: list[dict[str, Any]],
    queue_lookup: dict[str, dict[str, Any]],
) -> dict[str, dict[str, dict[str, int]]]:
    overrides: dict[str, dict[str, dict[str, int]]] = {}
    for decision in decisions:
        if decision.get("decision") != "approve_override":
            continue
        row = queue_lookup[decision["review_key"]]
        overrides.setdefault(row["source_sheet"], {})[str(row["legacy_row_id"])] = {
            row["override_field"]: int(decision["selected_legacy_id"])
        }
    return overrides


def merge_overrides(
    accepted_overrides: dict[str, dict[str, dict[str, int]]],
    approved_overrides: dict[str, dict[str, dict[str, int]]],
) -> dict[str, dict[str, dict[str, int]]]:
    merged = json.loads(json.dumps(accepted_overrides))
    for sheet, rows in approved_overrides.items():
        merged.setdefault(sheet, {}).update(rows)
    return merged


def build_decision_summary(
    decisions: list[dict[str, Any]],
    queue_lookup: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    counts_by_decision: dict[str, int] = {}
    counts_by_sheet: dict[str, dict[str, int]] = {}
    for decision in decisions:
        action = str(decision.get("decision", "")).strip()
        if not action:
            continue
        counts_by_decision[action] = counts_by_decision.get(action, 0) + 1
        row = queue_lookup.get(str(decision.get("review_key")))
        if row is None:
            continue
        sheet_counts = counts_by_sheet.setdefault(row["source_sheet"], {})
        sheet_counts[action] = sheet_counts.get(action, 0) + 1
    return {
        "decision_count": sum(counts_by_decision.values()),
        "counts_by_decision": counts_by_decision,
        "counts_by_sheet": counts_by_sheet,
    }


def write_queue_csv(path: Path, queue_rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "review_key",
                "source_sheet",
                "legacy_row_id",
                "classification",
                "reason",
                "required_field",
                "override_field",
                "priority",
                "candidate_count",
                "candidate_legacy_ids",
                "summary",
                "site_legacy_id",
                "site_name",
                "certificate_number",
                "alt_case_ref",
                "decision_hint",
            ],
        )
        writer.writeheader()
        for row in queue_rows:
            legacy_context = row.get("legacy_context") or {}
            writer.writerow(
                {
                    "review_key": row["review_key"],
                    "source_sheet": row["source_sheet"],
                    "legacy_row_id": row["legacy_row_id"],
                    "classification": row["classification"],
                    "reason": row["reason"],
                    "required_field": row["required_field"],
                    "override_field": row["override_field"],
                    "priority": row["priority"],
                    "candidate_count": row["candidate_count"],
                    "candidate_legacy_ids": ",".join(
                        str(value) for value in row["candidate_legacy_ids"]
                    ),
                    "summary": row["summary"],
                    "site_legacy_id": legacy_context.get("site_legacy_id"),
                    "site_name": legacy_context.get("site_name"),
                    "certificate_number": legacy_context.get("certificate_number"),
                    "alt_case_ref": legacy_context.get("alt_case_ref"),
                    "decision_hint": row["decision_hint"],
                }
            )


def build_phase3h_analysis() -> dict[str, Any]:
    accepted_overrides = load_json(_phase3g_accepted_overrides_path())
    queue_bundle = build_phase3h_queue()
    queue_rows = queue_bundle["queue"]
    queue_lookup = build_queue_lookup(queue_rows)
    decision_template = build_decision_template(queue_rows)

    submitted_decisions = []
    validation_errors: list[str] = []
    if PHASE3H_DECISIONS_PATH.exists():
        submitted_decisions = load_json(PHASE3H_DECISIONS_PATH)
        for decision in submitted_decisions:
            validation_errors.extend(validate_decision(decision, queue_lookup))

    approved_overrides: dict[str, dict[str, dict[str, int]]] = {}
    merged_overrides = json.loads(json.dumps(accepted_overrides))
    decision_summary = build_decision_summary(submitted_decisions, queue_lookup)
    if submitted_decisions and not validation_errors:
        approved_overrides = build_approved_overrides(submitted_decisions, queue_lookup)
        merged_overrides = merge_overrides(accepted_overrides, approved_overrides)

    return {
        "accepted_override_count": sum(len(rows) for rows in accepted_overrides.values()),
        "queue_summary": {
            "actionable_count": queue_bundle["actionable_count"],
            "classification_counts": queue_bundle["classification_counts"],
            "sheet_counts": queue_bundle["sheet_counts"],
        },
        "queue": queue_rows,
        "decision_template": decision_template,
        "submitted_decision_count": len(submitted_decisions),
        "decision_summary": decision_summary,
        "validation_errors": validation_errors,
        "approved_overrides": approved_overrides,
        "merged_overrides": merged_overrides,
    }
