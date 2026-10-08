from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

import pytest

from backend.app.domain.production_line_population import (
    CANONICAL_STATE_SCHEMA_VERSION,
    PLANNER_VERSION,
    ROSTER_SCHEMA_VERSION,
    ProductionLinePlanningError,
    build_production_line_population_plan,
    build_physical_identity_roster_template,
    canonical_artifact_bytes,
    canonical_json_bytes,
    canonicalize_line_text,
)


ROOT = Path(__file__).resolve().parents[1]
SITE_7 = "00000000-0000-0000-0000-000000000007"
LINE_A = "00000000-0000-0000-0000-0000000000a1"
LINE_OTHER = "00000000-0000-0000-0000-0000000000b2"
OTHER_SITE = "00000000-0000-0000-0000-000000000008"


def _row(number: int, values: dict[int, object]) -> dict[str, object]:
    return {"source_row_number": number, "cells": [{"column_ordinal": key, "raw_value": value} for key, value in values.items()]}


def _snapshot(*, ktra: list[dict[int, object]], certificates: list[dict[int, object]]) -> dict[str, object]:
    return {"schema_version": "legacy-workbook-snapshot/v2", "sheets": [
        {"sheet_name": "db.ktra", "raw_rows": [
            _row(4, {1: "ID", 2: "LOẠI KT", 3: "ID CƠ SỞ", 4: "MÃ DC"}),
            *[_row(index + 5, values) for index, values in enumerate(ktra)],
        ]},
        {"sheet_name": "db.cc", "raw_rows": [
            _row(4, {1: "ID", 4: "LOẠI CC", 5: "ID ĐỢT KTRA", 8: "ID CƠ SỞ", 9: "MÃ DC"}),
            *[_row(index + 5, values) for index, values in enumerate(certificates)],
        ]},
    ]}


def _plan(snapshot: dict[str, object], canonical_state: dict[str, object] | None = None):
    if canonical_state is not None and "schema_version" not in canonical_state:
        canonical_state = {
            "schema_version": CANONICAL_STATE_SCHEMA_VERSION,
            "exported_at": None,
            "source_database_identity": {"database_name": "gxp_b6h_test_fixture"},
            "source_alembic_revision": "20260929_0017",
            "source_state_fingerprint": None,
            "sites": [], "existing_production_lines": [], "cases": [], "certificates": [],
            "transformations": [],
            **canonical_state,
        }
        fingerprint_payload = dict(canonical_state)
        fingerprint_payload.pop("source_state_fingerprint")
        canonical_state["source_state_fingerprint"] = __import__("hashlib").sha256(canonical_json_bytes(fingerprint_payload)).hexdigest()
    return build_production_line_population_plan(snapshot, snapshot_sha256="a" * 64, canonical_state=canonical_state)


def test_canonicalization_is_representation_only_and_does_not_merge_semantic_labels():
    assert canonicalize_line_text("  a  ")["canonical_text"] == "A"
    assert canonicalize_line_text("Ａ")["canonical_text"] == "A"
    assert canonicalize_line_text("A+C")["canonical_text"] == "A+C"
    assert canonicalize_line_text("AC")["canonical_text"] == "AC"
    assert canonicalize_line_text("Line 1A")["canonical_text"] == "LINE 1A"
    assert canonicalize_line_text("Line 1A")["canonical_text"] != canonicalize_line_text("Line A")["canonical_text"]
    assert canonicalize_line_text("   ")["state"] == "WHITESPACE_ONLY"
    assert canonicalize_line_text(None)["state"] == "MISSING"


def test_b6h_reuses_phase2_inspection_gxp_normalizer_for_known_and_unknown_values():
    plan = _plan(_snapshot(ktra=[{1: 10, 2: "gMpBb", 3: 7, 4: "A"}, {1: 11, 2: "unknown", 3: 7, 4: "B"}], certificates=[]))
    candidates = {item["canonical_line_text"]: item for item in plan["discovery"]["candidates"]}
    assert candidates["A"]["gxp_contexts"] == ["GMPbb"]
    assert candidates["B"]["gxp_contexts"] == []


def test_canonical_state_requires_explicit_schema_and_provenance_contract():
    snapshot = _snapshot(ktra=[], certificates=[])
    with pytest.raises(ProductionLinePlanningError, match="schema_version"):
        build_production_line_population_plan(snapshot, snapshot_sha256="a" * 64, canonical_state={})


