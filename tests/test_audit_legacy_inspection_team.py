from __future__ import annotations

from copy import deepcopy
from hashlib import sha256

import pytest

import tools.audit_legacy_inspection_team as audit
from tools.audit_legacy_inspection_team import build_discovery, parse_source_team, select_snapshot_v2_db_ktra_rows


def _roster(name: str, row: int, *, pct: bool = False, star: bool = False) -> dict[str, object]:
    return {
        "classification": "IMPORT_CANDIDATE",
        "legacy_raw_full_name": name,
        "cleaned_full_name": name.removeprefix("PCT. ").removesuffix("*").strip(),
        "pct_marker": pct,
        "star_marker": star,
        "snapshot_sha256": "a" * 64,
        "source_sheet": "TTviên",
        "source_row_number": row,
    }


def _member(kind: str | None, *, profile: str | None = None, person: str | None = None, catalog: str | None = None, **extra: object) -> dict[str, object]:
    return {
        "identity_kind": kind,
        "inspector_profile_id": profile,
        "person_id": person,
        "participant_catalog_id": catalog,
        "display_name": "Display name",
        "role_code": "LEADER",
        "sort_order": 1,
        "profile_exists": True if profile else None,
        "profile_is_active": True if profile else None,
        "person_exists": True if person else None,
        "person_is_inspector_owned": False if person else None,
        "participant_catalog_exists": True if catalog else None,
        "participant_catalog_is_active": True if catalog else None,
        "participant_catalog_kind": "ORGANIZATION_REPRESENTATIVE" if catalog else None,
        **extra,
    }


def test_source_parser_preserves_order_and_duplicate_occurrences():
    parsed = parse_source_team("A, A, B")
    assert [(item["ordinal"], item["role_code"]) for item in parsed["members"]] == [(1, "LEADER"), (2, "SECRETARY"), (3, "MEMBER")]
    report = build_discovery([{"ID": "1", "source_row_number": 20, "T.tra viên": "A, A"}], snapshot_sha256="snapshot")
    duplicate = report["duplicate_occurrence_audit"]
    assert duplicate["policy"] == "PRESERVE_APPROVED_SOURCE_OCCURRENCES"
    assert duplicate["duplicate_group_count"] == 1
    assert duplicate["groups"][0]["source_occurrences"] == [
        {"source_row_number": 20, "source_ordinal": 1},
        {"source_row_number": 20, "source_ordinal": 2},
    ]
    assert report["database_mutated"] is False


@pytest.mark.parametrize("value", [None, "A", "A, B", "A, , B", "A; B", "A / B", "A\nB"])
def test_audit_parser_is_a_thin_adapter_over_canonical_parser(value: object):
    from backend.app.domain.legacy_db_ktra_reconciliation import parse_legacy_team
    canonical = parse_legacy_team(value)
    adapted = parse_source_team(value)
    assert adapted["split_state"] == canonical["state"]
    assert [(item["ordinal"], item["raw_name"], item["role_code"]) for item in adapted["members"]] == [
        (item["ordinal"], item["display_name"], item["role_code"]) for item in canonical["members"]
    ]


def test_snapshot_v2_selector_rejects_old_or_malformed_inputs():
    with pytest.raises(ValueError, match="Snapshot V2 provenance"):
        select_snapshot_v2_db_ktra_rows({"db.ktra": []}, expected_snapshot_sha256="a" * 64)
    snapshot = {"schema_version": "legacy-workbook-snapshot/v2", "sheets": [{"sheet_name": "db.ktra", "raw_rows": [{"source_row_number": "bad", "cells": []}]}]}
    from backend.app.domain.legacy_snapshot_v2 import snapshot_bytes
    with pytest.raises(ValueError, match="row provenance"):
        select_snapshot_v2_db_ktra_rows(snapshot, expected_snapshot_sha256=__import__("hashlib").sha256(snapshot_bytes(snapshot)).hexdigest())


