"""Read-only TTviên personnel projection from the authoritative Snapshot V2."""
from __future__ import annotations

from hashlib import sha256
import re
from typing import Any

from backend.app.domain.legacy_snapshot_v2 import snapshot_bytes


ROSTER_GROUPS = (
    (6, 53, "DRUG_ADMINISTRATION_AND_TRADITIONAL_MEDICINE"),
    (59, 89, "NATIONAL_INSTITUTE_OF_DRUG_QUALITY_CONTROL"),
    (95, 143, "HO_CHI_MINH_CITY_DRUG_QUALITY_CONTROL_INSTITUTE"),
    (148, 176, "NATIONAL_INSTITUTE_FOR_VACCINE_AND_BIOLOGICALS_CONTROL"),
    (182, 384, "PROVINCIAL_HEALTH_DEPARTMENTS"),
)
SOURCE_SHEET = "TTviên"
PCT_PREFIX = "PCT."


def _cell(row: dict[str, Any], column: int) -> Any:
    for cell in row.get("cells", []):
        if cell.get("column_ordinal") == column:
            return cell.get("raw_value")
    raise ValueError(f"TTviên row {row.get('source_row_number')} is missing column {column}")


def _group_for_row(row_number: int) -> str | None:
    matches = [group for first, last, group in ROSTER_GROUPS if first <= row_number <= last]
    if len(matches) > 1:
        raise ValueError(f"TTviên row {row_number} belongs to multiple roster groups")
    return matches[0] if matches else None


def split_approved_name_markers(raw_full_name: str) -> tuple[str, bool, bool]:
    """Remove only the two approved presentation markers, never normalize names."""
    value = raw_full_name
    pct_marker = value.startswith(PCT_PREFIX)
    if pct_marker:
        value = value[len(PCT_PREFIX):].lstrip()
    star_marker = value.endswith("*")
    if star_marker:
        value = value[:-1].rstrip()
    if not value:
        raise ValueError("TTviên name becomes empty after approved marker handling")
    return value, pct_marker, star_marker


def _source_provenance_hash(snapshot_sha256: str, row_number: int) -> str:
    return sha256(f"{snapshot_sha256}:{SOURCE_SHEET}:{row_number}".encode("utf-8")).hexdigest()


def _substantive(value: object) -> bool:
    return value is not None and (not isinstance(value, str) or value.strip() not in {"", "-", "???"})


def build_personnel_plan(snapshot: dict[str, Any], *, expected_snapshot_sha256: str) -> dict[str, Any]:
    if snapshot.get("schema_version") != "legacy-workbook-snapshot/v2":
        raise ValueError("TTviên planner requires Snapshot V2")
    if not re.fullmatch(r"[0-9a-f]{64}", expected_snapshot_sha256) or sha256(snapshot_bytes(snapshot)).hexdigest() != expected_snapshot_sha256:
        raise ValueError("TTviên planner snapshot provenance guard failed")
    sheet = next((item for item in snapshot.get("sheets", []) if item.get("sheet_name") == SOURCE_SHEET), None)
    if sheet is None:
        raise ValueError("Snapshot V2 is missing TTviên")

    records: list[dict[str, Any]] = []
    classifications: dict[str, int] = {"IMPORT_CANDIDATE": 0, "SOURCE_CONFLICT": 0, "SOURCE_UNRESOLVED": 0, "NON_PERSONNEL_ROW": 0, "LAYOUT_ROW": 0}
    for row in sheet.get("raw_rows", []):
        row_number = row.get("source_row_number")
        if not isinstance(row_number, int):
            raise ValueError("TTviên source row number is invalid")
        group = _group_for_row(row_number)
        raw_name = _cell(row, 6)
        honorific = _cell(row, 4)
        if group is None:
            classifications["LAYOUT_ROW"] += 1
            continue
        if not isinstance(honorific, str) or not honorific.strip() or not isinstance(raw_name, str) or not raw_name.strip():
            classifications["NON_PERSONNEL_ROW"] += 1
            continue
        cleaned_name, pct_marker, star_marker = split_approved_name_markers(raw_name)
        inactive_marker = _cell(row, 14)
        if inactive_marker not in (None, "", "x"):
            raise ValueError(f"TTviên row {row_number} has unsupported inactive marker")
        records.append({
            "classification": "IMPORT_CANDIDATE",
            "source_sheet": SOURCE_SHEET,
            "snapshot_sha256": expected_snapshot_sha256,
            "source_row_number": row_number,
            "source_group": group,
            "source_ordinal": _cell(row, 3),
            "raw_honorific": honorific,
            "raw_qualification": _cell(row, 5),
            "legacy_raw_full_name": raw_name,
            "cleaned_full_name": cleaned_name,
            "pct_marker": pct_marker,
            "star_marker": star_marker,
            "position": _cell(row, 7),
            "organizational_unit": _cell(row, 8),
            "legacy_initial": _cell(row, 12),
            "professional_specialty": _cell(row, 16),
            "is_active": inactive_marker != "x",
            "inactive_marker_raw": inactive_marker,
            "sensitive_field_presence": {"citizen_identity": _substantive(_cell(row, 9)), "citizen_identity_issue_date": _substantive(_cell(row, 10)), "citizen_identity_issuing_place": _substantive(_cell(row, 11)), "payment": _substantive(_cell(row, 13)), "airline_contact_like": _substantive(_cell(row, 15))},
            "source_provenance_hash": _source_provenance_hash(expected_snapshot_sha256, row_number),
        })
        classifications["IMPORT_CANDIDATE"] += 1
    records.sort(key=lambda item: item["source_row_number"])
    if len(records) != 358 or len({item["source_row_number"] for item in records}) != 358:
        raise ValueError("TTviên eligible-person invariant failed")
    return {"schema_version": "ttvien-personnel-source-plan/v1", "snapshot_sha256": expected_snapshot_sha256, "database_accessed": False, "records": records, "classification_counts": classifications, "c16_contract": {"source_header": "Chuyên môn", "business_semantic": "inspector professional specialty", "nonblank_count": sum(_substantive(item["professional_specialty"]) for item in records), "distinct_count": len({item["professional_specialty"] for item in records if _substantive(item["professional_specialty"])}), "canonical_owner": "InspectorProfile", "canonical_field": "professional_specialty", "datatype": "String(255)", "migration_status": "IMPORT_TYPED", "filter_query_usage": "future inspector-specialty workflow filters", "raw_preservation": "preserve exact source value"}, "separate_regions": {"travel_vendor": {"source_sheet": SOURCE_SHEET, "columns": [18, 19, 20, 21, 22], "row_start": 6, "row_end": 14, "migration_status": "SEPARATE_DOMAIN"}}, "group_counts": {group: sum(item["source_group"] == group for item in records) for _, _, group in ROSTER_GROUPS}, "marker_counts": {"pct": sum(item["pct_marker"] for item in records), "star": sum(item["star_marker"] for item in records)}, "inactive_count": sum(not item["is_active"] for item in records), "sensitive_field_presence_counts": {key: sum(item["sensitive_field_presence"][key] for item in records) for key in records[0]["sensitive_field_presence"]}}