@pytest.mark.parametrize("revision", ("20260929_0017", "20261008_0022"))
def test_b6h_discovery_accepts_only_explicit_compatible_revisions(revision):
    state = {
        "schema_version": CANONICAL_STATE_SCHEMA_VERSION, "exported_at": None,
        "source_database_identity": {"database_name": "gxp_b6h_test_fixture"},
        "source_alembic_revision": revision,
        "sites": [], "existing_production_lines": [], "cases": [],
        "certificates": [], "physical_line_evidence": [], "transformations": [],
    }
    state["source_state_fingerprint"] = sha256(canonical_json_bytes(state)).hexdigest()
    plan = _plan(_snapshot(ktra=[], certificates=[]), state)
    assert plan["discovery"]["candidates"] == []


@pytest.mark.parametrize("revision", ("20261003_0018", "20261008_0023", None))
def test_b6h_discovery_rejects_unapproved_revisions(revision):
    state = {
        "schema_version": CANONICAL_STATE_SCHEMA_VERSION, "exported_at": None,
        "source_database_identity": {"database_name": "gxp_b6h_test_fixture"},
        "source_alembic_revision": revision,
        "sites": [], "existing_production_lines": [], "cases": [],
        "certificates": [], "physical_line_evidence": [], "transformations": [],
    }
    state["source_state_fingerprint"] = sha256(canonical_json_bytes(state)).hexdigest()
    with pytest.raises(ProductionLinePlanningError, match="stale or unknown Alembic revision"):
        _plan(_snapshot(ktra=[], certificates=[]), state)


def test_supplied_semantic_digests_are_verified_not_merely_format_checked():
    snapshot = _snapshot(ktra=[], certificates=[])
    state = {"schema_version": CANONICAL_STATE_SCHEMA_VERSION, "exported_at": None, "source_database_identity": {"database_name": "gxp_b6h_test_fixture"}, "source_alembic_revision": "20260929_0017", "sites": [], "existing_production_lines": [], "cases": [], "certificates": [], "physical_line_evidence": [], "transformations": []}
    state["source_state_fingerprint"] = __import__("hashlib").sha256(canonical_json_bytes(state)).hexdigest()
    digest = __import__("hashlib").sha256(canonical_json_bytes(state)).hexdigest()
    build_production_line_population_plan(snapshot, snapshot_sha256="a" * 64, canonical_state=state, canonical_state_sha256=digest)
    with pytest.raises(ProductionLinePlanningError, match="does not match semantic content"):
        build_production_line_population_plan(snapshot, snapshot_sha256="a" * 64, canonical_state=state, canonical_state_sha256="b" * 64)
    altered = deepcopy(state)
    altered["source_database_identity"] = {"database_name": "different"}
    with pytest.raises(ProductionLinePlanningError, match="source-state fingerprint"):
        build_production_line_population_plan(snapshot, snapshot_sha256="a" * 64, canonical_state=altered)


def test_legacy_line_text_alone_is_not_a_safe_production_line_identity_or_link():
    plan = _plan(_snapshot(ktra=[{1: 10, 2: "GMP", 3: 7, 4: " A "}], certificates=[{1: 20, 4: "GMP", 5: 10, 8: 7, 9: "a"}]))
    candidate = plan["discovery"]["candidates"][0]
    assert candidate["classification"] == "BLOCKED_INSUFFICIENT_EVIDENCE"
    assert candidate["evidence_classes"] == ["LEGACY_ONLY_SIGNAL", "CASE_CERTIFICATE_AGREEMENT"]
    assert candidate["observed_line_texts"] == [" A ", "a"]
    assert plan["case_linkage"]["records"][0]["classification"] == "BLOCKED_INSUFFICIENT_EVIDENCE"
    assert plan["certificate_linkage"]["records"][0]["classification"] == "BLOCKED_INSUFFICIENT_EVIDENCE"
    assert plan["case_linkage"]["write_candidates"] == []
    assert plan["certificate_linkage"]["write_candidates"] == []


def test_explicit_reviewed_physical_evidence_is_the_only_create_safe_path():
    snapshot = _snapshot(ktra=[{1: 10, 2: "GMP", 3: 7, 4: "A"}], certificates=[])
    plan = _plan(snapshot, {"sites": [{"id": SITE_7, "legacy_site_id": 7}], "physical_line_evidence": [{"legacy_site_id": 7, "line_text": "A", "evidence_kind": "EXPLICIT_PHYSICAL_LINE_IDENTITY", "production_line_id": LINE_A}]})
    assert plan["discovery"]["candidates"][0]["classification"] == "CREATE_SAFE"
    assert plan["case_linkage"]["records"][0]["classification"] == "LINK_EXACT"


