"""Fail-closed B6J Site-local ProductionLine planning."""
from __future__ import annotations

from collections import Counter
from datetime import date
from hashlib import sha256
import json
import re
from typing import Any, Mapping
from uuid import NAMESPACE_URL, uuid5

from backend.app.domain.production_line_canonical_state import REQUIRED_ALEMBIC_REVISION, SUPPORTED_ALEMBIC_REVISIONS
from backend.app.domain.inspection_periods import InspectionPeriodSourceState, parse_legacy_inspection_periods
from backend.app.domain.legacy_db_ktra_source_v2 import excel_serial_date, snapshot_cell, snapshot_cell_value, snapshot_header_map
from backend.app.domain.phase2_import import parse_date
from backend.app.domain.legacy_snapshot_v2 import snapshot_legacy_int
from backend.app.domain.production_line_population import CANONICAL_STATE_SCHEMA_VERSION, ProductionLinePlanningError, canonical_json_bytes, source_line_evidence
from backend.app.domain.production_line_population import canonical_artifact_bytes as b6h_canonical_artifact_bytes
from backend.app.domain.production_line_review_workspace import REVIEW_SCHEMA_VERSION, candidate_set_digest

PLANNER_VERSION = "b6j-production-line-population/v1"
PLAN_SCHEMA_VERSION = "production-line-population-plan/v1"
PLAN_NAMESPACE = "https://gxp.example/migration/b6j/production-line-plan/v1"
_SHA256 = re.compile(r"[0-9a-f]{64}")


class ProductionLinePopulationPlanError(ProductionLinePlanningError):
    pass


def canonical_artifact_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _digest(value: Mapping[str, Any]) -> str:
    return sha256(canonical_json_bytes(value)).hexdigest()


def plan_digest(plan: Mapping[str, Any]) -> str:
    payload = dict(plan)
    payload.pop("plan_sha256", None)
    return _digest(payload)


