from __future__ import annotations

from hashlib import sha256

import json

from backend.app.domain.production_line_canonical_state import PROTECTED_DATABASE_NAMES, canonical_state_digest_pair
from backend.app.domain.production_line_population import CANONICAL_STATE_SCHEMA_VERSION, build_production_line_population_plan, canonical_artifact_bytes, canonical_json_bytes
from tools.plan_production_line_population_b6h import load_json_with_sha256


def test_exporter_contract_has_explicit_schema_revision_and_protected_target_fence():
    assert CANONICAL_STATE_SCHEMA_VERSION == "production-line-canonical-state/v1"
    assert "gxp_qlcl" in PROTECTED_DATABASE_NAMES
    source = open("tools/export_production_line_canonical_state_b6h.py", encoding="utf-8").read()
    assert 'add_argument("--database-url", required=True' in source
    assert "SET TRANSACTION READ ONLY" in source
    assert "--apply" not in source
    assert "DATABASE_URL" not in source


def test_canonical_state_semantic_digest_is_distinct_from_exact_pretty_file_digest(tmp_path):
    state = {"schema_version": CANONICAL_STATE_SCHEMA_VERSION, "items": [{"id": "00000000-0000-0000-0000-000000000001"}]}
    semantic_sha, file_sha = canonical_state_digest_pair(state)
    assert semantic_sha == sha256(canonical_json_bytes(state)).hexdigest()
    assert file_sha == sha256(canonical_artifact_bytes(state)).hexdigest()
    assert semantic_sha != file_sha
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    first.write_bytes(canonical_artifact_bytes(state))
    second.write_text(json.dumps(state, ensure_ascii=False, indent=4) + "\n", encoding="utf-8")
    _, first_semantic = load_json_with_sha256(first)
    _, second_semantic = load_json_with_sha256(second)
    assert first_semantic == second_semantic == semantic_sha
    assert sha256(first.read_bytes()).hexdigest() != sha256(second.read_bytes()).hexdigest()


def test_exporter_reports_semantic_and_file_sha_labels_without_swapping_them():
    source = open("tools/export_production_line_canonical_state_b6h.py", encoding="utf-8").read()
    assert 'print(f"CANONICAL_STATE_SHA256={semantic_sha256}")' in source
    assert 'print(f"CANONICAL_STATE_FILE_SHA256={file_sha256}")' in source


def test_planner_accepts_exporter_semantic_digest_not_file_digest():
    state = {"schema_version": CANONICAL_STATE_SCHEMA_VERSION, "exported_at": None, "source_database_identity": {"database_name": "fixture"}, "source_alembic_revision": "20260929_0017", "sites": [], "existing_production_lines": [], "cases": [], "certificates": [], "physical_line_evidence": [], "transformations": []}
    state["source_state_fingerprint"] = sha256(canonical_json_bytes(state)).hexdigest()
    semantic_sha, file_sha = canonical_state_digest_pair(state)
    snapshot = {"schema_version": "legacy-workbook-snapshot/v2", "sheets": [
        {"sheet_name": "db.ktra", "raw_rows": [{"source_row_number": 4, "cells": [{"column_ordinal": 1, "raw_value": "ID"}, {"column_ordinal": 2, "raw_value": "LOẠI KT"}, {"column_ordinal": 3, "raw_value": "ID CƠ SỞ"}, {"column_ordinal": 4, "raw_value": "MÃ DC"}]}]},
        {"sheet_name": "db.cc", "raw_rows": [{"source_row_number": 4, "cells": [{"column_ordinal": 1, "raw_value": "ID"}, {"column_ordinal": 4, "raw_value": "LOẠI CC"}, {"column_ordinal": 5, "raw_value": "ID ĐỢT KTRA"}, {"column_ordinal": 8, "raw_value": "ID CƠ SỞ"}, {"column_ordinal": 9, "raw_value": "MÃ DC"}]}]},
    ]}
    build_production_line_population_plan(snapshot, snapshot_sha256="a" * 64, canonical_state=state, canonical_state_sha256=semantic_sha)
    try:
        build_production_line_population_plan(snapshot, snapshot_sha256="a" * 64, canonical_state=state, canonical_state_sha256=file_sha)
    except ValueError as exc:
        assert "does not match semantic content" in str(exc)
    else:
        raise AssertionError("file SHA must not be accepted as canonical semantic provenance")
