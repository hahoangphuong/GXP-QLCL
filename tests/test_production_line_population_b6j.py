from __future__ import annotations

from hashlib import sha256
import json

import pytest

from backend.app.domain.production_line_population import canonical_artifact_bytes, canonical_json_bytes
from backend.app.domain.production_line_population_b6j import ProductionLinePopulationPlanError, _dates, bind_candidate_roster, build_population_plan, plan_digest
from backend.app.domain.production_line_population_writer_b6j import ProductionLinePopulationApplyError, _validate_authoritative_rehearsal_plan, _validate_plan, _validate_target_mode
from backend.app.domain.legacy_db_ktra_source_v2 import snapshot_cell, snapshot_header_map, snapshot_sheet
from backend.app.domain.legacy_snapshot_v2 import snapshot_legacy_int
from backend.app.domain.production_line_review_workspace import REVIEW_SCHEMA_VERSION, candidate_set_digest
from tools.plan_production_line_population_b6j import main as planner_main
from tools.apply_production_line_population_b6j import main as writer_cli_main


SITE_7 = "00000000-0000-0000-0000-000000000007"
SITE_8 = "00000000-0000-0000-0000-000000000008"


def _row(number: int, cells: dict[int, object]) -> dict[str, object]:
    return {"source_row_number": number, "cells": [{"column_ordinal": key, "raw_value": value} for key, value in cells.items()]}


def _snapshot() -> dict[str, object]:
    return {"schema_version": "legacy-workbook-snapshot/v2", "sheets": [
        {"sheet_name": "db.ktra", "raw_rows": [
            _row(4, {1: "ID", 2: "LOẠI KT", 3: "ID CƠ SỞ", 4: "MÃ DC", 5: "Ngày K.tra"}),
            _row(5, {1: 10, 2: "GMP", 3: 7, 4: "A", 5: "17-19/07/2026"}),
            _row(6, {1: 11, 2: "GMP", 3: 8, 4: "A", 5: "20/07/2026"}),
            _row(7, {1: 12, 2: "GMP", 3: 7, 4: "B", 5: "-"}),
        ]},
        {"sheet_name": "db.cc", "raw_rows": [
            _row(4, {1: "ID", 4: "LOẠI CC", 5: "ID ĐỢT KTRA", 8: "ID CƠ SỞ", 9: "MÃ DC", 10: "Ngày cấp CC"}),
            _row(5, {1: 20, 4: "GMP", 5: 10, 8: 7, 9: "A", 10: "2026-08-21"}),
            _row(6, {1: 21, 4: "GMP", 5: 11, 8: 7, 9: "A", 10: "2026-08-21"}),
            _row(7, {1: 22, 4: "GMP", 5: 12, 8: 7, 9: "B", 10: "2020-01-01"}),
        ]},
    ]}


def _state() -> tuple[dict[str, object], str]:
    state: dict[str, object] = {"schema_version": "production-line-canonical-state/v1", "exported_at": None,
        "source_database_identity": {"database_name": "fixture"}, "source_alembic_revision": "20260929_0017",
        "sites": [{"id": SITE_7, "legacy_site_id": 7}, {"id": SITE_8, "legacy_site_id": 8}],
        "existing_production_lines": [],
        "cases": [{"id": "case-10", "legacy_inspection_id": 10, "site_id": SITE_7, "production_line_id": None, "row_version": 1}, {"id": "case-11", "legacy_inspection_id": 11, "site_id": SITE_8, "production_line_id": None, "row_version": 1}, {"id": "case-12", "legacy_inspection_id": 12, "site_id": SITE_7, "production_line_id": None, "row_version": 1}],
        "certificates": [{"id": "certificate-20", "legacy_certificate_id": 20, "site_id": SITE_7, "case_id": "case-10", "production_line_id": None, "row_version": 1}, {"id": "certificate-21", "legacy_certificate_id": 21, "site_id": SITE_7, "case_id": "case-11", "production_line_id": None, "row_version": 1}, {"id": "certificate-22", "legacy_certificate_id": 22, "site_id": SITE_7, "case_id": "case-12", "production_line_id": None, "row_version": 1}],
        "physical_line_evidence": [], "transformations": []}
    state["source_state_fingerprint"] = sha256(canonical_json_bytes(state)).hexdigest()
    return state, sha256(canonical_json_bytes(state)).hexdigest()


def _seal_roster(roster: dict[str, object]) -> dict[str, object]:
    unsigned = dict(roster)
    unsigned.pop("content_sha256", None)
    roster["content_sha256"] = sha256(canonical_artifact_bytes(unsigned)).hexdigest()
    return roster


def _roster_for_candidates(candidates: list[dict[str, object]], *, snapshot_sha256: str, canonical_state_sha256: str) -> dict[str, object]:
    items = [{
        "candidate_key": candidate["candidate_key"],
        "source_site_legacy_id": candidate["legacy_site_id"],
        "canonical_site_id": candidate["canonical_site_id"],
        "canonical_line_text": candidate["canonical_line_code"],
        "source_case_ids": candidate["source_case_ids"],
        "source_certificate_ids": candidate["source_certificate_ids"],
        "case_count": len(candidate["source_case_ids"]),
        "certificate_count": len(candidate["source_certificate_ids"]),
        "existing_production_line_id": candidate["existing_production_line_id"],
        # Historical review state is intentionally outside B6J identity semantics.
        "review_tags": [], "review_status": "PENDING_HUMAN_REVIEW",
    } for candidate in candidates]
    return _seal_roster({
        "schema_version": REVIEW_SCHEMA_VERSION,
        "artifact_kind": "production_line_physical_identity_review_roster",
        "generated_at": None,
        "planner_version": "b6h-production-line-population/v2",
        "legacy_snapshot_sha256": snapshot_sha256,
        "canonical_state_sha256": canonical_state_sha256,
        "candidate_set_sha256": candidate_set_digest(items),
        "items": items,
    })


