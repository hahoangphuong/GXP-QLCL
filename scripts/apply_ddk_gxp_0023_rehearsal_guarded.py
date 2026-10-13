"""Rehearsal-only guarded application of a *reviewed* Alembic 0023 SQL artifact.

Uses Python 3 stdlib and PostgreSQL psql. Default is NO-WRITE preflight.
Applying schema is explicit, separately authorized and atomic. This tool
never inserts provenance, creates canonical links, or touches production DB.

Example (review only):
  python3 apply_ddk_gxp_0023_rehearsal_guarded.py \
    --sql-file /path/to/GXP_DDK_0023_OFFLINE_POSTGRESQL_REVIEW.sql

Application requires both --apply and --confirm-target gxp_legacy_rehearsal.
The reviewed SQL file must match the hard-pinned SHA-256 exactly.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import subprocess
import sys

EXPECTED_SHA256 = "0aafa71accd6795e7e2e89c83985b63a4490463cbd7f3ee6f4aeca358fee561a"
EXPECTED_DB = "gxp_legacy_rehearsal"
FROM_REV = "20261008_0022"
TO_REV = "20261012_0023"
GROUP = "business_eligibility_gxp_source_group"
REFERENCE = "business_eligibility_gxp_reference_evidence"
INDEX_NAMES = {
    "ix_begxp_group_source_workbook",
    "ix_business_eligibility_gxp_reference_evidence_source_group_id",
}


class GuardFailure(Exception):
    pass


def verify_reviewed_sql(raw: bytes) -> str:
    digest = hashlib.sha256(raw).hexdigest()
    if digest != EXPECTED_SHA256:
        raise GuardFailure("SQL SHA-256 differs from the reviewed Alembic artifact")
    try:
        content = raw.decode("utf-8")
    except UnicodeError as exc:
        raise GuardFailure("SQL is not UTF-8") from exc
    trimmed = content.strip()
    if not re.fullmatch(r"BEGIN\s*;[\s\S]*?COMMIT\s*;", trimmed, re.I):
        raise GuardFailure("Expected one BEGIN/COMMIT SQL artifact")
    body = re.sub(r"\ABEGIN\s*;", "", trimmed, count=1, flags=re.I)
    body = re.sub(r"COMMIT\s*;\Z", "", body, count=1, flags=re.I).strip()
    tables = re.findall(r"\bCREATE\s+TABLE\s+([a-z_][a-z_0-9]*)\s*\(", body, re.I)
    indexes = re.findall(r"\bCREATE\s+INDEX\s+([a-z_][a-z_0-9]*)\s+ON\s+", body, re.I)
    if len(tables) != 2 or set(tables) != {GROUP, REFERENCE}:
        raise GuardFailure("Unexpected CREATE TABLE operations")
    if len(indexes) != 2 or set(indexes) != INDEX_NAMES:
        raise GuardFailure("Unexpected CREATE INDEX operations")
    update = re.findall(
        r"UPDATE\s+alembic_version\s+SET\s+version_num\s*=\s*'20261012_0023'"
        r"\s+WHERE\s+alembic_version\.version_num\s*=\s*'20261008_0022'\s*;",
        body, re.I,
    )
    if len(update) != 1:
        raise GuardFailure("Expected one exact Alembic revision UPDATE")
    return body


def build_guarded_transaction(body: str) -> str:
    """Return one server-atomic transaction, not nested Alembic BEGIN/COMMIT."""
    return f"""\\set ON_ERROR_STOP on
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE READ WRITE;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';
SET LOCAL search_path = public, pg_catalog;
DO $gxp_ddk_0023_before$
DECLARE
  actual_revision text;
  revision_count integer;
BEGIN
  IF current_database() <> '{EXPECTED_DB}' THEN
    RAISE EXCEPTION 'Wrong DDK rehearsal database';
  END IF;
  IF current_setting('transaction_isolation') <> 'serializable'
     OR current_setting('transaction_read_only') <> 'off' THEN
    RAISE EXCEPTION 'Serializable read-write transaction required';
  END IF;
  IF to_regclass('public.alembic_version') IS NULL THEN
    RAISE EXCEPTION 'Missing Alembic version table';
  END IF;
  -- LOCK serializes this migration with other revision writers.
  LOCK TABLE public.alembic_version IN ACCESS EXCLUSIVE MODE;
  SELECT count(*), min(version_num) INTO revision_count, actual_revision
  FROM public.alembic_version;
  IF revision_count <> 1 OR actual_revision <> '{FROM_REV}' THEN
    RAISE EXCEPTION 'Unexpected Alembic starting revision';
  END IF;
  IF to_regclass('public.{GROUP}') IS NOT NULL
     OR to_regclass('public.{REFERENCE}') IS NOT NULL THEN
    RAISE EXCEPTION 'DDK GxP provenance tables already exist';
  END IF;