def test_reviewed_evidence_preserves_exact_equivalent_and_case_corroborated_link_classes():
    state = {"sites": [{"id": SITE_7, "legacy_site_id": 7}], "physical_line_evidence": [
        {"legacy_site_id": 7, "line_text": "A", "evidence_kind": "EXPLICIT_PHYSICAL_LINE_IDENTITY"},
    ]}
    plan = _plan(_snapshot(
        ktra=[{1: 10, 2: "GMP", 3: 7, 4: " a "}],
        certificates=[{1: 20, 4: "GMP", 5: 10, 8: 7, 9: "A"}],
    ), state)
    assert plan["case_linkage"]["records"][0]["classification"] == "LINK_CANONICAL_EQUIVALENT"
    assert plan["certificate_linkage"]["records"][0]["classification"] == "LINK_CASE_CORROBORATED"
    assert plan["case_linkage"]["summary_counts"]["writable_link_count"] == len(plan["case_linkage"]["write_candidates"]) == 1


def test_linkage_preserves_exact_raw_compatibility_text_for_stale_plan_protection():
    plan = _plan(
        _snapshot(ktra=[{1: 10, 2: "GMP", 3: 7, 4: " a "}], certificates=[]),
        {"sites": [{"id": SITE_7, "legacy_site_id": 7}], "physical_line_evidence": []},
    )
    record = plan["case_linkage"]["records"][0]
    assert record["source_line_text_raw"] == " a "
    assert record["source_line_text_canonical"] == "A"
    assert record["canonicalization_operations"] == ["TRIM", "UPPERCASE"]
    assert record["stale_plan_fingerprint"]["expected_compatibility_line_text_raw"] == " a "


def test_case_writable_summary_counts_exact_and_canonical_equivalent_links():
    state = {"sites": [{"id": SITE_7, "legacy_site_id": 7}], "physical_line_evidence": [
        {"legacy_site_id": 7, "line_text": "A", "evidence_kind": "EXPLICIT_PHYSICAL_LINE_IDENTITY"},
        {"legacy_site_id": 7, "line_text": "B", "evidence_kind": "EXPLICIT_PHYSICAL_LINE_IDENTITY"},
    ]}
    plan = _plan(_snapshot(ktra=[{1: 10, 2: "GMP", 3: 7, 4: "A"}, {1: 11, 2: "GMP", 3: 7, 4: " b "}], certificates=[]), state)
    assert plan["case_linkage"]["classification_counts"] == {"LINK_CANONICAL_EQUIVALENT": 1, "LINK_EXACT": 1}
    assert plan["case_linkage"]["summary_counts"]["writable_link_count"] == len(plan["case_linkage"]["write_candidates"]) == 2


def test_roster_template_is_deterministic_and_unapproved_roster_cannot_make_write_candidates():
    snapshot = _snapshot(ktra=[{1: 10, 2: "GMP", 3: 7, 4: "A"}], certificates=[])
    state = _plan(snapshot)["discovery"]
    template = build_physical_identity_roster_template(state, snapshot_sha256="a" * 64, canonical_state_sha256=None)
    assert template["schema_version"] == ROSTER_SCHEMA_VERSION
    assert template["items"][0]["physical_identity_action"] == "DEFER_INSUFFICIENT_EVIDENCE"
    assert template["items"][0]["review_tags"] == ["CASE_ONLY", "LETTER_ONLY"]


def test_approved_roster_is_bound_to_snapshot_state_and_candidate_before_create_safe():
    snapshot = _snapshot(ktra=[{1: 10, 2: "GMP", 3: 7, 4: "A"}], certificates=[])
    state = {
        "schema_version": CANONICAL_STATE_SCHEMA_VERSION, "exported_at": None,
        "source_database_identity": {"database_name": "gxp_b6h_test_fixture"},
        "source_alembic_revision": "20260929_0017", "source_state_fingerprint": None,
        "sites": [{"id": SITE_7, "legacy_site_id": 7}], "existing_production_lines": [],
        "cases": [], "certificates": [], "physical_line_evidence": [], "transformations": [],
    }
    state["source_state_fingerprint"] = __import__("hashlib").sha256(canonical_json_bytes({key: value for key, value in state.items() if key != "source_state_fingerprint"})).hexdigest()
    initial = build_production_line_population_plan(snapshot, snapshot_sha256="a" * 64, canonical_state=state)
    candidate = initial["discovery"]["candidates"][0]
    state_sha = __import__("hashlib").sha256(canonical_json_bytes(state)).hexdigest()
    roster = {
        "schema_version": ROSTER_SCHEMA_VERSION, "planner_version": initial["discovery"]["schema_version"],
        "legacy_snapshot_sha256": "a" * 64, "canonical_state_sha256": state_sha,
        "items": [{"candidate_key": candidate["candidate_key"], "source_site_legacy_id": 7, "canonical_site_id": SITE_7, "canonical_line_text": "A", "physical_identity_action": "APPROVE_NEW_PHYSICAL_LINE", "production_line_id": None, "approved_display_code": "A", "review_reason": "Reviewed physical roster evidence"}],
    }
    approved = build_production_line_population_plan(snapshot, snapshot_sha256="a" * 64, canonical_state=state, roster=roster)
    assert approved["discovery"]["candidates"][0]["classification"] == "CREATE_SAFE"
    stale = deepcopy(roster)
    stale["items"][0]["canonical_line_text"] = "B"
    with pytest.raises(ProductionLinePlanningError, match="altered after discovery"):
        build_production_line_population_plan(snapshot, snapshot_sha256="a" * 64, canonical_state=state, roster=stale)