def test_snapshot_v2_selector_uses_same_b5b_eligible_population_and_rejects_ambiguous_coordinates():
    def row(number, cells): return {"source_row_number": number, "cells": [{"column_ordinal": index, "raw_value": value} for index, value in enumerate(cells, start=1)]}
    snapshot = {"schema_version": "legacy-workbook-snapshot/v2", "sheets": [{"sheet_name": "db.ktra", "raw_rows": [
        row(4, ["ID", "LOẠI KT", "ID CƠ SỞ", "T.tra viên"]),
        row(5, [1, "Tái", 10, "A"]), row(6, ["bad", "Tái", 10, "B"]), row(7, [2, "", 10, "C"]), row(8, [3, "Tái", "", "D"]),
    ]}]}
    from backend.app.domain.legacy_snapshot_v2 import snapshot_bytes
    digest = __import__("hashlib").sha256(snapshot_bytes(snapshot)).hexdigest()
    assert select_snapshot_v2_db_ktra_rows(snapshot, expected_snapshot_sha256=digest) == [{"ID": 1, "T.tra viên": "A", "source_row_number": 5, "_b5b_eligible": True}]
    duplicate = deepcopy(snapshot); duplicate["sheets"][0]["raw_rows"].append(deepcopy(duplicate["sheets"][0]["raw_rows"][-1]))
    with pytest.raises(ValueError, match="row provenance is duplicated"):
        select_snapshot_v2_db_ktra_rows(duplicate, expected_snapshot_sha256=__import__("hashlib").sha256(snapshot_bytes(duplicate)).hexdigest())


def test_identity_resolution_uses_only_approved_marker_equivalence_and_preserves_provenance_layers():
    roster = [_roster("PCT. Nguyễn Văn A", 6, pct=True), _roster("Nguyễn Văn B", 7)]
    report = build_discovery(
        [{"ID": "1", "source_row_number": 20, "T.tra viên": "Nguyễn Văn A, Nguyễn Văn B"}],
        snapshot_sha256="a" * 64,
        identity_records=roster,
    )
    audit = report["identity_audit"]
    assert audit["match_counts"] == {"EXACT_AFTER_APPROVED_MARKER_EQUIVALENCE": 1, "EXACT_RAW_MATCH": 1}
    first = audit["resolved_occurrences"][0]
    assert first["team_source_provenance"]["source_sheet"] == "db.ktra"
    assert first["person_source_provenance"] == {"snapshot_sha256": "a" * 64, "source_sheet": "TTviên", "source_row_number": 6}


@pytest.mark.parametrize("alteration", [
    {"snapshot_sha256": "b" * 64},
    {"source_sheet": "db.ktra"},
    {"source_row_number": 0},
])
def test_identity_audit_fails_closed_for_invalid_personnel_provenance(alteration: dict[str, object]):
    record = _roster("A", 6)
    record.update(alteration)
    with pytest.raises(ValueError, match="approved TTviên"):
        build_discovery([{"ID": "1", "T.tra viên": "A"}], snapshot_sha256="a" * 64, identity_records=[record])


def test_identity_audit_fails_closed_for_duplicate_personnel_provenance():
    with pytest.raises(ValueError, match="provenance is duplicated"):
        build_discovery(
            [{"ID": "1", "T.tra viên": "A"}], snapshot_sha256="a" * 64,
            identity_records=[_roster("A", 6), _roster("Other A", 6)],
        )


@pytest.mark.parametrize("token, roster_name", [
    ("Nguyen Van A", "Nguyễn Văn A"),
    ("Nguyễn Văn", "Nguyễn Văn A"),
    ("N. Văn A", "Nguyễn Văn A"),
])
def test_identity_resolution_rejects_accent_substring_and_abbreviation_equivalence(token: str, roster_name: str):
    report = build_discovery(
        [{"ID": "1", "T.tra viên": token}], snapshot_sha256="a" * 64,
        identity_records=[_roster(roster_name, 6)],
    )
    assert report["identity_audit"]["match_counts"] == {"ZERO_MATCH": 1}
    assert report["diagnostic_similarity"]["purpose"].startswith("aggregate discovery")


