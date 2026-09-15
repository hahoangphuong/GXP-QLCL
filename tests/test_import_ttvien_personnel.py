from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import inspect
import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.orm import Session

from backend.app.db.base import Base
from backend.app.db.models.phase1 import InspectorProfile, InspectionTeamMember, LegacyInspectorSourceRecord, Person
from backend.app.domain.legacy_ttvien_personnel import build_personnel_plan, preview_team_crosswalk
from backend.app.services import legacy_ttvien_personnel_import as importer
from tools import import_ttvien_personnel as cli


TEST_DATABASE_NAME = "ttvien_import_test"


@pytest.fixture(scope="module")
def canonical_source_plan() -> tuple[bytes, dict[str, object]]:
    snapshot = json.loads(Path("artifacts/phase3c/legacy_snapshot_v2.json").read_text(encoding="utf-8"))
    plan = build_personnel_plan(snapshot, expected_snapshot_sha256="484cf37603aacc5ff01a7bde5ffab01ed444748d5c7b1a0b30e7fc3a04936caa")
    plan["team_crosswalk_preview"] = preview_team_crosswalk(snapshot, plan)
    source = (json.dumps(plan, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    assert sha256(source).hexdigest() == importer.CANONICAL_SOURCE_PLAN_SHA256
    return source, plan


def _session() -> tuple[object, Session]:
    engine = create_engine("sqlite:///:memory:", future=True)

    @event.listens_for(engine, "connect")
    def _register_current_database(dbapi_connection, _connection_record):
        dbapi_connection.create_function("current_database", 0, lambda: TEST_DATABASE_NAME)

    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        connection.execute(text("INSERT INTO alembic_version (version_num) VALUES (:revision)"), {"revision": importer.REQUIRED_REVISION})
    return engine, Session(engine)


def _counts(session: Session) -> tuple[int, int, int, int]:
    with session.no_autoflush:
        return tuple(session.scalar(select(func.count()).select_from(model)) for model in (Person, InspectorProfile, LegacyInspectorSourceRecord, InspectionTeamMember))


def test_public_guarded_path_accepts_only_actual_canonical_bytes(canonical_source_plan):
    source, _ = canonical_source_plan
    engine, session = _session()
    try:
        report = importer.guarded_preflight(session, source, expected_database_name=TEST_DATABASE_NAME)
        assert report == {
            "classification_counts": {"INSERT_CANDIDATE": 358, "NOOP_IDEMPOTENT": 0, "CONFLICT": 0, "SOURCE_UNRESOLVED": 0},
            "inserted": 0,
            "noop": 0,
            "database_mutated": False,
            "team_imported": False,
        }
        changed = bytearray(source)
        changed[-2] = ord(" ")
        with pytest.raises(importer.PersonnelImportFenceError, match="SHA256"):
            importer.guarded_preflight(session, bytes(changed), expected_database_name=TEST_DATABASE_NAME)
        with pytest.raises(TypeError):
            importer.guarded_preflight(
                session,
                source,
                expected_database_name=TEST_DATABASE_NAME,
                expected_source_plan_sha256="0" * 64,
            )
    finally:
        session.close()
        engine.dispose()


def test_dry_run_is_preflight_only_and_never_flushes_personnel_rows(canonical_source_plan, monkeypatch):
    source, _ = canonical_source_plan
    engine, session = _session()
    try:
        flush_calls: list[object] = []
        monkeypatch.setattr(session, "flush", lambda *args, **kwargs: flush_calls.append((args, kwargs)))
        report = importer.guarded_preflight(session, source, expected_database_name=TEST_DATABASE_NAME)
        assert report["classification_counts"]["INSERT_CANDIDATE"] == 358
        assert report["inserted"] == 0 and report["database_mutated"] is False
        assert flush_calls == []
        assert _counts(session) == (0, 0, 0, 0)
    finally:
        session.close()
        engine.dispose()


def test_first_import_and_idempotent_rerun_preserve_personnel_contract(canonical_source_plan):
    source, plan = canonical_source_plan
    engine, session = _session()
    try:
        first = importer.guarded_apply(session, source, expected_database_name=TEST_DATABASE_NAME)
        session.commit()
        assert first["inserted"] == 358 and first["noop"] == 0 and first["database_mutated"] is True
        assert _counts(session) == (358, 358, 358, 0)

        source_records = plan["records"]
        pct = next(record for record in source_records if record["pct_marker"])
        star = next(record for record in source_records if record["star_marker"])
        inactive = next(record for record in source_records if not record["is_active"])
        specialty = next(record for record in source_records if record["professional_specialty"])
        provenance_by_row = {item.source_row_number: item for item in session.scalars(select(LegacyInspectorSourceRecord))}
        profiles = {item.id: item for item in session.scalars(select(InspectorProfile))}
        assert profiles[provenance_by_row[pct["source_row_number"]].inspector_profile_id].legacy_display_text == pct["legacy_raw_full_name"]
        assert profiles[provenance_by_row[pct["source_row_number"]].inspector_profile_id].legacy_pct_marker is True
        assert profiles[provenance_by_row[star["source_row_number"]].inspector_profile_id].legacy_star_marker is True
        assert profiles[provenance_by_row[inactive["source_row_number"]].inspector_profile_id].is_active is False
        assert profiles[provenance_by_row[specialty["source_row_number"]].inspector_profile_id].professional_specialty == specialty["professional_specialty"]
        assert len({person.full_name for person in session.scalars(select(Person))}) < 358

        rerun = importer.guarded_apply(session, source, expected_database_name=TEST_DATABASE_NAME)
        session.commit()
        assert rerun["inserted"] == 0 and rerun["noop"] == 358 and rerun["database_mutated"] is False
        assert _counts(session) == (358, 358, 358, 0)
    finally:
        session.close()
        engine.dispose()


def test_target_database_fence_rejects_wrong_target_without_writes(canonical_source_plan):
    source, _ = canonical_source_plan
    engine, session = _session()
    try:
        with pytest.raises(importer.PersonnelImportFenceError, match="unexpected database"):
            importer.guarded_preflight(session, source, expected_database_name="wrong_target")
        assert _counts(session) == (0, 0, 0, 0)
    finally:
        session.close()
        engine.dispose()


def test_pending_new_state_is_rejected_by_preflight_without_flush(canonical_source_plan, monkeypatch):
    source, _ = canonical_source_plan
    engine, session = _session()
    try:
        pending = Person(full_name="Caller pending")
        session.add(pending)
        flush_calls: list[object] = []
        monkeypatch.setattr(session, "flush", lambda *args, **kwargs: flush_calls.append((args, kwargs)))
        with pytest.raises(importer.PersonnelImportFenceError, match="clean SQLAlchemy Session"):
            importer.guarded_preflight(session, source, expected_database_name=TEST_DATABASE_NAME)
        assert pending in session.new
        assert flush_calls == []
        assert _counts(session) == (0, 0, 0, 0)
    finally:
        session.close()
        engine.dispose()


def test_pending_dirty_or_deleted_state_is_rejected_without_caller_state_flush(canonical_source_plan):
    source, _ = canonical_source_plan
    engine, session = _session()
    try:
        person = Person(full_name="Persisted caller state")
        session.add(person)
        session.commit()
        person.full_name = "Pending caller update"
        with pytest.raises(importer.PersonnelImportFenceError, match="clean SQLAlchemy Session"):
            importer.guarded_apply(session, source, expected_database_name=TEST_DATABASE_NAME)
        assert person in session.dirty
        assert person.full_name == "Pending caller update"
        assert _counts(session) == (1, 0, 0, 0)
        session.rollback()

        session.delete(person)
        with pytest.raises(importer.PersonnelImportFenceError, match="clean SQLAlchemy Session"):
            importer.guarded_apply(session, source, expected_database_name=TEST_DATABASE_NAME)
        assert person in session.deleted
        assert _counts(session) == (1, 0, 0, 0)
    finally:
        session.close()
        engine.dispose()


def test_apply_rechecks_session_cleanliness_before_savepoint(canonical_source_plan, monkeypatch):
    source, _ = canonical_source_plan
    engine, session = _session()
    original_prepare = importer._prepare_import
    try:
        def _prepare_then_make_session_dirty(*args, **kwargs):
            prepared = original_prepare(*args, **kwargs)
            session.add(Person(full_name="Late caller state"))
            return prepared

        monkeypatch.setattr(importer, "_prepare_import", _prepare_then_make_session_dirty)
        with pytest.raises(importer.PersonnelImportFenceError, match="clean SQLAlchemy Session"):
            importer.guarded_apply(session, source, expected_database_name=TEST_DATABASE_NAME)
        assert len(session.new) == 1
        assert _counts(session) == (0, 0, 0, 0)
    finally:
        session.close()
        engine.dispose()


def test_canonical_drift_and_invalid_source_content_fail_closed(canonical_source_plan):
    source, plan = canonical_source_plan
    engine, session = _session()
    try:
        importer.guarded_apply(session, source, expected_database_name=TEST_DATABASE_NAME)
        session.commit()
        session.scalar(select(Person).limit(1)).full_name = "Drifted"
        session.commit()
        with pytest.raises(importer.PersonnelImportFenceError, match="conflicts"):
            importer.guarded_apply(session, source, expected_database_name=TEST_DATABASE_NAME)
        assert _counts(session) == (358, 358, 358, 0)

        malformed = deepcopy(plan)
        malformed["records"] = malformed["records"][:-1]
        with pytest.raises(importer.PersonnelImportFenceError, match="record count"):
            importer.validate_source_plan(malformed)
        duplicate = deepcopy(plan)
        duplicate["records"][1] = deepcopy(duplicate["records"][0])
        with pytest.raises(ValueError, match="duplicate source provenance"):
            importer.preflight_import(session, duplicate["records"])
    finally:
        session.close()
        engine.dispose()


def test_partial_insert_failure_leaves_no_persisted_personnel_rows(canonical_source_plan):
    source, _ = canonical_source_plan
    engine, session = _session()
    insert_count = 0

    def _fail_third_provenance_insert(*_args):
        nonlocal insert_count
        insert_count += 1
        if insert_count == 3:
            raise RuntimeError("injected failure")

    event.listen(LegacyInspectorSourceRecord, "before_insert", _fail_third_provenance_insert)
    try:
        with pytest.raises(RuntimeError, match="injected failure"):
            importer.guarded_apply(session, source, expected_database_name=TEST_DATABASE_NAME)
        assert _counts(session) == (0, 0, 0, 0)
    finally:
        event.remove(LegacyInspectorSourceRecord, "before_insert", _fail_third_provenance_insert)
        session.close()
        engine.dispose()


def test_cli_uses_runtime_database_configuration_not_a_secret_argument():
    source = inspect.getsource(cli)
    assert "--database-url" not in source
    assert "load_app_config" in source
    assert "--expected-database-name" in source