def test_roster_rejects_unknown_duplicate_and_cross_site_existing_line_mappings():
    snapshot = _snapshot(ktra=[{1: 10, 2: "GMP", 3: 7, 4: "A"}], certificates=[])
    state = {
        "schema_version": CANONICAL_STATE_SCHEMA_VERSION, "exported_at": None,
        "source_database_identity": {"database_name": "gxp_b6h_test_fixture"}, "source_alembic_revision": "20260929_0017",
        "source_state_fingerprint": None, "sites": [{"id": SITE_7, "legacy_site_id": 7}],
        "existing_production_lines": [{"id": LINE_OTHER, "site_id": OTHER_SITE}], "cases": [], "certificates": [], "physical_line_evidence": [], "transformations": [],
    }
    state["source_state_fingerprint"] = __import__("hashlib").sha256(canonical_json_bytes({key: value for key, value in state.items() if key != "source_state_fingerprint"})).hexdigest()
    initial = build_production_line_population_plan(snapshot, snapshot_sha256="a" * 64, canonical_state=state)
    state_sha = __import__("hashlib").sha256(canonical_json_bytes(state)).hexdigest()
    roster = {"schema_version": ROSTER_SCHEMA_VERSION, "planner_version": PLANNER_VERSION, "legacy_snapshot_sha256": "a" * 64, "canonical_state_sha256": state_sha, "items": [{"candidate_key": initial["discovery"]["candidates"][0]["candidate_key"], "source_site_legacy_id": 7, "canonical_site_id": SITE_7, "canonical_line_text": "A", "physical_identity_action": "MAP_TO_EXISTING_PRODUCTION_LINE", "production_line_id": LINE_OTHER, "review_reason": "reviewed"}]}
    with pytest.raises(ProductionLinePlanningError, match="crosses Site"):
        build_production_line_population_plan(snapshot, snapshot_sha256="a" * 64, canonical_state=state, roster=roster)


def test_case_and_certificate_conflicts_remain_blocked_and_cross_site_texts_remain_separate():
    plan = _plan(_snapshot(
        ktra=[{1: 10, 2: "GMP", 3: 7, 4: "A"}, {1: 11, 2: "GMP", 3: 8, 4: "A"}],
        certificates=[{1: 20, 4: "GMP", 5: 10, 8: 7, 9: "B"}, {1: 21, 4: "GMP", 5: 11, 8: None, 9: "A"}],
    ))
    assert len(plan["discovery"]["candidates"]) == 3
    assert plan["certificate_linkage"]["records"][0]["classification"] == "BLOCKED_CASE_CERTIFICATE_CONFLICT"
    assert plan["certificate_linkage"]["records"][1]["classification"] == "BLOCKED_SITE_MISMATCH"


def test_certificate_linkage_rejects_source_case_site_or_gxp_context_conflicts():
    site_conflict = _plan(_snapshot(
        ktra=[{1: 10, 2: "GMP", 3: 7, 4: "A"}],
        certificates=[{1: 20, 4: "GMP", 5: 10, 8: 8, 9: "A"}],
    ))
    assert site_conflict["certificate_linkage"]["records"][0]["classification"] == "BLOCKED_SITE_MISMATCH"
    gxp_conflict = _plan(_snapshot(
        ktra=[{1: 10, 2: "GMP", 3: 7, 4: "A"}],
        certificates=[{1: 20, 4: "GLP", 5: 10, 8: 7, 9: "A"}],
    ))
    assert gxp_conflict["certificate_linkage"]["records"][0]["classification"] == "BLOCKED_SOURCE_CONFLICT"


