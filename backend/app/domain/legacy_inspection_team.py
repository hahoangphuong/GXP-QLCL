"""Deterministic, source-only planning for legacy inspection teams."""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Mapping

from backend.app.domain.legacy_db_ktra_reconciliation import parse_legacy_team
from backend.app.domain.legacy_db_ktra_source_v2 import (
    snapshot_cell_value as _value,
    snapshot_columns as _columns,
    substantive_source_value as _substantive,
)
from backend.app.domain.legacy_ttvien_personnel import SOURCE_SHEET as PERSONNEL_SOURCE_SHEET, resolve_team_member_token
from backend.app.domain.legacy_snapshot_v2 import snapshot_bytes
from backend.app.domain.phase2_import import parse_int


TEAM_SOURCE_SHEET = "db.ktra"
ORG_REPRESENTATIVE_ALIASES = {
    "Đại diện Cục Khoa học công nghệ và đào tạo": {
        "code": "ORG_REP_SCIENCE_TECH_TRAINING",
        "display_name": "Đại diện Cục Khoa học công nghệ và đào tạo",
    },
    "Đại diện Cục Quản lý Y‚ Dược cổ truyền": {
        "code": "ORG_REP_TRADITIONAL_MEDICINE",
        "display_name": "Đại diện Cục Quản lý Y, Dược cổ truyền",
    },
}
AUDITED_LEGACY_PERSON_NAMES = frozenset({
    "Bùi Khánh Toàn", "Dương Minh Đào", "Hồ Mai Anh", "Hồ Ngọc Thần", "Lê Đông Anh",
    "Ng. Minh Hằng", "Nguyễn Hiền Thanh", "Nguyễn Kim Phượng", "Nguyễn Minh Hùng",
    "Nguyễn Thị Thanh Hà", "Nguyễn Trường Thắng", "Nguyễn Văn Tựu", "Nguyễn Đức Chí Anh",
    "Trương Thị Nguyệt", "Trần Công Kỷ", "Trần Quang Hải", "Trần Văn Quyến", "Viên Quang Mai", "Đỗ Lê Huấn",
})


def _source_key(snapshot_sha256: str, row_number: int) -> dict[str, Any]:
    return {"snapshot_sha256": snapshot_sha256, "source_sheet": TEAM_SOURCE_SHEET, "source_row_number": row_number}


def _person_source_provenance(record: Mapping[str, Any], *, expected_snapshot_sha256: str) -> dict[str, Any]:
    """Copy the approved B2 personnel key; team occurrence provenance is separate."""
    snapshot_sha256 = record.get("snapshot_sha256")
    source_sheet = record.get("source_sheet")
    source_row_number = record.get("source_row_number")
    if (
        snapshot_sha256 != expected_snapshot_sha256
        or source_sheet != PERSONNEL_SOURCE_SHEET
        or not isinstance(source_row_number, int)
        or source_row_number < 1
    ):
        raise ValueError("inspection-team planner personnel provenance is invalid")
    return {
        "snapshot_sha256": snapshot_sha256,
        "source_sheet": source_sheet,
        "source_row_number": source_row_number,
    }


def _team_members(
    parsed: Mapping[str, Any],
    roster_records: list[dict[str, Any]],
    *,
    expected_snapshot_sha256: str,
) -> list[dict[str, Any]]:
    members: list[dict[str, Any]] = []
    for member in parsed["members"]:
        token = str(member["display_name"])
        catalog = ORG_REPRESENTATIVE_ALIASES.get(token)
        if catalog is not None:
            members.append({"identity_kind": "ORGANIZATION_REPRESENTATIVE", "display_name": catalog["display_name"], "catalog_code": catalog["code"], "legacy_source_token": token, "role_code": member["role_code"], "sort_order": member["ordinal"]})
            continue
        match_state, record = resolve_team_member_token(token, roster_records)
        if record is not None:
            members.append({"identity_kind": "INSPECTOR_PROFILE", "display_name": record["cleaned_full_name"], "person_source_provenance": _person_source_provenance(record, expected_snapshot_sha256=expected_snapshot_sha256), "match_state": match_state, "legacy_source_token": token, "role_code": member["role_code"], "sort_order": member["ordinal"]})
        elif token in AUDITED_LEGACY_PERSON_NAMES:
            members.append({"identity_kind": "LEGACY_PERSON", "display_name": token, "legacy_source_token": token, "role_code": member["role_code"], "sort_order": member["ordinal"]})
        else:
            members.append({"identity_kind": "BLOCKED_UNRESOLVED", "display_name": token, "legacy_source_token": token, "role_code": member["role_code"], "sort_order": member["ordinal"]})
    return members


