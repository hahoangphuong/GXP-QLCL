from __future__ import annotations

import json
from backend.app.domain.legacy_inspection_team import build_inspection_team_plan, plan_sha256
from backend.app.domain.legacy_ttvien_personnel import resolve_team_member_token
from backend.app.domain.legacy_snapshot_v2 import snapshot_bytes
from hashlib import sha256
from pathlib import Path
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from uuid import uuid4
from backend.app.db.models import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import (
    Case,
    InspectorProfile,
    InspectionTeam,
    InspectionTeamMember,
    InspectionTeamParticipantAlias,
    InspectionTeamParticipantCatalog,
    LegacyInspectorSourceRecord,
    Person,
)
from backend.app.services import legacy_inspection_team_import as importer
from backend.app.services.legacy_inspection_team_import import _apply, InspectionTeamImportFenceError


def _row(number: int, values: dict[int, object]) -> dict:
    return {"source_row_number": number, "cells": [{"column_ordinal": column, "raw_value": value} for column, value in values.items()]}


def _snapshot(team: object, *, legacy_id: object = "1") -> dict:
    headers = {1: "ID", 2: "LOẠI KT", 3: "ID CƠ SỞ", 4: "T.tra viên"}
    return {"schema_version": "legacy-workbook-snapshot/v2", "sheets": [{"sheet_name": "db.ktra", "raw_rows": [_row(4, headers), _row(5, {1: legacy_id, 2: "GMP", 3: "1", 4: team})]}]}


def _roster(*records: dict) -> dict:
    snapshot = _snapshot("Nguyễn Văn A")
    digest = sha256(snapshot_bytes(snapshot)).hexdigest()
    return {"schema_version": "ttvien-personnel-source-plan/v1", "snapshot_sha256": digest, "records": list(records)}


def _person(name: str, row: int = 6) -> dict:
    return {"classification": "IMPORT_CANDIDATE", "legacy_raw_full_name": name, "cleaned_full_name": name.removeprefix("PCT. "), "pct_marker": name.startswith("PCT."), "star_marker": name.endswith("*"), "snapshot_sha256": "a" * 64, "source_sheet": "TTviên", "source_row_number": row}


def test_b5b_planner_preserves_order_and_all_three_identity_kinds():
    roster = _roster(_person("PCT. Nguyễn Văn A"), _person("Nguyễn Văn B", 7))
    snapshot = _snapshot("Nguyễn Văn A, Nguyễn Văn B, Đại diện Cục Quản lý Y‚ Dược cổ truyền, Bùi Khánh Toàn")
    digest = sha256(snapshot_bytes(snapshot)).hexdigest()
    roster["snapshot_sha256"] = digest
    for item in roster["records"]:
        item["snapshot_sha256"] = digest
    result = build_inspection_team_plan(snapshot, roster, expected_snapshot_sha256=digest)
    assert result["team_count"] == 1
    assert result["member_count"] == 4
    assert result["classification_counts"] == {"INSPECTOR_PROFILE": 2, "LEGACY_PERSON": 1, "ORGANIZATION_REPRESENTATIVE": 1}
    members = result["teams"][0]["members"]
    assert [item["sort_order"] for item in members] == [1, 2, 3, 4]
    assert members[2]["display_name"] == "Đại diện Cục Quản lý Y, Dược cổ truyền"
    assert members[2]["legacy_source_token"] == "Đại diện Cục Quản lý Y‚ Dược cổ truyền"
    assert members[3]["identity_kind"] == "LEGACY_PERSON"
    assert members[0]["person_source_provenance"] == {
        "snapshot_sha256": digest,
        "source_sheet": "TTviên",
        "source_row_number": 6,
    }
    assert result["teams"][0]["source_provenance"] == {
        "snapshot_sha256": digest,
        "source_sheet": "db.ktra",
        "source_row_number": 5,
    }


def test_b5b_planner_excludes_non_effective_rows_without_fabricating_team():
    snapshot = _snapshot("Người cũ", legacy_id="")
    digest = sha256(snapshot_bytes(snapshot)).hexdigest()
    roster = _roster()
    roster["snapshot_sha256"] = digest
    result = build_inspection_team_plan(snapshot, roster, expected_snapshot_sha256=digest)
    assert result["teams"] == []


