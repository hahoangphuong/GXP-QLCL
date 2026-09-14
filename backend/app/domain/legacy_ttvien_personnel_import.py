"""Classify TTviên personnel imports without matching or writing canonical people."""
from __future__ import annotations

from hashlib import sha256
import json
import re
from typing import Any, Iterable, Mapping


IMPORT_STATES = ("INSERT_CANDIDATE", "NOOP_IDEMPOTENT", "CONFLICT", "SOURCE_UNRESOLVED")
PROVENANCE_FIELDS = ("snapshot_sha256", "source_sheet", "source_row_number")
SOURCE_PAYLOAD_FIELDS = (
    "cleaned_full_name",
    "legacy_initial",
    "legacy_raw_full_name",
    "source_group",
    "raw_honorific",
    "raw_qualification",
    "position",
    "organizational_unit",
    "professional_specialty",
    "pct_marker",
    "star_marker",
    "is_active",
)
PROFILE_PAYLOAD_FIELDS = (
    "legacy_initials",
    "legacy_display_text",
    "roster_group",
    "honorific",
    "qualification",
    "position",
    "organizational_unit",
    "professional_specialty",
    "legacy_pct_marker",
    "legacy_star_marker",
    "is_active",
)
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


def source_key(record: Mapping[str, Any]) -> tuple[str, str, int]:
    try:
        snapshot_sha256 = record["snapshot_sha256"]
        source_sheet = record["source_sheet"]
        source_row_number = record["source_row_number"]
    except KeyError as exc:
        raise ValueError(f"TTviên import source record is missing {exc.args[0]}") from exc
    if not isinstance(snapshot_sha256, str) or not SHA256_PATTERN.fullmatch(snapshot_sha256):
        raise ValueError("TTviên import source snapshot SHA is invalid")
    if source_sheet != "TTviên" or not isinstance(source_row_number, int) or source_row_number < 1:
        raise ValueError("TTviên import source identity is invalid")
    return snapshot_sha256, source_sheet, source_row_number


def _canonical_payload(*, full_name: Any, profile_values: Mapping[str, Any]) -> dict[str, Any]:
    missing = [field for field in PROFILE_PAYLOAD_FIELDS if field not in profile_values]
    if missing:
        raise ValueError(f"TTviên import canonical profile state is missing fields: {', '.join(missing)}")
    return {
        "person": {"full_name": full_name},
        "inspector_profile": {field: profile_values[field] for field in PROFILE_PAYLOAD_FIELDS},
    }


def canonical_payload_from_source(record: Mapping[str, Any]) -> dict[str, Any]:
    """The future Person/Profile write shape, intentionally excluding sensitive source cells."""
    missing = [field for field in SOURCE_PAYLOAD_FIELDS if field not in record]
    if missing:
        raise ValueError(f"TTviên import source record is missing payload fields: {', '.join(missing)}")
    return _canonical_payload(
        full_name=record["cleaned_full_name"],
        profile_values={
            "legacy_initials": record["legacy_initial"],
            "legacy_display_text": record["legacy_raw_full_name"],
            "roster_group": record["source_group"],
            "honorific": record["raw_honorific"],
            "qualification": record["raw_qualification"],
            "position": record["position"],
            "organizational_unit": record["organizational_unit"],
            "professional_specialty": record["professional_specialty"],
            "legacy_pct_marker": record["pct_marker"],
            "legacy_star_marker": record["star_marker"],
            "is_active": record["is_active"],
        },
    )


def canonical_payload_from_db_state(person: Mapping[str, Any], inspector_profile: Mapping[str, Any]) -> dict[str, Any]:
    if "full_name" not in person:
        raise ValueError("TTviên import canonical person state is missing full_name")
    return _canonical_payload(full_name=person["full_name"], profile_values=inspector_profile)


def canonical_payload(record: Mapping[str, Any]) -> dict[str, Any]:
    """Compatibility alias for source-record payload construction."""
    return canonical_payload_from_source(record)


def canonical_payload_sha256(payload_or_source: Mapping[str, Any]) -> str:
    payload = payload_or_source if {"person", "inspector_profile"}.issubset(payload_or_source) else canonical_payload_from_source(payload_or_source)
    content = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(content).hexdigest()


