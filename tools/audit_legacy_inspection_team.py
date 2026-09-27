"""Read-only B5B contract audit for legacy ``db.ktra`` inspection teams."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
import re
import unicodedata
from typing import Any

from backend.app.domain.inspection_contracts import TEAM_IDENTITY_KINDS, role_code_for_sort_order
from backend.app.domain.legacy_db_ktra_reconciliation import parse_legacy_team
from backend.app.domain.legacy_inspection_team import ORG_REPRESENTATIVE_ALIASES, _substantive
from backend.app.domain.legacy_snapshot_v2 import SCHEMA_VERSION, snapshot_bytes
from backend.app.domain.legacy_ttvien_personnel import SOURCE_SHEET as PERSONNEL_SOURCE_SHEET
from backend.app.domain.legacy_ttvien_personnel import resolve_team_member_token
from backend.app.domain.phase2_import import parse_int


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "artifacts" / "legacy_audit" / "inspection_team_legacy_discovery_v3.json"
SOURCE_FIELD = "T.tra viên"
TEAM_SOURCE_SHEET = "db.ktra"
COMPLETE_CATALOG_MODE = "COMPLETE_B5B_CATALOG"


def _finding_codes(component: str, result: dict[str, Any]) -> list[str]:
    """Return deterministic machine-readable finding identifiers for one component."""
    codes = result.get("failure_counts", {})
    if isinstance(codes, dict) and codes:
        return [f"{component}:{code}" for code in sorted(codes)]
    return [f"{component}:{result.get('status', 'UNKNOWN')}" ]


def _audit_result(components: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Apply the B5C gate without treating unavailable optional evidence as PASS."""
    blocking: list[str] = []
    incomplete: list[str] = []
    for name, result in sorted(components.items()):
        status = result.get("status")
        if status == "PASS":
            continue
        if status == "INCOMPLETE_EVIDENCE":
            incomplete.extend(_finding_codes(name, result))
        else:
            blocking.extend(_finding_codes(name, result))
    status = "FAIL" if blocking else "INCOMPLETE_EVIDENCE" if incomplete else "PASS"
    return {
        "status": status,
        "precedence": ["FAIL", "INCOMPLETE_EVIDENCE", "PASS"],
        "blocking_findings": blocking,
        "incomplete_evidence": incomplete,
        "evaluated_components": sorted(components),
        "cli_exit_policy": "PARTIAL_OBSERVATION permits INCOMPLETE_EVIDENCE with exit 0; COMPLETE_B5B_CATALOG fails closed with nonzero exit",
    }


def _sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _diagnostic_fold(value: str) -> str:
    """Aggregate-only similarity key; this is never an identity resolver."""
    value = value.replace("Đ", "D").replace("đ", "d")
    value = "".join(char for char in unicodedata.normalize("NFKD", value) if not unicodedata.combining(char))
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))


def parse_source_team(value: object) -> dict[str, Any]:
    """Thin diagnostic adapter over the canonical db.ktra team parser."""
    parsed = parse_legacy_team(value)
    state = parsed["state"]
    if state != "KNOWN":
        return {"family": state, "raw": parsed["raw"], "members": [], "split_state": state}
    return {
        "family": "SINGLE_NAME" if len(parsed["members"]) == 1 else "COMMA_DELIMITED",
        "raw": parsed["raw"], "split_state": state,
        "members": [
            {
                "ordinal": member["ordinal"], "raw_name": member["display_name"],
                "role_code": member["role_code"], "diagnostic_similarity_key": _diagnostic_fold(member["display_name"]),
            }
            for member in parsed["members"]
        ],
    }