def test_b5b_planner_blocks_unknown_unresolved_tokens():
    snapshot = _snapshot("Unknown future text")
    digest = sha256(snapshot_bytes(snapshot)).hexdigest()
    roster = _roster()
    roster["snapshot_sha256"] = digest
    result = build_inspection_team_plan(snapshot, roster, expected_snapshot_sha256=digest)
    assert result["blocked_unresolved_count"] == 1
    assert result["teams"][0]["members"][0]["identity_kind"] == "BLOCKED_UNRESOLVED"


def test_b5b_planner_rejects_non_ttvien_personnel_provenance():
    snapshot = _snapshot("Nguyễn Văn A")
    digest = sha256(snapshot_bytes(snapshot)).hexdigest()
    roster = _roster(_person("Nguyễn Văn A"))
    roster["snapshot_sha256"] = digest
    roster["records"][0]["snapshot_sha256"] = digest
    roster["records"][0]["source_sheet"] = "db.ktra"

    with pytest.raises(ValueError, match="roster record provenance"):
        build_inspection_team_plan(snapshot, roster, expected_snapshot_sha256=digest)


def test_marker_resolver_requires_exact_approved_marker_difference():
    roster = [_person("PCT. Nguyễn Văn A")]
    assert resolve_team_member_token("Nguyễn Văn A", roster)[0] == "EXACT_AFTER_APPROVED_MARKER_EQUIVALENCE"
    assert resolve_team_member_token("PCT. Nguyễn Văn A", roster)[0] == "EXACT_RAW_MATCH"
    assert resolve_team_member_token("Nguyễn Văn Aa", roster)[0] == "ZERO_MATCH"


def test_marker_resolver_fails_closed_for_ambiguous_cleaned_name():
    roster = [_person("PCT. Nguyễn Văn A", 6), _person("PCT. Nguyễn Văn A*", 7)]
    roster[1]["cleaned_full_name"] = "Nguyễn Văn A"
    assert resolve_team_member_token("Nguyễn Văn A", roster) == ("AMBIGUOUS", None)


def test_b5b_identity_shape_preserves_transitional_legacy_identity():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        team = InspectionTeam(case_id="case-1")
        catalog = InspectionTeamParticipantCatalog(code="ORG", display_name="Organization")
        session.add_all([team, catalog])
        session.flush()
        session.add(InspectionTeamMember(team_id=team.id, identity_kind=None, person_id="person-1", sort_order=1))
        session.add(InspectionTeamMember(team_id=team.id, identity_kind="LEGACY_PERSON", display_name="Historical", sort_order=2))
        session.add(InspectionTeamMember(team_id=team.id, identity_kind="ORGANIZATION_REPRESENTATIVE", display_name="Organization", participant_catalog_id=catalog.id, sort_order=3))
        session.flush()
        session.rollback()
    with engine.begin() as connection:
        with pytest.raises(IntegrityError):
            connection.execute(text("INSERT INTO inspection_team_member (team_id, id, sort_order) VALUES (:team_id, :id, 4)"), {"team_id": "case-1", "id": "member-1"})


def _apply_record(case_id: str = "case-apply", *, name: str = "Historical") -> dict:
    return {"classification": "WRITE_CANDIDATE", "canonical_case_id": case_id, "legacy_inspection_id": 1, "legacy_display_text": name, "members": [{"identity_kind": "LEGACY_PERSON", "display_name": name, "legacy_source_token": name, "role_code": "LEADER", "sort_order": 1, "inspector_profile_id": None, "person_id": None, "participant_catalog_id": None}]}


class _TargetResult:
    def __init__(self, value: str):
        self.value = value

    def scalar_one(self) -> str:
        return self.value


class _TargetSession:
    def __init__(self, database_name: str, revision: str):
        self.database_name = database_name
        self.revision = revision

    def execute(self, statement):
        if "current_database" in str(statement):
            return _TargetResult(self.database_name)
        return _TargetResult(self.revision)