def preview_team_crosswalk(snapshot: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    """Read-only team preview; cleaned names alone can never select a record."""
    sheet = next((item for item in snapshot.get("sheets", []) if item.get("sheet_name") == "db.ktra"), None)
    if sheet is None:
        raise ValueError("Snapshot V2 is missing db.ktra")
    header = next((row for row in sheet["raw_rows"] if row.get("source_row_number") == 4), None)
    if header is None:
        raise ValueError("db.ktra header row is missing")
    team_column = next((cell.get("column_ordinal") for cell in header["cells"] if cell.get("raw_value") == "T.tra viên"), None)
    if team_column is None:
        raise ValueError("db.ktra T.tra viên column is missing")
    raw_index: dict[str, list[dict[str, Any]]] = {}
    cleaned_index: dict[str, list[dict[str, Any]]] = {}
    for record in plan["records"]:
        raw_index.setdefault(record["legacy_raw_full_name"], []).append(record)
        cleaned_index.setdefault(record["cleaned_full_name"], []).append(record)
    from backend.app.domain.legacy_db_ktra_reconciliation import parse_legacy_team
    records = []
    for row in sheet["raw_rows"]:
        if row.get("source_row_number", 0) <= 4:
            continue
        raw_team = _cell(row, team_column)
        parsed = parse_legacy_team(raw_team)
        tokens = [member["display_name"] for member in parsed["members"]]
        for ordinal, token in enumerate(tokens, start=1):
            raw_matches = raw_index.get(token, [])
            duplicate = tokens.count(token) > 1
            cleaned, pct, star = split_approved_name_markers(token)
            candidates = cleaned_index.get(cleaned, [])
            if len(raw_matches) == 1:
                match_basis, target = "EXACT_RAW_MATCH", raw_matches[0]
            elif len(candidates) != 1:
                match_basis, target = ("AMBIGUOUS" if candidates else "ZERO_MATCH"), None
            elif pct and candidates[0]["pct_marker"]:
                match_basis, target = "EXACT_AFTER_PCT_MARKER_HANDLING", candidates[0]
            elif star and candidates[0]["star_marker"]:
                match_basis, target = "EXACT_AFTER_STAR_MARKER_HANDLING", candidates[0]
            else:
                match_basis, target = "ZERO_MATCH", None
            classification = "DUPLICATE_SOURCE_OCCURRENCE" if duplicate else match_basis
            records.append({"source_row_number": row["source_row_number"], "member_ordinal": ordinal, "raw_team_token": token, "classification": classification, "match_basis": match_basis, "person_source_provenance_hash": None if target is None else target["source_provenance_hash"]})
    records.sort(key=lambda item: (item["source_row_number"], item["member_ordinal"]))
    return {"records": records, "classification_counts": {key: sum(item["classification"] == key for item in records) for key in ("EXACT_RAW_MATCH", "EXACT_AFTER_PCT_MARKER_HANDLING", "EXACT_AFTER_STAR_MARKER_HANDLING", "ZERO_MATCH", "AMBIGUOUS", "DUPLICATE_SOURCE_OCCURRENCE")}, "distinct_planned_person_records_referenced": len({item["person_source_provenance_hash"] for item in records if item["person_source_provenance_hash"]})}
