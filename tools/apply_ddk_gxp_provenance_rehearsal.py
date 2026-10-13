"""Load sealed DDK physical GxP provenance into *rehearsal* only.

The payload contains SOURCE EVIDENCE, not canonical GxP/ĐĐK associations.
One exclusive transaction either writes all groups/tokens or none. A second
invocation with exactly the same source data is a verified no-op.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any, Callable
from uuid import uuid4

from sqlalchemy import create_engine, insert, inspect, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import NullPool

from backend.app.config import resolve_database_url
from backend.app.db.models.phase1 import (
    BusinessEligibilityGxpReferenceEvidence,
    BusinessEligibilityGxpSourceGroup,
)
from tools.audit_ddk_idcc_physical import MissingPhysicalEvidence
from tools.env_utils import parse_env_file
from tools.preflight_ddk_gxp_rehearsal import (
    EXPECTED_DB,
    EXPECTED_REVISION,
    GROUP_TABLE,
    TOKEN_TABLE,
    _table_shape,
    assess_rehearsal_preflight,
    validate_sealed_plan,
)


class SourceLoadBlocked(RuntimeError):
    """No source rows may be written when the import contract is violated."""


def checked_rehearsal_url(runtime_env: dict[str, str]) -> str:
    """Check effective DSN, not merely its declarative DB_NAME label."""
    if runtime_env.get("DB_MODE", "").strip() != "local_postgres":
        raise SourceLoadBlocked("Expected local_postgres DB mode")
    if runtime_env.get("DB_NAME", "").strip() != EXPECTED_DB:
        raise SourceLoadBlocked("Runtime DB_NAME is not rehearsal")
    if runtime_env.get("DB_USER", "").strip() != "gxp_app":
        raise SourceLoadBlocked("Runtime role must be gxp_app")
    url = resolve_database_url(runtime_env)
    try:
        parsed = make_url(url)
    except (ValueError, TypeError) as exc:
        raise SourceLoadBlocked("Invalid runtime database URL") from exc
    if (
        parsed.get_backend_name() != "postgresql"
        or parsed.database != EXPECTED_DB
        or parsed.username != "gxp_app"
        or parsed.host not in {"127.0.0.1", "localhost", "::1"}
    ):
        raise SourceLoadBlocked("Effective database URL is not local rehearsal")
    return url


def _source_snapshot(connection, workbook_sha256: str) -> dict[str, Any]:
    """Read the entire target count and selected source rows in *this* lock."""
    db = connection.execute(text("SELECT current_database()")).scalar_one()
    revisions = list(connection.execute(
        text("SELECT version_num FROM public.alembic_version ORDER BY version_num")
        if connection.dialect.name == "postgresql"
        else text("SELECT version_num FROM alembic_version ORDER BY version_num")
    ).scalars())
    schema = "public" if connection.dialect.name == "postgresql" else None
    inspector = inspect(connection)
    names = {GROUP_TABLE, TOKEN_TABLE}
    available = names & set(inspector.get_table_names(schema=schema))
    structure = {
        name: _table_shape(connection, inspector, name)
        if schema == "public" else {
            "columns": [x["name"] for x in inspector.get_columns(name)],
            "not_null": [x["name"] for x in inspector.get_columns(name) if not x["nullable"]],
            "check_clauses": [str(x.get("sqltext") or "") for x in inspector.get_check_constraints(name)],
            "uniques": [list(x.get("column_names") or []) for x in inspector.get_unique_constraints(name)],
            "foreign_keys": [{
                "constrained_columns": list(x.get("constrained_columns") or []),
                "referred_table": x.get("referred_table"),
                "referred_columns": list(x.get("referred_columns") or []),
            } for x in inspector.get_foreign_keys(name)],
        }
        for name in available
    }
    groups: list[dict[str, Any]] = []
    tokens: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    if GROUP_TABLE in available:
        counts[GROUP_TABLE] = connection.execute(
            text(f"SELECT count(*) FROM {GROUP_TABLE}")
        ).scalar_one()
        groups = [dict(row) for row in connection.execute(text(f"""
            SELECT source_workbook_sha256, source_sheet_name, source_row_number,
                   source_group, legacy_dkkd_id, id_cc_excel_column,
                   certificate_scope_excel_column, applicable_standard_excel_column,
                   business_activity_excel_column, id_cc_raw, certificate_scope_raw,
                   applicable_standard_raw, business_activity_raw, source_values_sha256
            FROM {GROUP_TABLE} WHERE source_workbook_sha256 = :fingerprint
        """), {"fingerprint": workbook_sha256}).mappings()]
    if TOKEN_TABLE in available:
        counts[TOKEN_TABLE] = connection.execute(
            text(f"SELECT count(*) FROM {TOKEN_TABLE}")
        ).scalar_one()
        if GROUP_TABLE in available:
            tokens = [dict(row) for row in connection.execute(text(f"""
                SELECT g.source_workbook_sha256, g.source_sheet_name,
                       g.source_row_number, g.source_group, t.token_index,
                       t.raw_token, t.parsed_legacy_certificate_id
                FROM {TOKEN_TABLE} AS t
                JOIN {GROUP_TABLE} AS g ON t.source_group_id = g.id
                WHERE g.source_workbook_sha256 = :fingerprint
            """), {"fingerprint": workbook_sha256}).mappings()]
    read_only = (
        connection.execute(text("SELECT current_setting('transaction_read_only')")).scalar_one() == "on"
        if connection.dialect.name == "postgresql" else False
    )
    return {
        "database_name": EXPECTED_DB if connection.dialect.name == "sqlite" else db,
        "transaction_read_only": read_only,
        "alembic_revisions": revisions,
        "present_tables": sorted(available),
        "table_structure": structure,
        "global_counts": counts,
        "existing_groups": groups,
        "existing_tokens": tokens,
    }


def apply_sealed_plan(
    engine: Engine,
    plan: dict[str, Any],
    *,
    unchanged_source: Callable[[], bool] | None = None,
    allow_sqlite_for_tests: bool = False,
) -> dict[str, Any]:
    """Apply in one transaction, comparing both before and after images.

    SQLite is admitted solely by explicit test opt-in. Runtime CLI never
    exposes this flag, and always verifies a PostgreSQL rehearsal DSN.
    """
    expected_groups, expected_tokens = validate_sealed_plan(plan)
    dialect = engine.dialect.name
    if dialect != "postgresql" and not (dialect == "sqlite" and allow_sqlite_for_tests):
        raise SourceLoadBlocked("Only PostgreSQL rehearsal is write-authorized")
    # A source group can legitimately have no ID CC tokens. Refuse only an
    # entirely empty source plan; don't invent tokens for GDP activity.
    if not expected_groups:
        raise SourceLoadBlocked("Source plan contains no GxP groups")

    group_table = BusinessEligibilityGxpSourceGroup.__table__
    token_table = BusinessEligibilityGxpReferenceEvidence.__table__
    with engine.begin() as conn:
        if dialect == "postgresql":
            conn.exec_driver_sql("SET LOCAL lock_timeout = '10s'")
            conn.exec_driver_sql("SET LOCAL statement_timeout = '120s'")
            conn.exec_driver_sql(
                "LOCK TABLE public.alembic_version, "
                "public.business_eligibility_gxp_source_group, "
                "public.business_eligibility_gxp_reference_evidence "
                "IN SHARE ROW EXCLUSIVE MODE"
            )
            actual_db = conn.execute(text("SELECT current_database()")).scalar_one()
            if actual_db != EXPECTED_DB:
                raise SourceLoadBlocked("Connected to the wrong database")
        before = assess_rehearsal_preflight(
            plan, _source_snapshot(conn, plan["source_workbook_sha256"]),
            require_read_only=False,
        )
        if before["status"] == "SOURCE_PROVENANCE_ALREADY_MATCHES_PLAN":
            if unchanged_source is not None and not unchanged_source():
                raise SourceLoadBlocked("Source plan bytes changed during verification")
            return {
                "status": "SOURCE_PROVENANCE_ALREADY_MATCHES_PLAN",
                "database_name": EXPECTED_DB,
                "revision": EXPECTED_REVISION,
                "group_rows": len(expected_groups),
                "token_rows": len(expected_tokens),
                "inserted_groups": 0,
                "inserted_tokens": 0,
                "canonical_links_created": 0,
            }
        if before["status"] != "EMPTY_SCHEMA_READY_FOR_SEPARATE_APPLY_APPROVAL":
            raise SourceLoadBlocked("Existing schema/source data conflict: " + before["status"])

        group_ids: dict[tuple[str, str, int, str], str] = {}
        group_rows: list[dict[str, Any]] = []
        for item in plan["payload"]["source_groups"]:
            source = item["values"]
            key = (
                source["source_workbook_sha256"], source["source_sheet_name"],
                source["source_row_number"], source["source_group"],
            )
            assigned = str(uuid4())
            group_ids[key] = assigned
            group_rows.append({"id": assigned, **source})
        if len(group_ids) != len(expected_groups):
            raise SourceLoadBlocked("Source-group identity collapsed")

        token_rows: list[dict[str, Any]] = []
        for item in plan["payload"]["reference_tokens"]:
            group = item["source_group_key"]
            key = (
                group["source_workbook_sha256"], group["source_sheet_name"],
                group["source_row_number"], group["source_group"],
            )
            token_rows.append({
                "id": str(uuid4()),
                "source_group_id": group_ids[key],
                **item["values"],
            })
        if len(token_rows) != len(expected_tokens):
            raise SourceLoadBlocked("Source-token identity collapsed")

        conn.execute(insert(group_table), group_rows)
        if token_rows:
            conn.execute(insert(token_table), token_rows)
        after = assess_rehearsal_preflight(
            plan, _source_snapshot(conn, plan["source_workbook_sha256"]),
            require_read_only=False,
        )
        if after["status"] != "SOURCE_PROVENANCE_ALREADY_MATCHES_PLAN":
            raise SourceLoadBlocked("Post-insert evidence comparison failed")
        if unchanged_source is not None and not unchanged_source():
            raise SourceLoadBlocked("Source plan bytes changed before COMMIT")
        return {
            "status": "SOURCE_PROVENANCE_LOADED_AND_VERIFIED",
            "database_name": EXPECTED_DB,
            "revision": EXPECTED_REVISION,
            "group_rows": len(expected_groups),
            "token_rows": len(expected_tokens),
            "inserted_groups": len(group_rows),
            "inserted_tokens": len(token_rows),
            "canonical_links_created": 0,
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-json", required=True, type=Path)
    parser.add_argument("--runtime-env", type=Path, default=Path("/etc/gxp/runtime.env"))
    parser.add_argument("--expected-workbook-sha256")
    parser.add_argument("--expected-groups", type=int)
    parser.add_argument("--expected-tokens", type=int)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-target")
    args = parser.parse_args(argv)
    try:
        original = args.plan_json.read_bytes()
        plan = json.loads(original.decode("utf-8"))
        groups, tokens = validate_sealed_plan(plan)
        expected = args.expected_workbook_sha256
        if expected is not None and expected != plan["source_workbook_sha256"]:
            raise SourceLoadBlocked("Workbook fingerprint differs from expected")
        if args.expected_groups is not None and len(groups) != args.expected_groups:
            raise SourceLoadBlocked("Unexpected source-group count")
        if args.expected_tokens is not None and len(tokens) != args.expected_tokens:
            raise SourceLoadBlocked("Unexpected source-token count")
        plan_sha256 = sha256(original).hexdigest()

        if args.apply:
            if args.confirm_target != EXPECTED_DB:
                raise SourceLoadBlocked("Explicit --confirm-target gxp_legacy_rehearsal required")
            if not expected:
                raise SourceLoadBlocked("External --expected-workbook-sha256 required for write")
            env = parse_env_file(args.runtime_env)
            database_url = checked_rehearsal_url(env)
            engine = create_engine(database_url, future=True, poolclass=NullPool)
            try:
                report = apply_sealed_plan(
                    engine, plan,
                    unchanged_source=lambda: args.plan_json.read_bytes() == original,
                )
            finally:
                engine.dispose()
        else:
            if args.confirm_target:
                raise SourceLoadBlocked("--confirm-target only applies to write mode")
            report = {
                "status": "OFFLINE_PLAN_VALIDATED_NO_DB_IO",
                "group_rows": len(groups),
                "token_rows": len(tokens),
                "inserted_groups": 0,
                "inserted_tokens": 0,
                "canonical_links_created": 0,
            }
        report["plan_sha256"] = plan_sha256
        report["workbook_sha256"] = plan["source_workbook_sha256"]
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 0
    except (
        SourceLoadBlocked, MissingPhysicalEvidence, SQLAlchemyError,
        OSError, ValueError, TypeError, KeyError, UnicodeError,
    ) as exc:
        # Never reveal source text, passwords, SQL rows or raw driver errors.
        print("DDK_PROVENANCE_LOAD_BLOCKED: " + type(exc).__name__, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
