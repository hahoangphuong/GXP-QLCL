"""Read-only PostgreSQL preflight for DDK GxP source provenance.

This script NEVER applies migrations, allocates UUIDs, performs an INSERT,
UPDATE or DELETE, or creates canonical Certificate relationships. Database
connections are guarded to the exact gxp_legacy_rehearsal name and a
PostgreSQL read-only transaction; input plan is a separately sealed dry-run.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import NullPool

from backend.app.domain.phase2_import import parse_int
from tools.audit_ddk_idcc_physical import DDK_GROUP_LABELS, MissingPhysicalEvidence, split_idcc_references
from tools.plan_ddk_gxp_provenance_load import (
    GROUP_TABLE, PLAN_SCHEMA, TOKEN_TABLE, _digest, _source_value_digest,
)

EXPECTED_DB = "gxp_legacy_rehearsal"
EXPECTED_REVISION = "20261012_0023"
PREFLIGHT_SCHEMA = "GXP_DDK_GXP_REHEARSAL_PREFLIGHT_V1"
GROUP_UNIQUE = frozenset(("source_workbook_sha256", "source_sheet_name", "source_row_number", "source_group"))
TOKEN_UNIQUE = frozenset(("source_group_id", "token_index"))
GROUP_COLUMNS = frozenset((
    "id", "source_workbook_sha256", "source_sheet_name", "source_row_number",
    "legacy_dkkd_id", "source_group", "id_cc_excel_column",
    "certificate_scope_excel_column", "applicable_standard_excel_column",
    "business_activity_excel_column", "id_cc_raw", "certificate_scope_raw",
    "applicable_standard_raw", "business_activity_raw", "source_values_sha256",
))
TOKEN_COLUMNS = frozenset((
    "id", "source_group_id", "token_index", "raw_token",
    "parsed_legacy_certificate_id",
))
GROUP_NOT_NULL = GROUP_COLUMNS - {"legacy_dkkd_id"}
TOKEN_NOT_NULL = TOKEN_COLUMNS - {"parsed_legacy_certificate_id"}
GROUP_EXPECTED_CHECK_FIELDS = (
    "source_sheet_name", "source_group", "source_row_number",
    "certificate_scope_excel_column", "source_workbook_sha256",
)
TOKEN_EXPECTED_CHECK_FIELDS = ("token_index", "parsed_legacy_certificate_id")


def _require(condition: bool, explanation: str) -> None:
    if not condition:
        raise MissingPhysicalEvidence(explanation)


def _key(workbook: str, row: int, role: str) -> tuple[str, str, int, str]:
    return (workbook, "db.dkkd", row, role)


def validate_sealed_plan(plan: dict[str, Any]) -> tuple[dict, dict]:
    """Check source payload conservation without interpreting business relations."""
    _require(isinstance(plan, dict) and plan.get("schema") == PLAN_SCHEMA,
             "Expected the sealed source-only dry-run plan")
    _require(plan.get("status") == "DRY_RUN_ONLY_NOT_APPLIED",
             "Input plan cannot assert database apply or approval")
    workbook = plan.get("source_workbook_sha256")
    _require(isinstance(workbook, str) and len(workbook) == 64
             and all(c in "0123456789abcdef" for c in workbook.lower()),
             "Missing accepted source workbook fingerprint")
    source = plan.get("source_baseline")
    counts = plan.get("counts")
    target = plan.get("target")
    payload = plan.get("payload")
    _require(all(isinstance(x, dict) for x in (source, counts, target, payload)),
             "Missing source, target or logical payload")
    _require(source.get("source_validation") == "PARTIAL_INDEPENDENT_EXPORTS_ONLY"
             and source.get("excel_com_check") == "WAIVED_BY_OWNER_NOT_PERFORMED",
             "Unexpected source acceptance and COM-waiver state")
    _require(target.get("alembic_revision_required") == EXPECTED_REVISION
             and target.get("database_state") == "NOT_CONNECTED_NOT_INSPECTED"
             and target.get("sql_writes_executed") == 0
             and target.get("canonical_link_changes") == 0
             and target.get("foreign_key_to_canonical_certificate") is False
             and target.get("uuid_allocation") == "NOT_PERFORMED",
             "Dry-run plan unexpectedly claims DB writes or canonical links")
    _require(payload.get("group_table") == GROUP_TABLE
             and payload.get("token_table") == TOKEN_TABLE
             and plan.get("payload_sha256") == _digest(payload),
             "Dry-run logical payload checksum or table ownership mismatch")

    planned_groups: dict[tuple[str, str, int, str], dict] = {}
    rows_seen: dict[int, set[str]] = defaultdict(set)
    entries = payload.get("source_groups")
    tokens = payload.get("reference_tokens")
    _require(isinstance(entries, list) and isinstance(tokens, list),
             "Missing planned groups or reference tokens")
    for entry in entries:
        _require(isinstance(entry, dict) and isinstance(entry.get("values"), dict)
                 and isinstance(entry.get("logical_source_key"), dict),
                 "Malformed planned physical source group")
        values = entry["values"]
        k = entry["logical_source_key"]
        row, role = values.get("source_row_number"), values.get("source_group")
        _require(type(row) is int and row > 0 and role in DDK_GROUP_LABELS,
                 "Malformed planned Excel row or role")
        key = _key(workbook, row, role)
        _require(key not in planned_groups
                 and k == {name: val for name, val in zip(
                     ("source_workbook_sha256", "source_sheet_name",
                      "source_row_number", "source_group"), key)}
                 and all(values.get(name) == val for name, val in k.items()),
                 "Duplicate or unbound planned source natural key")
        _require(type(values.get("legacy_dkkd_id")) is int and values["legacy_dkkd_id"] > 0,
                 "Missing original DDK legacy ID")
        col = values.get("id_cc_excel_column")
        _require(type(col) is int and col > 0
                 and all(values.get(name) == col + offset for name, offset in (
                     ("certificate_scope_excel_column", 1),
                     ("applicable_standard_excel_column", 2),
                     ("business_activity_excel_column", 3))),
                 "Truncated or noncontiguous original physical source group")
        raw = [values.get(name) for name in (
            "id_cc_raw", "certificate_scope_raw", "applicable_standard_raw",
            "business_activity_raw",
        )]
        _require(all(isinstance(v, str) for v in raw)
                 and values.get("source_values_sha256") == _source_value_digest(raw),
                 "Original four-field group checksum mismatch")
        planned_groups[key] = values
        rows_seen[row].add(role)
    _require(all(roles == DDK_GROUP_LABELS for roles in rows_seen.values()),
             "A physical DDK source row lost one GxP group")
    _require(all(type(counts.get(n)) is int for n in (
        "original_ddk_rows", "excluded_ddk_rows", "effective_ddk_rows",
        "group_rows", "field_positions", "reference_tokens")),
        "Missing baseline population counters")
    _require(counts["effective_ddk_rows"] == len(rows_seen)
             and counts["group_rows"] == len(planned_groups)
             and counts["field_positions"] == len(planned_groups) * 4
             and counts["effective_ddk_rows"] + counts["excluded_ddk_rows"]
                 == counts["original_ddk_rows"]
             and counts["reference_tokens"] == len(tokens)
             and all(counts.get("groups_" + r) == len(rows_seen) for r in DDK_GROUP_LABELS)
             and counts["original_ddk_rows"] == source.get("ddk_rows")
             and counts["excluded_ddk_rows"] == source.get("excluded_ddk_rows")
             and counts["reference_tokens"] == source.get("reference_tokens"),
             "Planned group/token population differs from accepted source")
    excluded = plan.get("excluded_source_rows")
    _require(isinstance(excluded, list) and len(excluded) == counts["excluded_ddk_rows"],
             "Missing excluded physical-row records")
    excluded_rows = set()
    for item in excluded:
        _require(isinstance(item, dict)
                 and type(item.get("source_row_number")) is int
                 and type(item.get("legacy_dkkd_id")) is int,
                 "Invalid excluded source row identity")
        row = item["source_row_number"]
        _require(row not in excluded_rows and row not in rows_seen,
                 "Duplicate or reintroduced approved excluded source row")
        excluded_rows.add(row)

    expected: dict[tuple[tuple[str, str, int, str], int], tuple[str, int]] = {}
    token_groups: dict[tuple[str, str, int, str], list[tuple[int, str]]] = defaultdict(list)
    for entry in tokens:
        _require(isinstance(entry, dict) and isinstance(entry.get("values"), dict),
                 "Malformed source token preview")
        source_key = entry.get("source_group_key")
        _require(isinstance(source_key, dict), "Unbound source token key")
        k = _key(source_key.get("source_workbook_sha256"),
                 source_key.get("source_row_number"), source_key.get("source_group"))
        _require(source_key.get("source_sheet_name") == "db.dkkd"
                 and k in planned_groups, "Token points to absent physical source group")
        v = entry["values"]
        i, raw, cid = v.get("token_index"), v.get("raw_token"), v.get("parsed_legacy_certificate_id")
        _require(type(i) is int and i > 0 and isinstance(raw, str)
                 and type(cid) is int and cid > 0 and parse_int(raw) == cid,
                 "Invalid original source ID CC token")
        _require((k, i) not in expected, "Duplicate source token ordinal")
        expected[(k, i)] = (raw, cid)
        token_groups[k].append((i, raw))
    for key, group in planned_groups.items():
        raw = group["id_cc_raw"]
        original = split_idcc_references(raw) if raw.strip() else []
        observed = sorted(token_groups.get(key, []))
        _require(observed == list(enumerate(original, 1)),
                 "Token order/count differs from original physical ID CC cell")
    return planned_groups, expected


def _metadata_health(structure: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for table, required, unique_cols, not_null, expected_checks in (
        (GROUP_TABLE, GROUP_COLUMNS, GROUP_UNIQUE, GROUP_NOT_NULL, GROUP_EXPECTED_CHECK_FIELDS),
        (TOKEN_TABLE, TOKEN_COLUMNS, TOKEN_UNIQUE, TOKEN_NOT_NULL, TOKEN_EXPECTED_CHECK_FIELDS),
    ):
        meta = structure.get(table)
        if not isinstance(meta, dict):
            errors.append("MISSING_STRUCTURE_" + table)
            continue
        if not required.issubset(set(meta.get("columns", []))):
            errors.append("MISSING_COLUMNS_" + table)
        if unique_cols not in {frozenset(x) for x in meta.get("uniques", [])}:
            errors.append("MISSING_UNIQUE_" + table)
        if not not_null.issubset(set(meta.get("not_null", []))):
            errors.append("MISSING_NOT_NULL_" + table)
        check_clauses = " ".join(meta.get("check_clauses", [])).lower()
        if any(name not in check_clauses for name in expected_checks):
            errors.append("MISSING_CHECK_CONSTRAINTS_" + table)
        fks = meta.get("foreign_keys", [])
        if table == GROUP_TABLE and fks:
            errors.append("UNEXPECTED_GROUP_FOREIGN_KEYS")
        if table == TOKEN_TABLE and (
            len(fks) != 1
            or fks[0].get("constrained_columns") != ["source_group_id"]
            or fks[0].get("referred_table") != GROUP_TABLE
            or fks[0].get("referred_columns") != ["id"]
        ):
            errors.append("TOKEN_SOURCE_GROUP_FOREIGN_KEY_MISSING")
    return errors


def assess_rehearsal_preflight(
    plan: dict[str, Any],
    snapshot: dict[str, Any],
    *,
    require_read_only: bool = True,
) -> dict[str, Any]:
    """Compare source-state; require read-only unless a writer explicitly opts out.

    A writer compares under its own exclusive transaction, so it must never
    misrepresent that connection as read-only. Legacy preflight defaults to
    strict read-only and retains its original result contract.
    """
    expected_groups, expected_tokens = validate_sealed_plan(plan)
    _require(isinstance(snapshot, dict)
             and snapshot.get("database_name") == EXPECTED_DB
             and (snapshot.get("transaction_read_only") is True
                  or (not require_read_only
                      and snapshot.get("transaction_read_only") is False)),
             "Wrong target or database transaction not proven read-only (writer mode must be explicit)")
    revisions = snapshot.get("alembic_revisions", [])
    tables = set(snapshot.get("present_tables", []))
    present = tables & {GROUP_TABLE, TOKEN_TABLE}
    structure_errors = _metadata_health(snapshot.get("table_structure", {})) if len(present) == 2 else []
    conflicts: Counter = Counter()
    current_groups = snapshot.get("existing_groups", [])
    current_tokens = snapshot.get("existing_tokens", [])
    _require(isinstance(current_groups, list) and isinstance(current_tokens, list),
             "Missing database source comparison rows")
    if len(present) == 0 and revisions == ["20261008_0022"]:
        state = "SCHEMA_0023_NOT_APPLIED"
    elif len(present) != 2 or revisions != [EXPECTED_REVISION] or structure_errors:
        state = "SCHEMA_OR_REVISION_DRIFT_REVIEW"
    else:
        actual_groups = {}
        for item in current_groups:
            _require(isinstance(item, dict), "Malformed database source group")
            key = _key(item.get("source_workbook_sha256"),
                       item.get("source_row_number"), item.get("source_group"))
            if item.get("source_sheet_name") != "db.dkkd" or key in actual_groups:
                conflicts["duplicate_or_wrong_source_group"] += 1
            actual_groups[key] = item
            matched = expected_groups.get(key)
            if matched is None:
                conflicts["unexpected_source_group"] += 1
            else:
                fieldnames = (
                    "legacy_dkkd_id", "id_cc_excel_column",
                    "certificate_scope_excel_column", "applicable_standard_excel_column",
                    "business_activity_excel_column", "id_cc_raw",
                    "certificate_scope_raw", "applicable_standard_raw",
                    "business_activity_raw", "source_values_sha256",
                )
                if any(item.get(name) != matched[name] for name in fieldnames):
                    conflicts["source_group_values_mismatch"] += 1
                else:
                    values = [item[name] for name in (
                        "id_cc_raw", "certificate_scope_raw",
                        "applicable_standard_raw", "business_activity_raw")]
                    if item.get("source_values_sha256") != _source_value_digest(values):
                        conflicts["source_group_invalid_digest"] += 1
        for key in expected_groups:
            if key not in actual_groups:
                conflicts["planned_source_group_missing"] += 1

        actual_tokens = {}
        for item in current_tokens:
            _require(isinstance(item, dict), "Malformed database source token")
            key = _key(item.get("source_workbook_sha256"),
                       item.get("source_row_number"), item.get("source_group"))
            token_index = item.get("token_index")
            pair = (key, token_index)
            if item.get("source_sheet_name") != "db.dkkd" or pair in actual_tokens:
                conflicts["duplicate_or_wrong_source_token"] += 1
            actual_tokens[pair] = item
            expected = expected_tokens.get(pair)
            if expected is None:
                conflicts["unexpected_source_token"] += 1
            elif (item.get("raw_token"), item.get("parsed_legacy_certificate_id")) != expected:
                conflicts["source_token_values_mismatch"] += 1
        for pair in expected_tokens:
            if pair not in actual_tokens:
                conflicts["planned_source_token_missing"] += 1

        total = snapshot.get("global_counts", {})
        group_total, token_total = total.get(GROUP_TABLE), total.get(TOKEN_TABLE)
        _require(type(group_total) is int and type(token_total) is int
                 and group_total >= len(current_groups) and token_total >= len(current_tokens),
                 "Database table count inconsistent with selected-source rows")
        if group_total > len(current_groups) or token_total > len(current_tokens):
            conflicts["other_workbook_data_present"] += 1

        if group_total == 0 and token_total == 0:
            state = "EMPTY_SCHEMA_READY_FOR_SEPARATE_APPLY_APPROVAL"
        elif not conflicts and len(actual_groups) == len(expected_groups) and len(actual_tokens) == len(expected_tokens):
            state = "SOURCE_PROVENANCE_ALREADY_MATCHES_PLAN"
        else:
            state = "TARGET_DATA_CONFLICT_OR_PARTIAL_REVIEW"

    return {
        "schema": PREFLIGHT_SCHEMA,
        "status": state,
        "approval_status": (
            "READ_ONLY_PREFLIGHT_NO_APPLY_AUTHORIZATION"
            if require_read_only else "INTERNAL_WRITER_SNAPSHOT_COMPARISON"
        ),
        "database_name": EXPECTED_DB,
        "database_transaction_read_only": snapshot.get("transaction_read_only"),
        "alembic_revisions": revisions,
        "required_alembic_revision": EXPECTED_REVISION,
        "present_provenance_tables": sorted(present),
        "schema_errors": structure_errors,
        "planned_counts": {
            "source_groups": len(expected_groups),
            "reference_tokens": len(expected_tokens),
        },
        "observed_counts": snapshot.get("global_counts", {}),
        "conflict_counts": dict(sorted(conflicts.items())),
        "source_workbook_sha256": plan["source_workbook_sha256"],
        "source_payload_sha256": plan["payload_sha256"],
        "db_writes": 0 if require_read_only else None,
        "migration_operations": 0,
        "canonical_certificate_links_created": 0,
        "limitations": (
            [
                "Current DB state observed only at read-only snapshot time",
                "No database revision changed; no table created; no INSERT/UPDATE/DELETE",
                "No UUIDs or canonical Certificate/BusinessEligibilityVersion FK inferred",
                "A ready/identical source-only state is not authority to link or deploy",
                "Excel COM waived by owner, not performed",
            ] if require_read_only else [
                "This is an observation within the importer's write transaction",
                "Actual writes, if any, are owned and verified by the importer",
                "No canonical Certificate/BusinessEligibilityVersion FK inferred",
                "Excel COM waived by owner, not performed",
            ]
        ),
    }


def _table_shape(conn, inspector, table: str) -> dict[str, Any]:
    return {
        "columns": [x["name"] for x in inspector.get_columns(table, schema="public")],
        "not_null": [
            x["name"] for x in inspector.get_columns(table, schema="public")
            if x.get("nullable") is False
        ],
        "check_clauses": [
            str(x.get("sqltext") or "")
            for x in inspector.get_check_constraints(table, schema="public")
        ],
        "uniques": [list(x.get("column_names", []))
                    for x in inspector.get_unique_constraints(table, schema="public")],
        "foreign_keys": [
            {
                "constrained_columns": list(x.get("constrained_columns", [])),
                "referred_table": x.get("referred_table"),
                "referred_columns": list(x.get("referred_columns", [])),
            }
            for x in inspector.get_foreign_keys(table, schema="public")
        ],
    }


def read_rehearsal_snapshot(database_url: str, workbook_sha256: str) -> dict[str, Any]:
    """Read public schema and same-workbook rows; never send a write query."""
    url = make_url(database_url)
    _require(url.get_backend_name() == "postgresql" and url.database == EXPECTED_DB,
             "Database URL must target PostgreSQL gxp_legacy_rehearsal exactly")
    engine = create_engine(
        url, poolclass=NullPool,
        connect_args={"options": "-c default_transaction_read_only=on -c statement_timeout=15000"},
    )
    try:
        with engine.connect() as conn:
            # FIRST application SQL command. Server session is also read-only
            # before connect through startup options, including driver probes.
            conn.exec_driver_sql(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
            )
            confirmed = conn.execute(text(
                "SELECT current_database(), current_setting('transaction_read_only')"
            )).one()
            _require(confirmed[0] == EXPECTED_DB and confirmed[1] == "on",
                     "Connected database or read-only transaction guard failed")
            versions_exist = conn.execute(text(
                "SELECT to_regclass('public.alembic_version') IS NOT NULL"
            )).scalar_one()
            revisions = (
                list(conn.execute(text(
                    "SELECT version_num FROM public.alembic_version ORDER BY version_num"
                )).scalars()) if versions_exist else []
            )
            names = {GROUP_TABLE, TOKEN_TABLE}
            inspector = inspect(conn)
            available = names & set(inspector.get_table_names(schema="public"))
            structure = {name: _table_shape(conn, inspector, name) for name in available}
            counts: dict[str, int] = {}
            groups: list[dict] = []
            tokens: list[dict] = []
            if GROUP_TABLE in available:
                counts[GROUP_TABLE] = conn.execute(text(
                    "SELECT count(*) FROM public.business_eligibility_gxp_source_group"
                )).scalar_one()
                groups = [dict(x) for x in conn.execute(text("""
                    SELECT source_workbook_sha256, source_sheet_name, source_row_number,
                           source_group, legacy_dkkd_id, id_cc_excel_column,
                           certificate_scope_excel_column,
                           applicable_standard_excel_column, business_activity_excel_column,
                           id_cc_raw, certificate_scope_raw, applicable_standard_raw,
                           business_activity_raw, source_values_sha256
                    FROM public.business_eligibility_gxp_source_group
                    WHERE source_workbook_sha256 = :fingerprint
                """), {"fingerprint": workbook_sha256}).mappings()]
            if TOKEN_TABLE in available:
                counts[TOKEN_TABLE] = conn.execute(text(
                    "SELECT count(*) FROM public.business_eligibility_gxp_reference_evidence"
                )).scalar_one()
                if GROUP_TABLE in available:
                    tokens = [dict(x) for x in conn.execute(text("""
                        SELECT g.source_workbook_sha256, g.source_sheet_name,
                               g.source_row_number, g.source_group,
                               t.token_index, t.raw_token,
                               t.parsed_legacy_certificate_id
                        FROM public.business_eligibility_gxp_reference_evidence AS t
                        JOIN public.business_eligibility_gxp_source_group AS g
                          ON t.source_group_id = g.id
                        WHERE g.source_workbook_sha256 = :fingerprint
                    """), {"fingerprint": workbook_sha256}).mappings()]
            conn.rollback()  # Read-only transaction: no persistent effects.
            return {
                "database_name": EXPECTED_DB,
                "transaction_read_only": True,
                "alembic_revisions": revisions,
                "present_tables": sorted(available),
                "table_structure": structure,
                "global_counts": counts,
                "existing_groups": groups,
                "existing_tokens": tokens,
            }
    finally:
        engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-json", type=Path, required=True)
    parser.add_argument("--database-url-env", default="GXP_REHEARSAL_READONLY_DATABASE_URL")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve() == args.plan_json.resolve():
        parser.exit(2, "Preflight blocked: output cannot overwrite source plan\n")
    if args.output.exists():
        parser.exit(2, "Preflight blocked: output already exists\n")
    try:
        original = args.plan_json.read_bytes()
        plan = json.loads(original.decode("utf-8"))
        validate_sealed_plan(plan)
        dsn = os.environ.get(args.database_url_env)
        if not dsn:
            raise MissingPhysicalEvidence(
                "Missing read-only PostgreSQL DSN environment variable"
            )
        snapshot = read_rehearsal_snapshot(dsn, plan["source_workbook_sha256"])
        result = assess_rehearsal_preflight(plan, snapshot)
        result["input_plan_json_sha256"] = sha256(original).hexdigest()
        if args.plan_json.read_bytes() != original:
            raise MissingPhysicalEvidence("Source plan changed during read-only preflight")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as out:
            json.dump(result, out, ensure_ascii=False, indent=2)
            out.write("\n")
    except (MissingPhysicalEvidence, SQLAlchemyError, OSError, ValueError, TypeError, KeyError) as exc:
        # Never print DSNs, credentials or source business contents.
        parser.exit(2, f"Read-only DDK preflight blocked: {type(exc).__name__}\n")
    print(json.dumps({
        "status": result["status"],
        "schema_errors": result["schema_errors"],
        "conflict_counts": result["conflict_counts"],
        "observed_counts": result["observed_counts"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
