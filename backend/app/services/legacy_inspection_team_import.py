"""Guarded importer for the structured legacy inspection-team plan."""
from __future__ import annotations

from dataclasses import dataclass
import json
from hashlib import sha256
from typing import Any, Mapping

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from backend.app.db.models.phase1 import (
    Case, InspectorProfile, InspectionTeam, InspectionTeamMember,
    InspectionTeamParticipantAlias, InspectionTeamParticipantCatalog,
    LegacyInspectorSourceRecord, Person,
)

REQUIRED_REVISION = "20260915_0016"
EXPECTED_SNAPSHOT_SHA256 = "484cf37603aacc5ff01a7bde5ffab01ed444748d5c7b1a0b30e7fc3a04936caa"
CANONICAL_PRODUCTION_DATABASE = "gxp_qlcl"


class InspectionTeamImportFenceError(RuntimeError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise InspectionTeamImportFenceError(message)


def _require_clean_session(session: Session) -> None:
    _require(not session.new and not session.dirty and not session.deleted, "inspection-team import requires a clean SQLAlchemy Session")


def decode_plan(plan_bytes: bytes) -> Mapping[str, Any]:
    _require(sha256(plan_bytes).hexdigest() == EXPECTED_PLAN_SHA256, "inspection-team source plan SHA256 does not match the approved artifact")
    try:
        plan = json.loads(plan_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InspectionTeamImportFenceError("inspection-team source plan is not valid JSON") from exc
    _require(isinstance(plan, Mapping) and plan.get("snapshot_sha256") == EXPECTED_SNAPSHOT_SHA256, "inspection-team source plan provenance is invalid")
    _require(plan.get("blocked_unresolved_count") == 0, "inspection-team source plan contains unresolved member identities")
    _require(plan.get("schema_version") == "inspection-team-source-plan/v1", "inspection-team source plan schema is invalid")
    _require(isinstance(plan.get("teams"), list), "inspection-team source plan teams are missing")
    return plan


# Filled by the CLI from the approved source artifact; callers of the service
# still receive a byte fence and cannot substitute an arbitrary plan.
EXPECTED_PLAN_SHA256 = "0827c3f68715d24f2603b3642ce1149a52000e81970c4a665d8d9e95653aee41"


def verify_target(session: Session, expected_database_name: str) -> None:
    _require(
        isinstance(expected_database_name, str) and expected_database_name.strip(),
        "inspection-team import expected database name is required",
    )
    _require(
        expected_database_name != CANONICAL_PRODUCTION_DATABASE,
        "inspection-team import refuses the canonical production database",
    )
    actual_database_name = session.execute(text("SELECT current_database()")).scalar_one()
    _require(
        actual_database_name != CANONICAL_PRODUCTION_DATABASE,
        "inspection-team import refuses the canonical production database",
    )
    _require(
        actual_database_name == expected_database_name,
        "inspection-team import connected to an unexpected database",
    )
    _require(session.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == REQUIRED_REVISION, "inspection-team import requires Alembic revision 20260915_0016")


def _live_team(session: Session, case_id: str) -> InspectionTeam | None:
    return session.scalar(select(InspectionTeam).where(InspectionTeam.case_id == case_id))


def _catalog(session: Session, item: Mapping[str, Any], *, create: bool) -> InspectionTeamParticipantCatalog | None:
    code = str(item["catalog_code"])
    row = session.scalar(select(InspectionTeamParticipantCatalog).where(InspectionTeamParticipantCatalog.code == code))
    if row is None and create:
        row = InspectionTeamParticipantCatalog(code=code, participant_kind="ORGANIZATION_REPRESENTATIVE", display_name=str(item["display_name"]), is_active=True)
        session.add(row)
        session.flush()
    if row is None:
        return None
    _require(row.participant_kind == "ORGANIZATION_REPRESENTATIVE" and row.is_active, "inspection-team participant catalog entry is inactive or invalid")
    source_value = str(item.get("legacy_source_token") or item["display_name"])
    source_hash = sha256(source_value.encode("utf-8")).hexdigest()
    alias = session.scalar(select(InspectionTeamParticipantAlias).where(
        InspectionTeamParticipantAlias.source_system == "legacy_workbook",
        InspectionTeamParticipantAlias.source_sheet == "db.ktra",
        InspectionTeamParticipantAlias.source_value_hash == source_hash,
    ))
    if alias is None and create:
        session.add(InspectionTeamParticipantAlias(
            participant_id=row.id, source_system="legacy_workbook", source_sheet="db.ktra",
            source_value=source_value, source_value_hash=source_hash,
        ))
        session.flush()
    elif alias is not None:
        _require(alias.participant_id == row.id and alias.source_value == source_value, "inspection-team participant alias conflicts with catalog")
    return row


def _profile(session: Session, provenance: Mapping[str, Any]) -> tuple[InspectorProfile, Person]:
    row = session.scalar(select(LegacyInspectorSourceRecord).where(
        LegacyInspectorSourceRecord.snapshot_sha256 == provenance["snapshot_sha256"],
        LegacyInspectorSourceRecord.source_sheet == provenance["source_sheet"],
        LegacyInspectorSourceRecord.source_row_number == provenance["source_row_number"],
    ))
    _require(row is not None, "inspection-team member has no canonical personnel provenance")
    profile = session.get(InspectorProfile, row.inspector_profile_id)
    _require(profile is not None, "inspection-team member profile is unavailable")
    person = session.get(Person, profile.person_id)
    _require(person is not None, "inspection-team member profile has no Person")
    return profile, person


def _member_shape(session: Session, item: Mapping[str, Any]) -> dict[str, Any]:
    kind = item.get("identity_kind")
    _require(kind in {"INSPECTOR_PROFILE", "LEGACY_PERSON", "ORGANIZATION_REPRESENTATIVE"}, "inspection-team member identity kind is invalid")
    result = {"identity_kind": kind, "display_name": item["display_name"], "legacy_source_token": item.get("legacy_source_token"), "role_code": item["role_code"], "sort_order": int(item["sort_order"]), "inspector_profile_id": None, "person_id": None, "participant_catalog_id": None}
    if kind == "INSPECTOR_PROFILE":
        profile, _person = _profile(session, item["person_source_provenance"])
        result["inspector_profile_id"] = profile.id
    elif kind == "ORGANIZATION_REPRESENTATIVE":
        catalog = _catalog(session, item, create=False)
        if catalog is not None:
            result["participant_catalog_id"] = catalog.id
        result["catalog_code"] = item["catalog_code"]
    return result


def _prepare(plan: Mapping[str, Any], session: Session) -> list[dict[str, Any]]:
    prepared: list[dict[str, Any]] = []
    for source in sorted(plan["teams"], key=lambda item: (item["legacy_inspection_id"], item["source_provenance"]["source_row_number"])):
        case = session.scalar(select(Case).where(Case.legacy_inspection_id == source["legacy_inspection_id"]))
        if case is None:
            prepared.append({"classification": "BLOCKED_NO_CANONICAL_CASE", "legacy_inspection_id": source["legacy_inspection_id"]})
            continue
        prepared.append({"classification": "WRITE_CANDIDATE", "legacy_inspection_id": source["legacy_inspection_id"], "canonical_case_id": case.id, "source_provenance": source["source_provenance"], "legacy_display_text": source["legacy_display_text"], "members": [_member_shape(session, item) for item in source["members"]]})
    return prepared


def guarded_preflight(session: Session, plan_bytes: bytes, *, expected_database_name: str) -> dict[str, Any]:
    _require_clean_session(session)
    plan = decode_plan(plan_bytes)
    verify_target(session, expected_database_name)
    with session.no_autoflush:
        records = _prepare(plan, session)
    _require(
        all(record["classification"] == "WRITE_CANDIDATE" for record in records),
        "inspection-team import has no canonical Case for every planned team",
    )
    return {"database_mutated": False, "records": records, "write_candidate_count": sum(r["classification"] == "WRITE_CANDIDATE" for r in records)}


def _apply(session: Session, records: list[dict[str, Any]]) -> int:
    _require(
        all(record["classification"] == "WRITE_CANDIDATE" for record in records),
        "inspection-team import has blocked records and refuses a partial import",
    )
    written = 0
    for record in records:
        team = _live_team(session, record["canonical_case_id"])
        created_team = team is None
        if team is None:
            team = InspectionTeam(case_id=record["canonical_case_id"], display_text=record["legacy_display_text"])
            session.add(team)
            session.flush()
        _require(team.display_text == record["legacy_display_text"], "inspection-team import found a legacy display_text collision")
        existing = list(session.scalars(select(InspectionTeamMember).where(InspectionTeamMember.team_id == team.id).order_by(InspectionTeamMember.sort_order, InspectionTeamMember.id)))
        desired = record["members"]
        for item in desired:
            if item["identity_kind"] == "ORGANIZATION_REPRESENTATIVE":
                item["participant_catalog_id"] = _catalog(session, item, create=True).id  # type: ignore[union-attr]
                item.pop("catalog_code", None)
        current = [{k: getattr(member, k) for k in ("identity_kind", "display_name", "legacy_source_token", "role_code", "sort_order", "inspector_profile_id", "person_id", "participant_catalog_id")} for member in existing]
        if current == desired:
            continue
        if not created_team:
            _require(existing, "inspection-team import refuses to adopt an empty existing team")
            raise InspectionTeamImportFenceError("inspection-team import found a conflicting existing team")
        for item in desired:
            session.add(InspectionTeamMember(team_id=team.id, **item))
        session.flush()
        written += 1
    return written


def guarded_apply(session: Session, plan_bytes: bytes, *, expected_database_name: str) -> dict[str, Any]:
    _require_clean_session(session)
    prepared = guarded_preflight(session, plan_bytes, expected_database_name=expected_database_name)
    _require_clean_session(session)
    with session.begin_nested():
        written = _apply(session, prepared["records"])
    return {**prepared, "database_mutated": written > 0, "written_team_count": written}
