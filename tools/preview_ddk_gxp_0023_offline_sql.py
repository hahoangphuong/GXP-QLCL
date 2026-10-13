"""Render and audit exact Alembic 0022 -> 0023 SQL, without a DB connection.

This is an *offline preview only*. It never invokes an online Alembic
upgrade, psql, a database URL with credentials, or canonical link creation.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import os
from pathlib import Path
import re
import subprocess
import sys

from tools.audit_ddk_idcc_physical import MissingPhysicalEvidence

BASE_REV = "20261008_0022"
TARGET_REV = "20261012_0023"
GROUP = "business_eligibility_gxp_source_group"
REFERENCE = "business_eligibility_gxp_reference_evidence"
# A deliberately non-routable PostgreSQL URL: used ONLY by Alembic --sql to
# choose the PostgreSQL SQL dialect, never to open a network connection.
OFFLINE_DIALECT_URL = "postgresql+psycopg://postgres@127.0.0.1:1/gxp_legacy_rehearsal"
ALLOWED_CREATED_TABLES = frozenset({GROUP, REFERENCE})
ALLOWED_CREATED_INDEXES = frozenset({
    "ix_begxp_group_source_workbook",
    "ix_business_eligibility_gxp_reference_evidence_source_group_id",
})


def audit_offline_ddl(sql: str) -> dict[str, object]:
    """Fail closed when rendered SQL touches unrelated tables or operations."""
    if not isinstance(sql, str) or not sql.strip():
        raise MissingPhysicalEvidence("Empty Alembic offline SQL")
    create_tables = re.findall(
        r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:(?:public\.)?\"?)([a-z_0-9]+)\"?\s*\(",
        sql, flags=re.I,
    )
    create_indexes = re.findall(
        r"\bCREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:\"?)([a-z_0-9]+)\"?\s+ON\b",
        sql, flags=re.I,
    )
    if len(create_tables) != 2 or set(create_tables) != ALLOWED_CREATED_TABLES:
        raise MissingPhysicalEvidence("Offline SQL creates unexpected tables")
    if len(create_indexes) != 2 or set(create_indexes) != ALLOWED_CREATED_INDEXES:
        raise MissingPhysicalEvidence("Offline SQL creates unexpected indexes")
    forbidden = [
        r"\bDROP\s+(?:TABLE|INDEX|SCHEMA|COLUMN)\b",
        r"\bALTER\s+TABLE\b",
        r"\bDELETE\s+FROM\b",
        r"\bINSERT\s+INTO\b",
        r"\bTRUNCATE\b",
        r"\bGRANT\b|\bREVOKE\b",
        r"\bUPDATE\s+(?!\"?(?:public\.)?alembic_version\b)",
    ]
    if any(re.search(pattern, sql, flags=re.I) for pattern in forbidden):
        raise MissingPhysicalEvidence("Offline migration contains disallowed operations")
    revision_updates = re.findall(
        r"\bUPDATE\s+(?:public\.)?\"?alembic_version\"?\s+SET\b",
        sql, flags=re.I,
    )
    if len(revision_updates) != 1:
        raise MissingPhysicalEvidence("Offline SQL must update Alembic revision exactly once")
    if BASE_REV not in sql or TARGET_REV not in sql:
        raise MissingPhysicalEvidence("Offline Alembic revision bounds mismatch")
    return {
        "from_revision": BASE_REV,
        "to_revision": TARGET_REV,
        "created_tables": sorted(ALLOWED_CREATED_TABLES),
        "created_indexes": sorted(ALLOWED_CREATED_INDEXES),
        "sql_sha256": sha256(sql.encode("utf-8")).hexdigest(),
        "status": "OFFLINE_DDL_PREVIEW_ONLY_NO_DB_IO",
    }


def render_offline_ddl(root: Path) -> str:
    """Use Alembic's real migration renderer, with no valid network endpoint."""
    root = root.resolve()
    migration_path = root / "migrations/versions/20261012_0023_ddk_gxp_source_provenance.py"
    if not (root / "alembic.ini").is_file() or not migration_path.is_file():
        raise MissingPhysicalEvidence("Missing owner Alembic 0023 migration at repository root")
    env = os.environ.copy()
    env["DATABASE_URL"] = OFFLINE_DIALECT_URL
    env["DB_MODE"] = "local_postgres"
    # Do not import subprocess shell or pass credentials into command argv.
    command = [
        sys.executable, "-m", "alembic", "upgrade",
        f"{BASE_REV}:{TARGET_REV}", "--sql",
    ]
    process = subprocess.run(
        command, cwd=root, env=env, capture_output=True, text=True,
        timeout=60, check=False,
    )
    if process.returncode != 0:
        # Alembic stderr could reveal environment config details: do not print it.
        raise MissingPhysicalEvidence("Alembic offline SQL render failed")
    audit_offline_ddl(process.stdout)
    return process.stdout


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.exit(2, "Offline preview blocked: output already exists\n")
    try:
        sql = render_offline_ddl(args.repo)
        report = audit_offline_ddl(sql)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as handle:
            handle.write(sql)
    except (MissingPhysicalEvidence, OSError, subprocess.TimeoutExpired) as exc:
        parser.exit(2, f"Offline preview blocked: {type(exc).__name__}\n")
    print(
        f"{report['status']} {report['from_revision']} -> "
        f"{report['to_revision']} sha256={report['sql_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