END
$gxp_ddk_0023_before$;

-- The following statements come verbatim from the exact reviewed Alembic SQL,
-- without its own BEGIN/COMMIT wrappers. The outer transaction owns rollback.
{body}

DO $gxp_ddk_0023_after$
DECLARE
  actual_revision text;
  revision_count integer;
  group_count bigint;
  token_count bigint;
BEGIN
  SELECT count(*), min(version_num) INTO revision_count, actual_revision
  FROM public.alembic_version;
  IF revision_count <> 1 OR actual_revision <> '{TO_REV}' THEN
    RAISE EXCEPTION 'Alembic revision did not transition to 0023';
  END IF;
  IF to_regclass('public.{GROUP}') IS NULL
     OR to_regclass('public.{REFERENCE}') IS NULL THEN
    RAISE EXCEPTION 'Expected source-only provenance tables were not created';
  END IF;
  SELECT count(*) INTO group_count FROM public.{GROUP};
  SELECT count(*) INTO token_count FROM public.{REFERENCE};
  IF group_count <> 0 OR token_count <> 0 THEN
    RAISE EXCEPTION 'New source-only provenance tables are unexpectedly populated';
  END IF;
END
$gxp_ddk_0023_after$;
COMMIT;
"""


def require_gxp_web_inactive() -> None:
    """Block a schema-head change while the managed VM backend may use its DB.

    This local systemd check is necessary but not sufficient: it cannot prove
    that other processes or external clients are disconnected. An authorized
    maintenance/deploy plan and independent database preflight are still required.
    """
    completed = subprocess.run(
        [
            "systemctl", "show", "gxp-web",
            "--property=LoadState", "--property=ActiveState",
            "--property=MainPID", "--no-pager",
        ],
        capture_output=True, text=True, check=False, timeout=8,
    )
    if completed.returncode != 0:
        raise GuardFailure("Cannot verify gxp-web shutdown")
    fields: dict[str, str] = {}
    for line in completed.stdout.splitlines():
        name, separator, value = line.partition("=")
        if not separator or name in fields:
            raise GuardFailure("Invalid gxp-web systemd state")
        fields[name] = value
    if fields != {"LoadState": "loaded", "ActiveState": "inactive", "MainPID": "0"}:
        raise GuardFailure("gxp-web must be inactive before schema migration")


def apply_transaction(sql: str) -> None:
    require_gxp_web_inactive()
    # The only subprocess capable of contacting DB. No shell, no env database
    # fallback, explicit database and non-interactive privilege escalation.
    command = [
        "sudo", "-n", "-u", "postgres", "psql", "-X",
        "-v", "ON_ERROR_STOP=1", "-h", "/var/run/postgresql",
        "-U", "postgres", "-d", EXPECTED_DB,
    ]
    completed = subprocess.run(
        command, input=sql, text=True, capture_output=True,
        check=False, timeout=90,
    )
    if completed.returncode != 0:
        # PostgreSQL error message can contain site environment details;
        # keep all sensitive output private instead of re-emitting it.
        raise GuardFailure(f"PostgreSQL guarded transaction aborted, exit={completed.returncode}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sql-file", required=True, type=Path)
    parser.add_argument("--apply", action="store_true", help="Explicitly execute schema-only upgrade")
    parser.add_argument("--confirm-target", help="Required only with --apply")
    args = parser.parse_args(argv)
    try:
        raw = args.sql_file.read_bytes()
        body = verify_reviewed_sql(raw)
        if args.apply:
            if args.confirm_target != EXPECTED_DB:
                raise GuardFailure("--apply requires --confirm-target gxp_legacy_rehearsal")
            guarded = build_guarded_transaction(body)
            # Check against a concurrent file replacement immediately before I/O.
            if args.sql_file.read_bytes() != raw:
                raise GuardFailure("SQL source changed since checksum validation")
            apply_transaction(guarded)
            print("DDK_PROVENANCE_SCHEMA_0023_COMMITTED; provenance rows remain 0")
        else:
            if args.confirm_target:
                raise GuardFailure("--confirm-target is valid only with --apply")
            print("NO_WRITE_REVIEW_ONLY: SQL fingerprint and DDL allowlist PASS")
        print(f"reviewed_sql_sha256={EXPECTED_SHA256}")
    except (GuardFailure, OSError, subprocess.TimeoutExpired) as exc:
        print(f"DDK schema gate BLOCKED: {type(exc).__name__}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
