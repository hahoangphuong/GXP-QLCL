"""Adversarial read-only DDK rehearsal preflight tests; no live database."""
from __future__ import annotations

import copy
import json
import sys
import pytest

from tools.audit_ddk_idcc_physical import MissingPhysicalEvidence
from tools.plan_ddk_gxp_provenance_load import _digest, _source_value_digest
from tools.preflight_ddk_gxp_rehearsal import (
    EXPECTED_DB, EXPECTED_REVISION, GROUP_TABLE, TOKEN_TABLE,
    GROUP_COLUMNS, TOKEN_COLUMNS, GROUP_UNIQUE, TOKEN_UNIQUE,
    GROUP_NOT_NULL, TOKEN_NOT_NULL,
    assess_rehearsal_preflight, read_rehearsal_snapshot, validate_sealed_plan,
    main,
)

SHA = "a" * 64
ROLES = (("GMP", 15), ("GLP", 19), ("GSP", 23), ("GDP", 27))


def _group(role, col):
    fields = ["200; 201", " Sterile\n", "WHO-GMP", "Manufacture"] if role == "GMP" else (
        ["", "", "", "GDP activity without certificate ID"] if role == "GDP"
        else ["", "", "", ""]
    )
    values = {
        "source_workbook_sha256": SHA, "source_sheet_name": "db.dkkd",
        "source_row_number": 7, "source_group": role, "legacy_dkkd_id": 400,
        "id_cc_excel_column": col, "certificate_scope_excel_column": col + 1,
        "applicable_standard_excel_column": col + 2,
        "business_activity_excel_column": col + 3,
        "id_cc_raw": fields[0], "certificate_scope_raw": fields[1],
        "applicable_standard_raw": fields[2], "business_activity_raw": fields[3],
        "source_values_sha256": _source_value_digest(fields),
    }
    logical = {name: values[name] for name in (
        "source_workbook_sha256", "source_sheet_name", "source_row_number", "source_group",
    )}
    return {"logical_source_key": logical, "values": values}


def sealed_plan():
    groups = [_group(role, col) for role, col in ROLES]
    tokens = [{
        "source_group_key": groups[0]["logical_source_key"],
        "values": {
            "token_index": index,
            "raw_token": str(cid),
            "parsed_legacy_certificate_id": cid,
        },
    } for index, cid in enumerate((200, 201), 1)]
    payload = {"group_table": GROUP_TABLE, "token_table": TOKEN_TABLE,
               "source_groups": groups, "reference_tokens": tokens}
    return {
        "schema": "GXP_DDK_GXP_PROVENANCE_DRY_RUN_V1",
        "status": "DRY_RUN_ONLY_NOT_APPLIED",
        "source_workbook_sha256": SHA,
        "source_baseline": {
            "ddk_rows": 2, "excluded_ddk_rows": 1, "reference_tokens": 2,
            "source_validation": "PARTIAL_INDEPENDENT_EXPORTS_ONLY",
            "excel_com_check": "WAIVED_BY_OWNER_NOT_PERFORMED",
        },
        "target": {
            "alembic_revision_required": EXPECTED_REVISION,
            "database_state": "NOT_CONNECTED_NOT_INSPECTED",
            "foreign_key_to_canonical_certificate": False,
            "canonical_link_changes": 0, "sql_writes_executed": 0,
            "uuid_allocation": "NOT_PERFORMED",
        },
        "counts": {
            "original_ddk_rows": 2, "excluded_ddk_rows": 1,
            "effective_ddk_rows": 1, "group_rows": 4, "field_positions": 16,
            "reference_tokens": 2, "groups_GMP": 1, "groups_GLP": 1,
            "groups_GSP": 1, "groups_GDP": 1,
        },
        "excluded_source_rows": [{"source_row_number": 8, "legacy_dkkd_id": 401}],
        "payload_sha256": _digest(payload),
        "payload": payload,
    }


def _structure():
    return {
        GROUP_TABLE: {
            "columns": list(GROUP_COLUMNS), "not_null": list(GROUP_NOT_NULL),
            "check_clauses": [
                "source_sheet_name = 'db.dkkd'",
                "source_group IN ('GMP', 'GLP', 'GSP', 'GDP')",
                "source_row_number > 0",
                "certificate_scope_excel_column = id_cc_excel_column + 1",
                "length(source_workbook_sha256) = 64",
            ],
            "uniques": [list(GROUP_UNIQUE)], "foreign_keys": [],
        },
        TOKEN_TABLE: {
            "columns": list(TOKEN_COLUMNS), "not_null": list(TOKEN_NOT_NULL),
            "check_clauses": [
                "token_index > 0", "parsed_legacy_certificate_id IS NULL OR parsed_legacy_certificate_id > 0",
            ],
            "uniques": [list(TOKEN_UNIQUE)],
            "foreign_keys": [{
                "constrained_columns": ["source_group_id"],
                "referred_table": GROUP_TABLE, "referred_columns": ["id"],
            }],
        },
    }