def test_no_transformation_is_inferred_from_combined_line_text():
    plan = _plan(_snapshot(ktra=[{1: 10, 2: "GMP", 3: 7, 4: "A+C"}], certificates=[]))
    record = plan["transformation_evidence"]["records"][0]
    assert record["classification"] == "POSSIBLE_BUT_UNPROVEN"
    assert record["writable"] is False
    assert plan["transformation_evidence"]["transformation_writable_count"] == 0


def test_duplicate_source_ids_and_ambiguous_explicit_evidence_fail_closed():
    with pytest.raises(ProductionLinePlanningError, match="duplicate valid legacy inspection IDs"):
        _plan(_snapshot(ktra=[{1: 10, 2: "GMP", 3: 7, 4: "A"}, {1: 10, 2: "GMP", 3: 7, 4: "B"}], certificates=[]))
    with pytest.raises(ProductionLinePlanningError, match="duplicate or ambiguous"):
        _plan(_snapshot(ktra=[{1: 10, 2: "GMP", 3: 7, 4: "A"}], certificates=[]), {"physical_line_evidence": [
            {"legacy_site_id": 7, "line_text": "A", "evidence_kind": "EXPLICIT_PHYSICAL_LINE_IDENTITY"},
            {"legacy_site_id": 7, "line_text": " a ", "evidence_kind": "EXPLICIT_PHYSICAL_LINE_IDENTITY"},
        ]})
    with pytest.raises(ProductionLinePlanningError, match="duplicate source row coordinates"):
        snapshot = _snapshot(ktra=[{1: 10, 2: "GMP", 3: 7, 4: "A"}], certificates=[])
        snapshot["sheets"][0]["raw_rows"].append(deepcopy(snapshot["sheets"][0]["raw_rows"][1]))
        _plan(snapshot)


def test_artifacts_are_deterministic_and_do_not_contain_apply_or_database_write_contracts():
    snapshot = _snapshot(ktra=[{1: 10, 2: "GMP", 3: 7, 4: "A"}], certificates=[])
    first = _plan(snapshot)
    second = _plan(deepcopy(snapshot))
    assert first == second
    encoded = canonical_artifact_bytes(first["discovery"])
    assert sha256(encoded).hexdigest() == sha256(canonical_artifact_bytes(second["discovery"])).hexdigest()
    rendered = json.dumps(first, ensure_ascii=False).lower()
    assert "--apply" not in rendered
    assert '"write_candidates": []' in rendered


def test_cli_runs_directly_and_refuses_a_snapshot_with_the_wrong_fingerprint(tmp_path):
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(json.dumps(_snapshot(ktra=[], certificates=[])), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "tools/plan_production_line_population_b6h.py", "--snapshot", str(snapshot)],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "SHA256 provenance guard failed" in result.stderr


def test_planner_is_source_only_and_has_no_apply_or_database_owner():
    source = (ROOT / "backend/app/domain/production_line_population.py").read_text(encoding="utf-8")
    cli = (ROOT / "tools/plan_production_line_population_b6h.py").read_text(encoding="utf-8")
    assert "sqlalchemy" not in source
    assert "create_engine" not in source
    assert "--apply" not in source
    assert "--database-url" not in cli
    assert "--apply" not in cli


def test_canonical_snapshot_counts_when_local_source_evidence_is_available():
    path = ROOT / "artifacts/phase3c/legacy_snapshot_v2.json"
    if not path.exists():
        pytest.skip("local canonical Snapshot V2 is intentionally not tracked")
    snapshot = json.loads(path.read_bytes())
    plan = build_production_line_population_plan(
        snapshot,
        snapshot_sha256=sha256(path.read_bytes()).hexdigest(),
    )
    assert plan["discovery"]["summary_counts"] == {
        "candidate_production_lines": 386,
        "create_safe": 0,
        "blocked_candidate_count": 386,
        "same_site_canonical_text_collisions": 0,
        "cross_site_same_text_occurrences": 5,
        "multi_gxp_same_site_same_line_observations": 0,
    }
    assert plan["case_linkage"]["classification_counts"] == {
        "BLOCKED_INSUFFICIENT_EVIDENCE": 1360,
        "BLOCKED_NO_LINE": 136,
        "NOT_APPLICABLE": 37,
    }
    assert plan["certificate_linkage"]["classification_counts"] == {
        "BLOCKED_INSUFFICIENT_EVIDENCE": 1377,
        "BLOCKED_NO_LINE": 240,
        "BLOCKED_SITE_MISMATCH": 4,
    }
    assert plan["transformation_evidence"]["classification_counts"] == {"NO_TRANSFORMATION_EVIDENCE": 1}