def test_identity_invariants_cover_three_kinds_inactive_bypass_and_invalid_shapes():
    members = [
        _member("INSPECTOR_PROFILE", profile="profile-1"),
        _member("LEGACY_PERSON"),
        _member("ORGANIZATION_REPRESENTATIVE", catalog="catalog-1"),
        _member("INSPECTOR_PROFILE", profile="inactive", profile_is_active=False),
        _member("INSPECTOR_PROFILE", profile="profile-2", person="person-2", person_is_inspector_owned=True),
        _member("LEGACY_PERSON", person="illegal-person"),
        _member("INSPECTOR_PROFILE", profile="missing-profile", profile_exists=False),
        _member("ORGANIZATION_REPRESENTATIVE", catalog="missing-catalog", participant_catalog_exists=False),
    ]
    report = build_discovery([], snapshot_sha256="snapshot", canonical_member_records=members)
    failures = report["identity_invariants"]["failure_counts"]
    assert failures["INACTIVE_INSPECTOR_PROFILE"] == 1
    assert failures["INSPECTOR_BYPASS_VIA_PERSON"] == 1
    assert failures["INVALID_INSPECTOR_PROFILE_SHAPE"] == 1
    assert failures["INVALID_LEGACY_PERSON_SHAPE"] == 1
    assert failures["ORPHAN_INSPECTOR_PROFILE"] == 1
    assert failures["ORPHAN_PARTICIPANT_CATALOG"] == 1
    assert report["runtime_contract_audit"]["legacy_person"] == "HISTORICAL_READ_ONLY"


def test_identity_invariants_include_runtime_compatibility_without_new_persisted_kind():
    members = [
        _member(None, person="generic-person"),
        _member(None, profile="profile-1"),
        _member(None),
        _member(None, profile="profile-2", person="person-2"),
        _member(None, person="inspector-owned-person", person_is_inspector_owned=True),
    ]
    report = build_discovery([], snapshot_sha256="snapshot", canonical_member_records=members)
    failures = report["identity_invariants"]["failure_counts"]
    assert failures["INVALID_COMPATIBILITY_IDENTITY_SHAPE"] == 2
    assert failures["INSPECTOR_BYPASS_VIA_PERSON"] == 1
    assert report["runtime_contract_audit"]["runtime_compatibility_path"].startswith("identity_kind_null")


def test_unknown_runtime_evidence_is_incomplete_not_pass():
    report = build_discovery([], snapshot_sha256="snapshot", canonical_member_records=[_member("INSPECTOR_PROFILE", profile="profile", profile_exists=None, profile_is_active=None)])
    assert report["identity_invariants"]["status"] == "INCOMPLETE_EVIDENCE"
    assert report["identity_invariants"]["failure_counts"]["MISSING_PROFILE_EXISTENCE_EVIDENCE"] == 1


def test_proven_invalid_invariant_overrides_missing_evidence():
    report = build_discovery([], snapshot_sha256="snapshot", canonical_member_records=[
        _member("INSPECTOR_PROFILE", profile="profile", person="illegal", profile_exists=None, profile_is_active=None),
    ])
    assert report["identity_invariants"]["status"] == "FAIL"


def test_catalog_alias_requires_explicit_catalog_route_and_orphans_are_reported():
    report = build_discovery(
        [], snapshot_sha256="snapshot",
        catalog_records=[{"id": "catalog-1", "code": "ORG_REP_TRADITIONAL_MEDICINE", "participant_kind": "ORGANIZATION_REPRESENTATIVE", "display_name": "Đại diện Cục Quản lý Y, Dược cổ truyền", "is_active": True}],
        alias_records=[{"participant_id": "catalog-1", "source_system": "legacy_workbook", "source_sheet": "db.ktra", "source_value": "Đại diện Cục Quản lý Y‚ Dược cổ truyền", "source_value_hash": sha256("Đại diện Cục Quản lý Y‚ Dược cổ truyền".encode("utf-8")).hexdigest()}],
    )
    assert report["catalog_audit"]["status"] == "PASS"
    bad = build_discovery(
        [], snapshot_sha256="snapshot",
        catalog_records=[{"id": "catalog-1", "code": "ORG", "participant_kind": "ORGANIZATION_REPRESENTATIVE", "display_name": "Canonical", "is_active": True}],
        alias_records=[{"participant_id": "missing", "source_system": "legacy_workbook", "source_sheet": "db.ktra", "source_value": "Raw", "source_value_hash": sha256(b"Raw").hexdigest()}],
    )
    assert bad["alias_audit"]["failure_counts"] == {"ORPHAN_ALIAS_PARTICIPANT": 1}