def _bound_plan(snapshot: dict[str, object], state: dict[str, object], digest: str) -> tuple[dict[str, object], dict[str, object]]:
    snapshot_sha256 = "a" * 64
    preliminary = build_population_plan(snapshot, snapshot_sha256=snapshot_sha256, canonical_state=state, canonical_state_sha256=digest, candidate_set_sha256="b" * 64)
    roster = _roster_for_candidates(preliminary["candidates"], snapshot_sha256=snapshot_sha256, canonical_state_sha256=digest)
    raw_sha256 = sha256(canonical_artifact_bytes(roster)).hexdigest()
    plan = build_population_plan(snapshot, snapshot_sha256=snapshot_sha256, canonical_state=state, canonical_state_sha256=digest, candidate_set_sha256=roster["candidate_set_sha256"], candidate_roster=roster, candidate_roster_raw_sha256=raw_sha256)
    return plan, roster


def test_site_local_codes_create_independent_lines_with_earliest_bound_date():
    state, digest = _state()
    plan = build_population_plan(_snapshot(), snapshot_sha256="a" * 64, canonical_state=state, canonical_state_sha256=digest, candidate_set_sha256="b" * 64)
    candidates = {(item["legacy_site_id"], item["canonical_line_code"]): item for item in plan["candidates"]}
    assert candidates[7, "A"]["classification"] == "CREATE_NEW_PRODUCTION_LINE"
    assert candidates[8, "A"]["classification"] == "CREATE_NEW_PRODUCTION_LINE"
    assert candidates[7, "A"]["proposed_production_line_id"] != candidates[8, "A"]["proposed_production_line_id"]
    assert candidates[7, "A"]["effective_from"] == "2026-07-17"
    assert candidates[7, "A"]["effective_from_source_type"] == "CASE"
    assert candidates[7, "B"]["effective_from"] == "2020-01-01"
    assert candidates[7, "B"]["effective_from_source_type"] == "CERTIFICATE"


def test_site_mismatch_certificate_and_unknown_effective_date_fail_closed():
    state, digest = _state()
    snapshot = _snapshot()
    for cell in snapshot["sheets"][1]["raw_rows"][3]["cells"]:
        if cell["column_ordinal"] == 10:
            cell["raw_value"] = "-"
    plan = build_population_plan(snapshot, snapshot_sha256="a" * 64, canonical_state=state, canonical_state_sha256=digest, candidate_set_sha256="b" * 64)
    candidates = {(item["legacy_site_id"], item["canonical_line_code"]): item for item in plan["candidates"]}
    assert candidates[7, "B"]["classification"] == "BLOCKED_EFFECTIVE_FROM_UNKNOWN"
    mismatch = next(item for item in plan["certificate_links"] if item["legacy_id"] == 21)
    assert mismatch["classification"] == "BLOCKED_SITE_MISMATCH"


def test_plan_is_deterministic_sealed_and_accounts_for_every_valid_source_row():
    state, digest = _state()
    first = build_population_plan(_snapshot(), snapshot_sha256="a" * 64, canonical_state=state, canonical_state_sha256=digest, candidate_set_sha256="b" * 64)
    second = build_population_plan(_snapshot(), snapshot_sha256="a" * 64, canonical_state=state, canonical_state_sha256=digest, candidate_set_sha256="b" * 64)
    assert first == second
    assert first["plan_sha256"] == plan_digest(first)
    assert sum(first["summary_counts"]["candidates"].values()) == len(first["candidates"])
    assert sum(first["summary_counts"]["cases"].values()) == 3
    assert sum(first["summary_counts"]["certificates"].values()) == 3
    candidate = next(item for item in first["candidates"] if item["legacy_site_id"] == 7 and item["canonical_line_code"] == "A")
    assert candidate["effective_from_basis"] == "EARLIEST_EVIDENCED_ACTIVE_DATE"
    assert candidate["effective_from_source_state"] == "KNOWN"
    assert candidate["effective_from_source_sheet"] == "db.ktra"
    assert candidate["effective_from_source_field"] == "Ngày K.tra"


def test_b6i_roster_binding_seals_exact_identity_universe_without_review_gate():
    state, digest = _state()
    plan, roster = _bound_plan(_snapshot(), state, digest)
    assert plan["candidate_set_roster_item_count"] == 3
    assert plan["candidate_set_roster_content_sha256_verified"] is True
    assert plan["candidate_set_roster_content_sha256"] == roster["content_sha256"]
    assert all(item["review_status"] == "PENDING_HUMAN_REVIEW" for item in roster["items"])


def test_writer_rejects_plan_without_immutable_b6i_roster_binding():
    state, digest = _state()
    unbound = build_population_plan(_snapshot(), snapshot_sha256="a" * 64, canonical_state=state, canonical_state_sha256=digest, candidate_set_sha256="b" * 64)
    with pytest.raises(ProductionLinePopulationApplyError, match="immutable candidate_set_roster_sha256"):
        _validate_plan(unbound)
    bound, _ = _bound_plan(_snapshot(), state, digest)
    _validate_plan(bound)


