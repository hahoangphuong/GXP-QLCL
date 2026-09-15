"""Guarded writer for the approved TTviên personnel source-plan artifact."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Mapping, Sequence

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from backend.app.db.models.phase1 import InspectorProfile, LegacyInspectorSourceRecord, Person
from backend.app.domain.legacy_ttvien_personnel_import import canonical_payload_from_source, classify_personnel_import


REQUIRED_REVISION = "20260914_0015"
CANONICAL_SOURCE_PLAN_SHA256 = "f2a5ab81dd768aed45b4706167518b8c11378b1264ad82e3486eca54ef34a6a2"
EXPECTED_IMPORT_CANDIDATE_COUNT = 358


class PersonnelImportFenceError(RuntimeError):
    """Raised when the guarded personnel import must fail before a write."""


@dataclass(frozen=True)
class _PreparedImport:
    source_records: Sequence[Mapping[str, Any]]
    import_plan: Mapping[str, Any]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PersonnelImportFenceError(message)


def _require_clean_session(session: Session) -> None:
    """Reject caller-owned pending state before any guarded personnel operation."""
    _require(
        not session.new and not session.dirty and not session.deleted,
        "TTviên personnel import requires a clean SQLAlchemy Session",
    )


def source_plan_sha256(source_plan_bytes: bytes) -> str:
    return sha256(source_plan_bytes).hexdigest()


def _decode_canonical_source_plan(source_plan_bytes: bytes) -> list[Mapping[str, Any]]:
    _require(
        source_plan_sha256(source_plan_bytes) == CANONICAL_SOURCE_PLAN_SHA256,
        "TTviên personnel source plan SHA256 does not match the approved artifact",
    )
    try:
        source_plan = json.loads(source_plan_bytes)
    except (TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PersonnelImportFenceError("TTviên personnel source plan is not valid JSON") from exc
    _require(isinstance(source_plan, Mapping), "TTviên personnel source plan root is invalid")
    return validate_source_plan(source_plan)


def validate_source_plan(source_plan: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Pure structural validation after the public byte-SHA fence has passed."""
    records = source_plan.get("records")
    _require(isinstance(records, list), "TTviên personnel source plan records are missing")
    _require(len(records) == EXPECTED_IMPORT_CANDIDATE_COUNT, "TTviên personnel source plan record count is unexpected")
    _require(
        all(isinstance(record, Mapping) and record.get("classification") == "IMPORT_CANDIDATE" for record in records),
        "TTviên personnel source plan contains a non-import record",
    )
    return records


def verify_target_database(session: Session, expected_database_name: str) -> None:
    _require(isinstance(expected_database_name, str) and expected_database_name.strip(), "TTviên personnel expected database name is required")
    actual_database_name = session.execute(text("SELECT current_database()")).scalar_one()
    _require(actual_database_name == expected_database_name, "TTviên personnel import connected to an unexpected database")


def verify_schema_revision(session: Session) -> None:
    revision = session.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
    _require(revision == REQUIRED_REVISION, "TTviên personnel import requires Alembic revision 20260914_0015")


def _live_state(session: Session) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    provenance_rows = list(session.scalars(select(LegacyInspectorSourceRecord)))
    profiles = list(session.scalars(select(InspectorProfile)))
    persons = list(session.scalars(select(Person)))
    provenance = [
        {"snapshot_sha256": item.snapshot_sha256, "source_sheet": item.source_sheet, "source_row_number": item.source_row_number,
         "inspector_profile_id": item.inspector_profile_id, "canonical_payload_sha256": item.canonical_payload_sha256}
        for item in provenance_rows
    ]
    profile_state = [
        {"id": item.id, "person_id": item.person_id, "legacy_initials": item.legacy_initials,
         "legacy_display_text": item.legacy_display_text, "roster_group": item.roster_group, "honorific": item.honorific,
         "qualification": item.qualification, "position": item.position, "organizational_unit": item.organizational_unit,
         "professional_specialty": item.professional_specialty, "legacy_pct_marker": item.legacy_pct_marker,
         "legacy_star_marker": item.legacy_star_marker, "is_active": item.is_active}
        for item in profiles
    ]
    person_state = [{"id": item.id, "full_name": item.full_name} for item in persons]
    return provenance, profile_state, person_state


