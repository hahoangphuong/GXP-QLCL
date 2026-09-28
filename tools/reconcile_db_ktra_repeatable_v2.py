"""Read-only reconciliation of Snapshot V2 repeatable db.ktra semantics."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date, time
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping
from urllib.parse import urlsplit

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

from backend.app.db.models.phase1 import (
    Case,
    InspectionDecision,
    InspectionMinutesRecord,
    InspectionOutcome,
    InspectionPlan,
    InspectionTeam,
    InspectionTeamMember,
    InspectorProfile,
    LegacyInspectorSourceRecord,
    Person,
)
from backend.app.domain.legacy_db_ktra_reconciliation import (
    safe_evidence,
    scalar_compatibility_projection,
    terminal_semicolon_decision_lineage_equivalent,
)
from backend.app.domain.legacy_db_ktra_repeatable_v2 import (
    excel_serial_minutes_representation_equivalent,
    parse_v2_repeatable_rows,
)
from backend.app.domain.legacy_snapshot_v2 import SCHEMA_VERSION, snapshot_bytes


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "artifacts" / "phase3c" / "legacy_snapshot_v2.json"
OUTPUT_DIR = ROOT / "artifacts" / "legacy_audit"
REHEARSAL_DATABASE = "gxp_legacy_rehearsal"
REQUIRED_REVISION = "20260914_0015"
CANONICAL_SNAPSHOT_SHA256 = "484cf37603aacc5ff01a7bde5ffab01ed444748d5c7b1a0b30e7fc3a04936caa"
RECONCILIATION_SCHEMA_VERSION = "b6b-repeatable-v2-reconciliation/v1"
TOPOLOGY_EVIDENCE_SCHEMA_VERSION = "b6b-repeatable-v2-topology/v1"


class ReconciliationFenceError(RuntimeError):
    """Raised when a B6B read-only provenance or target fence fails."""


def safe_error_summary(error: Exception) -> str:
    """Avoid echoing a caller-supplied database credential in CLI failures."""
    summary = str(error)
    summary = re.sub(r"(?i)(password|pwd)=([^\s&;]+)", r"\1=[REDACTED]", summary)
    return re.sub(r"(postgresql(?:\+[^:]+)?://)[^/@\s]+@", r"\1[REDACTED]@", summary)


def load_verified_snapshot_file(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    if sha256(raw).hexdigest() != CANONICAL_SNAPSHOT_SHA256:
        raise ReconciliationFenceError("B6B Snapshot V2 file SHA256 provenance guard failed")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ReconciliationFenceError("B6B Snapshot V2 payload is invalid")
    return payload


def exit_code_for_result(result: str) -> int:
    return 0 if result == "PASS" else 2 if result == "INCOMPLETE_EVIDENCE" else 3


def _legacy_id_set_sha256(legacy_ids: Iterable[int]) -> str:
    """Hash only sorted stable legacy IDs; no business payload enters topology evidence."""
    payload = json.dumps(sorted(legacy_ids), separators=(",", ":")).encode("utf-8")
    return sha256(payload).hexdigest()


def _clean_owner_integrity(canonical: Mapping[int, Mapping[str, Any]]) -> dict[str, Any]:
    """Represent a test-supplied one-owner mapping as clean physical topology."""
    case_ids = frozenset(canonical)
    plan_case_ids = frozenset(
        legacy_id for legacy_id, owner in canonical.items() if owner.get("inspection_plan_id") is not None
    )
    outcome_case_ids = frozenset(
        legacy_id for legacy_id, owner in canonical.items() if owner.get("inspection_outcome_id") is not None
    )
    return {
        "_canonical_case_ids": case_ids,
        "case_rows_with_legacy_id": len(case_ids),
        "distinct_case_legacy_ids": len(case_ids),
        "plan_rows_for_canonical_cases": len(plan_case_ids),
        "outcome_rows_for_canonical_cases": len(outcome_case_ids),
        "duplicate_case_legacy_ids": [],
        "duplicate_plan_case_ids": [],
        "duplicate_outcome_case_ids": [],
        "status": "PASS",
    }


def _public_owner_integrity(owner_integrity: Mapping[str, Any]) -> dict[str, Any]:
    """Keep internal comparison sets out of the committed reconciliation artifact."""
    return {key: value for key, value in owner_integrity.items() if not key.startswith("_")}


def topology_evidence_for_canonical(
    canonical: Mapping[int, Mapping[str, Any]], *, owner_integrity: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Build the read-only owner-topology facts that fence expected no-owner states."""
    integrity = owner_integrity or _clean_owner_integrity(canonical)
    case_ids = integrity["_canonical_case_ids"]
    plan_ids = integrity.get(
        "_plan_case_legacy_ids",
        {legacy_id for legacy_id, owner in canonical.items() if owner.get("inspection_plan_id") is not None},
    )
    outcome_ids = integrity.get(
        "_outcome_case_legacy_ids",
        {legacy_id for legacy_id, owner in canonical.items() if owner.get("inspection_outcome_id") is not None},
    )
    return {
        "schema_version": TOPOLOGY_EVIDENCE_SCHEMA_VERSION,
        "database": REHEARSAL_DATABASE,
        "alembic_revision": REQUIRED_REVISION,
        "case_count": integrity["case_rows_with_legacy_id"],
        "plan_count": integrity["plan_rows_for_canonical_cases"],
        "outcome_count": integrity["outcome_rows_for_canonical_cases"],
        "case_legacy_id_set_sha256": _legacy_id_set_sha256(case_ids),
        "plan_legacy_id_set_sha256": _legacy_id_set_sha256(plan_ids),
        "outcome_legacy_id_set_sha256": _legacy_id_set_sha256(outcome_ids),
    }