@pytest.mark.parametrize(
    ("field", "corrupt", "error"),
    (
        ("planned_production_line_id", "00000000-0000-0000-0000-000000000099", "target differs"),
        ("expected_site_id", SITE_8, "crosses candidate Site"),
        ("canonical_line_code", "OTHER", "code differs"),
        ("legacy_id", 999, "candidate membership differs from source roster"),
        ("classification", "LINK_TO_EXISTING_LINE", "classifications disagree"),
    ),
)
def test_b6j_writer_rejects_resealed_inconsistent_link_before_database_access(field, corrupt, error):
    state, digest = _state()
    plan, _ = _bound_plan(_snapshot(), state, digest)
    link = next(item for item in plan["case_links"] if item["classification"] == "LINK_TO_NEW_LINE")
    link[field] = corrupt
    plan["plan_sha256"] = plan_digest(plan)
    with pytest.raises(ProductionLinePopulationApplyError, match=error):
        _validate_plan(plan)


def test_planner_preserves_prelinked_canonical_owners_without_reassignment():
    state, _ = _state()
    candidate_site7 = SITE_7
    state["existing_production_lines"] = [
        {"id": "line-existing-A", "site_id": candidate_site7, "code": "A"},
        {"id": "line-unrelated", "site_id": candidate_site7, "code": "OTHER"},
    ]
    state["cases"][0]["production_line_id"] = "line-existing-A"
    state["certificates"][0]["production_line_id"] = "line-unrelated"
    state["source_state_fingerprint"] = sha256(canonical_json_bytes({
        key: value for key, value in state.items() if key != "source_state_fingerprint"
    })).hexdigest()
    digest = sha256(canonical_json_bytes(state)).hexdigest()
    plan, _ = _bound_plan(_snapshot(), state, digest)
    existing_case = next(item for item in plan["case_links"] if item["legacy_id"] == 10)
    conflicting_certificate = next(item for item in plan["certificate_links"] if item["legacy_id"] == 20)
    assert existing_case["classification"] == "NOT_APPLICABLE"
    assert existing_case["block_reason"] == "ALREADY_LINKED_TO_PLANNED_LINE"
    assert conflicting_certificate["classification"] == "BLOCKED_EXISTING_LINK"
    assert conflicting_certificate["block_reason"] == "CANONICAL_LINK_CONFLICT"
    assert not any(item["legacy_id"] in (10, 20) and item["classification"].startswith("LINK_")
                   for group in (plan["case_links"], plan["certificate_links"]) for item in group)
    _validate_plan(plan)


def test_dated_source_without_eligible_canonical_owner_is_blocked_and_rostered():
    snapshot = _snapshot()
    state, _ = _state()
    # The Site 8 / A Case is present in the source but absent canonically.
    # The Site 7 certificate linked to its source ID cannot substitute.
    state["cases"] = [x for x in state["cases"] if x["legacy_inspection_id"] != 11]
    state["source_state_fingerprint"] = sha256(canonical_json_bytes({
        key: value for key, value in state.items() if key != "source_state_fingerprint"
    })).hexdigest()
    digest = sha256(canonical_json_bytes(state)).hexdigest()
    plan, roster = _bound_plan(snapshot, state, digest)
    orphan = next(c for c in plan["candidates"] if c["legacy_site_id"] == 8)
    assert orphan["effective_from"] == "2026-07-20"
    assert orphan["classification"] == "BLOCKED_NO_ELIGIBLE_LINK_TARGET"
    assert orphan["block_reason"] == "NO_CANONICAL_OWNER_ELIGIBLE_FOR_LINK"
    assert orphan["proposed_production_line_id"] is None
    assert any(item["candidate_key"] == orphan["candidate_key"] for item in roster["items"])
    assert not any(r["classification"] == "LINK_TO_NEW_LINE" and r["candidate_key"] == orphan["candidate_key"]
                   for r in (*plan["case_links"], *plan["certificate_links"]))
    _validate_plan(plan)


def test_writer_rejects_resealed_orphan_creation_even_with_valid_plan_sha():
    state, digest = _state()
    plan, _ = _bound_plan(_snapshot(), state, digest)
    candidate = next(c for c in plan["candidates"] if c["legacy_site_id"] == 8)
    for record in (*plan["case_links"], *plan["certificate_links"]):
        if record["candidate_key"] == candidate["candidate_key"] and record["classification"] == "LINK_TO_NEW_LINE":
            record["classification"] = "BLOCKED_STALE_STATE"
            record["block_reason"] = "SYNTHETIC_REVIEW_ONLY"
    # Keep the plan's summary honest to isolate the orphan-create fence.
    for label, records in (("cases", plan["case_links"]), ("certificates", plan["certificate_links"])):
        plan["summary_counts"][label] = {
            key: sum(record["classification"] == key for record in records)
            for key in sorted({record["classification"] for record in records})
        }
    plan["plan_sha256"] = plan_digest(plan)
    with pytest.raises(ProductionLinePopulationApplyError, match="creation without an eligible canonical link"):
        _validate_plan(plan)


def test_writer_rejects_resealed_action_to_reassign_existing_canonical_fk():
    state, digest = _state()
    plan, _ = _bound_plan(_snapshot(), state, digest)
    record = next(item for item in plan["case_links"] if item["classification"] == "LINK_TO_NEW_LINE")
    record["expected_production_line_id"] = "00000000-0000-0000-0000-0000000000ff"
    plan["plan_sha256"] = plan_digest(plan)
    with pytest.raises(ProductionLinePopulationApplyError, match="refuses to replace an existing canonical"):
        _validate_plan(plan)


@pytest.mark.parametrize("field", ("case_links", "certificate_links"))
def test_writer_refuses_resealed_duplicate_legacy_action_even_if_identical(field):
    state, digest = _state()
    plan, _ = _bound_plan(_snapshot(), state, digest)
    action = next(item for item in plan[field] if item["classification"] == "LINK_TO_NEW_LINE")
    plan[field].append(dict(action))
    plan["plan_sha256"] = plan_digest(plan)
    with pytest.raises(ProductionLinePopulationApplyError, match="repeats or lacks a legacy source identity"):
        _validate_plan(plan)