def classify_personnel_import(
    source_records: Iterable[Mapping[str, Any]],
    existing_provenance: Iterable[Mapping[str, Any]],
    inspector_profiles: Iterable[Mapping[str, Any]],
    persons: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Return a deterministic no-write plan keyed only by immutable source provenance."""
    existing: dict[tuple[str, str, int], Mapping[str, Any]] = {}
    provenance_targets: set[Any] = set()
    for item in existing_provenance:
        key = source_key(item)
        if key in existing:
            raise ValueError("TTviên import canonical state has duplicate provenance")
        stored_hash = item.get("canonical_payload_sha256")
        if not isinstance(stored_hash, str) or not SHA256_PATTERN.fullmatch(stored_hash):
            raise ValueError("TTviên import canonical provenance payload SHA is invalid")
        inspector_profile_id = item.get("inspector_profile_id")
        if inspector_profile_id is None:
            raise ValueError("TTviên import canonical provenance is missing inspector profile")
        if inspector_profile_id in provenance_targets:
            raise ValueError("TTviên import canonical state has multiple provenance records for one inspector profile")
        provenance_targets.add(inspector_profile_id)
        existing[key] = item

    def index_by_id(items: Iterable[Mapping[str, Any]], label: str) -> dict[Any, Mapping[str, Any]]:
        indexed: dict[Any, Mapping[str, Any]] = {}
        for item in items:
            item_id = item.get("id")
            if item_id is None or item_id in indexed:
                raise ValueError(f"TTviên import canonical state has invalid or duplicate {label}")
            indexed[item_id] = item
        return indexed

    profiles_by_id = index_by_id(inspector_profiles, "inspector profile")
    persons_by_id = index_by_id(persons, "person")

    records: list[dict[str, Any]] = []
    source_keys: set[tuple[str, str, int]] = set()
    for source in source_records:
        key = source_key(source)
        if key in source_keys:
            raise ValueError("TTviên import source plan has duplicate source provenance")
        source_keys.add(key)
        if source.get("classification") != "IMPORT_CANDIDATE":
            records.append({
                "classification": "SOURCE_UNRESOLVED",
                "source_provenance": dict(zip(PROVENANCE_FIELDS, key)),
            })
            continue
        payload = canonical_payload_from_source(source)
        payload_hash = canonical_payload_sha256(payload)
        existing_item = existing.get(key)
        if existing_item is None:
            classification = "INSERT_CANDIDATE"
            inspector_profile_id = None
        else:
            inspector_profile_id = existing_item.get("inspector_profile_id")
            profile = profiles_by_id.get(inspector_profile_id)
            if profile is None:
                records.append({
                    "classification": "SOURCE_UNRESOLVED",
                    "conflict_reason": "MISSING_INSPECTOR_PROFILE",
                    "source_provenance": dict(zip(PROVENANCE_FIELDS, key)),
                })
                continue
            person = persons_by_id.get(profile.get("person_id"))
            if person is None:
                records.append({
                    "classification": "SOURCE_UNRESOLVED",
                    "conflict_reason": "MISSING_PERSON",
                    "source_provenance": dict(zip(PROVENANCE_FIELDS, key)),
                })
                continue
            stored_hash = existing_item["canonical_payload_sha256"]
            live_hash = canonical_payload_sha256(canonical_payload_from_db_state(person, profile))
            source_changed = payload_hash != stored_hash
            canonical_changed = live_hash != stored_hash
            if not source_changed and not canonical_changed:
                classification = "NOOP_IDEMPOTENT"
                conflict_reason = None
            else:
                classification = "CONFLICT"
                conflict_reason = (
                    "BOTH_CHANGED" if source_changed and canonical_changed
                    else "SOURCE_PAYLOAD_CHANGED" if source_changed
                    else "CANONICAL_STATE_DRIFTED"
                )
        records.append({
            "classification": classification,
            "source_provenance": dict(zip(PROVENANCE_FIELDS, key)),
            "canonical_payload_sha256": payload_hash,
            "inspector_profile_id": inspector_profile_id,
            "canonical_payload": payload,
            **({"conflict_reason": conflict_reason} if classification == "CONFLICT" else {}),
        })

    records.sort(key=lambda item: (
        item["source_provenance"]["snapshot_sha256"],
        item["source_provenance"]["source_sheet"],
        item["source_provenance"]["source_row_number"],
    ))
    return {
        "schema_version": "ttvien-personnel-import-plan/v1",
        "database_mutated": False,
        "team_imported": False,
        "records": records,
        "classification_counts": {state: sum(item["classification"] == state for item in records) for state in IMPORT_STATES},
    }