def build_inspection_team_plan(snapshot: Mapping[str, Any], roster_plan: Mapping[str, Any], *, expected_snapshot_sha256: str) -> dict[str, Any]:
    if snapshot.get("schema_version") != "legacy-workbook-snapshot/v2":
        raise ValueError("inspection-team planner requires Snapshot V2")
    if not isinstance(expected_snapshot_sha256, str) or sha256(snapshot_bytes(dict(snapshot))).hexdigest() != expected_snapshot_sha256:
        raise ValueError("inspection-team planner snapshot provenance guard failed")
    if roster_plan.get("schema_version") != "ttvien-personnel-source-plan/v1" or roster_plan.get("snapshot_sha256") != expected_snapshot_sha256:
        raise ValueError("inspection-team planner roster provenance is invalid")
    roster_records_raw = roster_plan.get("records")
    if (
        not isinstance(roster_records_raw, list)
        or any(
            not isinstance(item, Mapping)
            or item.get("snapshot_sha256") != expected_snapshot_sha256
            or item.get("source_sheet") != PERSONNEL_SOURCE_SHEET
            or not isinstance(item.get("source_row_number"), int)
            or item["source_row_number"] < 1
            for item in roster_records_raw
        )
    ):
        raise ValueError("inspection-team planner roster record provenance is invalid")
    required = ("ID", "LOẠI KT", "ID CƠ SỞ", "T.tra viên")
    rows, columns = _columns(snapshot, TEAM_SOURCE_SHEET, required_headers=required)
    missing = [name for name in required if name not in columns]
    if missing:
        raise ValueError(f"db.ktra team columns missing: {', '.join(missing)}")
    roster_records = [dict(item) for item in roster_records_raw if item.get("classification") == "IMPORT_CANDIDATE"]
    if len({(item["snapshot_sha256"], item["source_sheet"], item["source_row_number"]) for item in roster_records}) != len(roster_records):
        raise ValueError("inspection-team planner roster source provenance is duplicated")
    teams: list[dict[str, Any]] = []
    member_count = 0
    class_counts = {"INSPECTOR_PROFILE": 0, "LEGACY_PERSON": 0, "ORGANIZATION_REPRESENTATIVE": 0}
    for row in rows:
        row_number = row.get("source_row_number")
        if not isinstance(row_number, int) or row_number <= 4:
            continue
        legacy_id = parse_int(_value(row, columns["ID"]))
        if legacy_id is None or not _substantive(_value(row, columns["LOẠI KT"])) or not _substantive(_value(row, columns["ID CƠ SỞ"])):
            continue
        parsed = parse_legacy_team(_value(row, columns["T.tra viên"]))
        if parsed["state"] != "KNOWN":
            continue
        members = _team_members(parsed, roster_records, expected_snapshot_sha256=expected_snapshot_sha256)
        member_count += len(members)
        for item in members:
            if item["identity_kind"] == "BLOCKED_UNRESOLVED":
                continue
            class_counts[item["identity_kind"]] += 1
        teams.append({"legacy_inspection_id": legacy_id, "source_provenance": _source_key(expected_snapshot_sha256, row_number), "legacy_display_text": parsed["raw"], "members": members})
    teams.sort(key=lambda item: (item["legacy_inspection_id"], item["source_provenance"]["source_row_number"]))
    return {
        "schema_version": "inspection-team-source-plan/v1",
        "snapshot_sha256": expected_snapshot_sha256,
        "database_accessed": False,
        "teams": teams,
        "team_count": len(teams),
        "member_count": member_count,
        "classification_counts": class_counts,
        "blocked_unresolved_count": sum(sum(item["identity_kind"] == "BLOCKED_UNRESOLVED" for item in team["members"]) for team in teams),
        "catalog": sorted(ORG_REPRESENTATIVE_ALIASES.values(), key=lambda item: item["code"]),
        "guardrails": {"database_mutated": False, "importer_invoked": False, "fuzzy_matching_used": False},
    }


def plan_bytes(plan: Mapping[str, Any]) -> bytes:
    return (json.dumps(plan, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def plan_sha256(plan: Mapping[str, Any]) -> str:
    return sha256(plan_bytes(plan)).hexdigest()