def test_catalog_and_organization_member_activity_and_shape_are_audited():
    report = build_discovery(
        [], snapshot_sha256="snapshot",
        canonical_member_records=[
            _member("ORGANIZATION_REPRESENTATIVE", catalog="inactive", participant_catalog_is_active=False),
            _member("ORGANIZATION_REPRESENTATIVE", catalog="wrong-kind", participant_catalog_kind="OTHER"),
        ],
        catalog_records=[
            {"id": "duplicate", "code": "DUP", "participant_kind": "OTHER", "display_name": "", "is_active": "unknown"},
            {"id": "duplicate", "code": "DUP", "participant_kind": "ORGANIZATION_REPRESENTATIVE", "display_name": "Valid", "is_active": True},
        ],
    )
    assert report["identity_invariants"]["failure_counts"]["INACTIVE_PARTICIPANT_CATALOG"] == 1
    assert report["identity_invariants"]["failure_counts"]["INVALID_PARTICIPANT_CATALOG_KIND"] == 1
    catalog_failures = report["catalog_audit"]["failure_counts"]
    assert catalog_failures["DUPLICATE_CATALOG_ID"] == 1
    assert catalog_failures["DUPLICATE_CATALOG_CODE"] == 1
    assert catalog_failures["ACTIVITY_NOT_EXPLICITLY_OBSERVED"] == 1


def test_complete_catalog_requires_two_canonical_seed_rows_and_active_exact_display():
    seeds = [
        {"id": "science", "code": "ORG_REP_SCIENCE_TECH_TRAINING", "participant_kind": "ORGANIZATION_REPRESENTATIVE", "display_name": "Đại diện Cục Khoa học công nghệ và đào tạo", "is_active": True},
        {"id": "traditional", "code": "ORG_REP_TRADITIONAL_MEDICINE", "participant_kind": "ORGANIZATION_REPRESENTATIVE", "display_name": "Đại diện Cục Quản lý Y, Dược cổ truyền", "is_active": True},
    ]
    aliases = [
        {"participant_id": "science", "source_system": "legacy_workbook", "source_sheet": "db.ktra", "source_value": "Đại diện Cục Khoa học công nghệ và đào tạo", "source_value_hash": sha256("Đại diện Cục Khoa học công nghệ và đào tạo".encode()).hexdigest()},
        {"participant_id": "traditional", "source_system": "legacy_workbook", "source_sheet": "db.ktra", "source_value": "Đại diện Cục Quản lý Y‚ Dược cổ truyền", "source_value_hash": sha256("Đại diện Cục Quản lý Y‚ Dược cổ truyền".encode()).hexdigest()},
    ]
    assert build_discovery([], snapshot_sha256="snapshot", catalog_records=seeds, alias_records=aliases, catalog_mode="COMPLETE_B5B_CATALOG")["catalog_audit"]["status"] == "PASS"
    missing = build_discovery([], snapshot_sha256="snapshot", catalog_records=seeds[:1], alias_records=aliases, catalog_mode="COMPLETE_B5B_CATALOG")
    assert missing["catalog_audit"]["failure_counts"]["MISSING_CANONICAL_SEED"] == 1
    wrong = deepcopy(seeds); wrong[0]["display_name"] = "Wrong"; wrong[1]["is_active"] = False
    failures = build_discovery([], snapshot_sha256="snapshot", catalog_records=wrong, alias_records=aliases, catalog_mode="COMPLETE_B5B_CATALOG")["catalog_audit"]["failure_counts"]
    assert failures["CANONICAL_SEED_DISPLAY_MISMATCH"] == 1 and failures["INACTIVE_CANONICAL_SEED"] == 1


