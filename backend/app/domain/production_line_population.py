"""Read-only B6H production-line discovery and future-linkage planning.

Legacy ``MÃ DC`` values are compatibility text, not physical-line identities.
This module records deterministic evidence without creating a ProductionLine,
linking a Case/Certificate, or inferring transformation history.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from hashlib import sha256
import json
import re
from typing import Any, Mapping
import unicodedata
from uuid import UUID

from backend.app.domain.legacy_db_ktra_source_v2 import (
    snapshot_cell_value,
    snapshot_columns,
    substantive_source_value,
)
from backend.app.domain.legacy_snapshot_v2 import snapshot_legacy_int
from backend.app.domain.legacy_snapshot_v2 import SCHEMA_VERSION
from backend.app.domain.phase2_import import normalize_inspection_gxp_type


PLANNER_VERSION = "b6h-production-line-population/v2"
CANONICAL_SNAPSHOT_SHA256 = "484cf37603aacc5ff01a7bde5ffab01ed444748d5c7b1a0b30e7fc3a04936caa"
CANONICAL_STATE_SCHEMA_VERSION = "production-line-canonical-state/v1"
# One B6H source-of-truth for verified PostgreSQL revisions.  An unknown or
# intermediate revision must never inherit compatibility by numeric ordering.
SUPPORTED_ALEMBIC_REVISIONS = frozenset({"20260929_0017", "20261008_0022"})
ROSTER_SCHEMA_VERSION = "production-line-physical-identity-roster/v2"
LEGACY_ROSTER_SCHEMA_VERSION = "production-line-physical-identity-roster/v1"
SUPPORTED_ROSTER_ACTIONS = frozenset({
    "APPROVE_NEW_PHYSICAL_LINE",
    "MAP_TO_EXISTING_PRODUCTION_LINE",
    "REJECT_NOT_PHYSICAL_LINE",
    "DEFER_INSUFFICIENT_EVIDENCE",
    "SPLIT_REQUIRED",
    "CONFLICT",
})
_SENTINELS = {"", "-", "???"}
_CASE_HEADERS = ("ID", "ID CƠ SỞ", "LOẠI KT", "MÃ DC")
_CERTIFICATE_HEADERS = ("ID", "ID ĐỢT KTRA", "ID CƠ SỞ", "LOẠI CC", "MÃ DC")


class ProductionLinePlanningError(ValueError):
    """Raised when authoritative B6H source evidence is structurally unsafe."""


def canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    """Stable bytes for content-addressed, non-secret planning inputs."""
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _sha256(value: Mapping[str, Any]) -> str:
    return sha256(canonical_json_bytes(value)).hexdigest()


def _canonical_uuid(value: object, *, label: str, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ProductionLinePlanningError(f"B6H {label} must be a UUID")
    try:
        return str(UUID(value))
    except (ValueError, AttributeError) as exc:
        raise ProductionLinePlanningError(f"B6H {label} must be a valid UUID") from exc


def _validate_canonical_state(canonical_state: Mapping[str, Any] | None, *, supplied_sha256: str | None) -> tuple[Mapping[str, Any] | None, str | None]:
    if canonical_state is None:
        if supplied_sha256 is not None:
            raise ProductionLinePlanningError("B6H canonical-state SHA256 was supplied without canonical state")
        return None, None
    if canonical_state.get("schema_version") != CANONICAL_STATE_SCHEMA_VERSION:
        raise ProductionLinePlanningError("B6H canonical state has missing or unsupported schema_version")
    if canonical_state.get("source_alembic_revision") not in SUPPORTED_ALEMBIC_REVISIONS:
        raise ProductionLinePlanningError("B6H canonical state has stale or unknown Alembic revision")
    if not isinstance(canonical_state.get("source_database_identity"), Mapping):
        raise ProductionLinePlanningError("B6H canonical state has no source database identity")
    if not isinstance(canonical_state.get("source_state_fingerprint"), str) or not canonical_state["source_state_fingerprint"]:
        raise ProductionLinePlanningError("B6H canonical state has no source-state fingerprint")
    for name in ("sites", "existing_production_lines", "cases", "certificates", "physical_line_evidence", "transformations"):
        if not isinstance(canonical_state.get(name), list):
            raise ProductionLinePlanningError(f"B6H canonical state has invalid {name}")
    state_without_fingerprint = dict(canonical_state)
    declared_fingerprint = state_without_fingerprint.pop("source_state_fingerprint")
    if declared_fingerprint != _sha256(state_without_fingerprint):
        raise ProductionLinePlanningError("B6H canonical state source-state fingerprint does not match content")
    computed = _sha256(canonical_state)
    if supplied_sha256 is not None and supplied_sha256 != computed:
        raise ProductionLinePlanningError("B6H canonical-state SHA256 does not match semantic content")
    if not re.fullmatch(r"[0-9a-f]{64}", computed):
        raise ProductionLinePlanningError("B6H canonical-state SHA256 is invalid")
    return canonical_state, computed


def _canonical_state_index(canonical_state: Mapping[str, Any] | None) -> dict[str, Any]:
    """Validate read-only exported state before it can influence writability."""
    result = {"sites": {}, "lines": {}, "cases": {}, "certificates": {}}
    if canonical_state is None:
        return result
    for site in canonical_state["sites"]:
        if not isinstance(site, Mapping) or not isinstance(site.get("legacy_site_id"), int):
            raise ProductionLinePlanningError("B6H canonical site state is invalid")
        if site["legacy_site_id"] in result["sites"]:
            raise ProductionLinePlanningError("B6H canonical state has duplicate Site mappings")
        result["sites"][site["legacy_site_id"]] = {**site, "id": _canonical_uuid(site.get("id"), label="Site ID")}
    for line in canonical_state["existing_production_lines"]:
        if not isinstance(line, Mapping):
            raise ProductionLinePlanningError("B6H canonical state has malformed ProductionLine IDs")
        normalized = {**line, "id": _canonical_uuid(line.get("id"), label="ProductionLine ID"), "site_id": _canonical_uuid(line.get("site_id"), label="ProductionLine Site ID")}
        if normalized["id"] in result["lines"]:
            raise ProductionLinePlanningError("B6H canonical state has duplicate ProductionLine IDs")
        result["lines"][normalized["id"]] = normalized
    for kind, field in (("cases", "legacy_inspection_id"), ("certificates", "legacy_certificate_id")):
        for item in canonical_state[kind]:
            if not isinstance(item, Mapping) or not isinstance(item.get(field), int):
                raise ProductionLinePlanningError(f"B6H canonical state has malformed {kind}")
            if item[field] in result[kind]:
                raise ProductionLinePlanningError(f"B6H canonical state has duplicate {kind} legacy identity")
            result[kind][item[field]] = {
                **item,
                "id": _canonical_uuid(item.get("id"), label=f"{kind} ID"),
                "site_id": _canonical_uuid(item.get("site_id"), label=f"{kind} Site ID"),
                "production_line_id": _canonical_uuid(item.get("production_line_id"), label=f"{kind} ProductionLine ID", nullable=True),
            }
    seen_transformations: set[str] = set()
    for item in canonical_state["transformations"]:
        if not isinstance(item, Mapping):
            raise ProductionLinePlanningError("B6H canonical state has malformed transformations")
        transformation_id = _canonical_uuid(item.get("id"), label="ProductionLine transformation ID")
        _canonical_uuid(item.get("site_id"), label="ProductionLine transformation Site ID")
        if transformation_id in seen_transformations:
            raise ProductionLinePlanningError("B6H canonical state has duplicate ProductionLine transformation IDs")
        seen_transformations.add(transformation_id)
    return result


def _validate_roster(
    roster: Mapping[str, Any] | None,
    *,
    snapshot_sha256: str,
    canonical_state_sha256: str | None,
    supplied_sha256: str | None,
) -> tuple[dict[str, Mapping[str, Any]], str | None]:
    if roster is None:
        if supplied_sha256 is not None:
            raise ProductionLinePlanningError("B6H roster SHA256 was supplied without roster")
        return {}, None
    if roster.get("schema_version") not in {ROSTER_SCHEMA_VERSION, LEGACY_ROSTER_SCHEMA_VERSION}:
        raise ProductionLinePlanningError("B6H roster has missing or unsupported schema_version")
    if roster.get("planner_version") != PLANNER_VERSION or roster.get("legacy_snapshot_sha256") != snapshot_sha256:
        raise ProductionLinePlanningError("B6H roster has stale snapshot or planner provenance")
    if roster.get("canonical_state_sha256") != canonical_state_sha256:
        raise ProductionLinePlanningError("B6H roster canonical-state provenance does not match")
    items = roster.get("items")
    if not isinstance(items, list):
        raise ProductionLinePlanningError("B6H roster items are invalid")
    result: dict[str, Mapping[str, Any]] = {}
    for item in items:
        if not isinstance(item, Mapping) or not isinstance(item.get("candidate_key"), str):
            raise ProductionLinePlanningError("B6H roster item is invalid")
        if item["candidate_key"] in result:
            raise ProductionLinePlanningError("B6H roster has duplicate candidate decisions")
        action = item.get("physical_identity_action")
        if action not in SUPPORTED_ROSTER_ACTIONS:
            raise ProductionLinePlanningError("B6H roster has unsupported decision")
        if action != "DEFER_INSUFFICIENT_EVIDENCE" and not str(item.get("review_reason") or "").strip():
            raise ProductionLinePlanningError("B6H non-pending roster decision requires review reason")
        if action == "APPROVE_NEW_PHYSICAL_LINE" and not str(item.get("approved_display_code") or "").strip():
            raise ProductionLinePlanningError("B6H approved new physical line requires approved display code")
        result[item["candidate_key"]] = item
    computed = _sha256(roster)
    if supplied_sha256 is not None and supplied_sha256 != computed:
        raise ProductionLinePlanningError("B6H roster SHA256 does not match semantic content")
    if not re.fullmatch(r"[0-9a-f]{64}", computed):
        raise ProductionLinePlanningError("B6H roster SHA256 is invalid")
    return result, computed


def canonicalize_line_text(value: object) -> dict[str, object]:
    """Normalize presentation only; never merge distinct line semantics."""
    if value is None:
        return {"state": "MISSING", "canonical_text": None, "operations": []}
    if not isinstance(value, str):
        return {"state": "UNSUPPORTED_NON_TEXT", "canonical_text": None, "operations": []}
    normalized = unicodedata.normalize("NFKC", value)
    stripped = normalized.strip()
    if not stripped:
        return {"state": "WHITESPACE_ONLY", "canonical_text": None, "operations": []}
    if stripped in _SENTINELS:
        return {"state": "SENTINEL", "canonical_text": None, "operations": []}
    collapsed = " ".join(stripped.split())
    canonical = collapsed.upper()
    operations: list[str] = []
    if normalized != value:
        operations.append("UNICODE_NFKC")
    if stripped != normalized:
        operations.append("TRIM")
    if collapsed != stripped:
        operations.append("COLLAPSE_WHITESPACE")
    if canonical != collapsed:
        operations.append("UPPERCASE")
    return {
        "state": "CANONICAL",
        "source_text": value,
        "canonical_text": canonical,
        "operations": operations,
    }


def _parse_legacy_int(value: object) -> int | None:
    return snapshot_legacy_int(value)


def _normalized_gxp(value: object) -> str | None:
    if not substantive_source_value(value):
        return None
    return normalize_inspection_gxp_type(str(value))


def _source_ref(*, sheet: str, row_number: int, column: int, field: str) -> dict[str, object]:
    return {
        "source_sheet": sheet,
        "source_row_number": row_number,
        "source_column_ordinal": column,
        "source_field": field,
    }


def _validated_rows(snapshot: Mapping[str, Any], *, sheet: str, headers: tuple[str, ...]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    if snapshot.get("schema_version") != SCHEMA_VERSION:
        raise ProductionLinePlanningError("B6H requires a legacy Snapshot V2 payload")
    rows, columns = snapshot_columns(snapshot, sheet, required_headers=headers)
    missing = [header for header in headers if header not in columns]
    if missing:
        raise ProductionLinePlanningError(f"B6H source is missing required {sheet} headers: {', '.join(missing)}")
    return rows, columns


def _candidate_key(site_legacy_id: int, canonical_text: str) -> str:
    payload = json.dumps([site_legacy_id, canonical_text], ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return f"legacy-line:{sha256(payload).hexdigest()[:24]}"


def source_line_evidence(snapshot: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return immutable legacy line evidence for read-only review consumers."""
    cases: list[dict[str, Any]] = []
    certificates: list[dict[str, Any]] = []
    rows, columns = _validated_rows(snapshot, sheet="db.ktra", headers=_CASE_HEADERS)
    seen_cases: set[int] = set()
    seen_case_rows: set[int] = set()
    for row in rows:
        row_number = row.get("source_row_number")
        if not isinstance(row_number, int) or row_number <= 4:
            continue
        if row_number in seen_case_rows:
            raise ProductionLinePlanningError("B6H db.ktra has duplicate source row coordinates")
        seen_case_rows.add(row_number)
        legacy_id = _parse_legacy_int(snapshot_cell_value(row, columns["ID"]))
        if legacy_id is None:
            continue
        if legacy_id in seen_cases:
            raise ProductionLinePlanningError("B6H db.ktra has duplicate valid legacy inspection IDs")
        seen_cases.add(legacy_id)
        site_legacy_id = _parse_legacy_int(snapshot_cell_value(row, columns["ID CƠ SỞ"]))
        gxp_type = _normalized_gxp(snapshot_cell_value(row, columns["LOẠI KT"]))
        line = canonicalize_line_text(snapshot_cell_value(row, columns["MÃ DC"]))
        cases.append({
            "legacy_inspection_id": legacy_id,
            "source_site_legacy_id": site_legacy_id,
            "gxp_type": gxp_type,
            "scope_code": snapshot_cell_value(row, columns["Mã hồ sơ"]) if "Mã hồ sơ" in columns else None,
            "line": line,
            "eligible_case_source": site_legacy_id is not None and gxp_type is not None,
            "source_ref": _source_ref(
                sheet="db.ktra", row_number=row_number, column=columns["MÃ DC"], field="MÃ DC"
            ),
        })
    rows, columns = _validated_rows(snapshot, sheet="db.cc", headers=_CERTIFICATE_HEADERS)
    seen_certificates: set[int] = set()
    seen_certificate_rows: set[int] = set()
    for row in rows:
        row_number = row.get("source_row_number")
        if not isinstance(row_number, int) or row_number <= 4:
            continue
        if row_number in seen_certificate_rows:
            raise ProductionLinePlanningError("B6H db.cc has duplicate source row coordinates")
        seen_certificate_rows.add(row_number)
        legacy_id = _parse_legacy_int(snapshot_cell_value(row, columns["ID"]))
        if legacy_id is None:
            continue
        if legacy_id in seen_certificates:
            raise ProductionLinePlanningError("B6H db.cc has duplicate valid legacy certificate IDs")
        seen_certificates.add(legacy_id)
        certificates.append({
            "legacy_certificate_id": legacy_id,
            "source_inspection_legacy_id": _parse_legacy_int(snapshot_cell_value(row, columns["ID ĐỢT KTRA"])),
            "source_site_legacy_id": _parse_legacy_int(snapshot_cell_value(row, columns["ID CƠ SỞ"])),
            "gxp_type": _normalized_gxp(snapshot_cell_value(row, columns["LOẠI CC"])),
            "certificate_reference": snapshot_cell_value(row, columns["Mã số CC"]) if "Mã số CC" in columns else None,
            "line": canonicalize_line_text(snapshot_cell_value(row, columns["MÃ DC"])),
            "source_ref": _source_ref(
                sheet="db.cc", row_number=row_number, column=columns["MÃ DC"], field="MÃ DC"
            ),
        })
    return sorted(cases, key=lambda item: item["legacy_inspection_id"]), sorted(
        certificates, key=lambda item: item["legacy_certificate_id"]
    )