def _snapshot(*, revision=EXPECTED_REVISION, exists=True):
    return {
        "database_name": EXPECTED_DB, "transaction_read_only": True,
        "alembic_revisions": [revision],
        "present_tables": [GROUP_TABLE, TOKEN_TABLE] if exists else [],
        "table_structure": _structure() if exists else {},
        "global_counts": {GROUP_TABLE: 0, TOKEN_TABLE: 0} if exists else {},
        "existing_groups": [], "existing_tokens": [],
    }


def _populated_snapshot(plan):
    snapshot = _snapshot()
    groups = [dict(item["values"]) for item in plan["payload"]["source_groups"]]
    tokens = [{**item["source_group_key"], **item["values"]}
              for item in plan["payload"]["reference_tokens"]]
    snapshot["existing_groups"] = groups
    snapshot["existing_tokens"] = tokens
    snapshot["global_counts"] = {GROUP_TABLE: len(groups), TOKEN_TABLE: len(tokens)}
    return snapshot


def test_valid_plan_and_pending_migration_are_read_only_not_auto_applied():
    plan = sealed_plan()
    groups, tokens = validate_sealed_plan(plan)
    assert len(groups) == 4 and len(tokens) == 2
    report = assess_rehearsal_preflight(plan, _snapshot(
        revision="20261008_0022", exists=False,
    ))
    assert report["status"] == "SCHEMA_0023_NOT_APPLIED"
    assert report["db_writes"] == 0
    assert report["migration_operations"] == 0
    assert report["canonical_certificate_links_created"] == 0
    assert report["planned_counts"] == {"source_groups": 4, "reference_tokens": 2}


def test_empty_schema_requires_separate_apply_approval():
    report = assess_rehearsal_preflight(sealed_plan(), _snapshot())
    assert report["status"] == "EMPTY_SCHEMA_READY_FOR_SEPARATE_APPLY_APPROVAL"
    assert report["observed_counts"][GROUP_TABLE] == 0
    assert report["approval_status"] == "READ_ONLY_PREFLIGHT_NO_APPLY_AUTHORIZATION"


def test_identical_provenance_is_not_inserted_again():
    plan = sealed_plan()
    report = assess_rehearsal_preflight(plan, _populated_snapshot(plan))
    assert report["status"] == "SOURCE_PROVENANCE_ALREADY_MATCHES_PLAN"
    assert report["conflict_counts"] == {}
    assert report["db_writes"] == 0


def test_content_digest_tamper_and_missing_token_are_detected():
    plan = sealed_plan()
    snapshot = _populated_snapshot(plan)
    snapshot["existing_groups"][0]["certificate_scope_raw"] = "Wrong GMP scope"
    report = assess_rehearsal_preflight(plan, snapshot)
    assert report["status"] == "TARGET_DATA_CONFLICT_OR_PARTIAL_REVIEW"
    assert report["conflict_counts"]["source_group_values_mismatch"] == 1
    snapshot = _populated_snapshot(plan)
    snapshot["existing_tokens"].pop()
    snapshot["global_counts"][TOKEN_TABLE] = 1
    report = assess_rehearsal_preflight(plan, snapshot)
    assert report["conflict_counts"]["planned_source_token_missing"] == 1


def test_other_workbook_and_unverified_schema_do_not_look_empty():
    plan = sealed_plan()
    snapshot = _snapshot()
    snapshot["global_counts"][GROUP_TABLE] = 12
    report = assess_rehearsal_preflight(plan, snapshot)
    assert report["status"] == "TARGET_DATA_CONFLICT_OR_PARTIAL_REVIEW"
    assert report["conflict_counts"]["other_workbook_data_present"] == 1
    snapshot = _snapshot()
    snapshot["table_structure"][GROUP_TABLE]["uniques"] = []
    report = assess_rehearsal_preflight(plan, snapshot)
    assert report["status"] == "SCHEMA_OR_REVISION_DRIFT_REVIEW"
    assert "MISSING_UNIQUE_" + GROUP_TABLE in report["schema_errors"]


def test_missing_one_table_and_unknown_revision_are_never_ready():
    plan = sealed_plan()
    snap = _snapshot()
    snap["present_tables"] = [GROUP_TABLE]
    assert assess_rehearsal_preflight(plan, snap)["status"] == "SCHEMA_OR_REVISION_DRIFT_REVIEW"
    snap = _snapshot(revision="20261008_0022")
    assert assess_rehearsal_preflight(plan, snap)["status"] == "SCHEMA_OR_REVISION_DRIFT_REVIEW"


def test_invalid_plan_checksums_and_canonical_link_claims_fail_closed():
    plan = sealed_plan()
    for field, value in [("payload_sha256", "f" * 64), ("status", "APPLIED")]:
        bad = copy.deepcopy(plan)
        bad[field] = value
        with pytest.raises(MissingPhysicalEvidence):
            validate_sealed_plan(bad)
    bad = sealed_plan()
    bad["target"]["canonical_link_changes"] = 1
    with pytest.raises(MissingPhysicalEvidence, match="canonical"):
        validate_sealed_plan(bad)
    bad = sealed_plan()
    bad["payload"]["source_groups"][3]["values"]["business_activity_raw"] = ""
    with pytest.raises(MissingPhysicalEvidence, match="checksum"):
        validate_sealed_plan(bad)