def test_writer_refuses_resealed_two_legacy_sources_for_one_canonical_owner():
    state, digest = _state()
    plan, _ = _bound_plan(_snapshot(), state, digest)
    links = [item for item in plan["case_links"] if item["classification"] == "LINK_TO_NEW_LINE"]
    assert len(links) >= 2
    links[1]["canonical_record_id"] = links[0]["canonical_record_id"]
    plan["plan_sha256"] = plan_digest(plan)
    with pytest.raises(ProductionLinePopulationApplyError, match="repeats a canonical owner"):
        _validate_plan(plan)


@pytest.mark.parametrize("field", ("case_links", "certificate_links"))
def test_writer_rejects_omission_of_candidate_source_even_if_plan_resealed(field):
    state, digest = _state()
    plan, _ = _bound_plan(_snapshot(), state, digest)
    victim = next(r for r in plan[field] if r["candidate_key"] is not None)
    plan[field].remove(victim)
    plan["plan_sha256"] = plan_digest(plan)
    with pytest.raises(ProductionLinePopulationApplyError, match="omits candidate source actions"):
        _validate_plan(plan)


def test_ineligible_case_sharing_valid_site_code_has_no_candidate_membership():
    state, _ = _state()
    snapshot = _snapshot()
    snapshot["sheets"][0]["raw_rows"].append(
        _row(8, {1: 99, 2: None, 3: 7, 4: "A", 5: "21/07/2026"})
    )
    state["cases"].append({
        "id": "case-99", "legacy_inspection_id": 99, "site_id": SITE_7,
        "production_line_id": None, "row_version": 1,
    })
    state["source_state_fingerprint"] = sha256(canonical_json_bytes({
        key: value for key, value in state.items() if key != "source_state_fingerprint"
    })).hexdigest()
    digest = sha256(canonical_json_bytes(state)).hexdigest()
    plan, _ = _bound_plan(snapshot, state, digest)
    excluded = next(record for record in plan["case_links"] if record["legacy_id"] == 99)
    assert excluded["classification"] == "NOT_APPLICABLE"
    assert excluded["block_reason"] == "CASE_SOURCE_NOT_ELIGIBLE"
    assert excluded["candidate_key"] is None
    _validate_plan(plan)


def test_writer_rejects_blocked_source_reassigned_to_other_candidate():
    state, digest = _state()
    plan, _ = _bound_plan(_snapshot(), state, digest)
    victim = next(r for r in plan["certificate_links"]
                  if r["classification"].startswith("BLOCKED_") and r["candidate_key"] is not None)
    victim["candidate_key"] = next(c["candidate_key"] for c in plan["candidates"]
                                    if c["candidate_key"] != victim["candidate_key"])
    plan["plan_sha256"] = plan_digest(plan)
    with pytest.raises(ProductionLinePopulationApplyError, match="candidate membership differs"):
        _validate_plan(plan)


def test_writer_rejects_falsified_action_summary_even_if_resealed():
    state, digest = _state()
    plan, _ = _bound_plan(_snapshot(), state, digest)
    plan["summary_counts"]["cases"] = {"LINK_TO_NEW_LINE": 999}
    plan["plan_sha256"] = plan_digest(plan)
    with pytest.raises(ProductionLinePopulationApplyError, match="summary counts disagree"):
        _validate_plan(plan)


def test_apply_cli_refuses_missing_or_mismatched_independent_digests(tmp_path, capsys):
    state, digest = _state()
    plan, _ = _bound_plan(_snapshot(), state, digest)
    path = tmp_path / "sealed.json"
    path.write_bytes(canonical_artifact_bytes(plan))
    args = ["--database-url", "postgresql+psycopg://invalid@invalid/no_db",
            "--expected-database-name", "gxp_b6j_test_no_db", "--plan", str(path)]
    bad_cases = (
        ([], "independently recorded"),
        (["--expected-plan-sha256", plan["plan_sha256"],
          "--expected-plan-file-sha256", "0" * 64], "does not match exact plan bytes"),
        (["--expected-plan-sha256", "0" * 64,
          "--expected-plan-file-sha256", sha256(path.read_bytes()).hexdigest()], "does not match sealed plan"),
    )
    for options, error in bad_cases:
        with pytest.raises(SystemExit) as exc:
            writer_cli_main(args + options)
        assert exc.value.code == 2
        assert error in capsys.readouterr().err


def test_b6j_writer_rejects_resealed_duplicate_candidate_key():
    state, digest = _state()
    plan, _ = _bound_plan(_snapshot(), state, digest)
    plan["candidates"][1]["candidate_key"] = plan["candidates"][0]["candidate_key"]
    plan["plan_sha256"] = plan_digest(plan)
    with pytest.raises(ProductionLinePopulationApplyError, match="duplicate or missing"):
        _validate_plan(plan)


def test_b6j_writer_accepts_existing_line_mapping_consistency():
    state, digest = _state()
    state["existing_production_lines"] = [{"id": "line-7-a", "site_id": SITE_7, "code": "A"}]
    state["source_state_fingerprint"] = sha256(canonical_json_bytes({key: value for key, value in state.items() if key != "source_state_fingerprint"})).hexdigest()
    digest = sha256(canonical_json_bytes(state)).hexdigest()
    plan, _ = _bound_plan(_snapshot(), state, digest)
    assert any(record["classification"] == "LINK_TO_EXISTING_LINE" for record in plan["case_links"])
    _validate_plan(plan)