def test_b5b_target_database_fences_require_exact_explicit_nonproduction_target():
    disposable_name = "gxp_b5b_v4_it_20260915"
    importer.verify_target(_TargetSession(disposable_name, importer.REQUIRED_REVISION), disposable_name)

    with pytest.raises(InspectionTeamImportFenceError, match="expected database name"):
        importer.verify_target(_TargetSession(disposable_name, importer.REQUIRED_REVISION), " ")
    with pytest.raises(InspectionTeamImportFenceError, match="unexpected database"):
        importer.verify_target(_TargetSession("another_disposable", importer.REQUIRED_REVISION), disposable_name)
    with pytest.raises(InspectionTeamImportFenceError, match="canonical production"):
        importer.verify_target(_TargetSession("gxp_qlcl", importer.REQUIRED_REVISION), "gxp_qlcl")
    with pytest.raises(InspectionTeamImportFenceError, match="canonical production"):
        importer.verify_target(_TargetSession("gxp_qlcl", importer.REQUIRED_REVISION), disposable_name)
    with pytest.raises(InspectionTeamImportFenceError, match="requires Alembic"):
        importer.verify_target(_TargetSession(disposable_name, "20260914_0015"), disposable_name)


def test_b5b_missing_canonical_case_is_rejected_before_preflight_or_apply_mutation(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    plan = {
        "teams": [{
            "legacy_inspection_id": 999,
            "source_provenance": {"source_row_number": 5},
            "legacy_display_text": "Missing case",
            "members": [],
        }],
    }
    monkeypatch.setattr(importer, "decode_plan", lambda _plan_bytes: plan)
    monkeypatch.setattr(importer, "verify_target", lambda *_args, **_kwargs: None)

    with Session(engine) as session:
        with pytest.raises(InspectionTeamImportFenceError, match="no canonical Case"):
            importer.guarded_preflight(session, b"ignored", expected_database_name="disposable")
        with pytest.raises(InspectionTeamImportFenceError, match="no canonical Case"):
            importer.guarded_apply(session, b"ignored", expected_database_name="disposable")
        with pytest.raises(InspectionTeamImportFenceError, match="refuses a partial import"):
            _apply(session, [{"classification": "BLOCKED_NO_CANONICAL_CASE", "legacy_inspection_id": 999}])
        assert session.query(InspectionTeam).count() == 0
        assert session.query(InspectionTeamMember).count() == 0
        assert session.query(InspectionTeamParticipantCatalog).count() == 0
        assert session.query(InspectionTeamParticipantAlias).count() == 0


def test_b5b_apply_creates_new_team_and_members_then_exact_rerun_is_noop():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    case_id = str(uuid4())
    with Session(engine) as session:
        assert _apply(session, [_apply_record(case_id)]) == 1
        session.commit()
        assert _apply(session, [_apply_record(case_id)]) == 0
        assert session.query(InspectionTeam).count() == 1
        assert session.query(InspectionTeamMember).count() == 1


def test_b5b_apply_rejects_empty_or_mismatched_existing_team():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    case_id = str(uuid4())
    with Session(engine) as session:
        session.add(InspectionTeam(case_id=case_id, display_text="Other"))
        session.commit()
        with pytest.raises(InspectionTeamImportFenceError, match="display_text collision"):
            _apply(session, [_apply_record(case_id)])
        session.rollback()
        session.query(InspectionTeam).delete()
        team = InspectionTeam(case_id=case_id, display_text="Historical")
        session.add(team)
        session.flush()
        with pytest.raises(InspectionTeamImportFenceError, match="empty existing"):
            _apply(session, [_apply_record(case_id)])


def test_b5b_apply_creates_org_catalog_alias_and_rolls_back_injected_failure():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    org_member = {"identity_kind": "ORGANIZATION_REPRESENTATIVE", "display_name": "Canonical org", "catalog_code": "ORG_REP", "legacy_source_token": "Legacy org", "role_code": "LEADER", "sort_order": 1, "inspector_profile_id": None, "person_id": None, "participant_catalog_id": None}
    record = _apply_record(case_id=str(uuid4()), name="Org")
    record["members"] = [org_member]
    with Session(engine) as session:
        assert _apply(session, [record]) == 1
        session.commit()
        member = session.query(InspectionTeamMember).one()
        catalog = session.query(InspectionTeamParticipantCatalog).one()
        assert member.participant_catalog_id == catalog.id
        assert member.display_name == "Canonical org"
        assert session.execute(text("SELECT source_value FROM inspection_team_participant_alias")).scalar_one() == "Legacy org"
        failing_case_id = str(uuid4())
        failing = _apply_record(case_id=failing_case_id)
        failing["members"][0]["identity_kind"] = "BAD"
        with pytest.raises(Exception):
            with session.begin_nested():
                _apply(session, [_apply_record(case_id=str(uuid4())), failing])
        assert session.query(InspectionTeam).filter_by(case_id=failing_case_id).count() == 0


def test_b5b_apply_rolls_back_earlier_team_catalog_and_alias_when_later_team_fails():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    first_case_id = str(uuid4())
    failed_case_id = str(uuid4())
    first = _apply_record(case_id=first_case_id, name="Organization team")
    first["members"] = [{
        "identity_kind": "ORGANIZATION_REPRESENTATIVE",
        "display_name": "Canonical organization",
        "catalog_code": "ORG_REP",
        "legacy_source_token": "Raw organization",
        "role_code": "LEADER",
        "sort_order": 1,
        "inspector_profile_id": None,
        "person_id": None,
        "participant_catalog_id": None,
    }]
    failed = _apply_record(case_id=failed_case_id, name="Invalid team")
    failed["members"][0]["identity_kind"] = "INVALID"

    with Session(engine) as session:
        with pytest.raises(IntegrityError):
            with session.begin_nested():
                _apply(session, [first, failed])
        assert session.query(InspectionTeam).filter_by(case_id=first_case_id).count() == 0
        assert session.query(InspectionTeam).filter_by(case_id=failed_case_id).count() == 0
        assert session.query(InspectionTeamMember).count() == 0
        assert session.query(InspectionTeamParticipantCatalog).count() == 0
        assert session.query(InspectionTeamParticipantAlias).count() == 0


def test_b5b_apply_rejects_alias_collision_without_creating_a_team():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    source_value = "Legacy organization"
    with Session(engine) as session:
        catalog = InspectionTeamParticipantCatalog(code="ORG_REP", display_name="Canonical organization")
        session.add(catalog)
        session.flush()
        session.add(
            InspectionTeamParticipantAlias(
                participant_id=catalog.id,
                source_system="legacy_workbook",
                source_sheet="db.ktra",
                source_value="Conflicting legacy organization",
                source_value_hash=sha256(source_value.encode("utf-8")).hexdigest(),
            )
        )
        session.commit()

        record = _apply_record(case_id=str(uuid4()), name="Organization team")
        record["members"] = [{
            "identity_kind": "ORGANIZATION_REPRESENTATIVE",
            "display_name": "Canonical organization",
            "catalog_code": "ORG_REP",
            "legacy_source_token": source_value,
            "role_code": "LEADER",
            "sort_order": 1,
            "inspector_profile_id": None,
            "person_id": None,
            "participant_catalog_id": None,
        }]
        with pytest.raises(InspectionTeamImportFenceError, match="alias conflicts"):
            with session.begin_nested():
                _apply(session, [record])
        assert session.query(InspectionTeam).count() == 0
        assert session.query(InspectionTeamParticipantCatalog).count() == 1
        assert session.query(InspectionTeamParticipantAlias).count() == 1


CANONICAL_SNAPSHOT_SHA256 = "484cf37603aacc5ff01a7bde5ffab01ed444748d5c7b1a0b30e7fc3a04936caa"
CANONICAL_PLAN_SHA256 = "0827c3f68715d24f2603b3642ce1149a52000e81970c4a665d8d9e95653aee41"


@pytest.fixture(scope="module")
def canonical_b5b_plan() -> tuple[dict, dict, dict]:
    snapshot = json.loads(Path("artifacts/phase3c/legacy_snapshot_v2.json").read_text(encoding="utf-8"))
    roster_plan = json.loads(Path("artifacts/phase3c/ttvien_personnel_plan_b2.json").read_text(encoding="utf-8"))
    plan = build_inspection_team_plan(
        snapshot,
        roster_plan,
        expected_snapshot_sha256=CANONICAL_SNAPSHOT_SHA256,
    )
    return snapshot, roster_plan, plan


def test_b5b_canonical_plan_preserves_disjoint_team_and_person_provenance(canonical_b5b_plan):
    _snapshot, roster_plan, plan = canonical_b5b_plan
    approved_personnel_keys = {
        (record["snapshot_sha256"], record["source_sheet"], record["source_row_number"])
        for record in roster_plan["records"]
        if record["classification"] == "IMPORT_CANDIDATE"
    }
    inspector_members = [
        member
        for team in plan["teams"]
        for member in team["members"]
        if member["identity_kind"] == "INSPECTOR_PROFILE"
    ]
    person_keys = {
        (
            member["person_source_provenance"]["snapshot_sha256"],
            member["person_source_provenance"]["source_sheet"],
            member["person_source_provenance"]["source_row_number"],
        )
        for member in inspector_members
    }
    assert plan["team_count"] == 1293
    assert plan["member_count"] == 5162
    assert plan["classification_counts"] == {
        "INSPECTOR_PROFILE": 5135,
        "LEGACY_PERSON": 22,
        "ORGANIZATION_REPRESENTATIVE": 5,
    }
    assert plan["blocked_unresolved_count"] == 0
    assert plan_sha256(plan) == CANONICAL_PLAN_SHA256
    assert importer.EXPECTED_PLAN_SHA256 == CANONICAL_PLAN_SHA256
    assert len(inspector_members) == 5135
    assert len(person_keys) == 337
    assert person_keys <= approved_personnel_keys
    assert {key[0] for key in person_keys} == {CANONICAL_SNAPSHOT_SHA256}
    assert {key[1] for key in person_keys} == {"TTviên"}
    assert all(team["source_provenance"]["source_sheet"] == "db.ktra" for team in plan["teams"])
    assert all(
        "person_source_provenance" not in member
        for team in plan["teams"]
        for member in team["members"]
        if member["identity_kind"] != "INSPECTOR_PROFILE"
    )


def test_b5b_preflight_resolves_every_canonical_inspector_occurrence_without_writes(
    canonical_b5b_plan,
    monkeypatch,
):
    _snapshot, roster_plan, plan = canonical_b5b_plan
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(importer, "decode_plan", lambda _plan_bytes: plan)
    monkeypatch.setattr(importer, "verify_target", lambda *_args, **_kwargs: None)

    with Session(engine) as session:
        profiles_by_key: dict[tuple[str, str, int], str] = {}
        for source in roster_plan["records"]:
            if source["classification"] != "IMPORT_CANDIDATE":
                continue
            person = Person(full_name=source["cleaned_full_name"])
            session.add(person)
            session.flush()
            profile = InspectorProfile(person_id=person.id, is_active=source["is_active"])
            session.add(profile)
            session.flush()
            key = (source["snapshot_sha256"], source["source_sheet"], source["source_row_number"])
            profiles_by_key[key] = profile.id
            session.add(
                LegacyInspectorSourceRecord(
                    snapshot_sha256=key[0],
                    source_sheet=key[1],
                    source_row_number=key[2],
                    inspector_profile_id=profile.id,
                    canonical_payload_sha256=source["source_provenance_hash"],
                )
            )
        for team in plan["teams"]:
            session.add(
                Case(
                    legacy_inspection_id=team["legacy_inspection_id"],
                    site_id=str(uuid4()),
                    gxp_type="GMP",
                    state=CaseState.DRAFT,
                )
            )
        session.commit()

        preflight = importer.guarded_preflight(session, b"approved-plan", expected_database_name="equivalent-live-state")
        resolved_profile_ids = [
            member["inspector_profile_id"]
            for record in preflight["records"]
            for member in record["members"]
            if member["identity_kind"] == "INSPECTOR_PROFILE"
        ]
        referenced_personnel_keys = {
            (
                member["person_source_provenance"]["snapshot_sha256"],
                member["person_source_provenance"]["source_sheet"],
                member["person_source_provenance"]["source_row_number"],
            )
            for team in plan["teams"]
            for member in team["members"]
            if member["identity_kind"] == "INSPECTOR_PROFILE"
        }
        assert preflight["write_candidate_count"] == 1293
        assert len(resolved_profile_ids) == 5135
        assert len(referenced_personnel_keys) == 337
        assert set(resolved_profile_ids) == {
            profiles_by_key[key] for key in referenced_personnel_keys
        }
        assert session.query(InspectionTeam).count() == 0
        assert session.query(InspectionTeamMember).count() == 0
        assert session.query(InspectionTeamParticipantCatalog).count() == 0
        assert session.query(InspectionTeamParticipantAlias).count() == 0