def test_alias_audit_preserves_raw_punctuation_and_rejects_hash_or_provenance_collisions():
    raw = "Đại diện Cục Quản lý Y‚ Dược cổ truyền"
    alias = {
        "participant_id": "catalog-1", "source_system": "legacy_workbook", "source_sheet": "db.ktra",
        "source_value": raw, "source_value_hash": sha256(raw.encode("utf-8")).hexdigest(),
    }
    report = build_discovery(
        [], snapshot_sha256="snapshot",
        catalog_records=[{"id": "catalog-1", "code": "ORG_REP_TRADITIONAL_MEDICINE", "participant_kind": "ORGANIZATION_REPRESENTATIVE", "display_name": "Đại diện Cục Quản lý Y, Dược cổ truyền", "is_active": True}],
        alias_records=[alias, deepcopy(alias)],
    )
    assert report["alias_audit"]["failure_counts"] == {"DUPLICATE_ALIAS_PROVENANCE": 1}
    assert alias["source_value"] == raw


def test_alias_audit_requires_canonical_b5b_route():
    raw = "Đại diện Cục Quản lý Y‚ Dược cổ truyền"
    alias = {"participant_id": "wrong", "source_system": "wrong", "source_sheet": "wrong", "source_value": raw, "source_value_hash": sha256(raw.encode()).hexdigest()}
    report = build_discovery([], snapshot_sha256="snapshot", catalog_records=[{"id": "wrong", "code": "ORG_REP_SCIENCE_TECH_TRAINING", "participant_kind": "ORGANIZATION_REPRESENTATIVE", "display_name": "Wrong", "is_active": True}], alias_records=[alias])
    failures = report["alias_audit"]["failure_counts"]
    assert failures["INVALID_SOURCE_SYSTEM"] == 1 and failures["INVALID_SOURCE_SHEET"] == 1
    assert failures["CANONICAL_RAW_ALIAS_ROUTED_TO_WRONG_CATALOG"] == 1


def test_complete_alias_audit_requires_exact_raw_aliases_and_active_targets():
    raw_science = "Đại diện Cục Khoa học công nghệ và đào tạo"; raw_traditional = "Đại diện Cục Quản lý Y‚ Dược cổ truyền"
    catalogs = [
        {"id": "science", "code": "ORG_REP_SCIENCE_TECH_TRAINING", "participant_kind": "ORGANIZATION_REPRESENTATIVE", "display_name": raw_science, "is_active": True},
        {"id": "traditional", "code": "ORG_REP_TRADITIONAL_MEDICINE", "participant_kind": "ORGANIZATION_REPRESENTATIVE", "display_name": "Đại diện Cục Quản lý Y, Dược cổ truyền", "is_active": True},
    ]
    aliases = [{"participant_id": item[0], "source_system": "legacy_workbook", "source_sheet": "db.ktra", "source_value": item[1], "source_value_hash": sha256(item[1].encode()).hexdigest()} for item in [("science", raw_science), ("traditional", raw_traditional)]]
    assert build_discovery([], snapshot_sha256="snapshot", catalog_records=catalogs, alias_records=aliases, catalog_mode="COMPLETE_B5B_CATALOG")["alias_audit"]["status"] == "PASS"
    rewritten = deepcopy(aliases); rewritten[1]["source_value"] = catalogs[1]["display_name"]; rewritten[1]["source_value_hash"] = sha256(rewritten[1]["source_value"].encode()).hexdigest()
    assert build_discovery([], snapshot_sha256="snapshot", catalog_records=catalogs, alias_records=rewritten, catalog_mode="COMPLETE_B5B_CATALOG")["alias_audit"]["status"] == "FAIL"
    inactive = deepcopy(catalogs); inactive[1]["is_active"] = False
    assert build_discovery([], snapshot_sha256="snapshot", catalog_records=inactive, alias_records=aliases, catalog_mode="COMPLETE_B5B_CATALOG")["alias_audit"]["failure_counts"]["ALIAS_TARGET_NOT_ACTIVE"] == 1


