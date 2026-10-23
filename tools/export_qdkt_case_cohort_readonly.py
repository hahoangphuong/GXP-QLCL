"""Guarded read-only rehearsal Case cohort export for offline QĐKT audits.

No DDL, UPDATE, document writes, remote deployment or production DB access.
The operator supplies a PostgreSQL DSN through an environment variable.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url

from backend.app.db.models.phase1 import Case
from tools.audit_qdkt_snapshot_cohort import QdKtCohortAuditBlocked, write_private_report


EXPECTED_DATABASE = "gxp_legacy_rehearsal"


class QdKtRehearsalExportBlocked(ValueError):
    pass


def require_rehearsal_url(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise QdKtRehearsalExportBlocked("DATABASE_URL_MISSING")
    try:
        url = make_url(value)
    except Exception as exc:
        raise QdKtRehearsalExportBlocked("DATABASE_URL_INVALID") from exc
    if not url.drivername.startswith("postgresql") or url.database != EXPECTED_DATABASE:
        raise QdKtRehearsalExportBlocked("NON_REHEARSAL_DATABASE_DENIED")
    return value


def read_case_cohort_readonly(*, database_url: str) -> list[dict[str, object]]:
    """Use a PostgreSQL-enforced read-only transaction, not an ORM write session."""
    value = require_rehearsal_url(database_url)
    engine = create_engine(value, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            with connection.begin():
                connection.exec_driver_sql("SET TRANSACTION READ ONLY")
                rows = connection.execute(
                    select(Case.id, Case.legacy_inspection_id).order_by(Case.id)
                ).all()
        return [
            {"case_id": case_id, "legacy_inspection_id": legacy_id}
            for case_id, legacy_id in rows
        ]
    finally:
        engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url-env", default="QDKT_REHEARSAL_DATABASE_URL")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if not args.database_url_env or not args.database_url_env.isidentifier():
        parser.error("QDKT_DATABASE_ENV_INVALID")
    try:
        cohort = read_case_cohort_readonly(
            database_url=os.environ.get(args.database_url_env, ""),
        )
        if not cohort:
            raise QdKtRehearsalExportBlocked("CASE_COHORT_EMPTY")
        # The writer creates mode 0600 exactly once. Do not echo DSN or Cases.
        write_private_report(output=args.output, report=cohort, inputs=())
    except Exception:
        parser.error("QDKT_REHEARSAL_EXPORT_BLOCKED: database or output validation failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