def test_generic_roster_cardinality_is_relative_to_sealed_plan():
    state, digest = _state()
    plan, _ = _bound_plan(_snapshot(), state, digest)
    _validate_plan(plan)
    plan["candidate_set_roster_item_count"] = 2
    plan["plan_sha256"] = plan_digest(plan)
    with pytest.raises(ProductionLinePopulationApplyError, match="roster cardinality"):
        _validate_plan(plan)
    plan["candidate_set_roster_item_count"] = 0
    plan["plan_sha256"] = plan_digest(plan)
    with pytest.raises(ProductionLinePopulationApplyError, match="roster cardinality"):
        _validate_plan(plan)


@pytest.mark.parametrize("count,allowed", ((385, False), (386, True), (387, False)))
def test_authoritative_rehearsal_cardinality_is_exactly_386(count: int, allowed: bool):
    plan = {"candidate_set_roster_item_count": count, "candidates": [{} for _ in range(count)], "source_database_identity": {"database_name": "gxp_legacy_rehearsal", "dialect": "postgresql"}, "source_alembic_revision": "20260929_0017"}
    if allowed:
        _validate_authoritative_rehearsal_plan(plan)
    else:
        with pytest.raises(ProductionLinePopulationApplyError, match="exactly 386"):
            _validate_authoritative_rehearsal_plan(plan)


@pytest.mark.parametrize("revision", ("20260929_0017", "20261008_0022"))
def test_b6j_supported_revision_is_bound_to_export_plan_and_candidate_uuid(revision):
    state, _ = _state()
    state["source_alembic_revision"] = revision
    state["source_state_fingerprint"] = sha256(canonical_json_bytes({key: value for key, value in state.items() if key != "source_state_fingerprint"})).hexdigest()
    digest = sha256(canonical_json_bytes(state)).hexdigest()
    plan, _ = _bound_plan(_snapshot(), state, digest)
    assert plan["source_alembic_revision"] == revision
    _validate_plan(plan)


def test_b6j_rejects_0022_plan_for_protected_rehearsal():
    plan = {"candidate_set_roster_item_count": 386, "candidates": [{} for _ in range(386)],
            "source_database_identity": {"database_name": "gxp_legacy_rehearsal", "dialect": "postgresql"},
            "source_alembic_revision": "20261008_0022"}
    with pytest.raises(ProductionLinePopulationApplyError, match="protected rehearsal remains pinned"):
        _validate_authoritative_rehearsal_plan(plan)


def test_writer_rejects_wrong_alembic_revision_before_target_access():
    state, digest = _state()
    plan, _ = _bound_plan(_snapshot(), state, digest)
    plan["source_alembic_revision"] = "wrong"
    plan["plan_sha256"] = plan_digest(plan)
    with pytest.raises(ProductionLinePopulationApplyError, match="unsupported Alembic revision"):
        _validate_plan(plan)


def test_planner_cli_requires_exact_raw_roster_sha256(tmp_path, capsys):
    state, digest = _state()
    snapshot = _snapshot()
    snapshot_path, state_path, roster_path, output_path = (tmp_path / name for name in ("snapshot.json", "state.json", "roster.json", "plan.json"))
    snapshot_bytes = canonical_artifact_bytes(snapshot)
    state_bytes = canonical_artifact_bytes(state)
    snapshot_path.write_bytes(snapshot_bytes)
    state_path.write_bytes(state_bytes)
    preliminary = build_population_plan(snapshot, snapshot_sha256=sha256(snapshot_bytes).hexdigest(), canonical_state=state, canonical_state_sha256=digest, candidate_set_sha256="b" * 64)
    roster = _roster_for_candidates(preliminary["candidates"], snapshot_sha256=sha256(snapshot_bytes).hexdigest(), canonical_state_sha256=digest)
    roster_bytes = canonical_artifact_bytes(roster)
    roster_path.write_bytes(roster_bytes)
    args = ["--snapshot", str(snapshot_path), "--canonical-state", str(state_path), "--candidate-set-sha256", roster["candidate_set_sha256"], "--candidate-set-roster", str(roster_path), "--candidate-set-roster-sha256"]
    with pytest.raises(SystemExit):
        planner_main([*args, "not-a-sha", "--output", str(output_path)])
    assert planner_main([*args, sha256(roster_bytes).hexdigest(), "--output", str(output_path)]) == 0
    assert f"PRODUCTION_LINE_POPULATION_PLAN_FILE_SHA256={sha256(output_path.read_bytes()).hexdigest()}" in capsys.readouterr().out
    assert json.loads(output_path.read_bytes())["candidate_set_roster_sha256"] == sha256(roster_bytes).hexdigest()