def _sha(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ProductionLinePopulationPlanError(f"B6J {label} is invalid")
    return value


def _parse(value: object, *, inspection: bool) -> tuple[date | None, str]:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        parsed = excel_serial_date(value)
        return parsed, "EXCEL_SERIAL_DATE" if parsed else "INVALID"
    if inspection:
        result = parse_legacy_inspection_periods(None if value is None else str(value))
        if result.state is not InspectionPeriodSourceState.KNOWN or not result.segments:
            return None, result.state.value
        return min(segment.started_on for segment in result.segments), result.state.value
    parsed = parse_date("" if value is None else str(value))
    return parsed, "SINGLE_DATE" if parsed else "INVALID"


def _dates(snapshot: Mapping[str, Any]) -> tuple[dict[int, tuple[date, object, str, Mapping[str, Any]]], dict[int, tuple[date, object, str, Mapping[str, Any]]]]:
    """Read only exact db.ktra/db.cc date cells; never dkkd or db.CC."""
    output: list[dict[int, tuple[date, object, str, Mapping[str, Any]]]] = []
    for sheet, header, inspection in (("db.ktra", "Ngày K.tra", True), ("db.cc", "Ngày cấp CC", False)):
        # A renamed/missing authoritative date field is source-contract drift,
        # not evidence that every candidate lacks a date.
        rows, columns = snapshot_header_map(snapshot, sheet, required_headers=("ID", header))
        found: dict[int, tuple[date, object, str, Mapping[str, Any]]] = {}
        for row in rows:
            if not isinstance(row.get("source_row_number"), int) or row["source_row_number"] <= 4:
                continue
            identity = snapshot_legacy_int(snapshot_cell_value(row, columns["ID"]))
            if identity is None:
                continue
            source_cell = snapshot_cell(row, sheet_name=sheet, header=header, column_ordinal=columns[header])
            raw = source_cell["raw_value"]
            parsed, state = _parse(raw, inspection=inspection)
            if parsed is not None:
                if identity in found:
                    raise ProductionLinePopulationPlanError(f"B6J {sheet} has duplicate valid legacy IDs")
                found[identity] = (parsed, raw, state, source_cell)
        output.append(found)
    return output[0], output[1]


def _index(state: Mapping[str, Any], expected: str) -> dict[str, Any]:
    _sha(expected, "canonical state SHA256")
    if state.get("schema_version") != CANONICAL_STATE_SCHEMA_VERSION or state.get("source_alembic_revision") not in SUPPORTED_ALEMBIC_REVISIONS:
        raise ProductionLinePopulationPlanError("B6J canonical state schema or revision is invalid")
    if _digest(state) != expected:
        raise ProductionLinePopulationPlanError("B6J canonical state SHA256 does not match semantic content")
    unsealed = dict(state)
    seal = unsealed.pop("source_state_fingerprint", None)
    if seal != _digest(unsealed):
        raise ProductionLinePopulationPlanError("B6J canonical state source-state fingerprint is invalid")
    identity = state.get("source_database_identity")
    if not isinstance(identity, Mapping) or not isinstance(identity.get("database_name"), str):
        raise ProductionLinePopulationPlanError("B6J canonical state has no database identity")
    def items(key: str, identity_key: str) -> dict[int, Mapping[str, Any]]:
        values = state.get(key)
        if not isinstance(values, list):
            raise ProductionLinePopulationPlanError(f"B6J canonical {key} are invalid")
        result = {}
        for value in values:
            if not isinstance(value, Mapping) or not isinstance(value.get(identity_key), int) or value[identity_key] in result:
                raise ProductionLinePopulationPlanError(f"B6J canonical {key} contain duplicate or invalid identities")
            result[value[identity_key]] = value
        return result
    return {"sites": items("sites", "legacy_site_id"), "cases": items("cases", "legacy_inspection_id"), "certificates": items("certificates", "legacy_certificate_id"), "lines": list(state.get("existing_production_lines") or []), "database": dict(identity)}


def _key(site: int, code: str) -> str:
    encoded = json.dumps([site, code], ensure_ascii=False, separators=(",", ":")).encode()
    return "legacy-line:" + sha256(encoded).hexdigest()[:24]


def _counts(records: list[Mapping[str, Any]]) -> dict[str, int]:
    return dict(sorted(Counter(str(record["classification"]) for record in records).items()))


def bind_candidate_roster(
    roster: Mapping[str, Any], *, roster_raw_sha256: str, candidate_set_sha256: str,
    snapshot_sha256: str, canonical_state_sha256: str, candidates: list[Mapping[str, Any]],
) -> dict[str, Any]:
    """Bind B6J to the immutable B6I candidate universe, not review decisions."""
    _sha(roster_raw_sha256, "candidate roster raw SHA256")
    if roster.get("artifact_kind") != "production_line_physical_identity_review_roster" or roster.get("schema_version") != REVIEW_SCHEMA_VERSION:
        raise ProductionLinePopulationPlanError("B6J candidate roster kind or schema is invalid")
    if roster.get("planner_version") != "b6h-production-line-population/v2":
        raise ProductionLinePopulationPlanError("B6J candidate roster planner version is invalid")
    for field, expected in (("candidate_set_sha256", candidate_set_sha256), ("legacy_snapshot_sha256", snapshot_sha256), ("canonical_state_sha256", canonical_state_sha256)):
        if roster.get(field) != expected:
            raise ProductionLinePopulationPlanError(f"B6J candidate roster {field} does not match plan input")
    items = roster.get("items")
    if not isinstance(items, list):
        raise ProductionLinePopulationPlanError("B6J candidate roster items are invalid")
    content = roster.get("content_sha256")
    if not isinstance(content, str) or _SHA256.fullmatch(content) is None:
        raise ProductionLinePopulationPlanError("B6J candidate roster content SHA256 is invalid")
    unsealed = dict(roster); unsealed.pop("content_sha256", None)
    if content != sha256(b6h_canonical_artifact_bytes(unsealed)).hexdigest():
        raise ProductionLinePopulationPlanError("B6J candidate roster content SHA256 does not match content")
    by_key = {item.get("candidate_key"): item for item in items if isinstance(item, Mapping)}
    planned = {item.get("candidate_key"): item for item in candidates}
    if len(by_key) != len(items) or None in by_key:
        raise ProductionLinePopulationPlanError("B6J candidate roster has duplicate or invalid candidate keys")
    try:
        actual_candidate_set_sha256 = candidate_set_digest(items)
    except (KeyError, TypeError) as exc:
        raise ProductionLinePopulationPlanError("B6J candidate roster items are invalid") from exc
    if actual_candidate_set_sha256 != candidate_set_sha256:
        raise ProductionLinePopulationPlanError("B6J candidate roster candidate-set SHA256 does not match immutable items")
    if set(by_key) != set(planned):
        raise ProductionLinePopulationPlanError("B6J candidate roster candidate universe differs from B6J")
    for key, item in by_key.items():
        candidate = planned[key]
        pairs = (("canonical_site_id", "canonical_site_id"), ("source_site_legacy_id", "legacy_site_id"), ("canonical_line_text", "canonical_line_code"), ("existing_production_line_id", "existing_production_line_id"))
        if any(item.get(roster_field) != candidate.get(plan_field) for roster_field, plan_field in pairs):
            raise ProductionLinePopulationPlanError("B6J candidate roster identity differs from B6J candidate")
        for field in ("source_case_ids", "source_certificate_ids"):
            if sorted(item.get(field) or []) != sorted(candidate.get(field) or []):
                raise ProductionLinePopulationPlanError("B6J candidate roster source identities differ from B6J candidate")
        if item.get("case_count") != len(item.get("source_case_ids") or []) or item.get("certificate_count") != len(item.get("source_certificate_ids") or []):
            raise ProductionLinePopulationPlanError("B6J candidate roster source counts are invalid")
    return {"candidate_set_roster_sha256": roster_raw_sha256, "candidate_set_roster_content_sha256": content, "candidate_set_roster_content_sha256_verified": True, "candidate_set_roster_schema_version": roster["schema_version"], "candidate_set_roster_artifact_kind": roster["artifact_kind"], "candidate_set_roster_item_count": len(items), "candidate_set_roster_planner_version": roster["planner_version"]}


def build_population_plan(snapshot: Mapping[str, Any], *, snapshot_sha256: str, canonical_state: Mapping[str, Any], canonical_state_sha256: str, candidate_set_sha256: str, candidate_roster: Mapping[str, Any] | None = None, candidate_roster_raw_sha256: str | None = None) -> dict[str, Any]:
    """Produce an immutable plan; only the companion writer may mutate state."""
    _sha(snapshot_sha256, "snapshot SHA256")
    _sha(candidate_set_sha256, "candidate set SHA256")
    index, (case_dates, certificate_dates) = _index(canonical_state, canonical_state_sha256), _dates(snapshot)
    source_cases, source_certificates = source_line_evidence(snapshot)
    groups: dict[tuple[int, str], dict[str, Any]] = {}
    for kind, records, identifier in (("CASE", source_cases, "legacy_inspection_id"), ("CERTIFICATE", source_certificates, "legacy_certificate_id")):
        for record in records:
            line, site = record["line"], record.get("source_site_legacy_id")
            # A Case without the source owner's eligible GxP/Site context is
            # preserved for accounting, but cannot create a B6J line candidate.
            if kind == "CASE" and not record.get("eligible_case_source"):
                continue
            if line["state"] != "CANONICAL" or not isinstance(site, int):
                continue
            group = groups.setdefault((site, str(line["canonical_text"])), {"cases": [], "certificates": [], "raw": set(), "gxp": set()})
            group["cases" if kind == "CASE" else "certificates"].append(record[identifier])
            group["raw"].add(str(line["source_text"]))
            if record.get("gxp_type"):
                group["gxp"].add(record["gxp_type"])
    candidates: list[dict[str, Any]] = []
    for (legacy_site_id, code), group in sorted(groups.items()):
        site = index["sites"].get(legacy_site_id)
        case_ids, certificate_ids = sorted(group["cases"]), sorted(group["certificates"])
        case_evidence = [(case_dates[i][0], "CASE", i, case_dates[i][1], case_dates[i][2], case_dates[i][3]) for i in case_ids if i in case_dates]
        cert_evidence = [(certificate_dates[i][0], "CERTIFICATE", i, certificate_dates[i][1], certificate_dates[i][2], certificate_dates[i][3]) for i in certificate_ids if i in certificate_dates]
        evidence = sorted(case_evidence or cert_evidence, key=lambda item: (item[0], item[1], item[2]))
        existing = [] if site is None else [line for line in index["lines"] if isinstance(line, Mapping) and line.get("site_id") == site.get("id") and line.get("code") == code]
        if len(existing) > 1:
            raise ProductionLinePopulationPlanError("B6J canonical state has ambiguous same-Site ProductionLine mapping")
        classification, reason = "CREATE_NEW_PRODUCTION_LINE", None
        if site is None:
            classification, reason = "BLOCKED_SITE_UNRESOLVED", "CANONICAL_SITE_NOT_RESOLVED"
        elif not evidence:
            classification, reason = "BLOCKED_EFFECTIVE_FROM_UNKNOWN", "NO_AUTHORITATIVE_DATED_EVIDENCE"
        elif existing:
            classification, reason = "MAP_TO_EXISTING_PRODUCTION_LINE", "EXISTING_CANONICAL_LINE_SAME_SITE_CODE"
        selected = evidence[0] if evidence else None
        key = _key(legacy_site_id, code)
        candidates.append({"candidate_key": key, "legacy_site_id": legacy_site_id, "canonical_site_id": None if site is None else site.get("id"), "legacy_line_code_raw": sorted(group["raw"]), "canonical_line_code": code, "proposed_display_code": code, "source_case_ids": case_ids, "source_certificate_ids": certificate_ids, "gxp_contexts": sorted(group["gxp"]), "classification": classification, "block_reason": reason, "existing_production_line_id": None if not existing else existing[0].get("id"), "proposed_production_line_id": str(uuid5(NAMESPACE_URL, f"{PLAN_NAMESPACE}:{snapshot_sha256}:{canonical_state_sha256}:{key}")) if classification == "CREATE_NEW_PRODUCTION_LINE" else None, "effective_from": None if selected is None else selected[0].isoformat(), "effective_from_basis": None if selected is None else "EARLIEST_EVIDENCED_ACTIVE_DATE", "effective_from_source_type": None if selected is None else selected[1], "effective_from_source_id": None if selected is None else selected[2], "effective_from_source_date_raw": None if selected is None else selected[3], "effective_from_source_state": None if selected is None else selected[4], "effective_from_source_sheet": None if selected is None else selected[5]["sheet_name"], "effective_from_source_row": None if selected is None else selected[5]["source_row_number"], "effective_from_source_field": None if selected is None else selected[5]["header"], "effective_from_source_column_ordinal": None if selected is None else selected[5]["column_ordinal"], "effective_from_source_raw_state": None if selected is None else selected[5]["raw_state"]})
    by_key = {(candidate["legacy_site_id"], candidate["canonical_line_code"]): candidate for candidate in candidates}
    source_case_by_id = {record["legacy_inspection_id"]: record for record in source_cases}
    def links(records: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for source in records:
            identity = source["legacy_inspection_id"] if kind == "CASE" else source["legacy_certificate_id"]
            line, site = source["line"], source.get("source_site_legacy_id")
            candidate = by_key.get((site, line.get("canonical_text"))) if line["state"] == "CANONICAL" and isinstance(site, int) else None
            canonical = index["cases" if kind == "CASE" else "certificates"].get(identity)
            classification, reason = "NOT_APPLICABLE", "NO_CANONICAL_LINE_TEXT"
            if kind == "CASE" and not source.get("eligible_case_source"):
                classification, reason = "NOT_APPLICABLE", "CASE_SOURCE_NOT_ELIGIBLE"
            elif line["state"] != "CANONICAL": classification, reason = "BLOCKED_NO_LINE", f"LINE_{line['state']}"
            elif not isinstance(site, int): classification, reason = "BLOCKED_SITE_UNRESOLVED", "SOURCE_SITE_MISSING"
            elif kind == "CERTIFICATE" and (case := source_case_by_id.get(source.get("source_inspection_legacy_id"))) is not None and case.get("source_site_legacy_id") != site: classification, reason = "BLOCKED_SITE_MISMATCH", "CASE_CERTIFICATE_SITE_DIFFERS"
            elif candidate is None: classification, reason = "BLOCKED_IDENTITY_CONFLICT", "CANDIDATE_NOT_RESOLVED"
            elif candidate["classification"] == "CREATE_NEW_PRODUCTION_LINE": classification, reason = "LINK_TO_NEW_LINE", None
            elif candidate["classification"] == "MAP_TO_EXISTING_PRODUCTION_LINE": classification, reason = "LINK_TO_EXISTING_LINE", None
            else: classification, reason = candidate["classification"], candidate["block_reason"]
            expected_site = None if candidate is None else candidate["canonical_site_id"]
            if classification.startswith("LINK_") and canonical is None: classification, reason = "BLOCKED_STALE_STATE", "CANONICAL_RECORD_MISSING"
            elif classification.startswith("LINK_") and canonical.get("site_id") != expected_site: classification, reason = "BLOCKED_SITE_MISMATCH", "CANONICAL_SITE_DIFFERS"
            target = None if candidate is None else candidate["proposed_production_line_id"] or candidate["existing_production_line_id"]
            # B6J is migration-only population of missing canonical links.
            # A pre-existing FK is not permission to remap a physical identity.
            if classification.startswith("LINK_") and canonical.get("production_line_id") is not None:
                if canonical["production_line_id"] == target:
                    classification, reason = "NOT_APPLICABLE", "ALREADY_LINKED_TO_PLANNED_LINE"
                else:
                    classification, reason = "BLOCKED_EXISTING_LINK", "CANONICAL_LINK_CONFLICT"
            results.append({"legacy_id": identity, "candidate_key": None if candidate is None else candidate["candidate_key"], "classification": classification, "block_reason": reason, "raw_line_code": line.get("source_text"), "canonical_line_code": line.get("canonical_text"), "source_ref": source.get("source_ref"), "canonical_record_id": None if canonical is None else canonical.get("id"), "expected_site_id": expected_site, "expected_production_line_id": None if canonical is None else canonical.get("production_line_id"), "expected_row_version": None if canonical is None else canonical.get("row_version"), "expected_canonical_raw_line_code": None if canonical is None else canonical.get("scope_code_raw" if kind == "CASE" else "line_code_raw"), "planned_production_line_id": target})
        return results
    case_links, certificate_links = links(source_cases, "CASE"), links(source_certificates, "CERTIFICATE")
    # Source accounting can contain several legacy references for one DB owner.
    # Retain every source record, but refuse any non-convergent write target.
    for label, records in (("Case", case_links), ("Certificate", certificate_links)):
        targets: dict[object, tuple[object, object]] = {}
        for record in records:
            if not record["classification"].startswith("LINK_"):
                continue
            owner = record.get("canonical_record_id")
            if owner is None:
                continue
            desired = (record.get("planned_production_line_id"), record.get("expected_site_id"))
            previous = targets.setdefault(owner, desired)
            if previous != desired:
                raise ProductionLinePopulationPlanError(f"B6J conflicting duplicate canonical {label} write targets")
    roster_provenance = {} if candidate_roster is None else bind_candidate_roster(candidate_roster, roster_raw_sha256=_sha(candidate_roster_raw_sha256, "candidate roster raw SHA256"), candidate_set_sha256=candidate_set_sha256, snapshot_sha256=snapshot_sha256, canonical_state_sha256=canonical_state_sha256, candidates=candidates)
    plan = {"schema_version": PLAN_SCHEMA_VERSION, "planner_version": PLANNER_VERSION, "legacy_snapshot_sha256": snapshot_sha256, "canonical_state_sha256": canonical_state_sha256, "candidate_set_sha256": candidate_set_sha256, **roster_provenance, "source_database_identity": index["database"], "source_alembic_revision": canonical_state["source_alembic_revision"], "candidates": candidates, "case_links": case_links, "certificate_links": certificate_links, "summary_counts": {"candidates": _counts(candidates), "cases": _counts(case_links), "certificates": _counts(certificate_links)}, "transformation_actions": [], "scope_actions": [], "certificate_relationship_actions": []}
    plan["plan_sha256"] = plan_digest(plan)
    return plan