def test_source_provenance_never_fabricates_row_number_and_null_legacy_ids_do_not_cross_group():
    report = build_discovery(
        [{"ID": "not-an-id", "T.tra viên": "A"}, {"ID": "also-invalid", "T.tra viên": "A"}],
        snapshot_sha256="snapshot",
    )
    occurrences = report["provenance_audit"]["team_occurrences"]
    assert [item["team_source_provenance"] for item in occurrences] == [
        {"source_sheet": "db.ktra", "input_record_ordinal": 1, "source_row_provenance": "UNAVAILABLE_FROM_INPUT"},
        {"source_sheet": "db.ktra", "input_record_ordinal": 2, "source_row_provenance": "UNAVAILABLE_FROM_INPUT"},
    ]
    assert report["duplicate_occurrence_audit"]["duplicate_group_count"] == 0


def test_audit_is_deterministic_and_does_not_mutate_input():
    rows = [{"ID": "1", "T.tra viên": "PCT. A, B"}]
    roster = [_roster("PCT. A", 6, pct=True), _roster("B", 7)]
    original_rows, original_roster = deepcopy(rows), deepcopy(roster)
    first = build_discovery(rows, snapshot_sha256="a" * 64, identity_records=roster)
    second = build_discovery(rows, snapshot_sha256="a" * 64, identity_records=roster)
    assert first == second
    assert rows == original_rows
    assert roster == original_roster
    assert first["database_mutated"] is False


def test_audit_result_has_fail_closed_precedence_and_nonempty_findings():
    incomplete = build_discovery([], snapshot_sha256="snapshot", canonical_member_records=[_member("INSPECTOR_PROFILE", profile="profile", profile_exists=None)])
    assert incomplete["audit_result"]["status"] == "INCOMPLETE_EVIDENCE"
    assert incomplete["unresolved_findings"] == ["identity_invariants:MISSING_PROFILE_EXISTENCE_EVIDENCE"]
    failed = build_discovery([], snapshot_sha256="snapshot", canonical_member_records=[_member("INSPECTOR_PROFILE", profile="profile", profile_exists=None, profile_is_active=False)])
    assert failed["audit_result"]["status"] == "FAIL"
    assert "identity_invariants:INACTIVE_INSPECTOR_PROFILE" in failed["audit_result"]["blocking_findings"]


def test_complete_catalog_mode_requires_both_catalog_and_alias_evidence():
    with pytest.raises(ValueError, match="requires catalog and alias"):
        build_discovery([], snapshot_sha256="snapshot", catalog_records=[], catalog_mode="COMPLETE_B5B_CATALOG")


def test_catalog_malformed_unhashable_identifiers_fail_closed_without_typeerror():
    report = build_discovery([], snapshot_sha256="snapshot", catalog_records=[{"id": [], "code": {}, "participant_kind": "ORGANIZATION_REPRESENTATIVE", "display_name": "Name", "is_active": True}])
    assert report["catalog_audit"]["status"] == "FAIL"
    assert report["catalog_audit"]["failure_counts"] == {"MISSING_CATALOG_CODE": 1, "MISSING_CATALOG_ID": 1}


def test_source_counts_distinguish_eligible_known_and_unresolved_rows():
    report = build_discovery([
        {"ID": "1", "T.tra viên": "A", "_b5b_eligible": True},
        {"ID": "2", "T.tra viên": None, "_b5b_eligible": True},
        {"ID": "3", "T.tra viên": "B", "_b5b_eligible": False},
    ], snapshot_sha256="snapshot")
    assert report["team_counts"] == {
        "b5b_eligible_source_rows": 2,
        "b5b_plannable_known_team_rows": 1,
        "missing_or_unresolved_team_rows": 1,
        "member_occurrences": 1,
        "source_family_counts": {"MISSING": 1, "SINGLE_NAME": 1},
    }