def select_snapshot_v2_db_ktra_rows(snapshot: dict[str, Any], *, expected_snapshot_sha256: str) -> list[dict[str, Any]]:
    if snapshot.get("schema_version") != SCHEMA_VERSION or sha256(snapshot_bytes(snapshot)).hexdigest() != expected_snapshot_sha256:
        raise ValueError("inspection-team audit Snapshot V2 provenance guard failed")
    sheets = snapshot.get("sheets")
    if not isinstance(sheets, list):
        raise ValueError("inspection-team audit Snapshot V2 sheets are malformed")
    matches = [sheet for sheet in sheets if isinstance(sheet, dict) and sheet.get("sheet_name") == TEAM_SOURCE_SHEET]
    if len(matches) != 1 or not isinstance(matches[0].get("raw_rows"), list):
        raise ValueError("inspection-team audit Snapshot V2 is missing db.ktra raw rows")
    raw_rows = matches[0]["raw_rows"]
    row_numbers: set[int] = set()
    for row in raw_rows:
        if not isinstance(row, dict) or not isinstance(row.get("source_row_number"), int) or row["source_row_number"] < 1 or not isinstance(row.get("cells"), list):
            raise ValueError("inspection-team audit Snapshot V2 row provenance is malformed")
        if row["source_row_number"] in row_numbers:
            raise ValueError("inspection-team audit Snapshot V2 row provenance is duplicated")
        row_numbers.add(row["source_row_number"])
        columns: set[int] = set()
        for cell in row["cells"]:
            if not isinstance(cell, dict) or not isinstance(cell.get("column_ordinal"), int) or cell["column_ordinal"] < 1 or cell["column_ordinal"] in columns:
                raise ValueError("inspection-team audit Snapshot V2 cell provenance is malformed")
            columns.add(cell["column_ordinal"])
    header = next((row for row in raw_rows if row["source_row_number"] == 4), None)
    if header is None:
        raise ValueError("inspection-team audit Snapshot V2 db.ktra header is missing")
    required = ("ID", "LOẠI KT", "ID CƠ SỞ", SOURCE_FIELD)
    headers: dict[str, int] = {}
    for name in required:
        values = [cell.get("column_ordinal") for cell in header["cells"] if cell.get("raw_value") == name]
        if len(values) != 1 or not isinstance(values[0], int):
            raise ValueError("inspection-team audit Snapshot V2 db.ktra fields are missing or duplicated")
        headers[name] = values[0]
    if not headers:
        raise ValueError("inspection-team audit Snapshot V2 db.ktra fields are missing")
    result = []
    for row in raw_rows:
        if row["source_row_number"] <= 4:
            continue
        values = {cell.get("column_ordinal"): cell.get("raw_value") for cell in row["cells"] if isinstance(cell, dict)}
        if parse_int(values.get(headers["ID"])) is None or not _substantive(values.get(headers["LOẠI KT"])) or not _substantive(values.get(headers["ID CƠ SỞ"])):
            continue
        result.append({"ID": values.get(headers["ID"]), SOURCE_FIELD: values.get(headers[SOURCE_FIELD]), "source_row_number": row["source_row_number"], "_b5b_eligible": True})
    return result


def _load_optional_records(path: Path | None) -> list[dict[str, Any]] | None:
    if path is None:
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
        raise ValueError("optional audit input must be a JSON list of objects")
    return payload