def test_duplicate_group_token_or_wrong_database_blocks():
    plan = sealed_plan()
    bad = copy.deepcopy(plan)
    bad["payload"]["source_groups"].append(copy.deepcopy(bad["payload"]["source_groups"][0]))
    bad["payload_sha256"] = _digest(bad["payload"])
    with pytest.raises(MissingPhysicalEvidence, match="Duplicate"):
        validate_sealed_plan(bad)
    bad = copy.deepcopy(plan)
    bad["payload"]["reference_tokens"].append(copy.deepcopy(bad["payload"]["reference_tokens"][0]))
    bad["payload_sha256"] = _digest(bad["payload"])
    bad["counts"]["reference_tokens"] = 3
    bad["source_baseline"]["reference_tokens"] = 3
    with pytest.raises(MissingPhysicalEvidence, match="Duplicate source token ordinal"):
        validate_sealed_plan(bad)
    bad_target = _snapshot()
    bad_target["database_name"] = "gxp_qlcl"
    with pytest.raises(MissingPhysicalEvidence, match="Wrong target"):
        assess_rehearsal_preflight(plan, bad_target)
    bad_target = _snapshot()
    bad_target["transaction_read_only"] = False
    with pytest.raises(MissingPhysicalEvidence, match="read-only"):
        assess_rehearsal_preflight(plan, bad_target)


def test_connection_refuses_production_url_before_database_io(monkeypatch):
    def unexpected_engine(*args, **kwargs):
        raise AssertionError("Never create engine for disallowed DB")
    monkeypatch.setattr(
        "tools.preflight_ddk_gxp_rehearsal.create_engine", unexpected_engine,
    )
    with pytest.raises(MissingPhysicalEvidence, match="gxp_legacy_rehearsal"):
        read_rehearsal_snapshot("postgresql://user:secret@localhost/gxp_qlcl", SHA)
    with pytest.raises(MissingPhysicalEvidence, match="PostgreSQL"):
        read_rehearsal_snapshot("sqlite:///:memory:", SHA)


def test_cli_source_not_overwritten_or_read_without_dsn(tmp_path, monkeypatch):
    planfile = tmp_path / "source_plan.json"
    original = json.dumps(sealed_plan()).encode("utf-8")
    planfile.write_bytes(original)
    target = tmp_path / "preflight.json"
    monkeypatch.delenv("GXP_REHEARSAL_READONLY_DATABASE_URL", raising=False)
    monkeypatch.setattr(sys, "argv", [
        "preflight_ddk_gxp_rehearsal", "--plan-json", str(planfile),
        "--output", str(target),
    ])
    with pytest.raises(SystemExit) as err:
        main()
    assert err.value.code == 2
    assert not target.exists() and planfile.read_bytes() == original
    monkeypatch.setattr(sys, "argv", [
        "preflight_ddk_gxp_rehearsal", "--plan-json", str(planfile),
        "--output", str(planfile),
    ])
    with pytest.raises(SystemExit) as err:
        main()
    assert err.value.code == 2
    assert planfile.read_bytes() == original


def test_missing_source_not_null_or_check_constraint_never_marked_ready():
    plan = sealed_plan()
    snapshot = _snapshot()
    snapshot["table_structure"][GROUP_TABLE]["not_null"].remove("id_cc_raw")
    report = assess_rehearsal_preflight(plan, snapshot)
    assert report["status"] == "SCHEMA_OR_REVISION_DRIFT_REVIEW"
    assert "MISSING_NOT_NULL_" + GROUP_TABLE in report["schema_errors"]
    snapshot = _snapshot()
    snapshot["table_structure"][TOKEN_TABLE]["check_clauses"] = []
    report = assess_rehearsal_preflight(plan, snapshot)
    assert "MISSING_CHECK_CONSTRAINTS_" + TOKEN_TABLE in report["schema_errors"]


def test_original_literal_leading_zero_certificate_id_keeps_raw_token():
    plan = sealed_plan()
    group = plan["payload"]["source_groups"][0]["values"]
    group["id_cc_raw"] = "00200; 201"
    group["source_values_sha256"] = _source_value_digest([
        group["id_cc_raw"], group["certificate_scope_raw"],
        group["applicable_standard_raw"], group["business_activity_raw"],
    ])
    plan["payload"]["reference_tokens"][0]["values"]["raw_token"] = "00200"
    plan["payload_sha256"] = _digest(plan["payload"])
    groups, tokens = validate_sealed_plan(plan)
    assert len(groups) == 4
    assert tokens[next(k for k in tokens if k[1] == 1)] == ("00200", 200)
