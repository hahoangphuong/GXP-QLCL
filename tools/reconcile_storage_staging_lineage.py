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

from backend.app.storage.staging import StagingAudit, StagingCandidate
from backend.app.storage.staging_lineage import reconcile_staging_lineage


_ENV_KEY = "GXP_STORAGE_LINEAGE_READONLY_DATABASE_URL"
_MAX_JSON_BYTES = 8 * 1024 * 1024
_MAX_CANDIDATES = 10000


def _parse_inventory(path: Path) -> StagingAudit:
    if path.stat().st_size > _MAX_JSON_BYTES:
        raise ValueError("Audit input exceeds the allowed size.")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("candidates"), list):
        raise ValueError("Invalid inventory format.")
    if len(data["candidates"]) > _MAX_CANDIDATES:
        raise ValueError("Audit candidate limit exceeded.")
    candidates = tuple(
        StagingCandidate(
            root=item["root"],
            relative_path=item["relative_path"],
            category=item["category"],
            size=item["size"],
        )
        for item in data["candidates"]
    )
    return StagingAudit(
        candidates=candidates,
        scanned_directories=data["scanned_directories"],
        scanned_entries=data["scanned_entries"],
        truncated=data["truncated"],
        incomplete_reason=data.get("incomplete_reason"),
        failed_root=data.get("failed_root"),
        failed_relative_path=data.get("failed_relative_path"),
    )


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
            has_schema_privilege(current_schema(), 'CREATE') AS schema_create,
            has_table_privilege('document_version', 'SELECT') AS version_read,
            has_table_privilege('template_definition', 'SELECT') AS template_read,
            has_table_privilege('storage_binding', 'SELECT') AS binding_read,
            has_table_privilege('document_version', 'INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER') AS version_write,
            has_table_privilege('template_definition', 'INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER') AS template_write,
            has_table_privilege('storage_binding', 'INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER') AS binding_write
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
            WHERE n.nspname = current_schema()
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
                conn.exec_driver_sql("SET TRANSACTION READ ONLY")
                if conn.exec_driver_sql("SHOW transaction_read_only").scalar_one() != "on":
                    raise RuntimeError("Read-only transaction was not confirmed.")
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
