"""Static fail-closed safety contract for VM-local read-only 0023 postflight.

The true PostgreSQL execution proof must come from gxp-web-prod. These
tests prevent accidental removal of important source-only schema guards.
"""
from __future__ import annotations

from pathlib import Path
import re

POSTFLIGHT = Path("scripts/verify_ddk_gxp_0023_postflight_readonly.sql")
REHEARSAL = "gxp_legacy_rehearsal"
GROUP = "business_eligibility_gxp_source_group"
TOKEN = "business_eligibility_gxp_reference_evidence"


def _sql():
    lines = POSTFLIGHT.read_text(encoding="utf-8").splitlines()
    return "\n".join(line for line in lines if not line.lstrip().startswith("--"))


def _has(sql: str, value: str):
    assert value in sql, f"Required owner guard missing: {value}"


def _check_sql(sql: str):
    # The file is expected to work even when the application runtime
    # does not have Python/Alembic: only psql/PostgreSQL built-ins.
    _has(sql, r"\set ON_ERROR_STOP on")
    assert re.search(
        r"\bBEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY\s*;",
        sql,
    )
    assert re.search(r"\bROLLBACK\s*;\s*$", sql)
    _has(sql, f"current_database() <> '{REHEARSAL}'")
    _has(sql, "transaction_read_only")
    _has(sql, "transaction_isolation")
    _has(sql, "'20261012_0023'")
    _has(sql, "revision_count <> 1")
    _has(sql, "relkind = 'r'")
    _has(sql, "att_count <> att_expected")
    _has(sql, "matched_columns <> 17")
    _has(sql, "matched_columns <> 7")
    _has(sql, "matched_columns <> 16")
    _has(sql, "matched_columns <> 6")
    _has(sql, "actual.attname = expected.name")
    _has(sql, "format_type(actual.atttypid, actual.atttypmod)")
    _has(sql, "primary_count <> 1 OR unique_count <> 1 OR check_count <> 5")
    _has(sql, "primary_count <> 1 OR unique_count <> 1 OR check_count <> 2")
    _has(sql, "fk_count <> 0")
    _has(sql, "fk_count <> 1")
    _has(sql, "c.confrelid = group_oid")
    _has(sql, "group_rows <> 0 OR reference_rows <> 0")
    _has(sql, "DDK 0023 named source CHECK semantics mismatch")
    _has(sql, "ck_business_eligibility_gxp_source_group_begxp_group_so_d1cc")
    _has(sql, "ck_business_eligibility_gxp_source_group_begxp_group_co_8a89")
    _has(sql, "ck_business_eligibility_gxp_reference_evidence_begxp_re_7ca6")
    _has(sql, "pg_catalog.pg_get_constraintdef(c.oid)")
    _has(sql, "matched_columns <> 7 THEN")

    _has(sql, "PASS_SCHEMA_0023_SOURCE_ONLY_EMPTY")
    _has(sql, "source_workbook_sha256")
    _has(sql, "source_sheet_name")
    _has(sql, "source_row_number")
    _has(sql, "source_group")
    _has(sql, "source_group_id")
    _has(sql, "token_index")
    assert f"FROM public.{GROUP};" in sql
    assert f"FROM public.{TOKEN};" in sql
    assert sql.index("BEGIN TRANSACTION") < sql.index("DO $ddk_0023_postflight$")
    assert sql.index("$ddk_0023_postflight$;") < sql.index(
        "PASS_SCHEMA_0023_SOURCE_ONLY_EMPTY"
    )


def test_postflight_is_a_single_readonly_snapshot_and_guards_source_contract():
    _check_sql(_sql())


def test_mutations_to_required_guard_text_fail_contract():
    original = _sql()
    for old, new in (
        ("READ ONLY", "READ WRITE"),
        ("gxp_legacy_rehearsal", "gxp_qlcl"),
        ("20261012_0023", "20261008_0022"),
        ("group_rows <> 0 OR reference_rows <> 0", "false"),
        ("fk_count <> 0", "false"),
        ("check_count <> 5", "check_count <> 0"),
        ("matched_columns <> 17", "matched_columns <> 0"),
        ("PASS_SCHEMA_0023_SOURCE_ONLY_EMPTY", "SKIP_CHECK"),
    ):
        assert old in original
        try:
            _check_sql(original.replace(old, new))
        except AssertionError:
            continue
        raise AssertionError(f"Guard regression was accepted after changing: {old}")


def test_postflight_has_no_data_writes_or_raw_source_data_dump():
    sql = _sql()
    # SQL keywords in a PL/pgSQL DO block do not imply write permission,
    # but this file must contain no SQL data-writing statements at all.
    for disallowed in (
        r"\bINSERT\s+INTO\b",
        r"\bDELETE\s+FROM\b",
        r"\bUPDATE\s+[a-z_]",
        r"\bALTER\s+TABLE\b",
        r"\bCREATE\s+TABLE\b",
        r"\bDROP\s+TABLE\b",
        r"\bTRUNCATE\b",
        r"\bGRANT\b",
        r"\bREVOKE\b",
        r"\\copy",
    ):
        assert not re.search(disallowed, sql, flags=re.I), disallowed
    assert not re.search(r"\bSELECT\s+\*", sql, flags=re.I)
    assert "id_cc_raw" in sql  # column contract only, no SELECT id_cc_raw.
    assert not re.search(r"\bSELECT\s+id_cc_raw\b", sql, flags=re.I)
    assert "reviewed_sql_sha256" not in sql
