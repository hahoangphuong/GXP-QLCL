"""Opt-in, read-only PostgreSQL reconciliation of a prior staging inventory.

Step 1: python -m tools.audit_storage_staging --root inspection > staging.json
Step 2: configure GXP_STORAGE_LINEAGE_READONLY_DATABASE_URL with an authorized
        metadata reader (never a runtime/migration role).
Step 3: python -m tools.reconcile_storage_staging_lineage --inventory-json staging.json

This command never reads binary files, mutates the database, or deletes storage.
No database connection is opened without both an explicit inventory and a
separate, explicitly configured read-only database URL.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from backend.app.storage.staging import RootScanCoverage, StagingAudit, StagingCandidate
from backend.app.storage.staging_lineage import reconcile_staging_lineage, validate_staging_inventory


_ENV_KEY = "GXP_STORAGE_LINEAGE_READONLY_DATABASE_URL"
_MAX_JSON_BYTES = 8 * 1024 * 1024
_MAX_CANDIDATES = 10000


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object key.")
        result[key] = value
    return result


def _parse_inventory(path: Path) -> StagingAudit:
    # Bound the actual read (rather than checking stat then reading an
    # unbounded, potentially replaced file). Reject ambiguous JSON keys.
    with path.open("rb") as fh:
        raw = fh.read(_MAX_JSON_BYTES + 1)
    if len(raw) > _MAX_JSON_BYTES:
        raise ValueError("Audit input exceeds the allowed size.")
    data = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_json_keys)
    required = {
        "candidates", "scanned_directories", "scanned_entries",
        "truncated", "incomplete_reason", "requested_roots", "root_coverage",
    }
    optional = {"failed_root", "failed_relative_path"}
    if not isinstance(data, dict) or not required.issubset(data) or set(data) - required - optional:
        raise ValueError("Invalid staging inventory format.")
    entries = data["candidates"]
    if not isinstance(entries, list) or len(entries) > _MAX_CANDIDATES:
        raise ValueError("Invalid staging candidate list.")
    candidates = []
    for item in entries:
        if not isinstance(item, dict) or set(item) != {"root", "relative_path", "category", "size"}:
            raise ValueError("Invalid staging candidate format.")
        candidates.append(StagingCandidate(**item))
    if not isinstance(data["requested_roots"], list):
        raise ValueError("Invalid staging inventory root scope.")
    if not isinstance(data["root_coverage"], list):
        raise ValueError("Invalid staging root coverage.")
    coverage = []
    for entry in data["root_coverage"]:
        if not isinstance(entry, dict) or set(entry) != {
            "root", "status", "scanned_directories", "scanned_entries",
        }:
            raise ValueError("Invalid staging root coverage record.")
        coverage.append(RootScanCoverage(**entry))
    inventory = StagingAudit(
        root_coverage=tuple(coverage),
        candidates=tuple(candidates),
        requested_roots=tuple(data["requested_roots"]),
        scanned_directories=data["scanned_directories"],
        scanned_entries=data["scanned_entries"],
        truncated=data["truncated"],
        incomplete_reason=data["incomplete_reason"],
        failed_root=data.get("failed_root"),
        failed_relative_path=data.get("failed_relative_path"),
    )
    # Scanner category/filename identity is a trust-boundary contract.
    # This validates structure, not that the file was actually observed.
    validate_staging_inventory(
        inventory, max_candidates=_MAX_CANDIDATES,
        require_scanner_categories=True, require_declared_scope=True,
        require_root_coverage=True,
    )
    return inventory


def _require_metadata_reader(conn) -> None:
    """Reject privileged or writable DB identities, even in a read-only tx.

    Operator policy requires a dedicated reader, not a runtime/migration
    account that happens to use a SELECT-only transaction in this process.
    PostgreSQL computes inherited grants via has_table_privilege.
    """
    row = conn.exec_driver_sql(
        """
        SELECT
            (r.rolsuper OR r.rolcreatedb OR r.rolcreaterole
             OR r.rolreplication OR r.rolbypassrls) AS elevated,
            has_database_privilege(current_database(), 'CREATE') AS db_create,
            has_schema_privilege('public', 'CREATE') AS schema_create,
            has_table_privilege('public.document_version', 'SELECT') AS version_read,
            has_table_privilege('public.template_definition', 'SELECT') AS template_read,
            has_table_privilege('public.storage_binding', 'SELECT') AS binding_read,
            has_table_privilege('public.document_version', 'INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER') AS version_write,
            has_table_privilege('public.template_definition', 'INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER') AS template_write,
            has_table_privilege('public.storage_binding', 'INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER') AS binding_write
        FROM pg_roles AS r WHERE r.rolname = current_user
        """
    ).one()
    elevated, db_create, schema_create, *table_flags = row
    if elevated or db_create or schema_create or table_flags != [
        True, True, True, False, False, False,
    ]:
        raise RuntimeError("A dedicated metadata SELECT-only PostgreSQL role is required.")
    # Checking only the three queried tables is insufficient: a runtime role
    # may have business-table DML elsewhere in the same schema. Reject
    # effective write grants on any user table/view in the active schema.
    any_schema_write = conn.exec_driver_sql(
        """
        SELECT EXISTS (
            SELECT 1
            FROM pg_catalog.pg_class AS c
            JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
              AND c.relkind IN ('r', 'p', 'v', 'f', 'm')
              AND has_table_privilege(
                    c.oid,
                    'INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER'
                  )
        )
        """
    ).scalar_one()
    if any_schema_write:
        raise RuntimeError("A dedicated metadata SELECT-only PostgreSQL role is required.")


def _read_only_reconcile(database_url: str, inventory: StagingAudit):
    # Reject even programmatically supplied malformed inventory before a
    # socket, engine, role or DB session is created.
    validate_staging_inventory(
        inventory, max_candidates=_MAX_CANDIDATES,
        require_declared_scope=True, require_root_coverage=True,
    )
    # PostgreSQL only. Transaction-level read-only is confirmed before
    # any lineage SELECT. A rollback is issued even for successful audits.
    url = make_url(database_url)
    if url.get_backend_name() != "postgresql":
        raise ValueError("Only PostgreSQL read-only reconciliation is supported.")
    # VM runtime locks psycopg3, not psycopg2. An unqualified PostgreSQL URL
    # otherwise makes SQLAlchemy attempt the unavailable psycopg2 driver.
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+psycopg")
    if url.drivername != "postgresql+psycopg":
        raise ValueError("Unsupported PostgreSQL driver for read-only reconciliation.")
    engine = create_engine(url, future=True, connect_args={"connect_timeout": 10})
    try:
        with engine.connect() as conn:
            tx = conn.begin()
            try:
                # A lineage report must reflect one coherent metadata
                # snapshot, even if another transaction commits between
                # the batched SELECTs. Read-only alone defaults to READ
                # COMMITTED and can mix different committed epochs.
                conn.exec_driver_sql(
                    "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
                )
                if conn.exec_driver_sql("SHOW transaction_read_only").scalar_one() != "on":
                    raise RuntimeError("Read-only transaction was not confirmed.")
                if conn.exec_driver_sql("SHOW transaction_isolation").scalar_one() != "repeatable read":
                    raise RuntimeError("Repeatable-read isolation was not confirmed.")
                # Bound the unqualified ORM SELECT names to the migrated
                # application schema, regardless of URL-provided search_path
                # or preexisting temporary tables. Explicit pg_temp last
                # prevents temp-table shadowing of public lineage tables.
                conn.exec_driver_sql(
                    "SET LOCAL search_path = pg_catalog, public, pg_temp"
                )
                _require_metadata_reader(conn)
                with Session(bind=conn, autoflush=False) as session:
                    return reconcile_staging_lineage(
                        session, inventory, max_candidates=_MAX_CANDIDATES,
                    )
            finally:
                tx.rollback()
    finally:
        engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory-json", type=Path, required=True)
    args = parser.parse_args(argv)

    # No implicit fallback to production DATABASE_URL or app runtime roles.
    database_url = os.environ.get(_ENV_KEY, "").strip()
    if not database_url:
        print(json.dumps({"status": "incomplete", "reason": "read_only_database_url_not_configured"}))
        return 3
    try:
        inventory = _parse_inventory(args.inventory_json)
        report = _read_only_reconcile(database_url, inventory)
    except (Exception):
        # Database and filesystem exception strings can contain credentials
        # or private paths; never include them in operator-facing output.
        print(json.dumps({"status": "incomplete", "reason": "lineage_audit_failed"}))
        return 3
    print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
    return 2 if report.input_inventory_truncated else 0


if __name__ == "__main__":
    raise SystemExit(main())