def preflight_import(session: Session, source_records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Classify all source rows against live state without mutating it."""
    # Preflight is read-only even if a caller reuses a session with pending work.
    with session.no_autoflush:
        provenance, profiles, persons = _live_state(session)
    plan = classify_personnel_import(source_records, provenance, profiles, persons)
    counts = plan["classification_counts"]
    _require(counts["CONFLICT"] == 0, "TTviên personnel import canonical state has conflicts")
    _require(counts["SOURCE_UNRESOLVED"] == 0, "TTviên personnel import source is unresolved")
    _require(counts["INSERT_CANDIDATE"] + counts["NOOP_IDEMPOTENT"] == EXPECTED_IMPORT_CANDIDATE_COUNT,
             "TTviên personnel import classification count is unexpected")
    return plan


def _prepare_import(session: Session, source_plan_bytes: bytes, expected_database_name: str) -> _PreparedImport:
    source_records = _decode_canonical_source_plan(source_plan_bytes)
    verify_target_database(session, expected_database_name)
    verify_schema_revision(session)
    return _PreparedImport(source_records=source_records, import_plan=preflight_import(session, source_records))


def _summary(import_plan: Mapping[str, Any], *, inserted: int) -> dict[str, Any]:
    counts = import_plan["classification_counts"]
    return {"classification_counts": counts, "inserted": inserted, "noop": counts["NOOP_IDEMPOTENT"],
            "database_mutated": inserted > 0, "team_imported": False}


def guarded_preflight(session: Session, source_plan_bytes: bytes, *, expected_database_name: str) -> dict[str, Any]:
    """Run all fences and B3 classification without adding or flushing ORM rows."""
    _require_clean_session(session)
    prepared = _prepare_import(session, source_plan_bytes, expected_database_name)
    return _summary(prepared.import_plan, inserted=0)


def _apply_import_plan(session: Session, prepared: _PreparedImport) -> int:
    sources_by_key = {(source["snapshot_sha256"], source["source_sheet"], source["source_row_number"]): source for source in prepared.source_records}
    inserted = 0
    for record in prepared.import_plan["records"]:
        if record["classification"] == "NOOP_IDEMPOTENT":
            continue
        _require(record["classification"] == "INSERT_CANDIDATE", "TTviên personnel import has a non-write record")
        provenance = record["source_provenance"]
        source = sources_by_key[(provenance["snapshot_sha256"], provenance["source_sheet"], provenance["source_row_number"])]
        payload = canonical_payload_from_source(source)
        person = Person(full_name=payload["person"]["full_name"])
        session.add(person)
        session.flush()
        profile = InspectorProfile(person_id=person.id, **payload["inspector_profile"])
        session.add(profile)
        session.flush()
        session.add(LegacyInspectorSourceRecord(
            snapshot_sha256=provenance["snapshot_sha256"], source_sheet=provenance["source_sheet"],
            source_row_number=provenance["source_row_number"], inspector_profile_id=profile.id,
            canonical_payload_sha256=record["canonical_payload_sha256"],
        ))
        inserted += 1
    session.flush()
    return inserted


def guarded_apply(session: Session, source_plan_bytes: bytes, *, expected_database_name: str) -> dict[str, Any]:
    """Fence and atomically apply the canonical artifact in the caller's transaction."""
    _require_clean_session(session)
    prepared = _prepare_import(session, source_plan_bytes, expected_database_name)
    inserted = 0
    if prepared.import_plan["classification_counts"]["INSERT_CANDIDATE"]:
        _require_clean_session(session)
        # Preserve caller transaction ownership while making the personnel batch atomic.
        with session.begin_nested():
            inserted = _apply_import_plan(session, prepared)
    return _summary(prepared.import_plan, inserted=inserted)