@pytest.mark.parametrize(
    "mutate",
    (
        lambda roster: roster.__setitem__("artifact_kind", "wrong"),
        lambda roster: roster.__setitem__("schema_version", "wrong"),
        lambda roster: roster.__setitem__("candidate_set_sha256", "c" * 64),
        lambda roster: roster.__setitem__("legacy_snapshot_sha256", "c" * 64),
        lambda roster: roster.__setitem__("canonical_state_sha256", "c" * 64),
        lambda roster: roster["items"].append(dict(roster["items"][0])),
        lambda roster: roster["items"].pop(),
        lambda roster: roster["items"].append({"candidate_key": "extra"}),
        lambda roster: roster["items"][0].__setitem__("canonical_site_id", "wrong"),
        lambda roster: roster["items"][0].__setitem__("source_site_legacy_id", 999),
        lambda roster: roster["items"][0].__setitem__("canonical_line_text", "wrong"),
        lambda roster: roster["items"][0].__setitem__("source_case_ids", [999]),
        lambda roster: roster["items"][0].__setitem__("source_certificate_ids", [999]),
        lambda roster: roster["items"][0].__setitem__("existing_production_line_id", "wrong"),
        lambda roster: roster["items"][0].__setitem__("case_count", 999),
        lambda roster: roster["items"][0].__setitem__("certificate_count", 999),
    ),
)
def test_b6i_roster_identity_drift_fails_closed(mutate):
    state, digest = _state()
    preliminary = build_population_plan(_snapshot(), snapshot_sha256="a" * 64, canonical_state=state, canonical_state_sha256=digest, candidate_set_sha256="b" * 64)
    roster = _roster_for_candidates(preliminary["candidates"], snapshot_sha256="a" * 64, canonical_state_sha256=digest)
    candidate_set_sha256 = roster["candidate_set_sha256"]
    mutate(roster)
    _seal_roster(roster)
    with pytest.raises(ProductionLinePopulationPlanError):
        bind_candidate_roster(roster, roster_raw_sha256=sha256(canonical_artifact_bytes(roster)).hexdigest(), candidate_set_sha256=candidate_set_sha256, snapshot_sha256="a" * 64, canonical_state_sha256=digest, candidates=preliminary["candidates"])


@pytest.mark.parametrize(
    ("expected_database_name", "apply", "allow", "identity", "allowed"),
    (
        ("gxp_legacy_rehearsal", False, True, {"database_name": "gxp_legacy_rehearsal", "dialect": "postgresql"}, True),
        ("gxp_legacy_rehearsal", False, False, {"database_name": "gxp_legacy_rehearsal", "dialect": "postgresql"}, False),
        ("gxp_legacy_rehearsal", True, True, {"database_name": "gxp_legacy_rehearsal", "dialect": "postgresql"}, False),
        ("gxp_qlcl", False, True, {"database_name": "gxp_qlcl", "dialect": "postgresql"}, False),
        ("unexpected", False, True, {"database_name": "unexpected", "dialect": "postgresql"}, False),
        ("gxp_legacy_rehearsal", False, True, {"database_name": "wrong", "dialect": "postgresql"}, False),
    ),
)
def test_rehearsal_dry_run_override_is_exact_and_never_grants_apply(expected_database_name, apply, allow, identity, allowed):
    plan = {"source_database_identity": identity}
    if allowed:
        _validate_target_mode(plan, expected_database_name=expected_database_name, apply=apply, allow_rehearsal_dry_run=allow)
    else:
        with pytest.raises(ProductionLinePopulationApplyError):
            _validate_target_mode(plan, expected_database_name=expected_database_name, apply=apply, allow_rehearsal_dry_run=allow)


@pytest.mark.parametrize("apply", (False, True))
@pytest.mark.parametrize(
    "database_name",
    ("gxp_qlcl_prod", "gxp_qlcl_test", "gxp_b6h_test_staging", "gxp_legacy_rehearsal_copy"),
)
def test_non_rehearsal_writer_rejects_non_disposable_database_for_dry_run_and_apply(database_name, apply):
    plan = {"source_database_identity": {"database_name": database_name, "dialect": "postgresql"}}
    with pytest.raises(ProductionLinePopulationApplyError, match="disposable gxp_b6j_test_"):
        _validate_target_mode(
            plan, expected_database_name=database_name, apply=apply, allow_rehearsal_dry_run=False,
        )


@pytest.mark.parametrize("apply", (False, True))
@pytest.mark.parametrize("dialect", (None, "sqlite", "postgresql+psycopg"))
def test_non_rehearsal_requires_exact_postgresql_source_dialect(apply, dialect):
    database_name = "gxp_b6j_test_contract"
    plan = {"source_database_identity": {"database_name": database_name, "dialect": dialect}}
    with pytest.raises(ProductionLinePopulationApplyError, match="identity differs from PostgreSQL target"):
        _validate_target_mode(
            plan, expected_database_name=database_name,
            apply=apply, allow_rehearsal_dry_run=False,
        )


@pytest.mark.parametrize("apply", (False, True))
def test_non_rehearsal_apply_accepts_0022_compatibility_disposable_database(apply):
    name = "gxp_b6c_test_contract"
    plan = {"source_database_identity": {"database_name": name, "dialect": "postgresql"}}
    _validate_target_mode(plan, expected_database_name=name, apply=apply, allow_rehearsal_dry_run=False)


@pytest.mark.parametrize("apply", (False, True))
def test_non_rehearsal_apply_accepts_explicit_b6j_disposable_database(apply):
    database_name = "gxp_b6j_test_contract"
    plan = {"source_database_identity": {"database_name": database_name, "dialect": "postgresql"}}
    _validate_target_mode(
        plan, expected_database_name=database_name, apply=apply, allow_rehearsal_dry_run=False,
    )


def test_existing_line_maps_and_links_without_new_uuid():
    state, digest = _state()
    state["existing_production_lines"] = [{"id": "line-7-a", "site_id": SITE_7, "code": "A"}]
    state["source_state_fingerprint"] = sha256(canonical_json_bytes({key: value for key, value in state.items() if key != "source_state_fingerprint"})).hexdigest()
    digest = sha256(canonical_json_bytes(state)).hexdigest()
    plan = build_population_plan(_snapshot(), snapshot_sha256="a" * 64, canonical_state=state, canonical_state_sha256=digest, candidate_set_sha256="b" * 64)
    candidate = next(item for item in plan["candidates"] if item["legacy_site_id"] == 7 and item["canonical_line_code"] == "A")
    assert candidate["classification"] == "MAP_TO_EXISTING_PRODUCTION_LINE"
    assert candidate["proposed_production_line_id"] is None
    assert next(item for item in plan["case_links"] if item["legacy_id"] == 10)["classification"] == "LINK_TO_EXISTING_LINE"


