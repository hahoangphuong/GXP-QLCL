from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from backend.app.db.models import Base
from backend.app.db.models.phase1 import InspectorProfile, LegacyInspectorSourceRecord, Person
from backend.app.domain.legacy_ttvien_personnel_import import (
    canonical_payload,
    canonical_payload_sha256,
    classify_personnel_import,
)
from tools import plan_ttvien_personnel_import


def _source_record(row_number: int, *, full_name: str = "Nguyễn Văn A", active: bool = True) -> dict:
    return {
        "classification": "IMPORT_CANDIDATE",
        "snapshot_sha256": "a" * 64,
        "source_sheet": "TTviên",
        "source_row_number": row_number,
        "cleaned_full_name": full_name,
        "legacy_initial": "NVA",
        "legacy_raw_full_name": full_name,
        "source_group": "DRUG_ADMINISTRATION_AND_TRADITIONAL_MEDICINE",
        "raw_honorific": "Ông",
        "raw_qualification": "Ds.",
        "position": "Inspector",
        "organizational_unit": "Unit",
        "professional_specialty": "Specialty",
        "pct_marker": False,
        "star_marker": False,
        "is_active": active,
        "sensitive_field_presence": {"citizen_identity": True, "payment": True},
    }


def _migration_source() -> str:
    return Path("migrations/versions/20260914_0015_inspector_personnel_provenance.py").read_text(encoding="utf-8")


def _canonical_state_for(source: dict, *, profile_overrides: dict | None = None, person_overrides: dict | None = None) -> dict:
    profile = {
        "id": "profile-1",
        "person_id": "person-1",
        "legacy_initials": source["legacy_initial"],
        "legacy_display_text": source["legacy_raw_full_name"],
        "roster_group": source["source_group"],
        "honorific": source["raw_honorific"],
        "qualification": source["raw_qualification"],
        "position": source["position"],
        "organizational_unit": source["organizational_unit"],
        "professional_specialty": source["professional_specialty"],
        "legacy_pct_marker": source["pct_marker"],
        "legacy_star_marker": source["star_marker"],
        "is_active": source["is_active"],
    }
    profile.update(profile_overrides or {})
    person = {"id": "person-1", "full_name": source["cleaned_full_name"]}
    person.update(person_overrides or {})
    provenance = {
        "snapshot_sha256": source["snapshot_sha256"],
        "source_sheet": source["source_sheet"],
        "source_row_number": source["source_row_number"],
        "inspector_profile_id": "profile-1",
        "canonical_payload_sha256": canonical_payload_sha256(source),
    }
    return {
        "existing_provenance": [provenance],
        "inspector_profiles": [profile],
        "persons": [person],
    }


