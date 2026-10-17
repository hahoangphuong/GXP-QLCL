"""VM-native DDK preflight SQL safety contract; DB integration runs separately.

The static guard makes it harder for later refactors to accidentally turn
the operating-script into an implicit migration or production DB update.
"""
from pathlib import Path
import re


SOURCE = Path("scripts/check_ddk_gxp_provenance_rehearsal_readonly.sql")


def _sql():
    return SOURCE.read_text(encoding="utf-8")


def _executable():
    return "\n".join(
        line for line in _sql().splitlines()
        if not line.lstrip().startswith("--")
    )


def test_rehearsal_psql_script_is_one_explicit_readonly_snapshot():
    sql = _executable()
    assert "\\set ON_ERROR_STOP on" in sql
    assert re.search(
        r"BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY\s*;", sql
    )
    assert "current_database() <> 'gxp_legacy_rehearsal'" in sql
    assert "current_setting('transaction_read_only')" in sql
    assert "current_setting('transaction_isolation')" in sql
    assert "RAISE EXCEPTION" in sql
    assert re.search(r"ROLLBACK\s*;\s*$", sql)
    assert sql.index("BEGIN TRANSACTION") < sql.index("DO $gxp_preflight_guard$")
    assert sql.index("$gxp_preflight_guard$;") < sql.index("SELECT version_num")
    assert sql.index("ROLLBACK;") > sql.index("count(*)")


def test_sql_counts_are_conditional_when_0023_tables_not_installed():
    sql = _executable()
    for table, flag in (
        ("business_eligibility_gxp_source_group", "gxp_has_group"),
        ("business_eligibility_gxp_reference_evidence", "gxp_has_token"),
    ):
        assert "to_regclass('public." + table + "')" in sql
        assert "\\if :" + flag in sql
        assert sql.index("\\if :" + flag) < sql.index("FROM public." + table + ";")
        assert "\\endif" in sql
    assert "to_regclass('public.alembic_version')" in sql
    assert "\\if :gxp_has_alembic" in sql


def test_readonly_psql_has_no_database_mutations_or_business_data_dump():
    sql = _executable().lower()
    for forbidden in (
        "insert into ", "update public.", "delete from ", "truncate ",
        "create table ", "alter table ", "drop table ", "create index ",
        "alembic upgrade", "pg_dump", "\\copy", "select *",
        "from public.certificate ", "from public.business_eligibility_version ",
    ):
        assert forbidden not in sql
    assert "select count(*)" not in sql  # each target count is clearly labeled
    assert "count(*) as existing_rows" in sql
    # The output never emits source values, Certificate IDs or credentials.
    assert "id_cc_raw" not in sql
    assert "raw_token" not in sql
    assert "parsed_legacy_certificate_id" not in sql
    assert "password" not in sql