def test_invalid_candidate_digest_and_stale_canonical_digest_fail_closed():
    state, digest = _state()
    with pytest.raises(ProductionLinePopulationPlanError, match="candidate set SHA256"):
        build_population_plan(_snapshot(), snapshot_sha256="a" * 64, canonical_state=state, canonical_state_sha256=digest, candidate_set_sha256="not-a-digest")
    with pytest.raises(ProductionLinePopulationPlanError, match="canonical state SHA256"):
        build_population_plan(_snapshot(), snapshot_sha256="a" * 64, canonical_state=state, canonical_state_sha256="c" * 64, candidate_set_sha256="b" * 64)


def test_ineligible_case_source_is_not_applicable_and_cannot_create_candidate():
    state, digest = _state()
    snapshot = _snapshot()
    snapshot["sheets"][0]["raw_rows"].append(_row(8, {1: 99, 2: None, 3: 7, 4: "D", 5: "21/07/2026"}))
    state["cases"].append({"id": "case-99", "legacy_inspection_id": 99, "site_id": SITE_7, "production_line_id": None, "row_version": 1})
    state["source_state_fingerprint"] = sha256(canonical_json_bytes({key: value for key, value in state.items() if key != "source_state_fingerprint"})).hexdigest()
    digest = sha256(canonical_json_bytes(state)).hexdigest()
    plan = build_population_plan(snapshot, snapshot_sha256="a" * 64, canonical_state=state, canonical_state_sha256=digest, candidate_set_sha256="b" * 64)
    assert next(item for item in plan["case_links"] if item["legacy_id"] == 99)["classification"] == "NOT_APPLICABLE"
    assert all(item["canonical_line_code"] != "D" for item in plan["candidates"])


def test_snapshot_v2_accessor_is_exact_case_sensitive_and_preserves_raw_cell_metadata():
    snapshot = _snapshot()
    snapshot["sheets"].append({"sheet_name": "db.CC", "raw_rows": [_row(4, {1: "ID"})]})
    rows, headers = snapshot_header_map(snapshot, "db.cc", required_headers=("ID", "Ngày cấp CC"))
    assert snapshot_sheet(snapshot, "db.cc")["sheet_name"] == "db.cc"
    assert snapshot_sheet(snapshot, "db.CC")["sheet_name"] == "db.CC"
    value = snapshot_cell(rows[1], sheet_name="db.cc", header="Ngày cấp CC", column_ordinal=headers["Ngày cấp CC"])
    assert value["raw_value"] == "2026-08-21"
    assert value["sheet_name"] == "db.cc"
    assert value["source_row_number"] == 5
    with pytest.raises(ValueError, match="exact sheet"):
        snapshot_sheet(snapshot, "DB.CC")


def test_only_lowercase_db_cc_can_supply_certificate_effective_date():
    state, digest = _state()
    snapshot = _snapshot()
    # Remove the authoritative db.cc B date and add lookalike non-GxP domains.
    for cell in snapshot["sheets"][1]["raw_rows"][3]["cells"]:
        if cell["column_ordinal"] == 10:
            cell["raw_value"] = "-"
    snapshot["sheets"].extend((
        {"sheet_name": "db.dkkd", "raw_rows": [_row(4, {1: "ID", 2: "Ngày cấp CC"}), _row(5, {1: 21, 2: "2010-01-01"})]},
        {"sheet_name": "db.CC", "raw_rows": [_row(4, {1: "ID", 2: "Ngày cấp CC"})]},
    ))
    plan = build_population_plan(snapshot, snapshot_sha256="a" * 64, canonical_state=state, canonical_state_sha256=digest, candidate_set_sha256="b" * 64)
    candidate = next(item for item in plan["candidates"] if item["legacy_site_id"] == 7 and item["canonical_line_code"] == "B")
    assert candidate["classification"] == "BLOCKED_EFFECTIVE_FROM_UNKNOWN"


@pytest.mark.parametrize(("sheet_index", "header"), ((0, "Ngày K.tra"), (1, "Ngày cấp CC")))
def test_missing_authoritative_date_header_fails_closed(sheet_index: int, header: str):
    state, digest = _state()
    snapshot = _snapshot()
    for cell in snapshot["sheets"][sheet_index]["raw_rows"][0]["cells"]:
        if cell["raw_value"] == header:
            cell["raw_value"] = "renamed"
    with pytest.raises(ValueError, match="missing required source headers"):
        build_population_plan(snapshot, snapshot_sha256="a" * 64, canonical_state=state, canonical_state_sha256=digest, candidate_set_sha256="b" * 64)


@pytest.mark.parametrize(("sheet_index", "header"), ((0, "Ngày K.tra"), (1, "Ngày cấp CC")))
def test_duplicate_authoritative_date_header_fails_closed(sheet_index: int, header: str):
    state, digest = _state()
    snapshot = _snapshot()
    snapshot["sheets"][sheet_index]["raw_rows"][0]["cells"].append({"column_ordinal": 99, "raw_value": header})
    with pytest.raises(ValueError, match="duplicate required source headers"):
        build_population_plan(snapshot, snapshot_sha256="a" * 64, canonical_state=state, canonical_state_sha256=digest, candidate_set_sha256="b" * 64)


