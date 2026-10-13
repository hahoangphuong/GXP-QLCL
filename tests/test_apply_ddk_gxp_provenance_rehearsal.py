"""Source-only DDK provenance writer; all tests use disposable SQLite."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, insert, select, text, update

from backend.app.db.models.phase1 import (
    BusinessEligibilityGxpReferenceEvidence,
    BusinessEligibilityGxpSourceGroup,
)
from tools.apply_ddk_gxp_provenance_rehearsal import (
    SourceLoadBlocked,
    apply_sealed_plan,
    checked_rehearsal_url,
    main,
)
from tools.plan_ddk_gxp_provenance_load import _digest, _source_value_digest


SHA = "a" * 64
ROLES = [("GMP", 15), ("GLP", 19), ("GSP", 23), ("GDP", 27)]


def _source_plan():
    groups = []
    tokens = []
    for role, col in ROLES:
        values = ["200; 201", " Sterile\n", "WHO-GMP", "Manufacture"] if role == "GMP" else (
            ["", "", "", "GDP activity without a certificate ID"] if role == "GDP"
            else ["", "", "", ""]
        )
        entry = {
            "source_workbook_sha256": SHA,
            "source_sheet_name": "db.dkkd",
            "source_row_number": 7,
            "source_group": role,
            "legacy_dkkd_id": 400,
            "id_cc_excel_column": col,
            "certificate_scope_excel_column": col + 1,
            "applicable_standard_excel_column": col + 2,
            "business_activity_excel_column": col + 3,
            "id_cc_raw": values[0],
            "certificate_scope_raw": values[1],
            "applicable_standard_raw": values[2],
            "business_activity_raw": values[3],
            "source_values_sha256": _source_value_digest(values),
        }
        key = {k: entry[k] for k in (
            "source_workbook_sha256", "source_sheet_name",
            "source_row_number", "source_group",
        )}
        groups.append({"logical_source_key": key, "values": entry})
        if role == "GMP":
            for pos, certificate_id in enumerate([200, 201], 1):
                tokens.append({
                    "source_group_key": key,
                    "values": {
                        "token_index": pos,
                        "raw_token": str(certificate_id),
                        "parsed_legacy_certificate_id": certificate_id,
                    },
                })
    payload = {
        "group_table": "business_eligibility_gxp_source_group",
        "token_table": "business_eligibility_gxp_reference_evidence",
        "source_groups": groups,
        "reference_tokens": tokens,
    }
    return {
        "schema": "GXP_DDK_GXP_PROVENANCE_DRY_RUN_V1",
        "status": "DRY_RUN_ONLY_NOT_APPLIED",
        "source_workbook_sha256": SHA,
        "source_baseline": {
            "ddk_rows": 2,
            "excluded_ddk_rows": 1,
            "reference_tokens": 2,
            "source_validation": "PARTIAL_INDEPENDENT_EXPORTS_ONLY",
            "excel_com_check": "WAIVED_BY_OWNER_NOT_PERFORMED",
        },
        "target": {
            "alembic_revision_required": "20261012_0023",
            "database_state": "NOT_CONNECTED_NOT_INSPECTED",
            "foreign_key_to_canonical_certificate": False,
            "canonical_link_changes": 0,
            "sql_writes_executed": 0,
            "uuid_allocation": "NOT_PERFORMED",
        },
        "counts": {
            "original_ddk_rows": 2, "excluded_ddk_rows": 1, "effective_ddk_rows": 1,
            "group_rows": 4, "field_positions": 16, "reference_tokens": 2,
            **{f"groups_{role}": 1 for role, _ in ROLES},
        },
        "excluded_source_rows": [{"source_row_number": 8, "legacy_dkkd_id": 401}],
        "payload_sha256": _digest(payload),
        "payload": payload,
    }


def _engine(revision="20261012_0023"):
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    BusinessEligibilityGxpSourceGroup.__table__.create(engine)
    BusinessEligibilityGxpReferenceEvidence.__table__.create(engine)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE alembic_version (version_num varchar(32) NOT NULL)"))
        connection.execute(text("INSERT INTO alembic_version(version_num) VALUES (:r)"), {"r": revision})
    return engine


def test_load_four_distinct_physical_groups_and_two_tokens_idempotently():
    engine = _engine()
    plan = _source_plan()
    try:
        first = apply_sealed_plan(engine, plan, allow_sqlite_for_tests=True)
        assert first["status"] == "SOURCE_PROVENANCE_LOADED_AND_VERIFIED"
        assert first["inserted_groups"] == 4
        assert first["inserted_tokens"] == 2
        assert first["canonical_links_created"] == 0
        with engine.connect() as connection:
            groups = connection.execute(
                select(BusinessEligibilityGxpSourceGroup.__table__)
            ).mappings().all()
            tokens = connection.execute(
                select(BusinessEligibilityGxpReferenceEvidence.__table__)
            ).mappings().all()
            assert len(groups) == 4
            assert len(tokens) == 2
            assert {g["source_group"] for g in groups} == {"GMP", "GLP", "GSP", "GDP"}
            assert next(g for g in groups if g["source_group"] == "GDP")["business_activity_raw"] == (
                "GDP activity without a certificate ID"
            )
            assert next(g for g in groups if g["source_group"] == "GMP")["certificate_scope_raw"] == " Sterile\n"
        second = apply_sealed_plan(engine, plan, allow_sqlite_for_tests=True)
        assert second["status"] == "SOURCE_PROVENANCE_ALREADY_MATCHES_PLAN"
        assert second["inserted_groups"] == second["inserted_tokens"] == 0
    finally:
        engine.dispose()


def test_wrong_schema_or_source_mutation_preserves_empty_target():
    engine = _engine(revision="20261008_0022")
    try:
        with pytest.raises(SourceLoadBlocked, match="Existing schema/source data conflict"):
            apply_sealed_plan(engine, _source_plan(), allow_sqlite_for_tests=True)
        with engine.connect() as connection:
            assert connection.execute(
                select(BusinessEligibilityGxpSourceGroup.__table__.c.id)
            ).all() == []
    finally:
        engine.dispose()
    engine = _engine()
    try:
        bad = copy.deepcopy(_source_plan())
        bad["payload"]["source_groups"][0]["values"]["id_cc_raw"] = "tampered"
        with pytest.raises(Exception):
            apply_sealed_plan(engine, bad, allow_sqlite_for_tests=True)
        with engine.connect() as connection:
            assert connection.execute(
                select(BusinessEligibilityGxpSourceGroup.__table__.c.id)
            ).all() == []
    finally:
        engine.dispose()


def test_existing_row_tampering_blocks_retry_without_partial_writes():
    engine = _engine()
    try:
        plan = _source_plan()
        apply_sealed_plan(engine, plan, allow_sqlite_for_tests=True)
        with engine.begin() as connection:
            connection.execute(
                update(BusinessEligibilityGxpSourceGroup.__table__)
                .where(BusinessEligibilityGxpSourceGroup.__table__.c.source_group == "GMP")
                .values(certificate_scope_raw="mutated")
            )
        with pytest.raises(SourceLoadBlocked, match="Existing schema/source data conflict"):
            apply_sealed_plan(engine, plan, allow_sqlite_for_tests=True)
        with engine.connect() as connection:
            assert len(connection.execute(
                select(BusinessEligibilityGxpReferenceEvidence.__table__.c.id)
            ).all()) == 2  # No automatic delete/repair of original evidence.
    finally:
        engine.dispose()


def test_changed_plan_bytes_before_commit_rolls_back_inserts():
    engine = _engine()
    try:
        with pytest.raises(SourceLoadBlocked, match="Source plan bytes changed"):
            apply_sealed_plan(
                engine, _source_plan(), allow_sqlite_for_tests=True,
                unchanged_source=lambda: False,
            )
        with engine.connect() as connection:
            assert connection.execute(
                select(BusinessEligibilityGxpSourceGroup.__table__.c.id)
            ).all() == []
    finally:
        engine.dispose()


@pytest.mark.parametrize("db_name,url", [
    ("gxp_qlcl", "postgresql+psycopg://gxp_app:secret@127.0.0.1:5432/gxp_qlcl"),
    ("gxp_legacy_rehearsal", "postgresql+psycopg://gxp_app:secret@127.0.0.1:5432/gxp_qlcl"),
    ("gxp_legacy_rehearsal", "sqlite:///tmp/test.db"),
    ("gxp_legacy_rehearsal", "postgresql+psycopg://gxp_app:secret@8.8.8.8:5432/gxp_legacy_rehearsal"),
])
def test_runtime_target_guard_refuses_other_database_or_host(db_name, url):
    with pytest.raises(SourceLoadBlocked):
        checked_rehearsal_url({
            "DB_NAME": db_name, "DB_USER": "gxp_app", "DB_MODE": "local_postgres",
            "DATABASE_URL": url,
        })


def test_apply_requires_external_source_identity_before_database_io(tmp_path: Path, capsys):
    path = tmp_path / "sealed-plan.json"
    path.write_text(json.dumps(_source_plan()), encoding="utf-8")
    assert main(["--plan-json", str(path)]) == 0
    assert "OFFLINE_PLAN_VALIDATED_NO_DB_IO" in capsys.readouterr().out
    assert main(["--plan-json", str(path), "--apply"]) == 2
    assert "DDK_PROVENANCE_LOAD_BLOCKED" in capsys.readouterr().err