def _cli_snapshot(path, *, source_team: str = "A") -> str:
    from backend.app.domain.legacy_snapshot_v2 import snapshot_bytes
    snapshot = {
        "schema_version": "legacy-workbook-snapshot/v2",
        "sheets": [{"sheet_name": "db.ktra", "raw_rows": [
            {"source_row_number": 4, "cells": [
                {"column_ordinal": 1, "raw_value": "ID"},
                {"column_ordinal": 2, "raw_value": "LOẠI KT"},
                {"column_ordinal": 3, "raw_value": "ID CƠ SỞ"},
                {"column_ordinal": 4, "raw_value": "T.tra viên"},
            ]},
            {"source_row_number": 5, "cells": [
                {"column_ordinal": 1, "raw_value": 1},
                {"column_ordinal": 2, "raw_value": "Tái"},
                {"column_ordinal": 3, "raw_value": 2},
                {"column_ordinal": 4, "raw_value": source_team},
            ]},
        ]}],
    }
    path.write_bytes(snapshot_bytes(snapshot))
    return sha256(path.read_bytes()).hexdigest()


def test_cli_exit_policy_and_declared_git_provenance(tmp_path):
    snapshot = tmp_path / "snapshot.json"; expected = _cli_snapshot(snapshot)
    working = tmp_path / "working.json"; working.write_text("{}", encoding="utf-8")
    output = tmp_path / "audit.json"
    base = ["--snapshot", str(snapshot), "--expected-snapshot-sha256", expected, "--git-commit", "declared-commit", "--git-blob-sha", "declared-blob", "--working-tree-snapshot", str(working), "--output", str(output)]
    assert audit.main(base) == 0
    report = __import__("json").loads(output.read_text(encoding="utf-8"))
    assert report["audit_result"]["status"] == "PASS"
    assert report["provenance"]["declared_git_commit"] == "declared-commit"
    assert report["provenance"]["git_provenance_verification"] == "NOT_VERIFIED_BY_THIS_TOOL"
    members = tmp_path / "members.json"
    members.write_text(__import__("json").dumps([_member("INSPECTOR_PROFILE", profile="profile", profile_is_active=False)]), encoding="utf-8")
    assert audit.main([*base, "--canonical-member-input", str(members)]) == 2


def test_cli_partial_incomplete_is_exploratory_but_complete_fails_closed(tmp_path):
    snapshot = tmp_path / "snapshot.json"; expected = _cli_snapshot(snapshot)
    working = tmp_path / "working.json"; working.write_text("{}", encoding="utf-8")
    output = tmp_path / "audit.json"
    incomplete = tmp_path / "members.json"
    incomplete.write_text(__import__("json").dumps([_member("INSPECTOR_PROFILE", profile="profile", profile_exists=None)]), encoding="utf-8")
    base = ["--snapshot", str(snapshot), "--expected-snapshot-sha256", expected, "--git-commit", "declared-commit", "--git-blob-sha", "declared-blob", "--working-tree-snapshot", str(working), "--output", str(output), "--canonical-member-input", str(incomplete)]
    assert audit.main(base) == 0
    with pytest.raises(ValueError, match="requires catalog and alias"):
        audit.main([*base, "--complete-b5b-catalog"])
    alias_only = tmp_path / "alias-only.json"
    alias_only.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="requires catalog and alias"):
        audit.main([*base, "--alias-input", str(alias_only), "--complete-b5b-catalog"])
    catalog = tmp_path / "catalog.json"
    catalog.write_text(__import__("json").dumps([
        {"id": "science", "code": "ORG_REP_SCIENCE_TECH_TRAINING", "participant_kind": "ORGANIZATION_REPRESENTATIVE", "display_name": "Đại diện Cục Khoa học công nghệ và đào tạo", "is_active": True},
        {"id": "traditional", "code": "ORG_REP_TRADITIONAL_MEDICINE", "participant_kind": "ORGANIZATION_REPRESENTATIVE", "display_name": "Đại diện Cục Quản lý Y, Dược cổ truyền", "is_active": True},
    ]), encoding="utf-8")
    aliases = tmp_path / "aliases.json"
    aliases.write_text(__import__("json").dumps([
        {"participant_id": "science", "source_system": "legacy_workbook", "source_sheet": "db.ktra", "source_value": "Đại diện Cục Khoa học công nghệ và đào tạo", "source_value_hash": sha256("Đại diện Cục Khoa học công nghệ và đào tạo".encode()).hexdigest()},
        {"participant_id": "traditional", "source_system": "legacy_workbook", "source_sheet": "db.ktra", "source_value": "Đại diện Cục Quản lý Y‚ Dược cổ truyền", "source_value_hash": sha256("Đại diện Cục Quản lý Y‚ Dược cổ truyền".encode()).hexdigest()},
    ]), encoding="utf-8")
    assert audit.main([*base, "--catalog-input", str(catalog), "--alias-input", str(aliases), "--complete-b5b-catalog"]) == 2