def test_excel_serial_date_cells_are_used_only_for_authoritative_date_headers():
    state, digest = _state()
    snapshot = _snapshot()
    # 45000 is the shared source-owner's 1900-workbook-system value for 2023-03-15.
    for cell in snapshot["sheets"][0]["raw_rows"][1]["cells"]:
        if cell["column_ordinal"] == 5:
            cell["raw_value"] = 45000
    for cell in snapshot["sheets"][0]["raw_rows"][3]["cells"]:
        if cell["column_ordinal"] == 5:
            cell["raw_value"] = "-"
    for cell in snapshot["sheets"][1]["raw_rows"][3]["cells"]:
        if cell["column_ordinal"] == 10:
            cell["raw_value"] = 45000
    # A numeric value in another source field is not selected as timing.
    snapshot["sheets"][0]["raw_rows"][1]["cells"].append({"column_ordinal": 98, "raw_value": 1})
    plan = build_population_plan(snapshot, snapshot_sha256="a" * 64, canonical_state=state, canonical_state_sha256=digest, candidate_set_sha256="b" * 64)
    candidates = {(item["legacy_site_id"], item["canonical_line_code"]): item for item in plan["candidates"]}
    assert candidates[7, "A"]["effective_from"] == "2023-03-15"
    assert candidates[7, "A"]["effective_from_source_state"] == "EXCEL_SERIAL_DATE"
    assert candidates[7, "B"]["effective_from"] == "2023-03-15"
    assert candidates[7, "B"]["effective_from_source_type"] == "CERTIFICATE"


def test_duplicate_canonical_case_owner_is_rejected_even_when_legacy_targets_converge():
    state, digest = _state()
    snapshot = _snapshot()
    for cell in snapshot["sheets"][0]["raw_rows"][2]["cells"]:
        if cell["column_ordinal"] == 3:
            cell["raw_value"] = 7
    state["cases"][1] = {**state["cases"][1], "id": "case-10", "site_id": SITE_7}
    state["source_state_fingerprint"] = sha256(canonical_json_bytes({key: value for key, value in state.items() if key != "source_state_fingerprint"})).hexdigest()
    digest = sha256(canonical_json_bytes(state)).hexdigest()
    with pytest.raises(ProductionLinePopulationPlanError, match="map multiple legacy IDs to one canonical owner"):
        build_population_plan(snapshot, snapshot_sha256="a" * 64, canonical_state=state, canonical_state_sha256=digest, candidate_set_sha256="b" * 64)


def test_duplicate_canonical_write_targets_with_different_lines_fail_closed():
    state, digest = _state()
    snapshot = _snapshot()
    for cell in snapshot["sheets"][0]["raw_rows"][2]["cells"]:
        if cell["column_ordinal"] == 3:
            cell["raw_value"] = 7
        if cell["column_ordinal"] == 4:
            cell["raw_value"] = "B"
    state["cases"][1] = {**state["cases"][1], "id": "case-10", "site_id": SITE_7}
    state["source_state_fingerprint"] = sha256(canonical_json_bytes({key: value for key, value in state.items() if key != "source_state_fingerprint"})).hexdigest()
    digest = sha256(canonical_json_bytes(state)).hexdigest()
    with pytest.raises(ProductionLinePopulationPlanError, match="map multiple legacy IDs to one canonical owner"):
        build_population_plan(snapshot, snapshot_sha256="a" * 64, canonical_state=state, canonical_state_sha256=digest, candidate_set_sha256="b" * 64)


@pytest.mark.parametrize(("value", "expected"), ((1, 1), (1.0, 1), ("1", 1), ("1.0", 1), (1.5, None), ("1.5", None), (None, None), (True, None), ("", None), ("-", None), ("???", None), (float("nan"), None), (float("inf"), None)))
def test_shared_snapshot_legacy_integer_decoder(value: object, expected: int | None):
    assert snapshot_legacy_int(value) == expected


def test_float_snapshot_ids_populate_authoritative_date_maps_and_case_effective_from():
    state, digest = _state()
    snapshot = _snapshot()
    for sheet in snapshot["sheets"]:
        for row in sheet["raw_rows"][1:]:
            for cell in row["cells"]:
                if cell["column_ordinal"] == 1:
                    cell.update({"raw_value": float(cell["raw_value"]), "observed_type": "float", "raw_state": "NUMBER"})
    case_dates, certificate_dates = _dates(snapshot)
    assert case_dates and certificate_dates
    assert case_dates[10][0].isoformat() == "2026-07-17"
    assert certificate_dates[20][0].isoformat() == "2026-08-21"
    plan = build_population_plan(snapshot, snapshot_sha256="a" * 64, canonical_state=state, canonical_state_sha256=digest, candidate_set_sha256="b" * 64)
    candidate = next(item for item in plan["candidates"] if item["legacy_site_id"] == 7 and item["canonical_line_code"] == "A")
    assert candidate["effective_from"] == "2026-07-17"
    assert candidate["effective_from_source_type"] == "CASE"


def test_float_snapshot_certificate_id_supplies_fallback_when_case_is_not_dated():
    state, digest = _state()
    snapshot = _snapshot()
    for cell in snapshot["sheets"][0]["raw_rows"][3]["cells"]:
        if cell["column_ordinal"] == 5:
            cell["raw_value"] = "-"
    for cell in snapshot["sheets"][1]["raw_rows"][3]["cells"]:
        if cell["column_ordinal"] == 1:
            cell.update({"raw_value": 22.0, "observed_type": "float", "raw_state": "NUMBER"})
    plan = build_population_plan(snapshot, snapshot_sha256="a" * 64, canonical_state=state, canonical_state_sha256=digest, candidate_set_sha256="b" * 64)
    candidate = next(item for item in plan["candidates"] if item["legacy_site_id"] == 7 and item["canonical_line_code"] == "B")
    assert candidate["classification"] == "CREATE_NEW_PRODUCTION_LINE"
    assert candidate["effective_from"] == "2020-01-01"
    assert candidate["effective_from_source_type"] == "CERTIFICATE"