def _migration_module():
    path = Path("migrations/versions/20260914_0015_inspector_personnel_provenance.py")
    spec = importlib.util.spec_from_file_location("migration_20260914_0015", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_person_and_inspector_profile_contracts_are_non_unique_and_one_to_one():
    assert Person.__table__.c.full_name.unique is not True
    unique_constraints = {
        tuple(column.name for column in constraint.columns)
        for constraint in InspectorProfile.__table__.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    assert ("person_id",) in unique_constraints


def test_inspector_profile_typed_fields_constraints_and_filter_indexes_match_contract():
    table = InspectorProfile.__table__
    assert table.c.professional_specialty.type.length == 255
    assert table.c.professional_specialty.nullable is True
    assert table.c.roster_group.type.length == 64
    assert {index.name for index in table.indexes}.issuperset(
        {"ix_inspector_profile_roster_group", "ix_inspector_profile_professional_specialty"}
    )
    checks = {constraint.name for constraint in table.constraints if constraint.__class__.__name__ == "CheckConstraint"}
    assert "ck_inspector_profile_inspector_profile_roster_group_known" in checks


def test_provenance_owner_has_only_source_identity_payload_digest_and_profile_fk():
    table = LegacyInspectorSourceRecord.__table__
    assert {"snapshot_sha256", "source_sheet", "source_row_number", "inspector_profile_id", "canonical_payload_sha256"}.issubset(table.c.keys())
    assert not {"citizen_identity", "payment", "airline_contact_like"}.intersection(table.c.keys())
    unique_constraints = {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    assert ("snapshot_sha256", "source_sheet", "source_row_number") in unique_constraints
    assert table.c.inspector_profile_id.foreign_keys
    assert {index.name for index in table.indexes} == {"ix_legacy_inspector_source_record_inspector_profile_id"}


def test_migration_0015_is_next_revision_and_schema_only_with_reversible_operations():
    source = _migration_source()
    assert 'revision = "20260914_0015"' in source
    assert 'down_revision = "20260913_0014"' in source
    assert "legacy_inspector_source_record" in source
    assert "ix_inspector_profile_roster_group" in source
    assert "ix_inspector_profile_professional_specialty" in source
    assert "op.drop_table(\"legacy_inspector_source_record\")" in source
    assert "INSERT INTO" not in source
    assert "UPDATE " not in source


def test_migration_0015_upgrade_and_downgrade_cover_exact_b3_schema_changes():
    migration = _migration_module()
    calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    class Recorder:
        def __getattr__(self, name):
            def record(*args, **kwargs):
                calls.append((name, args, kwargs))
            return record

    migration.op = Recorder()
    migration.upgrade()
    assert migration.revision == "20260914_0015"
    assert migration.down_revision == "20260913_0014"
    assert [args[1].name for name, args, _ in calls if name == "add_column"] == [
        "roster_group", "honorific", "qualification", "position", "organizational_unit",
        "professional_specialty", "legacy_pct_marker", "legacy_star_marker",
    ]
    assert [args[0] for name, args, _ in calls if name == "create_table"] == ["legacy_inspector_source_record"]
    create_table_args = next(args for name, args, _ in calls if name == "create_table")
    columns = {item.name: item for item in create_table_args if getattr(item, "name", None) in {"created_at", "updated_at", "inspector_profile_id"}}
    assert columns["created_at"].nullable is False
    assert columns["updated_at"].nullable is False
    assert columns["created_at"].server_default is not None
    assert columns["updated_at"].server_default is not None
    assert 'sa.ForeignKeyConstraint(["inspector_profile_id"], ["inspector_profile.id"])' in _migration_source()
    assert {(args[0], args[1]) for name, args, _ in calls if name == "create_index"} == {
        ("ix_inspector_profile_roster_group", "inspector_profile"),
        ("ix_inspector_profile_professional_specialty", "inspector_profile"),
        ("ix_legacy_inspector_source_record_inspector_profile_id", "legacy_inspector_source_record"),
    }

    calls.clear()
    migration.downgrade()
    assert [args[0] for name, args, _ in calls if name == "drop_table"] == ["legacy_inspector_source_record"]
    assert [args[1] for name, args, _ in calls if name == "drop_column"] == [
        "legacy_star_marker", "legacy_pct_marker", "professional_specialty", "organizational_unit",
        "position", "qualification", "honorific", "roster_group",
    ]


def test_empty_canonical_state_creates_insert_candidates_without_name_based_dedupe():
    first = _source_record(6)
    second = _source_record(7)
    plan = classify_personnel_import([first, second], [], [], [])
    assert plan["database_mutated"] is False
    assert plan["team_imported"] is False
    assert plan["classification_counts"] == {
        "INSERT_CANDIDATE": 2,
        "NOOP_IDEMPOTENT": 0,
        "CONFLICT": 0,
        "SOURCE_UNRESOLVED": 0,
    }
    assert [item["source_provenance"]["source_row_number"] for item in plan["records"]] == [6, 7]


def test_replay_requires_source_provenance_and_live_canonical_payload_match():
    source = _source_record(6)
    state = _canonical_state_for(source)
    record = classify_personnel_import([source], **state)["records"][0]
    assert record["classification"] == "NOOP_IDEMPOTENT"


def test_replay_conflicts_when_source_payload_changes_only():
    source = _source_record(6)
    state = _canonical_state_for(source)
    source["position"] = "Changed"
    record = classify_personnel_import([source], **state)["records"][0]
    assert record["classification"] == "CONFLICT"
    assert record["conflict_reason"] == "SOURCE_PAYLOAD_CHANGED"


def test_replay_conflicts_when_live_canonical_state_drifts_only():
    source = _source_record(6)
    state = _canonical_state_for(source, profile_overrides={"position": "Changed"})
    record = classify_personnel_import([source], **state)["records"][0]
    assert record["classification"] == "CONFLICT"
    assert record["conflict_reason"] == "CANONICAL_STATE_DRIFTED"


def test_replay_conflicts_when_source_and_live_canonical_state_change():
    source = _source_record(6)
    state = _canonical_state_for(source, profile_overrides={"position": "Canonical changed"})
    source["position"] = "Source changed"
    record = classify_personnel_import([source], **state)["records"][0]
    assert record["classification"] == "CONFLICT"
    assert record["conflict_reason"] == "BOTH_CHANGED"


def test_inactive_source_is_preserved_and_sensitive_source_values_are_not_copied():
    source = _source_record(6, active=False)
    payload = canonical_payload(source)
    assert payload["inspector_profile"]["is_active"] is False
    serialized = json.dumps(payload, ensure_ascii=False)
    assert "sensitive_field_presence" not in serialized
    assert "citizen_identity" not in serialized
    assert "payment" not in serialized


def test_non_import_source_never_becomes_personnel_candidate():
    source = _source_record(6)
    source["classification"] = "SOURCE_UNRESOLVED"
    plan = classify_personnel_import([source], [], [], [])
    assert plan["records"] == [{
        "classification": "SOURCE_UNRESOLVED",
        "source_provenance": {
            "snapshot_sha256": "a" * 64,
            "source_sheet": "TTviên",
            "source_row_number": 6,
        },
    }]


def test_no_write_cli_uses_only_supplied_canonical_state(tmp_path):
    source = {"records": [_source_record(6)]}
    state = {"legacy_inspector_source_records": [], "inspector_profiles": [], "persons": []}
    source_path = tmp_path / "source.json"
    state_path = tmp_path / "state.json"
    output_path = tmp_path / "output.json"
    source_path.write_text(json.dumps(source), encoding="utf-8")
    state_path.write_text(json.dumps(state), encoding="utf-8")
    assert plan_ttvien_personnel_import.main([
        "--source-plan", str(source_path),
        "--canonical-state", str(state_path),
        "--output", str(output_path),
    ]) == 0
    output = json.loads(output_path.read_text(encoding="utf-8"))
    assert output["database_mutated"] is False
    assert output["team_imported"] is False
    assert output["classification_counts"]["INSERT_CANDIDATE"] == 1
    assert "sensitive_field_presence" not in output_path.read_text(encoding="utf-8")


def test_missing_profile_or_person_is_source_unresolved_without_repair():
    source = _source_record(6)
    state = _canonical_state_for(source)
    state["inspector_profiles"] = []
    record = classify_personnel_import([source], **state)["records"][0]
    assert (record["classification"], record["conflict_reason"]) == ("SOURCE_UNRESOLVED", "MISSING_INSPECTOR_PROFILE")
    state = _canonical_state_for(source)
    state["persons"] = []
    record = classify_personnel_import([source], **state)["records"][0]
    assert (record["classification"], record["conflict_reason"]) == ("SOURCE_UNRESOLVED", "MISSING_PERSON")


def test_state_hashes_and_duplicate_live_targets_fail_closed():
    source = _source_record(6)
    source["snapshot_sha256"] = "A" * 64
    with pytest.raises(ValueError, match="snapshot SHA"):
        classify_personnel_import([source], [], [], [])

    source = _source_record(6)
    state = _canonical_state_for(source)
    state["existing_provenance"][0]["canonical_payload_sha256"] = "z" * 64
    with pytest.raises(ValueError, match="payload SHA"):
        classify_personnel_import([source], **state)

    state = _canonical_state_for(source)
    state["inspector_profiles"].append(dict(state["inspector_profiles"][0]))
    with pytest.raises(ValueError, match="duplicate inspector profile"):
        classify_personnel_import([source], **state)


def test_duplicate_source_provenance_in_source_plan_fails_closed():
    first = _source_record(6)
    duplicate = dict(first)
    duplicate["position"] = "Different payload must not matter"
    with pytest.raises(ValueError, match="duplicate source provenance"):
        classify_personnel_import([first, duplicate], [], [], [])


def test_multiple_provenance_records_for_one_profile_fails_closed():
    source = _source_record(6)
    state = _canonical_state_for(source)
    second_provenance = dict(state["existing_provenance"][0])
    second_provenance["source_row_number"] = 7
    state["existing_provenance"].append(second_provenance)
    with pytest.raises(ValueError, match="multiple provenance records for one inspector profile"):
        classify_personnel_import([source], **state)


def test_metadata_registers_new_provenance_table():
    assert "legacy_inspector_source_record" in Base.metadata.tables