def _source_occurrences(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    occurrences: list[dict[str, Any]] = []
    for input_record_ordinal, row in enumerate(rows, start=1):
        parsed = parse_source_team(row.get(SOURCE_FIELD))
        legacy_id = parse_int(row.get("ID", ""))
        source_row_number = row.get("source_row_number")
        has_source_row = isinstance(source_row_number, int) and source_row_number > 0
        for member in parsed["members"]:
            occurrences.append({
                "legacy_inspection_id": legacy_id,
                "source_row_number": source_row_number if has_source_row else None,
                "input_record_ordinal": input_record_ordinal,
                "source_ordinal": member["ordinal"],
                "raw_name": member["raw_name"],
                "role_code": member["role_code"],
                "team_source_provenance": (
                    {"source_sheet": TEAM_SOURCE_SHEET, "source_row_number": source_row_number}
                    if has_source_row
                    else {"source_sheet": TEAM_SOURCE_SHEET, "input_record_ordinal": input_record_ordinal,
                          "source_row_provenance": "UNAVAILABLE_FROM_INPUT"}
                ),
            })
    return occurrences


def _approved_roster(
    records: list[dict[str, Any]] | None, *, expected_snapshot_sha256: str,
) -> list[dict[str, Any]] | None:
    if records is None:
        return None
    roster: list[dict[str, Any]] = []
    provenance_keys: set[tuple[str, str, int]] = set()
    for record in records:
        required = ("legacy_raw_full_name", "cleaned_full_name", "pct_marker", "star_marker", "snapshot_sha256", "source_row_number")
        source_row_number = record.get("source_row_number")
        if (
            any(key not in record for key in required)
            or record.get("source_sheet") != PERSONNEL_SOURCE_SHEET
            or record.get("snapshot_sha256") != expected_snapshot_sha256
            or not isinstance(source_row_number, int)
            or source_row_number < 1
        ):
            raise ValueError("identity audit requires approved TTviên personnel-plan records")
        key = (record["snapshot_sha256"], record["source_sheet"], source_row_number)
        if key in provenance_keys:
            raise ValueError("identity audit personnel provenance is duplicated")
        provenance_keys.add(key)
        roster.append(record)
    return roster


def _identity_audit(occurrences: list[dict[str, Any]], roster_records: list[dict[str, Any]] | None) -> dict[str, Any]:
    if roster_records is None:
        return {
            "status": "UNAVAILABLE_NO_APPROVED_TTVIEN_PERSONNEL_PLAN",
            "canonical_resolution_owner": "legacy_ttvien_personnel.resolve_team_member_token",
        }
    counts: Counter[str] = Counter()
    resolved: list[dict[str, Any]] = []
    for occurrence in occurrences:
        classification, record = resolve_team_member_token(occurrence["raw_name"], roster_records)
        counts[classification] += 1
        resolved.append({
            **occurrence,
            "identity_resolution": classification,
            "person_source_provenance": None if record is None else {
                "snapshot_sha256": record["snapshot_sha256"],
                "source_sheet": record["source_sheet"],
                "source_row_number": record["source_row_number"],
            },
        })
    return {
        "status": "COMPUTED_FROM_APPROVED_TTVIEN_PERSONNEL_PLAN",
        "canonical_resolution_owner": "legacy_ttvien_personnel.resolve_team_member_token",
        "match_counts": dict(sorted(counts.items())),
        "resolved_occurrences": resolved,
        "forbidden_identity_inference": ["accent_folding", "abbreviation_matching", "substring_matching", "fuzzy_matching"],
    }


def _identity_invariants(members: list[dict[str, Any]] | None) -> dict[str, Any]:
    if members is None:
        return {"status": "UNAVAILABLE_NO_CANONICAL_MEMBER_INPUT"}
    failures: Counter[str] = Counter()
    counts: Counter[str] = Counter()
    for member in members:
        kind = member.get("identity_kind")
        profile, person, catalog = member.get("inspector_profile_id"), member.get("person_id"), member.get("participant_catalog_id")
        display, role, order = member.get("display_name"), member.get("role_code"), member.get("sort_order")
        counts[str(kind)] += 1
        if kind is None:
            if catalog or bool(profile) == bool(person):
                failures["INVALID_COMPATIBILITY_IDENTITY_SHAPE"] += 1
            elif profile:
                if member.get("profile_exists") is not True: failures["ORPHAN_INSPECTOR_PROFILE" if member.get("profile_exists") is False else "MISSING_PROFILE_EXISTENCE_EVIDENCE"] += 1
                if member.get("profile_is_active") is not True: failures["INACTIVE_INSPECTOR_PROFILE" if member.get("profile_is_active") is False else "MISSING_PROFILE_ACTIVITY_EVIDENCE"] += 1
            elif person:
                if member.get("person_exists") is not True: failures["ORPHAN_PERSON" if member.get("person_exists") is False else "MISSING_PERSON_EXISTENCE_EVIDENCE"] += 1
                if member.get("person_is_inspector_owned") is not False: failures["INSPECTOR_BYPASS_VIA_PERSON" if member.get("person_is_inspector_owned") is True else "MISSING_PERSON_OWNERSHIP_EVIDENCE"] += 1
        elif kind not in TEAM_IDENTITY_KINDS:
            failures["INVALID_IDENTITY_KIND"] += 1
        elif kind == "INSPECTOR_PROFILE" and (not profile or person or catalog):
            failures["INVALID_INSPECTOR_PROFILE_SHAPE"] += 1
        elif kind == "LEGACY_PERSON" and (profile or person or catalog):
            failures["INVALID_LEGACY_PERSON_SHAPE"] += 1
        elif kind == "ORGANIZATION_REPRESENTATIVE" and (not catalog or profile or person):
            failures["INVALID_ORGANIZATION_REPRESENTATIVE_SHAPE"] += 1
        if not isinstance(display, str) or not display.strip():
            failures["MISSING_DISPLAY_NAME"] += 1
        if not isinstance(order, int) or order < 1 or role != role_code_for_sort_order(order):
            failures["INVALID_ROLE_OR_SORT_ORDER"] += 1
        if kind == "INSPECTOR_PROFILE":
            if member.get("profile_exists") is not True: failures["ORPHAN_INSPECTOR_PROFILE" if member.get("profile_exists") is False else "MISSING_PROFILE_EXISTENCE_EVIDENCE"] += 1
            if member.get("profile_is_active") is not True: failures["INACTIVE_INSPECTOR_PROFILE" if member.get("profile_is_active") is False else "MISSING_PROFILE_ACTIVITY_EVIDENCE"] += 1
        if kind == "INSPECTOR_PROFILE" and member.get("person_is_inspector_owned") and person:
            failures["INSPECTOR_BYPASS_VIA_PERSON"] += 1
        if kind == "ORGANIZATION_REPRESENTATIVE":
            if member.get("participant_catalog_exists") is not True: failures["ORPHAN_PARTICIPANT_CATALOG" if member.get("participant_catalog_exists") is False else "MISSING_CATALOG_EXISTENCE_EVIDENCE"] += 1
            if member.get("participant_catalog_is_active") is not True: failures["INACTIVE_PARTICIPANT_CATALOG" if member.get("participant_catalog_is_active") is False else "MISSING_CATALOG_ACTIVITY_EVIDENCE"] += 1
            if member.get("participant_catalog_kind") != "ORGANIZATION_REPRESENTATIVE": failures["INVALID_PARTICIPANT_CATALOG_KIND" if member.get("participant_catalog_kind") is not None else "MISSING_CATALOG_KIND_EVIDENCE"] += 1
        if person and member.get("person_exists") is False:
            failures["ORPHAN_PERSON"] += 1
    return {
        "status": "PASS" if not failures else "FAIL" if any(not key.startswith("MISSING_") for key in failures) else "INCOMPLETE_EVIDENCE",
        "member_identity_counts": dict(sorted(counts.items())),
        "failure_counts": dict(sorted(failures.items())),
        "contract": {
            "INSPECTOR_PROFILE": "inspector_profile_id_only__active_for_runtime",
            "LEGACY_PERSON": "historical_read_only__no_runtime_identity_fk",
            "ORGANIZATION_REPRESENTATIVE": "participant_catalog_id_only__active_for_runtime",
            "COMPATIBILITY_IDENTITY_KIND_NULL": "exactly_one_of_inspector_profile_id_or_generic_non_inspector_person_id",
        },
    }


def _catalog_audit(catalog_records: list[dict[str, Any]] | None, *, mode: str) -> dict[str, Any]:
    if catalog_records is None:
        return {"status": "UNAVAILABLE_NO_CATALOG_INPUT"}
    failures: Counter[str] = Counter()
    identifiers: set[str] = set()
    codes: set[str] = set()
    for record in catalog_records:
        identifier = record.get("id")
        code = record.get("code")
        if not isinstance(identifier, str) or not identifier.strip():
            failures["MISSING_CATALOG_ID"] += 1
        elif identifier in identifiers:
            failures["DUPLICATE_CATALOG_ID"] += 1
        else:
            identifiers.add(identifier)
        if not isinstance(code, str) or not code.strip():
            failures["MISSING_CATALOG_CODE"] += 1
        elif code in codes:
            failures["DUPLICATE_CATALOG_CODE"] += 1
        else:
            codes.add(code)
        if record.get("participant_kind") != "ORGANIZATION_REPRESENTATIVE":
            failures["INVALID_PARTICIPANT_KIND"] += 1
        if not isinstance(record.get("display_name"), str) or not record["display_name"].strip():
            failures["MISSING_DISPLAY_NAME"] += 1
        if not isinstance(record.get("is_active"), bool):
            failures["ACTIVITY_NOT_EXPLICITLY_OBSERVED"] += 1
        elif record["is_active"] is False:
            failures["OBSERVED_INACTIVE_CATALOG"] += 1
    expected_codes = {item["code"]: item["display_name"] for item in ORG_REPRESENTATIVE_ALIASES.values()}
    observed_seed_codes = {
        record["code"]: record.get("display_name")
        for record in catalog_records
        if isinstance(record.get("code"), str) and record["code"] in expected_codes
    }
    if mode == "COMPLETE_B5B_CATALOG":
        for code, display_name in expected_codes.items():
            record = next((item for item in catalog_records if item.get("code") == code), None)
            if record is None: failures["MISSING_CANONICAL_SEED"] += 1
            elif record.get("display_name") != display_name: failures["CANONICAL_SEED_DISPLAY_MISMATCH"] += 1
            elif record.get("is_active") is not True: failures["INACTIVE_CANONICAL_SEED"] += 1
    return {
        "status": "PASS" if not failures else "OBSERVED_INACTIVE_NOT_RUNTIME_SELECTABLE" if mode == "PARTIAL_OBSERVATION" and set(failures) == {"OBSERVED_INACTIVE_CATALOG"} else "FAIL",
        "catalog_count": len(catalog_records),
        "mode": mode,
        "failure_counts": dict(sorted(failures.items())),
        "canonical_seed_contract_reference": "legacy_inspection_team.ORG_REPRESENTATIVE_ALIASES",
        "canonical_seed_observation": {
            "expected_codes": expected_codes,
            "observed_codes": observed_seed_codes,
        },
    }


def _alias_audit(
    catalog_records: list[dict[str, Any]] | None, alias_records: list[dict[str, Any]] | None, *, mode: str,
) -> dict[str, Any]:
    if alias_records is None:
        return {"status": "UNAVAILABLE_NO_ALIAS_INPUT"}
    catalogs = {
        record["id"]: record
        for record in catalog_records or []
        if isinstance(record.get("id"), str) and record["id"].strip()
    }
    failures: Counter[str] = Counter()
    provenance_keys: set[tuple[str, str, str]] = set()
    for alias in alias_records:
        participant_id = alias.get("participant_id")
        participant = catalogs.get(participant_id) if isinstance(participant_id, str) else None
        if not isinstance(participant_id, str) or not participant_id.strip():
            failures["INVALID_ALIAS_PARTICIPANT_ID"] += 1
        if participant is None:
            failures["ORPHAN_ALIAS_PARTICIPANT"] += 1
        elif participant.get("participant_kind") != "ORGANIZATION_REPRESENTATIVE":
            failures["ALIAS_TARGET_NOT_ORGANIZATION_REPRESENTATIVE"] += 1
        elif participant.get("is_active") is not True:
            failures["ALIAS_TARGET_NOT_ACTIVE"] += 1
        for field, expected in (("source_system", "legacy_workbook"), ("source_sheet", TEAM_SOURCE_SHEET)):
            if not isinstance(alias.get(field), str) or not alias[field].strip():
                failures[f"MISSING_{field.upper()}"] += 1
            elif alias[field] != expected:
                failures[f"INVALID_{field.upper()}"] += 1
        value = alias.get("source_value")
        value_hash = alias.get("source_value_hash")
        if not isinstance(value, str) or not value:
            failures["MISSING_RAW_ALIAS"] += 1
        if not isinstance(value_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", value_hash):
            failures["INVALID_SOURCE_VALUE_HASH"] += 1
        elif isinstance(value, str) and sha256(value.encode("utf-8")).hexdigest() != value_hash:
            failures["SOURCE_VALUE_HASH_MISMATCH"] += 1
        expected_catalog = ORG_REPRESENTATIVE_ALIASES.get(value) if isinstance(value, str) else None
        if expected_catalog is not None and participant is not None:
            if participant.get("code") != expected_catalog["code"]:
                failures["CANONICAL_RAW_ALIAS_ROUTED_TO_WRONG_CATALOG"] += 1
            if participant.get("display_name") != expected_catalog["display_name"]:
                failures["CANONICAL_RAW_ALIAS_DISPLAY_MISMATCH"] += 1
        key = (str(alias.get("source_system")), str(alias.get("source_sheet")), str(value_hash))
        if key in provenance_keys:
            failures["DUPLICATE_ALIAS_PROVENANCE"] += 1
        provenance_keys.add(key)
    if mode == "COMPLETE_B5B_CATALOG":
        for raw, expected in ORG_REPRESENTATIVE_ALIASES.items():
            matches = [item for item in alias_records if item.get("source_value") == raw]
            if len(matches) != 1:
                failures["MISSING_OR_DUPLICATE_CANONICAL_RAW_ALIAS"] += 1
    return {
        "status": "PASS" if not failures else "FAIL",
        "alias_count": len(alias_records),
        "mode": mode,
        "failure_counts": dict(sorted(failures.items())),
        "raw_source_evidence_policy": "source_value is preserved exactly; it is not normalized into catalog display_name",
    }


def _duplicate_occurrence_audit(occurrences: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[tuple[str, int, str], list[dict[str, Any]]] = defaultdict(list)
    for occurrence in occurrences:
        source_key = occurrence["team_source_provenance"]
        if "source_row_number" in source_key:
            key = ("SOURCE_ROW", source_key["source_row_number"], occurrence["raw_name"])
        else:
            key = ("INPUT_RECORD", source_key["input_record_ordinal"], occurrence["raw_name"])
        groups[key].append(occurrence)
    duplicates = [
        {
            "source_record_key": {"kind": key[0], "value": key[1]}, "raw_name": key[2], "occurrence_count": len(values),
            "source_occurrences": [{"source_row_number": value["source_row_number"], "source_ordinal": value["source_ordinal"]} for value in values],
        }
        for key, values in sorted(groups.items())
        if len(values) > 1
    ]
    return {
        "policy": "PRESERVE_APPROVED_SOURCE_OCCURRENCES",
        "duplicate_group_count": len(duplicates),
        "duplicate_occurrence_count": sum(item["occurrence_count"] for item in duplicates),
        "groups": duplicates,
    }


def build_discovery(
    rows: list[dict[str, Any]], *, snapshot_sha256: str,
    source_provenance: dict[str, Any] | None = None,
    identity_records: list[dict[str, Any]] | None = None,
    case_records: list[dict[str, Any]] | None = None,
    canonical_member_records: list[dict[str, Any]] | None = None,
    catalog_records: list[dict[str, Any]] | None = None,
    alias_records: list[dict[str, Any]] | None = None,
    catalog_mode: str = "PARTIAL_OBSERVATION",
) -> dict[str, Any]:
    """Observe source and explicit canonical inputs without writes or heuristic identity selection."""
    if catalog_mode not in {"PARTIAL_OBSERVATION", COMPLETE_CATALOG_MODE}:
        raise ValueError("catalog audit mode is invalid")
    if catalog_mode == COMPLETE_CATALOG_MODE and (catalog_records is None or alias_records is None):
        raise ValueError("complete B5B catalog audit requires catalog and alias evidence")
    eligible_input_rows = [row for row in rows if row.get("_b5b_eligible", True) is True]
    parsed_rows = [{"legacy_inspection_id": parse_int(row.get("ID", "")), "parsed": parse_source_team(row.get(SOURCE_FIELD))} for row in eligible_input_rows]
    families = Counter(item["parsed"]["family"] for item in parsed_rows)
    occurrences = _source_occurrences(eligible_input_rows)
    diagnostic_groups: dict[str, set[str]] = defaultdict(set)
    for occurrence in occurrences:
        diagnostic_groups[_diagnostic_fold(occurrence["raw_name"])].add(occurrence["raw_name"])
    case_counts: Counter[str] = Counter()
    if case_records is not None:
        indexed: dict[int, list[str]] = defaultdict(list)
        for record in case_records:
            if not isinstance(record.get("legacy_inspection_id"), int) or not isinstance(record.get("case_id"), str) or not record["case_id"]:
                raise ValueError("case records require integer legacy_inspection_id and nonblank case_id")
            indexed[record["legacy_inspection_id"]].append(record["case_id"])
        for legacy_id in {item["legacy_inspection_id"] for item in parsed_rows if item["legacy_inspection_id"] is not None}:
            case_counts["EXACTLY_ONE_CASE" if len(indexed[legacy_id]) == 1 else "NO_CASE" if not indexed[legacy_id] else "AMBIGUOUS_CASE"] += 1
    provenance = {"source_sheet": TEAM_SOURCE_SHEET, "source_field": SOURCE_FIELD, "snapshot_sha256": snapshot_sha256, "input_rows": len(rows), "database_mutated": False}
    if source_provenance:
        provenance.update(source_provenance)
    invariant_audit = _identity_invariants(canonical_member_records)
    catalog_audit = _catalog_audit(catalog_records, mode=catalog_mode)
    alias_audit = _alias_audit(catalog_records, alias_records, mode=catalog_mode)
    components: dict[str, dict[str, Any]] = {}
    if canonical_member_records is not None:
        components["identity_invariants"] = invariant_audit
    if catalog_records is not None:
        components["catalog_audit"] = catalog_audit
    if alias_records is not None:
        components["alias_audit"] = alias_audit
    audit_result = _audit_result(components)
    eligible_rows = len(eligible_input_rows)
    known_team_rows = sum(item["parsed"]["split_state"] == "KNOWN" for item in parsed_rows)
    unresolved_team_rows = len(eligible_input_rows) - known_team_rows
    return {
        "audit_version": "legacy-inspection-team-audit/v3",
        "database_mutated": False,
        "source_contract": {
            "team_occurrence_provenance": TEAM_SOURCE_SHEET,
            "person_identity_provenance": PERSONNEL_SOURCE_SHEET,
            "identity_resolution_owner": "legacy_ttvien_personnel.resolve_team_member_token",
            "identity_resolution_order": ["EXACT_RAW_MATCH", "EXACT_AFTER_APPROVED_MARKER_EQUIVALENCE"],
            "diagnostic_similarity_is_not_identity_resolution": True,
        },
        "provenance": provenance,
        "team_counts": {
            "b5b_eligible_source_rows": eligible_rows,
            "b5b_plannable_known_team_rows": known_team_rows,
            "missing_or_unresolved_team_rows": unresolved_team_rows,
            "member_occurrences": len(occurrences),
            "source_family_counts": dict(sorted(families.items())),
        },
        "member_identity_counts": invariant_audit.get("member_identity_counts"),
        "identity_invariants": invariant_audit,
        "catalog_audit": catalog_audit,
        "alias_audit": alias_audit,
        "duplicate_occurrence_audit": _duplicate_occurrence_audit(occurrences),
        "provenance_audit": {"team_occurrences": occurrences, "person_identity_provenance_source": PERSONNEL_SOURCE_SHEET},
        "orphan_audit": {
            "status": "UNAVAILABLE_NO_CANONICAL_MEMBER_INPUT" if canonical_member_records is None else "INCLUDED_IN_IDENTITY_INVARIANTS",
            "failure_codes": ["ORPHAN_INSPECTOR_PROFILE", "ORPHAN_PERSON", "ORPHAN_PARTICIPANT_CATALOG"],
        },
        "identity_audit": _identity_audit(occurrences, _approved_roster(identity_records, expected_snapshot_sha256=snapshot_sha256)),
        "canonical_case_coverage": {"status": "UNAVAILABLE_NO_EXPLICIT_CASE_IDENTITY_INPUT" if case_records is None else "COMPUTED_FROM_EXPLICIT_CASE_IDENTITY_INPUT", "coverage_counts": None if case_records is None else dict(sorted(case_counts.items()))},
        "diagnostic_similarity": {"purpose": "aggregate discovery only; never used to select a canonical identity", "groups_with_distinct_raw_tokens": {key: sorted(values) for key, values in sorted(diagnostic_groups.items()) if len(values) > 1}},
        "runtime_contract_audit": {
            "persisted_discriminated_identity_kinds": sorted(TEAM_IDENTITY_KINDS),
            "runtime_writable_discriminated_kinds": ["INSPECTOR_PROFILE", "ORGANIZATION_REPRESENTATIVE"],
            "runtime_compatibility_path": "identity_kind_null__exactly_one_profile_or_generic_non_inspector_person",
            "legacy_person": "HISTORICAL_READ_ONLY",
            "inactive_inspector_bypass": "REJECT_PERSON_ID_WHEN_PERSON_HAS_INSPECTOR_PROFILE",
            "arbitrary_free_text_participant": "FORBIDDEN",
        },
        "frontend_backend_contract_audit": {
            "status": "CONTRACT_REFERENCED_NOT_RUNTIME_INTROSPECTED",
            "contract_references": ["inspection_contracts.validate_runtime_team_member", "workflow._validate_team_member_identities", "catalog.list_inspection_team_identity_options"],
            "frontend_must_not_infer_identity_or_activity": True,
            "stale_discovery_findings_reused": False,
        },
        "audit_result": audit_result,
        "unresolved_findings": audit_result["blocking_findings"] + audit_result["incomplete_evidence"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only B5B inspection-team audit.")
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--expected-snapshot-sha256", required=True)
    parser.add_argument("--git-commit", required=True)
    parser.add_argument("--git-blob-sha", required=True)
    parser.add_argument("--working-tree-snapshot", type=Path, required=True)
    parser.add_argument("--identity-input", type=Path, help="Approved B2 TTviên personnel-plan records.")
    parser.add_argument("--case-input", type=Path)
    parser.add_argument("--canonical-member-input", type=Path)
    parser.add_argument("--catalog-input", type=Path)
    parser.add_argument("--alias-input", type=Path)
    parser.add_argument("--complete-b5b-catalog", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    snapshot = args.snapshot.resolve()
    snapshot_sha256 = _sha256(snapshot)
    if snapshot_sha256 != args.expected_snapshot_sha256.lower():
        raise ValueError("explicit snapshot does not match expected canonical SHA256")
    working_tree_snapshot = args.working_tree_snapshot.resolve()
    report = build_discovery(
        select_snapshot_v2_db_ktra_rows(json.loads(snapshot.read_text(encoding="utf-8")), expected_snapshot_sha256=snapshot_sha256), snapshot_sha256=snapshot_sha256,
        source_provenance={
            "declared_git_commit": args.git_commit,
            "declared_git_blob_sha": args.git_blob_sha,
            "provided_working_tree_snapshot_sha256": _sha256(working_tree_snapshot),
            "git_provenance_verification": "NOT_VERIFIED_BY_THIS_TOOL",
            "semantic_statistics_source": "CANONICAL_SNAPSHOT_ONLY",
        },
        identity_records=_load_optional_records(args.identity_input), case_records=_load_optional_records(args.case_input),
        canonical_member_records=_load_optional_records(args.canonical_member_input), catalog_records=_load_optional_records(args.catalog_input), alias_records=_load_optional_records(args.alias_input),
        catalog_mode="COMPLETE_B5B_CATALOG" if args.complete_b5b_catalog else "PARTIAL_OBSERVATION",
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(f"SHA256={_sha256(args.output)}")
    if report["audit_result"]["status"] == "FAIL":
        return 2
    if report["audit_result"]["status"] == "INCOMPLETE_EVIDENCE" and args.complete_b5b_catalog:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