def test_complete_cli_returns_pass_for_valid_required_evidence(tmp_path):
    snapshot = tmp_path / "snapshot.json"; expected = _cli_snapshot(snapshot)
    working = tmp_path / "working.json"; working.write_text("{}", encoding="utf-8")
    output = tmp_path / "audit.json"
    catalog = tmp_path / "catalog.json"
    catalog.write_text(__import__("json").dumps([
        {"id": "science", "code": "ORG_REP_SCIENCE_TECH_TRAINING", "participant_kind": "ORGANIZATION_REPRESENTATIVE", "display_name": "Đại diện Cục Khoa học công nghệ và đào tạo", "is_active": True},
        {"id": "traditional", "code": "ORG_REP_TRADITIONAL_MEDICINE", "participant_kind": "ORGANIZATION_REPRESENTATIVE", "display_name": "Đại diện Cục Quản lý Y, Dược cổ truyền", "is_active": True},
    ]), encoding="utf-8")
    aliases = tmp_path / "aliases.json"
    aliases.write_text(__import__("json").dumps([
        {"participant_id": "science", "source_system": "legacy_workbook", "source_sheet": "db.ktra", "source_value": "Đại diện Cục Khoa học công nghệ và đào tạo", "source_value_hash": sha256("Đại diện Cục Khoa học công nghệ và đào tạo".encode()).hexdigest()},
        {"participant_id": "traditional", "source_system": "legacy_workbook", "source_sheet": "db.ktra", "source_value": "Đại diện Cục Quản lý Y‚ Dược cổ truyền", "source_value_hash": sha256("Đại diện Cục Quản lý Y‚ Dược cổ truyền".encode()).hexdigest()},
    ]), encoding="utf-8")
    assert audit.main(["--snapshot", str(snapshot), "--expected-snapshot-sha256", expected, "--git-commit", "declared", "--git-blob-sha", "declared", "--working-tree-snapshot", str(working), "--catalog-input", str(catalog), "--alias-input", str(aliases), "--complete-b5b-catalog", "--output", str(output)]) == 0
    assert __import__("json").loads(output.read_text(encoding="utf-8"))["audit_result"]["status"] == "PASS"


def test_alias_malformed_unhashable_participant_id_fails_cleanly():
    report = build_discovery([], snapshot_sha256="snapshot", catalog_records=[], alias_records=[{"participant_id": [], "source_system": "legacy_workbook", "source_sheet": "db.ktra", "source_value": "Raw", "source_value_hash": sha256(b"Raw").hexdigest()}])
    assert report["alias_audit"]["failure_counts"] == {"INVALID_ALIAS_PARTICIPANT_ID": 1, "ORPHAN_ALIAS_PARTICIPANT": 1}