def _source_evidence(snapshot: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Backward-compatible private alias for the public evidence owner."""
    return source_line_evidence(snapshot)


def _canonical_site_map(canonical_index: Mapping[str, Any]) -> dict[int, str]:
    return {legacy_id: item["id"] for legacy_id, item in canonical_index["sites"].items()}


def _explicit_line_evidence(
    canonical_state: Mapping[str, Any] | None,
    *,
    roster_by_candidate: Mapping[str, Mapping[str, Any]],
    candidates_by_key: Mapping[str, Mapping[str, Any]] | None = None,
    canonical_index: Mapping[str, Any],
) -> dict[tuple[int, str], str | None]:
    """Accept only reviewed physical-line evidence; text alone never creates identity."""
    result: dict[tuple[int, str], str | None] = {}
    if canonical_state is None:
        return result
    for item in canonical_state.get("physical_line_evidence", []):
        if not isinstance(item, Mapping) or item.get("evidence_kind") != "EXPLICIT_PHYSICAL_LINE_IDENTITY":
            raise ProductionLinePlanningError("B6H physical line evidence is invalid or not explicit")
        site = item.get("legacy_site_id")
        normalized = canonicalize_line_text(item.get("line_text"))
        if not isinstance(site, int) or normalized["state"] != "CANONICAL":
            raise ProductionLinePlanningError("B6H physical line evidence has invalid site or line text")
        key = (site, str(normalized["canonical_text"]))
        if key in result:
            raise ProductionLinePlanningError("B6H physical line evidence is duplicate or ambiguous")
        line_id = _canonical_uuid(item.get("production_line_id"), label="physical evidence ProductionLine ID", nullable=True)
        result[key] = line_id
    # A roster approval is an explicit identity decision only after its candidate
    # is proven unchanged and any mapped existing line is site-compatible.
    if candidates_by_key is not None:
        for candidate_key, decision in roster_by_candidate.items():
            candidate = candidates_by_key.get(candidate_key)
            if candidate is None:
                raise ProductionLinePlanningError("B6H roster references an unknown candidate_key")
            for field in ("source_site_legacy_id", "canonical_site_id", "canonical_line_text"):
                if decision.get(field) != candidate.get(field):
                    raise ProductionLinePlanningError("B6H roster candidate was altered after discovery")
            action = decision["physical_identity_action"]
            if action not in {"APPROVE_NEW_PHYSICAL_LINE", "MAP_TO_EXISTING_PRODUCTION_LINE"}:
                continue
            key = (candidate["source_site_legacy_id"], candidate["canonical_line_text"])
            if key in result:
                raise ProductionLinePlanningError("B6H roster conflicts with existing explicit physical identity")
            line_id = decision.get("production_line_id")
            if action == "APPROVE_NEW_PHYSICAL_LINE":
                if line_id is not None:
                    raise ProductionLinePlanningError("B6H CREATE_NEW roster decision must not supply a ProductionLine ID")
                result[key] = None
            else:
                line_id = _canonical_uuid(line_id, label="roster ProductionLine ID")
                line = canonical_index["lines"].get(line_id)
                if line is None:
                    raise ProductionLinePlanningError("B6H MAP_EXISTING roster decision references unknown ProductionLine")
                if line["site_id"] != candidate["canonical_site_id"]:
                    raise ProductionLinePlanningError("B6H MAP_EXISTING roster decision crosses Site boundary")
                result[key] = str(line_id)
    return result


def _discovery(
    cases: list[dict[str, Any]],
    certificates: list[dict[str, Any]],
    *,
    snapshot_sha256: str,
    canonical_state: Mapping[str, Any] | None,
    canonical_index: Mapping[str, Any],
    roster_by_candidate: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    grouped: dict[tuple[int, str], dict[str, Any]] = {}
    site_map = _canonical_site_map(canonical_index)
    physical_evidence = _explicit_line_evidence(
        canonical_state,
        roster_by_candidate={},
        canonical_index=canonical_index,
    )
    for kind, records, id_key in (("CASE", cases, "legacy_inspection_id"), ("CERTIFICATE", certificates, "legacy_certificate_id")):
        for record in records:
            line = record["line"]
            site = record["source_site_legacy_id"]
            if line["state"] != "CANONICAL" or not isinstance(site, int):
                continue
            key = (site, str(line["canonical_text"]))
            item = grouped.setdefault(key, {
                "candidate_key": _candidate_key(*key),
                "source_site_legacy_id": site,
                "canonical_site_id": site_map.get(site),
                "canonical_site_resolution": "RESOLVED" if site in site_map else "NOT_RESOLVED_OFFLINE",
                "canonical_line_text": key[1],
                "observed_line_texts": set(),
                "source_case_ids": [],
                "source_certificate_ids": [],
                "legacy_source_refs": [],
                "gxp_contexts": set(),
            })
            item["observed_line_texts"].add(str(line["source_text"]))
            item["legacy_source_refs"].append(record["source_ref"])
            if record["gxp_type"] is not None:
                item["gxp_contexts"].add(record["gxp_type"])
            item["source_case_ids" if kind == "CASE" else "source_certificate_ids"].append(record[id_key])
    candidates: list[dict[str, Any]] = []
    for key, item in sorted(grouped.items()):
        case_count, certificate_count = len(item["source_case_ids"]), len(item["source_certificate_ids"])
        explicit_line_id = physical_evidence.get(key)
        evidence_classes = ["LEGACY_ONLY_SIGNAL"]
        if case_count and certificate_count:
            evidence_classes.append("CASE_CERTIFICATE_AGREEMENT")
        elif case_count:
            evidence_classes.append("CASE_ONLY_LINE_TEXT")
        else:
            evidence_classes.append("CERTIFICATE_ONLY_LINE_TEXT")
        if len(item["gxp_contexts"]) > 1:
            evidence_classes.append("GXP_CONTEXT_CONFLICT")
        if key in physical_evidence and item["canonical_site_id"] is not None:
            classification, confidence, writable = "CREATE_SAFE", "EXACT_EXPLICIT", True
            block_reason = None
        elif key in physical_evidence:
            classification, confidence, writable = "BLOCKED_SITE_CONFLICT", "BLOCKED", False
            block_reason = "CANONICAL_SITE_NOT_RESOLVED"
        else:
            classification, confidence, writable = "BLOCKED_INSUFFICIENT_EVIDENCE", "BLOCKED", False
            block_reason = "NO_EXPLICIT_PHYSICAL_LINE_IDENTITY_EVIDENCE"
        candidates.append({
            **item,
            "observed_line_texts": sorted(item["observed_line_texts"]),
            "source_case_ids": sorted(item["source_case_ids"]),
            "source_certificate_ids": sorted(item["source_certificate_ids"]),
            "legacy_source_refs": sorted(item["legacy_source_refs"], key=lambda ref: (ref["source_sheet"], ref["source_row_number"])),
            "gxp_contexts": sorted(item["gxp_contexts"]),
            "classification": classification,
            "evidence_classes": evidence_classes,
            "confidence_class": confidence,
            "writable": writable,
            "block_reason": block_reason,
            "planned_production_line_id": explicit_line_id,
        })
    candidate_by_key = {candidate["candidate_key"]: candidate for candidate in candidates}
    roster_evidence = _explicit_line_evidence(
        canonical_state,
        roster_by_candidate=roster_by_candidate,
        candidates_by_key=candidate_by_key,
        canonical_index=canonical_index,
    )
    for candidate in candidates:
        key = (candidate["source_site_legacy_id"], candidate["canonical_line_text"])
        if key not in roster_evidence or candidate["writable"]:
            continue
        if candidate["canonical_site_id"] is None:
            continue
        candidate.update({
            "classification": "CREATE_SAFE",
            "confidence_class": "EXACT_EXPLICIT",
            "writable": True,
            "block_reason": None,
            "planned_production_line_id": roster_evidence[key],
            "evidence_classes": [*candidate["evidence_classes"], "EXPLICIT_PHYSICAL_LINE_IDENTITY"],
        })
    counts = Counter(candidate["classification"] for candidate in candidates)
    return {
        "schema_version": PLANNER_VERSION,
        "artifact_kind": "production_line_discovery",
        "generated_at": None,
        "input": {"legacy_snapshot_sha256": snapshot_sha256},
        "summary_counts": {
            "candidate_production_lines": len(candidates),
            "create_safe": counts["CREATE_SAFE"],
            "blocked_candidate_count": len(candidates) - counts["CREATE_SAFE"],
            "same_site_canonical_text_collisions": 0,
            "cross_site_same_text_occurrences": sum(1 for text in {candidate["canonical_line_text"] for candidate in candidates} if sum(candidate["canonical_line_text"] == text for candidate in candidates) > 1),
            "multi_gxp_same_site_same_line_observations": sum(len(candidate["gxp_contexts"]) > 1 for candidate in candidates),
        },
        "classification_counts": dict(sorted(counts.items())),
        "supported_classifications": [
            "CREATE_SAFE",
            "BLOCKED_AMBIGUOUS",
            "BLOCKED_SITE_CONFLICT",
            "BLOCKED_TEXT_COLLISION",
            "BLOCKED_INSUFFICIENT_EVIDENCE",
            "NO_LINE_EVIDENCE",
        ],
        "candidates": candidates,
    }


def _candidate_by_key(discovery: Mapping[str, Any]) -> dict[tuple[int, str], Mapping[str, Any]]:
    return {(item["source_site_legacy_id"], item["canonical_line_text"]): item for item in discovery["candidates"]}


def _case_linkage(
    cases: list[dict[str, Any]],
    discovery: Mapping[str, Any],
    *,
    snapshot_sha256: str,
    canonical_state_sha256: str | None,
    roster_sha256: str | None,
    canonical_index: Mapping[str, Any],
) -> dict[str, Any]:
    candidates = _candidate_by_key(discovery)
    records: list[dict[str, Any]] = []
    for case in cases:
        line, site = case["line"], case["source_site_legacy_id"]
        canonical_case = canonical_index["cases"].get(case["legacy_inspection_id"])
        base = {
            "legacy_inspection_id": case["legacy_inspection_id"],
            "source_site_legacy_id": site,
            "source_ref": case["source_ref"],
            "canonical_case_id": None if canonical_case is None else canonical_case["id"],
            "source_line_text_raw": line.get("source_text"),
            "source_line_text_canonical": line.get("canonical_text"),
            "canonicalization_operations": line["operations"],
        }
        if not case["eligible_case_source"]:
            records.append({"classification": "NOT_APPLICABLE", "block_reason": "SOURCE_CASE_CONTEXT_UNRESOLVED", **base})
        elif line["state"] != "CANONICAL":
            records.append({"classification": "BLOCKED_NO_LINE", "block_reason": f"LINE_{line['state']}", **base})
        else:
            candidate = candidates[(site, line["canonical_text"])]
            records.append({
                "classification": (
                    "LINK_CANONICAL_EQUIVALENT"
                    if candidate["writable"] and line["operations"]
                    else "LINK_EXACT"
                    if candidate["writable"]
                    else "BLOCKED_INSUFFICIENT_EVIDENCE"
                ),
                "block_reason": candidate["block_reason"],
                "candidate_key": candidate["candidate_key"],
                "expected_case_production_line_id": None,
                "stale_plan_fingerprint": {
                    "expected_production_line_id": None if canonical_case is None else canonical_case.get("production_line_id"),
                    "expected_source_site_legacy_id": site,
                    "expected_compatibility_line_text_raw": line["source_text"],
                    "expected_canonical_case_id": None if canonical_case is None else canonical_case["id"],
                    "expected_case_site_id": None if canonical_case is None else canonical_case.get("site_id"),
                    "expected_case_row_version": None if canonical_case is None else canonical_case.get("row_version"),
                },
                **base,
            })
    counts = Counter(record["classification"] for record in records)
    return {
        "schema_version": PLANNER_VERSION,
        "artifact_kind": "production_line_case_linkage_plan",
        "generated_at": None,
        "input": {"legacy_snapshot_sha256": snapshot_sha256, "canonical_state_sha256": canonical_state_sha256, "physical_identity_roster_sha256": roster_sha256},
        "summary_counts": {"total_case_sources": len(records), "writable_link_count": sum(record["classification"] in {"LINK_EXACT", "LINK_CANONICAL_EQUIVALENT"} for record in records)},
        "classification_counts": dict(sorted(counts.items())),
        "supported_classifications": [
            "LINK_EXACT",
            "LINK_CANONICAL_EQUIVALENT",
            "BLOCKED_AMBIGUOUS",
            "BLOCKED_NO_LINE",
            "BLOCKED_SITE_MISMATCH",
            "BLOCKED_MULTIPLE_CANDIDATES",
            "BLOCKED_SOURCE_CONFLICT",
            "NOT_APPLICABLE",
            "BLOCKED_INSUFFICIENT_EVIDENCE",
        ],
        "records": records,
        "write_candidates": [
            record for record in records if record["classification"] in {"LINK_EXACT", "LINK_CANONICAL_EQUIVALENT"}
        ],
    }


def _certificate_linkage(
    cases: list[dict[str, Any]],
    certificates: list[dict[str, Any]],
    discovery: Mapping[str, Any],
    *,
    snapshot_sha256: str,
    canonical_state_sha256: str | None,
    roster_sha256: str | None,
    canonical_index: Mapping[str, Any],
) -> dict[str, Any]:
    candidates = _candidate_by_key(discovery)
    cases_by_id = {case["legacy_inspection_id"]: case for case in cases}
    records: list[dict[str, Any]] = []
    for certificate in certificates:
        line, site = certificate["line"], certificate["source_site_legacy_id"]
        canonical_certificate = canonical_index["certificates"].get(certificate["legacy_certificate_id"])
        base = {"legacy_certificate_id": certificate["legacy_certificate_id"], "source_site_legacy_id": site, "source_ref": certificate["source_ref"], "canonical_certificate_id": None if canonical_certificate is None else canonical_certificate["id"], "source_line_text_raw": line.get("source_text"), "source_line_text_canonical": line.get("canonical_text"), "canonicalization_operations": line["operations"]}
        source_case = cases_by_id.get(certificate["source_inspection_legacy_id"])
        if line["state"] != "CANONICAL":
            records.append({"classification": "BLOCKED_NO_LINE", "block_reason": f"LINE_{line['state']}", **base})
            continue
        if not isinstance(site, int):
            records.append({"classification": "BLOCKED_SITE_MISMATCH", "block_reason": "CERTIFICATE_SITE_MISSING", **base})
            continue
        if source_case is not None and source_case["source_site_legacy_id"] != site:
            records.append({"classification": "BLOCKED_SITE_MISMATCH", "block_reason": "CASE_CERTIFICATE_SITE_DIFFERS", **base})
            continue
        if source_case is not None and source_case["gxp_type"] is not None and certificate["gxp_type"] is not None and source_case["gxp_type"] != certificate["gxp_type"]:
            records.append({"classification": "BLOCKED_SOURCE_CONFLICT", "block_reason": "CASE_CERTIFICATE_GXP_CONTEXT_DIFFERS", **base})
            continue
        if source_case is not None and source_case["line"]["state"] == "CANONICAL" and source_case["line"]["canonical_text"] != line["canonical_text"]:
            records.append({"classification": "BLOCKED_CASE_CERTIFICATE_CONFLICT", "block_reason": "COMPATIBILITY_LINE_TEXT_DIFFERS", **base})
            continue
        candidate = candidates[(site, line["canonical_text"])]
        classification = "BLOCKED_INSUFFICIENT_EVIDENCE"
        if candidate["writable"]:
            if source_case is not None and source_case["line"]["state"] == "CANONICAL":
                classification = "LINK_CASE_CORROBORATED"
            elif line["operations"]:
                classification = "LINK_CANONICAL_EQUIVALENT"
            else:
                classification = "LINK_EXACT"
        records.append({
            "classification": classification,
            "block_reason": candidate["block_reason"],
            "candidate_key": candidate["candidate_key"],
            "source_case_corroboration": source_case is not None and source_case["line"]["state"] == "CANONICAL",
            "stale_plan_fingerprint": {
                "expected_production_line_id": None if canonical_certificate is None else canonical_certificate.get("production_line_id"),
                "expected_source_site_legacy_id": site,
                "expected_compatibility_line_text_raw": line["source_text"],
                "expected_canonical_certificate_id": None if canonical_certificate is None else canonical_certificate["id"],
                "expected_certificate_site_id": None if canonical_certificate is None else canonical_certificate.get("site_id"),
                "expected_certificate_case_id": None if canonical_certificate is None else canonical_certificate.get("case_id"),
                "expected_certificate_row_version": None if canonical_certificate is None else canonical_certificate.get("row_version"),
            },
            **base,
        })
    counts = Counter(record["classification"] for record in records)
    return {
        "schema_version": PLANNER_VERSION,
        "artifact_kind": "production_line_certificate_linkage_plan",
        "generated_at": None,
        "input": {"legacy_snapshot_sha256": snapshot_sha256, "canonical_state_sha256": canonical_state_sha256, "physical_identity_roster_sha256": roster_sha256},
        "summary_counts": {"total_certificate_sources": len(records), "writable_link_count": sum(record["classification"].startswith("LINK_") for record in records)},
        "classification_counts": dict(sorted(counts.items())),
        "supported_classifications": [
            "LINK_EXACT",
            "LINK_CASE_CORROBORATED",
            "LINK_CANONICAL_EQUIVALENT",
            "BLOCKED_NO_LINE",
            "BLOCKED_SITE_MISMATCH",
            "BLOCKED_CASE_CERTIFICATE_CONFLICT",
            "BLOCKED_MULTIPLE_CANDIDATES",
            "BLOCKED_SOURCE_CONFLICT",
            "BLOCKED_INSUFFICIENT_EVIDENCE",
        ],
        "records": records,
        "write_candidates": [record for record in records if record["classification"].startswith("LINK_")],
    }


def _transformation_evidence(discovery: Mapping[str, Any], *, snapshot_sha256: str, canonical_state_sha256: str | None, roster_sha256: str | None) -> dict[str, Any]:
    possible = [candidate for candidate in discovery["candidates"] if any(marker in candidate["canonical_line_text"] for marker in ("+", "->", "→"))]
    records = [{
        "classification": "POSSIBLE_BUT_UNPROVEN",
        "writable": False,
        "block_reason": "LINE_TEXT_ALONE_DOES_NOT_PROVE_TRANSFORMATION",
        "candidate_key": candidate["candidate_key"],
        "source_site_legacy_id": candidate["source_site_legacy_id"],
        "canonical_line_text": candidate["canonical_line_text"],
        "legacy_source_refs": candidate["legacy_source_refs"],
    } for candidate in possible]
    if not records:
        records = [{"classification": "NO_TRANSFORMATION_EVIDENCE", "writable": False, "block_reason": "NO_EXPLICIT_LINEAGE_SOURCE_FIELD"}]
    counts = Counter(record["classification"] for record in records)
    return {
        "schema_version": PLANNER_VERSION,
        "artifact_kind": "production_line_transformation_evidence",
        "generated_at": None,
        "input": {"legacy_snapshot_sha256": snapshot_sha256, "canonical_state_sha256": canonical_state_sha256, "physical_identity_roster_sha256": roster_sha256},
        "classification_counts": dict(sorted(counts.items())),
        "transformation_writable_count": 0,
        "records": records,
    }


def _readiness_audits(*, snapshot_sha256: str) -> dict[str, Any]:
    return {
        "scope_lifecycle": {
            "status": "BLOCKED_LEGACY_UNPHASED_CASE_SCOPE",
            "snapshot_sha256": snapshot_sha256,
            "rows_created": 0,
            "blockers": ["db.ktra.PHẠM VI KIỂM TRA has no proven REQUESTED/ASSESSED/INSPECTED/CONCLUDED phase"],
        },
        "certificate_lifecycle": {
            "status": "READINESS_ONLY_NO_RELATIONSHIP_INFERENCE",
            "snapshot_sha256": snapshot_sha256,
            "rows_created": 0,
            "blockers": ["latest compatibility flags and certificate-number patterns do not prove replacement/supersession"],
        },
    }


def canonical_artifact_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def artifact_with_digest(value: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(value)
    payload["content_sha256"] = sha256(canonical_artifact_bytes(payload)).hexdigest()
    return payload


def review_tags_for_candidate(
    candidate: Mapping[str, Any],
    *,
    cross_site_same_text: bool,
) -> list[str]:
    """Return deterministic review context only; tags never prove line identity."""
    text = str(candidate["canonical_line_text"])
    raw_values = candidate["observed_line_texts"]
    tags: list[str] = []
    case_count = len(candidate["source_case_ids"])
    certificate_count = len(candidate["source_certificate_ids"])
    if case_count and certificate_count:
        tags.append("CASE_AND_CERTIFICATE_AGREE")
    elif case_count:
        tags.append("CASE_ONLY")
    else:
        tags.append("CERTIFICATE_ONLY")
    if case_count > 1:
        tags.append("MULTIPLE_CASES")
    if certificate_count > 1:
        tags.append("MULTIPLE_CERTIFICATES")
    if case_count == certificate_count == 1:
        tags.append("SINGLE_CASE_SINGLE_CERTIFICATE")
    if len(raw_values) > 1:
        tags.append("MULTIPLE_RAW_TEXT_VARIANTS")
    if cross_site_same_text:
        tags.append("CROSS_SITE_TEXT_REUSE")
    if len(candidate["gxp_contexts"]) > 1:
        tags.append("MULTI_GXP_CONTEXT")
    if re.fullmatch(r"[A-Z0-9]+(?:[+&/]\s*[A-Z0-9]+)+", text):
        tags.append("COMBINED_NOTATION")
    if re.fullmatch(r"\d+", text):
        tags.append("NUMERIC_ONLY")
    if re.fullmatch(r"[A-Z]+", text):
        tags.append("LETTER_ONLY")
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").upper()
    if folded in {"LINE", "DAY CHUYEN", "DAY CHUYEN SAN XUAT", "UNIT", "KHU"}:
        tags.extend(("GENERIC_LINE_TERM", "LOW_INFORMATION_TEXT"))
    if len(text) >= 40:
        tags.append("LONG_DESCRIPTIVE_TEXT")
    if re.search(r"\b(BUILDING|NHA|XUONG|UNIT|KHU)\b", folded):
        tags.append("POSSIBLE_BUILDING_OR_UNIT_TEXT")
    if "CASE_AND_CERTIFICATE_AGREE" in tags and "LOW_INFORMATION_TEXT" not in tags:
        tags.append("HIGH_INFORMATION_FOR_REVIEW")
    return tags


def build_physical_identity_roster_template(
    discovery: Mapping[str, Any],
    *,
    snapshot_sha256: str,
    canonical_state_sha256: str | None,
) -> dict[str, Any]:
    """Create review work items without asserting that any line is physical."""
    items: list[dict[str, Any]] = []
    text_site_counts = Counter(candidate["canonical_line_text"] for candidate in discovery["candidates"])
    for candidate in discovery["candidates"]:
        raw_values = candidate["observed_line_texts"]
        tags = review_tags_for_candidate(
            candidate,
            cross_site_same_text=text_site_counts[candidate["canonical_line_text"]] > 1,
        )
        items.append({
            "candidate_key": candidate["candidate_key"],
            "source_site_legacy_id": candidate["source_site_legacy_id"],
            "canonical_site_id": candidate["canonical_site_id"],
            "canonical_line_text": candidate["canonical_line_text"],
            "observed_line_texts": raw_values,
            "source_case_ids": candidate["source_case_ids"],
            "source_certificate_ids": candidate["source_certificate_ids"],
            "gxp_contexts": candidate["gxp_contexts"],
            "evidence_classes": candidate["evidence_classes"],
            "legacy_source_refs": candidate["legacy_source_refs"],
            "review_tags": tags,
            "review_status": "PENDING_HUMAN_REVIEW",
            "review_reason": None,
            "physical_identity_action": "DEFER_INSUFFICIENT_EVIDENCE",
            "production_line_id": None,
            "reviewer": None,
            "reviewed_at": None,
        })
    items.sort(key=lambda item: ("HIGH_INFORMATION_FOR_REVIEW" not in item["review_tags"], item["source_site_legacy_id"], item["canonical_line_text"], item["candidate_key"]))
    return artifact_with_digest({
        "schema_version": ROSTER_SCHEMA_VERSION,
        "artifact_kind": "production_line_physical_identity_roster_template",
        "generated_at": None,
        "planner_version": PLANNER_VERSION,
        "legacy_snapshot_sha256": snapshot_sha256,
        "canonical_state_sha256": canonical_state_sha256,
        "items": items,
    })


def build_review_summary(roster: Mapping[str, Any]) -> str:
    items = roster["items"]
    tag_counts = Counter(tag for item in items for tag in item["review_tags"])
    return "\n".join([
        "# ProductionLine Physical Identity Review Summary",
        "",
        "This is a review-priority report. It proves no physical identity and authorizes no write.",
        "",
        f"- Total candidates: {len(items)}",
        *[f"- {tag}: {tag_counts[tag]}" for tag in sorted(tag_counts)],
        "",
        "## Review Order",
        "Review `HIGH_INFORMATION_FOR_REVIEW` first, then all remaining items by Site and canonical text.",
        "",
    ])


def build_production_line_population_plan(
    snapshot: Mapping[str, Any],
    *,
    snapshot_sha256: str,
    canonical_state: Mapping[str, Any] | None = None,
    canonical_state_sha256: str | None = None,
    roster: Mapping[str, Any] | None = None,
    roster_sha256: str | None = None,
) -> dict[str, dict[str, Any]]:
    if not re.fullmatch(r"[0-9a-f]{64}", snapshot_sha256):
        raise ProductionLinePlanningError("B6H snapshot SHA256 is invalid")
    state, state_sha = _validate_canonical_state(canonical_state, supplied_sha256=canonical_state_sha256)
    canonical_index = _canonical_state_index(state)
    roster_by_candidate, resolved_roster_sha = _validate_roster(
        roster,
        snapshot_sha256=snapshot_sha256,
        canonical_state_sha256=state_sha,
        supplied_sha256=roster_sha256,
    )
    cases, certificates = _source_evidence(snapshot)
    discovery = _discovery(cases, certificates, snapshot_sha256=snapshot_sha256, canonical_state=state, canonical_index=canonical_index, roster_by_candidate=roster_by_candidate)
    shared_input = {"legacy_snapshot_sha256": snapshot_sha256, "canonical_state_sha256": state_sha, "physical_identity_roster_sha256": resolved_roster_sha, "planner_version": PLANNER_VERSION}
    discovery["input"] = shared_input
    case_linkage = _case_linkage(cases, discovery, snapshot_sha256=snapshot_sha256, canonical_state_sha256=state_sha, roster_sha256=resolved_roster_sha, canonical_index=canonical_index)
    certificate_linkage = _certificate_linkage(cases, certificates, discovery, snapshot_sha256=snapshot_sha256, canonical_state_sha256=state_sha, roster_sha256=resolved_roster_sha, canonical_index=canonical_index)
    transformation = _transformation_evidence(discovery, snapshot_sha256=snapshot_sha256, canonical_state_sha256=state_sha, roster_sha256=resolved_roster_sha)
    readiness = _readiness_audits(snapshot_sha256=snapshot_sha256)
    discovery["population_counts"] = {
        "total_case_sources": len(cases),
        "eligible_case_sources": sum(item["eligible_case_source"] for item in cases),
        "total_certificate_sources": len(certificates),
        "cases_with_line_text": sum(item["line"]["state"] == "CANONICAL" for item in cases),
        "cases_without_line_text": sum(item["line"]["state"] != "CANONICAL" for item in cases),
        "certificates_with_line_text": sum(item["line"]["state"] == "CANONICAL" for item in certificates),
        "certificates_without_line_text": sum(item["line"]["state"] != "CANONICAL" for item in certificates),
        "canonical_case_count": "NOT_RUN_NO_DATABASE_READ",
        "canonical_certificate_count": "NOT_RUN_NO_DATABASE_READ",
    }
    discovery["readiness_audits"] = readiness
    return {
        "discovery": artifact_with_digest(discovery),
        "case_linkage": artifact_with_digest(case_linkage),
        "certificate_linkage": artifact_with_digest(certificate_linkage),
        "transformation_evidence": artifact_with_digest(transformation),
    }