def verify_topology_evidence(
    expected: Mapping[str, Any], canonical: Mapping[int, Mapping[str, Any]], *, owner_integrity: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Require exact independently captured owner topology before semantic PASS."""
    actual = topology_evidence_for_canonical(canonical, owner_integrity=owner_integrity)
    required = tuple(actual)
    if not isinstance(expected, Mapping) or any(expected.get(key) != actual[key] for key in required):
        raise ReconciliationFenceError("B6B reconciliation owner topology evidence does not match canonical state")
    return actual


def load_verified_topology_file(path: Path, *, expected_sha256: str) -> dict[str, Any]:
    raw = path.read_bytes()
    if sha256(raw).hexdigest() != expected_sha256:
        raise ReconciliationFenceError("B6B topology evidence file SHA256 provenance guard failed")
    payload = json.loads(raw)
    if not isinstance(payload, dict) or payload.get("schema_version") != TOPOLOGY_EVIDENCE_SCHEMA_VERSION:
        raise ReconciliationFenceError("B6B topology evidence payload is invalid")
    return payload


def _iso(value: object) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else value if isinstance(value, str) else None


def _safe_occurrence(occurrence: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: _iso(value)
        for key, value in occurrence.items()
        if key != "legacy_raw"
    } | safe_evidence(occurrence.get("legacy_raw"))


def _canonical_relation(existing: Mapping[str, Any], decisions_by_id: Mapping[str, Mapping[str, Any]]) -> tuple[str | None, tuple[object, object, object] | None]:
    relation_type = existing.get("relation_type")
    related_id = existing.get("related_decision_id")
    if relation_type is None and related_id is None:
        return None, None
    target = decisions_by_id.get(related_id)
    return relation_type, None if target is None else (target.get("inspection_plan_id"), target.get("ordinal"), target.get("reference"))


def _source_records(snapshot: Mapping[str, Any], *, expected_snapshot_sha256: str) -> list[dict[str, Any]]:
    return parse_v2_repeatable_rows(snapshot, expected_snapshot_sha256=expected_snapshot_sha256)


def _empty_counts() -> dict[str, int]:
    return {key: 0 for key in ("EXACT_MATCH", "EXCEL_SERIAL_DATE_REPRESENTATION_EQUIVALENT", "MISSING_IN_DB", "EXTRA_IN_DB", "FIELD_MISMATCH", "OWNER_MISMATCH", "RELATION_MISMATCH", "SOURCE_MISSING", "SOURCE_RAW_ONLY", "SOURCE_UNRESOLVED", "CANONICAL_CASE_MISSING", "EXPECTED_NOT_WRITABLE_NO_PLAN", "CANONICAL_OUTCOME_MISSING", "UNEXPECTED_OWNER_MISSING")}


def _compare_structured(
    source_rows: Iterable[Mapping[str, Any]],
    canonical: Mapping[int, Mapping[str, Any]],
    existing: Iterable[Mapping[str, Any]],
    *,
    kind: str,
) -> dict[str, Any]:
    owner_key = "inspection_plan_id" if kind == "decisions" else "inspection_outcome_id"
    fields = ("reference", "decision_on", "legacy_raw") if kind == "decisions" else ("recorded_on", "recorded_time", "precision", "source_format", "legacy_raw")
    existing_rows = list(existing)
    existing_by_source_key: dict[tuple[int, int], list[Mapping[str, Any]]] = defaultdict(list)
    existing_by_id = {str(item["id"]): item for item in existing_rows}
    for item in existing_rows:
        legacy_id = item.get("legacy_inspection_id")
        ordinal = item.get("ordinal")
        if isinstance(legacy_id, int) and isinstance(ordinal, int):
            existing_by_source_key[(legacy_id, ordinal)].append(item)

    counts = Counter(_empty_counts())
    records: list[dict[str, Any]] = []
    consumed: set[str] = set()
    source_occurrences = 0
    expected_structured_count = 0
    expected_not_writable_count = 0
    for source in source_rows:
        parsed = source[kind]
        legacy_id = source["legacy_inspection_id"]
        owner = canonical.get(legacy_id)
        if parsed["state"] != "KNOWN":
            classification = "SOURCE_MISSING" if parsed["state"] == "MISSING" else "SOURCE_RAW_ONLY" if parsed["state"] == "RAW_ONLY" else "SOURCE_UNRESOLVED"
            counts[classification] += 1
            record = {
                "classification": classification,
                "legacy_inspection_id": legacy_id,
                "source_state": parsed["state"],
                **safe_evidence(parsed["raw"]),
            }
            if owner is not None and owner.get(owner_key) is None:
                # Keep unresolved evidence visibly incomplete while recording
                # that it is not a writable missing repeatable row.
                record["owner_availability"] = (
                    "NO_INSPECTION_PLAN" if kind == "decisions" else "NO_INSPECTION_OUTCOME"
                )
            records.append(record)
            continue
        for occurrence in parsed["occurrences"]:
            source_occurrences += 1
            record: dict[str, Any] = {"legacy_inspection_id": legacy_id, "source_ordinal": occurrence["ordinal"], "expected": _safe_occurrence(occurrence)}
            if owner is None:
                counts["CANONICAL_CASE_MISSING"] += 1
                records.append({"classification": "CANONICAL_CASE_MISSING", **record})
                continue
            if owner.get(owner_key) is None:
                classification = "EXPECTED_NOT_WRITABLE_NO_PLAN" if kind == "decisions" else "CANONICAL_OUTCOME_MISSING"
                counts[classification] += 1
                if classification == "EXPECTED_NOT_WRITABLE_NO_PLAN":
                    expected_not_writable_count += 1
                records.append({"classification": classification, "canonical_case_id": owner["case_id"], **record})
                continue
            expected_structured_count += 1
            key = (legacy_id, occurrence["ordinal"])
            candidates = existing_by_source_key.get(key, [])
            expected_owner = owner[owner_key]
            same_owner = [item for item in candidates if item.get(owner_key) == expected_owner]
            if not same_owner:
                classification = "OWNER_MISMATCH" if candidates else "MISSING_IN_DB"
                counts[classification] += 1
                records.append({"classification": classification, "canonical_case_id": owner["case_id"], owner_key: expected_owner, **record})
                continue
            if len(same_owner) != 1:
                counts["OWNER_MISMATCH"] += 1
                records.append({"classification": "OWNER_MISMATCH", "canonical_case_id": owner["case_id"], owner_key: expected_owner, "detail": "DUPLICATE_BUSINESS_KEY", **record})
                continue
            row = same_owner[0]
            consumed.add(str(row["id"]))
            differences = [field for field in fields if row.get(field) != occurrence.get(field)]
            relation_differences: list[str] = []
            if kind == "decisions":
                actual_type, actual_target = _canonical_relation(row, existing_by_id)
                target_occurrences = [item for item in parsed["occurrences"] if item["reference"] == occurrence.get("replaces_source_reference")]
                expected_target = None if occurrence.get("relation_type") is None else target_occurrences[0] if len(target_occurrences) == 1 else None
                if actual_type != occurrence.get("relation_type"):
                    relation_differences.append("relation_type")
                if expected_target is None and occurrence.get("relation_type") is not None:
                    relation_differences.append("expected_related_source_occurrence")
                elif expected_target is not None and actual_target != (expected_owner, expected_target["ordinal"], expected_target["reference"]):
                    relation_differences.append("related_decision_semantics")
            representation_equivalent = kind == "minutes" and excel_serial_minutes_representation_equivalent(
                source_representation=source["minutes_representation"],
                expected=occurrence,
                historical=row,
            )
            if relation_differences:
                counts["RELATION_MISMATCH"] += 1
                records.append({"classification": "RELATION_MISMATCH", "canonical_case_id": owner["case_id"], owner_key: expected_owner, "differing_fields": relation_differences, **record})
            elif representation_equivalent:
                counts["EXCEL_SERIAL_DATE_REPRESENTATION_EQUIVALENT"] += 1
                records.append({
                    "classification": "EXCEL_SERIAL_DATE_REPRESENTATION_EQUIVALENT",
                    "canonical_case_id": owner["case_id"],
                    owner_key: expected_owner,
                    "representation_equivalence": {
                        "source_representation": source["minutes_representation"],
                        "historical_representation": "ISO_OFFSET_DATETIME_AT_MIDNIGHT",
                        "legacy_raw_contract": "HISTORICAL_V1_SOURCE_LINEAGE_SEMANTICALLY_EQUIVALENT",
                    },
                    **record,
                })
            elif differences:
                counts["FIELD_MISMATCH"] += 1
                records.append({"classification": "FIELD_MISMATCH", "canonical_case_id": owner["case_id"], owner_key: expected_owner, "differing_fields": differences, **record})
            else:
                counts["EXACT_MATCH"] += 1
                records.append({"classification": "EXACT_MATCH", "canonical_case_id": owner["case_id"], owner_key: expected_owner, **record})
    for row in existing_rows:
        if str(row["id"]) in consumed:
            continue
        counts["EXTRA_IN_DB"] += 1
        records.append({"classification": "EXTRA_IN_DB", "legacy_inspection_id": row.get("legacy_inspection_id"), "source_ordinal": row.get("ordinal"), "canonical_case_id": row.get("case_id"), owner_key: row.get(owner_key), "existing": _safe_occurrence(row)})
    records.sort(key=lambda item: (item.get("legacy_inspection_id") is None, item.get("legacy_inspection_id") or 0, item.get("source_ordinal") or 0, item["classification"]))
    return {"source_occurrences": source_occurrences, "expected_structured_count": expected_structured_count, "expected_not_writable_count": expected_not_writable_count, "existing_structured_count": len(existing_rows), "classification_counts": {key: counts[key] for key in _empty_counts()}, "records": records}


def _projection_state(occurrences: list[Mapping[str, Any]], current: tuple[Any, ...], expected: tuple[Any, ...]) -> str:
    if not occurrences:
        return "SOURCE_UNRESOLVED"
    if len(occurrences) > 1:
        return "MULTIPLE_NULL_EXACT" if all(value is None for value in current) else "MULTIPLE_SCALAR_PRESENT"
    return "SINGLETON_EXACT" if current == expected else "SINGLETON_FIELD_MISMATCH"


def _compatibility_status(*counts: Mapping[str, int]) -> str:
    if any(
        count.get(key, 0)
        for count in counts
        for key in ("SINGLETON_FIELD_MISMATCH", "MULTIPLE_SCALAR_PRESENT", "SOURCE_MISSING_SCALAR_PRESENT")
    ):
        return "FAIL"
    if any(count.get(key, 0) for count in counts for key in ("SOURCE_RAW_ONLY", "SOURCE_UNRESOLVED")):
        return "INCOMPLETE_EVIDENCE"
    return "PASS"


def _reconciliation_outcome(
    decisions: Mapping[str, Any], minutes: Mapping[str, Any], compatibility: Mapping[str, Any]
) -> dict[str, Any]:
    """Separate actionable gaps from incomplete evidence and hard conflicts."""
    reports = (decisions, minutes)
    apply_required = [
        record
        for report in reports
        for record in report["records"]
        if record["classification"] == "MISSING_IN_DB"
    ]
    incomplete = [
        record
        for report in reports
        for record in report["records"]
        if record["classification"] in {"SOURCE_RAW_ONLY", "SOURCE_UNRESOLVED"}
    ]
    hard_classifications = {
        "EXTRA_IN_DB",
        "FIELD_MISMATCH",
        "OWNER_MISMATCH",
        "RELATION_MISMATCH",
        "CANONICAL_CASE_MISSING",
        "CANONICAL_OUTCOME_MISSING",
        "UNEXPECTED_OWNER_MISSING",
    }
    hard_conflicts = [
        record
        for report in reports
        for record in report["records"]
        if record["classification"] in hard_classifications
    ]
    if compatibility["status"] == "FAIL":
        hard_conflicts.append({"classification": "SCALAR_COMPATIBILITY_CONFLICT"})
    labels = []
    if apply_required:
        labels.append("DATA_APPLY_REQUIRED")
    if incomplete:
        labels.append("INCOMPLETE_EVIDENCE")
    if hard_conflicts:
        labels.append("HARD_SEMANTIC_CONFLICT")
    return {
        "status": "PASS_EXACT" if not labels else "_AND_".join(labels),
        "exact_or_representation_equivalent": {
            "decisions": sum(
                decisions["classification_counts"][key]
                for key in ("EXACT_MATCH", "EXCEL_SERIAL_DATE_REPRESENTATION_EQUIVALENT")
            ),
            "minutes": sum(
                minutes["classification_counts"][key]
                for key in ("EXACT_MATCH", "EXCEL_SERIAL_DATE_REPRESENTATION_EQUIVALENT")
            ),
        },
        "data_apply_required": {"count": len(apply_required), "records": apply_required},
        "incomplete_evidence": {"count": len(incomplete), "records": incomplete},
        "hard_semantic_conflicts": {"count": len(hard_conflicts), "records": hard_conflicts},
    }


def build_dry_run_apply_plan(report: Mapping[str, Any]) -> dict[str, Any]:
    """Produce non-writing actions only for reconciliation-proven missing rows.

    A later explicitly-authorized writer must re-derive source facts from the
    verified Snapshot V2 and run a fresh read-only reconciliation before use.
    This source-review plan serializes safe evidence only.
    """
    actions = []
    for kind, owner_key in (("decisions", "inspection_plan_id"), ("minutes", "inspection_outcome_id")):
        for record in report[kind]["records"]:
            if record["classification"] != "MISSING_IN_DB":
                continue
            actions.append(
                {
                    "kind": kind,
                    "classification": "DATA_APPLY_REQUIRED",
                    "legacy_inspection_id": record["legacy_inspection_id"],
                    "canonical_case_id": record["canonical_case_id"],
                    owner_key: record[owner_key],
                    "source_ordinal": record["source_ordinal"],
                    "expected": record["expected"],
                }
            )
    actions.sort(key=lambda item: (item["kind"], item["legacy_inspection_id"], item["source_ordinal"]))
    return {
        "schema_version": "b6b-repeatable-v2-dry-run-apply/v1",
        "write_authorized": False,
        "writer_invoked": False,
        "requires_fresh_read_only_reconciliation": True,
        "actions": actions,
    }


def _compatibility_projection(source_rows: Iterable[Mapping[str, Any]], canonical: Mapping[int, Mapping[str, Any]]) -> dict[str, Any]:
    decision_counts: Counter[str] = Counter()
    minute_counts: Counter[str] = Counter()
    for source in source_rows:
        owner = canonical.get(source["legacy_inspection_id"])
        if owner is None:
            continue
        decision_state = source["decisions"]["state"]
        decisions = source["decisions"]["occurrences"] if decision_state == "KNOWN" else []
        if owner.get("plan") is not None:
            current = (owner["plan"].get("decision_reference"), owner["plan"].get("decision_date"), owner["plan"].get("decision_legacy_raw"))
            if decision_state == "MISSING":
                decision_counts["SOURCE_MISSING_NULL_EXACT" if all(value is None for value in current) else "SOURCE_MISSING_SCALAR_PRESENT"] += 1
            elif decision_state != "KNOWN":
                decision_counts["SOURCE_RAW_ONLY" if decision_state == "RAW_ONLY" else "SOURCE_UNRESOLVED"] += 1
            else:
                projection = scalar_compatibility_projection(decisions)
                expected = (None, None, None) if projection is None else (projection["reference"], projection["decision_on"], projection["legacy_raw"])
                if projection is not None and terminal_semicolon_decision_lineage_equivalent(
                    expected=projection,
                    historical_reference=current[0],
                    historical_date=current[1],
                    historical_raw=current[2],
                ):
                    decision_counts["TERMINAL_SEPARATOR_REPRESENTATION_EQUIVALENT"] += 1
                else:
                    decision_counts[_projection_state(decisions, current, expected)] += 1
        minute_state = source["minutes"]["state"]
        minutes = source["minutes"]["occurrences"] if minute_state == "KNOWN" else []
        if owner.get("outcome") is not None:
            current = (owner["outcome"].get("minutes_recorded_on"), owner["outcome"].get("minutes_recorded_time"), owner["outcome"].get("minutes_legacy_raw"))
            if minute_state == "MISSING":
                minute_counts["SOURCE_MISSING_NULL_EXACT" if all(value is None for value in current) else "SOURCE_MISSING_SCALAR_PRESENT"] += 1
            elif minute_state != "KNOWN":
                minute_counts["SOURCE_RAW_ONLY" if minute_state == "RAW_ONLY" else "SOURCE_UNRESOLVED"] += 1
            else:
                projection = scalar_compatibility_projection(minutes)
                expected = (None, None, None) if projection is None else (projection["recorded_on"], projection["recorded_time"], projection["legacy_raw"])
                historical = {
                    "recorded_on": current[0],
                    "recorded_time": current[1],
                    "precision": "DATE_TIME_LOCAL" if current[1] is not None else None,
                    "source_format": "ISO_OFFSET_DATETIME" if current[1] is not None else None,
                    "legacy_raw": current[2],
                }
                if projection is not None and excel_serial_minutes_representation_equivalent(
                    source_representation=source["minutes_representation"],
                    expected=projection,
                    historical=historical,
                ):
                    minute_counts["EXCEL_SERIAL_DATE_REPRESENTATION_EQUIVALENT"] += 1
                else:
                    minute_counts[_projection_state(minutes, current, expected)] += 1
    decisions = dict(sorted(decision_counts.items()))
    minutes = dict(sorted(minute_counts.items()))
    return {"decisions": decisions, "minutes": minutes, "status": _compatibility_status(decisions, minutes)}


def _case_universe(
    source_rows: Iterable[Mapping[str, Any]],
    canonical: Mapping[int, Mapping[str, Any]],
    *,
    canonical_case_ids: Iterable[int] | None = None,
) -> dict[str, Any]:
    """Reconcile effective Snapshot V2 cases independently of repeatable field state."""
    source_case_ids = {row["legacy_inspection_id"] for row in source_rows}
    resolved_case_ids = set(canonical) if canonical_case_ids is None else set(canonical_case_ids)
    missing = sorted(source_case_ids - resolved_case_ids)
    extra = sorted(resolved_case_ids - source_case_ids)
    return {
        "source_case_count": len(source_case_ids),
        "canonical_case_count": len(resolved_case_ids),
        "source_case_legacy_id_set_sha256": _legacy_id_set_sha256(source_case_ids),
        "canonical_case_legacy_id_set_sha256": _legacy_id_set_sha256(resolved_case_ids),
        "missing_canonical_case_ids": missing,
        "extra_canonical_case_ids": extra,
        "case_universe_status": "PASS" if not missing and not extra else "FAIL",
    }


def build_reconciliation(
    snapshot: Mapping[str, Any],
    canonical: Mapping[int, Mapping[str, Any]],
    decisions: Iterable[Mapping[str, Any]],
    minutes: Iterable[Mapping[str, Any]],
    *,
    expected_snapshot_sha256: str = CANONICAL_SNAPSHOT_SHA256,
    topology_evidence: Mapping[str, Any],
    owner_integrity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Pure reconciliation owner used by the read-only CLI and focused tests."""
    integrity = owner_integrity or _clean_owner_integrity(canonical)
    actual_topology = verify_topology_evidence(topology_evidence, canonical, owner_integrity=integrity)
    source_rows = _source_records(snapshot, expected_snapshot_sha256=expected_snapshot_sha256)
    case_universe = _case_universe(source_rows, canonical, canonical_case_ids=integrity["_canonical_case_ids"])
    decisions_report = _compare_structured(source_rows, canonical, decisions, kind="decisions")
    minutes_report = _compare_structured(source_rows, canonical, minutes, kind="minutes")
    repeated_minutes = [
        {"legacy_inspection_id": source["legacy_inspection_id"], "ordinals": [item["ordinal"] for item in source["minutes"]["occurrences"]]}
        for source in source_rows
        if source["minutes"]["state"] == "KNOWN" and len(source["minutes"]["occurrences"]) > 1
    ]
    hard_failures = ("MISSING_IN_DB", "EXTRA_IN_DB", "FIELD_MISMATCH", "OWNER_MISMATCH", "RELATION_MISMATCH", "CANONICAL_CASE_MISSING", "CANONICAL_OUTCOME_MISSING", "UNEXPECTED_OWNER_MISSING")
    incomplete = ("SOURCE_RAW_ONLY", "SOURCE_UNRESOLVED")
    structured_result = (
        "FAIL"
        if any(report["classification_counts"][key] for report in (decisions_report, minutes_report) for key in hard_failures)
        else "INCOMPLETE_EVIDENCE"
        if any(report["classification_counts"][key] for report in (decisions_report, minutes_report) for key in incomplete)
        else "PASS"
    )
    compatibility = _compatibility_projection(source_rows, canonical)
    outcome = _reconciliation_outcome(decisions_report, minutes_report, compatibility)
    result = (
        "FAIL"
        if "FAIL" in {integrity["status"], case_universe["case_universe_status"], structured_result, compatibility["status"]}
        else "INCOMPLETE_EVIDENCE"
        if "INCOMPLETE_EVIDENCE" in {structured_result, compatibility["status"]}
        else "PASS"
    )
    return {
        "schema_version": RECONCILIATION_SCHEMA_VERSION,
        "source": {"eligible_cases": len(source_rows), "decision_source_occurrences": decisions_report["source_occurrences"], "minutes_source_occurrences": minutes_report["source_occurrences"]},
        "owners": {"cases_resolved": len(canonical), "plans_resolved": sum(item.get("inspection_plan_id") is not None for item in canonical.values()), "outcomes_resolved": sum(item.get("inspection_outcome_id") is not None for item in canonical.values()), "canonical_owner_gaps": case_universe["missing_canonical_case_ids"], "case_universe": case_universe, "owner_integrity": _public_owner_integrity(integrity), "topology": actual_topology},
        "decisions": decisions_report,
        "minutes": {**minutes_report, "repeated_occurrence_ids": repeated_minutes},
        "compatibility_projection": compatibility,
        "reconciliation_outcome": outcome,
        "dry_run_apply_plan": build_dry_run_apply_plan({"decisions": decisions_report, "minutes": minutes_report}),
        "audit_result": result,
    }


def validate_target_url(database_url: str) -> None:
    parsed = urlsplit(database_url)
    if not parsed.scheme.startswith("postgresql"):
        raise ReconciliationFenceError("B6B reconciliation requires PostgreSQL")
    if parsed.path.rsplit("/", 1)[-1] != REHEARSAL_DATABASE:
        raise ReconciliationFenceError("B6B reconciliation refuses database other than gxp_legacy_rehearsal")


def verify_read_only_target(connection: Any) -> None:
    if connection.execute(text("SELECT current_database()")).scalar_one() != REHEARSAL_DATABASE:
        raise ReconciliationFenceError("B6B reconciliation connected to an unexpected database")
    if str(connection.execute(text("SHOW transaction_read_only")).scalar_one()).strip().lower() not in {"on", "true", "1"}:
        raise ReconciliationFenceError("B6B reconciliation requires a read-only transaction")
    if connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() != REQUIRED_REVISION:
        raise ReconciliationFenceError("B6B reconciliation requires Alembic revision 20260914_0015")


def _canonical_owner_state(
    case_rows: Iterable[Mapping[str, Any]],
    plan_rows: Iterable[Mapping[str, Any]],
    outcome_rows: Iterable[Mapping[str, Any]],
) -> tuple[dict[int, dict[str, Any]], dict[str, Any]]:
    """Validate raw physical owner topology before building a one-owner map."""
    cases = [row for row in case_rows if row.get("legacy_inspection_id") is not None]
    plans = list(plan_rows)
    outcomes = list(outcome_rows)
    cases_by_legacy_id: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    cases_by_id: dict[Any, Mapping[str, Any]] = {}
    for case in cases:
        cases_by_legacy_id[case["legacy_inspection_id"]].append(case)
        cases_by_id[case["id"]] = case
    relevant_case_ids = set(cases_by_id)
    plans_by_case: dict[Any, list[Mapping[str, Any]]] = defaultdict(list)
    outcomes_by_case: dict[Any, list[Mapping[str, Any]]] = defaultdict(list)
    for plan in plans:
        if plan.get("case_id") in relevant_case_ids:
            plans_by_case[plan["case_id"]].append(plan)
    for outcome in outcomes:
        if outcome.get("case_id") in relevant_case_ids:
            outcomes_by_case[outcome["case_id"]].append(outcome)

    duplicate_case_legacy_ids = sorted(
        legacy_id for legacy_id, owner_rows in cases_by_legacy_id.items() if len(owner_rows) > 1
    )
    duplicate_plan_case_ids = sorted(
        str(case_id) for case_id, owner_rows in plans_by_case.items() if len(owner_rows) > 1
    )
    duplicate_outcome_case_ids = sorted(
        str(case_id) for case_id, owner_rows in outcomes_by_case.items() if len(owner_rows) > 1
    )
    integrity = {
        "_canonical_case_ids": frozenset(cases_by_legacy_id),
        "_plan_case_legacy_ids": frozenset(
            cases_by_id[case_id]["legacy_inspection_id"] for case_id in plans_by_case
        ),
        "_outcome_case_legacy_ids": frozenset(
            cases_by_id[case_id]["legacy_inspection_id"] for case_id in outcomes_by_case
        ),
        "case_rows_with_legacy_id": len(cases),
        "distinct_case_legacy_ids": len(cases_by_legacy_id),
        "plan_rows_for_canonical_cases": sum(len(rows) for rows in plans_by_case.values()),
        "outcome_rows_for_canonical_cases": sum(len(rows) for rows in outcomes_by_case.values()),
        "duplicate_case_legacy_ids": duplicate_case_legacy_ids,
        "duplicate_plan_case_ids": duplicate_plan_case_ids,
        "duplicate_outcome_case_ids": duplicate_outcome_case_ids,
        "status": "FAIL" if any((duplicate_case_legacy_ids, duplicate_plan_case_ids, duplicate_outcome_case_ids)) else "PASS",
    }
    canonical: dict[int, dict[str, Any]] = {}
    for legacy_id, owner_rows in cases_by_legacy_id.items():
        if len(owner_rows) != 1:
            continue
        case = owner_rows[0]
        owner: dict[str, Any] = {"case_id": case["id"]}
        case_plans = plans_by_case.get(case["id"], [])
        case_outcomes = outcomes_by_case.get(case["id"], [])
        if len(case_plans) == 1:
            plan = case_plans[0]
            owner.update({"inspection_plan_id": plan["id"], "plan": {"decision_reference": plan.get("decision_reference"), "decision_date": plan.get("decision_date"), "decision_legacy_raw": plan.get("decision_legacy_raw")}})
        if len(case_outcomes) == 1:
            outcome = case_outcomes[0]
            owner.update({"inspection_outcome_id": outcome["id"], "outcome": {"minutes_recorded_on": outcome.get("minutes_recorded_on"), "minutes_recorded_time": outcome.get("minutes_recorded_time"), "minutes_legacy_raw": outcome.get("minutes_legacy_raw")}})
        canonical[legacy_id] = owner
    return canonical, integrity


def _read_canonical(session: Session) -> tuple[dict[int, dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    case_items = list(session.scalars(select(Case).where(Case.legacy_inspection_id.is_not(None))))
    plan_items = list(session.scalars(select(InspectionPlan)))
    outcome_items = list(session.scalars(select(InspectionOutcome)))
    canonical, owner_integrity = _canonical_owner_state(
        ({"id": item.id, "legacy_inspection_id": item.legacy_inspection_id} for item in case_items),
        ({"id": item.id, "case_id": item.case_id, "decision_reference": item.decision_reference, "decision_date": item.decision_date, "decision_legacy_raw": item.decision_legacy_raw} for item in plan_items),
        ({"id": item.id, "case_id": item.case_id, "minutes_recorded_on": item.minutes_recorded_on, "minutes_recorded_time": item.minutes_recorded_time, "minutes_legacy_raw": item.minutes_legacy_raw} for item in outcome_items),
    )
    cases = {item.id: item for item in case_items}
    plans_by_id = {item.id: item for item in plan_items}
    outcomes_by_id = {item.id: item for item in outcome_items}
    decisions = []
    for item in session.scalars(select(InspectionDecision)):
        plan = plans_by_id.get(item.inspection_plan_id)
        case = None if plan is None else cases.get(plan.case_id)
        decisions.append({"id": item.id, "legacy_inspection_id": None if case is None else case.legacy_inspection_id, "case_id": None if plan is None else plan.case_id, "inspection_plan_id": item.inspection_plan_id, "ordinal": item.ordinal, "reference": item.reference, "decision_on": item.decision_on, "legacy_raw": item.legacy_raw, "relation_type": item.relation_type, "related_decision_id": item.related_decision_id})
    minutes = []
    for item in session.scalars(select(InspectionMinutesRecord)):
        outcome = outcomes_by_id.get(item.inspection_outcome_id)
        case = None if outcome is None else cases.get(outcome.case_id)
        minutes.append({"id": item.id, "legacy_inspection_id": None if case is None else case.legacy_inspection_id, "case_id": None if outcome is None else outcome.case_id, "inspection_outcome_id": item.inspection_outcome_id, "ordinal": item.ordinal, "recorded_on": item.recorded_on, "recorded_time": item.recorded_time, "precision": item.precision, "source_format": item.source_format, "legacy_raw": item.legacy_raw})
    return canonical, decisions, minutes, owner_integrity


def _table_fingerprint(session: Session) -> dict[str, dict[str, Any]]:
    models = {"case": Case, "inspection_plan": InspectionPlan, "inspection_outcome": InspectionOutcome, "inspection_decision": InspectionDecision, "inspection_minutes_record": InspectionMinutesRecord, "inspection_team": InspectionTeam, "inspection_team_member": InspectionTeamMember, "person": Person, "inspector_profile": InspectorProfile, "legacy_inspector_source_record": LegacyInspectorSourceRecord}
    return {name: {"count": int(session.scalar(select(func.count()).select_from(model)) or 0), "max_updated_at": _iso(session.scalar(select(func.max(model.updated_at))))} for name, model in models.items()}


def run(database_url: str, snapshot: Mapping[str, Any], *, topology_evidence: Mapping[str, Any]) -> dict[str, Any]:
    validate_target_url(database_url)
    engine = create_engine(database_url, future=True)
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                connection.execute(text("SET TRANSACTION READ ONLY"))
                verify_read_only_target(connection)
                session = Session(bind=connection)
                before = _table_fingerprint(session)
                canonical, decisions, minutes, owner_integrity = _read_canonical(session)
                report = build_reconciliation(
                    snapshot,
                    canonical,
                    decisions,
                    minutes,
                    topology_evidence=topology_evidence,
                    owner_integrity=owner_integrity,
                )
                after = _table_fingerprint(session)
                if before != after:
                    raise ReconciliationFenceError("B6B reconciliation observed unexpected database mutation")
                return {"provenance": {"baseline_git_commit": "ee679d10bc2f36cce9c554e8a1d03f7c609a36f1", "snapshot_v2_path": "artifacts/phase3c/legacy_snapshot_v2.json", "snapshot_v2_sha256": CANONICAL_SNAPSHOT_SHA256, "snapshot_v2_schema_version": SCHEMA_VERSION, "database": REHEARSAL_DATABASE, "alembic_revision": REQUIRED_REVISION, "transaction_read_only": True}, **report, "read_only_mutation_proof": {"before": before, "after": after, "database_mutated": False}, "importer_invoked": False}
            finally:
                transaction.rollback()
    finally:
        engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only B6B Snapshot V2 repeatable reconciliation.")
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--snapshot", type=Path, default=SNAPSHOT)
    parser.add_argument("--topology-evidence", type=Path, required=True)
    parser.add_argument("--expected-topology-sha256", required=True)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args(argv)
    payload = load_verified_snapshot_file(args.snapshot.resolve())
    topology = load_verified_topology_file(
        args.topology_evidence.resolve(), expected_sha256=args.expected_topology_sha256
    )
    try:
        report = run(args.database_url, payload, topology_evidence=topology)
    except Exception as exc:
        raise SystemExit(f"B6B reconciliation failed: {safe_error_summary(exc)}") from None
    result = report["audit_result"]
    summary = {"schema_version": "b6b-repeatable-v2-summary/v1", "provenance": {**report["provenance"], "snapshot_v2_file_sha256": CANONICAL_SNAPSHOT_SHA256, "snapshot_v2_semantic_verification": "PASSED", "topology_evidence_file_sha256": args.expected_topology_sha256}, "source": report["source"], "owners": report["owners"], "decisions": {key: report["decisions"][key] for key in ("source_occurrences", "expected_structured_count", "expected_not_writable_count", "existing_structured_count", "classification_counts")}, "minutes": {key: report["minutes"][key] for key in ("source_occurrences", "expected_structured_count", "expected_not_writable_count", "existing_structured_count", "classification_counts", "repeated_occurrence_ids")}, "compatibility_projection": report["compatibility_projection"], "audit_result": result, "database_mutated": False, "importer_invoked": False}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, artifact in (("b6b_repeatable_v2_reconciliation.json", report), ("b6b_repeatable_v2_summary.json", summary)):
        (args.output_dir / name).write_bytes((json.dumps(artifact, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8"))
    return exit_code_for_result(result)


if __name__ == "__main__":
    raise SystemExit(main())
