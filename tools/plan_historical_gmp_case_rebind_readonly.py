"""Generate confidential, non-executable GMP historical Case FK review plan.

Reads an independently pinned original legacy export and the approved GMP
source-origin decision. A checked rehearsal connection executes SELECT only.
Never updates Case/Certificate/Document rows or starts a repair transaction.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from backend.app.domain.historical_gmp_case_rebind_plan import (
    HistoricalGmpRebindBlocked,
    plan_historical_gmp_case_rebind_readonly,
)
from backend.app.domain.legacy_certificate_case_source_audit import (
    audit_certificate_case_source_links,
)
from backend.app.domain.phase2_import import load_confirmed_blanked_row_keys
from tools.apply_ddk_gxp_provenance_rehearsal import checked_rehearsal_url
from tools.audit_certificate_case_site_owners_rehearsal_readonly import (
    EXPECTED_SNAPSHOT_SHA256, EXPECTED_SOURCE_CERTIFICATES,
    compare_source_to_rehearsal,
)
from tools.audit_ddk_gxp_canonical_candidates_readonly import _write_private_json
from tools.env_utils import parse_env_file
from tools.preflight_ddk_gxp_rehearsal import EXPECTED_DB, EXPECTED_REVISION


def _check(condition: bool, reason: str) -> None:
    if not condition:
        raise HistoricalGmpRebindBlocked(reason)


def _enforce_consistent_read_only_snapshot(conn) -> None:
    """Pin one consistent PostgreSQL source/target witness across all SELECTs.

    READ ONLY alone is insufficient under the default READ COMMITTED isolation:
    a concurrent writer can change target rows between witness and plan reads.
    """
    conn.exec_driver_sql(
        "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
    )
    _check(
        conn.execute(text("SHOW transaction_read_only")).scalar_one() == "on"
        and conn.execute(text("SHOW transaction_isolation")).scalar_one()
        == "repeatable read",
        "REHEARSAL_CONSISTENT_READ_ONLY_SNAPSHOT_NOT_VERIFIED",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-env", type=Path, default=Path("/etc/gxp/runtime.env"))
    parser.add_argument(
        "--snapshot", type=Path,
        default=Path("artifacts/phase3c/legacy_snapshot.json"),
    )
    parser.add_argument(
        "--decision", type=Path,
        default=Path("docs/decisions/GMP_376_CASE_380_OWNER_CONFIRMED_SOURCE_20261018.json"),
    )
    parser.add_argument("--private-output", required=True, type=Path)
    args = parser.parse_args(argv)

    try:
        raw = args.snapshot.read_bytes()
        _check(
            sha256(raw).hexdigest() == EXPECTED_SNAPSHOT_SHA256,
            "PINNED_ORIGINAL_SNAPSHOT_CHANGED",
        )
        snapshot_payload = json.loads(raw)
        snapshot = snapshot_payload.get("sheets", snapshot_payload)
        decision = json.loads(args.decision.read_text(encoding="utf-8"))
        excluded = {
            key for sheet, key in load_confirmed_blanked_row_keys()
            if sheet == "db.cc"
        }
        source_report = audit_certificate_case_source_links(
            snapshot, excluded_certificate_row_keys=excluded,
        )
        _check(
            source_report.get("effective_certificate_source_rows") == 1601
            and {item["certificate_legacy_id"] for item in source_report["effective_anomalies"]}
            == EXPECTED_SOURCE_CERTIFICATES,
            "PINNED_ORIGINAL_SOURCE_POPULATION_CHANGED",
        )

        url = checked_rehearsal_url(parse_env_file(args.runtime_env))
        engine = create_engine(
            url, poolclass=NullPool,
            connect_args={
                "options": "-c default_transaction_read_only=on -c statement_timeout=30000",
            },
        )
        try:
            with engine.connect() as conn:
                with conn.begin():
                    _enforce_consistent_read_only_snapshot(conn)
                    _check(
                        conn.execute(text("SELECT current_database()")).scalar_one() == EXPECTED_DB,
                        "REHEARSAL_READ_ONLY_TARGET_NOT_VERIFIED",
                    )
                    revisions = list(conn.execute(
                        text("SELECT version_num FROM public.alembic_version")
                    ).scalars())
                    _check(revisions == [EXPECTED_REVISION], "REHEARSAL_SCHEMA_CHANGED")
                    with Session(bind=conn) as session:
                        witness = compare_source_to_rehearsal(
                            session, source_report,
                            expected_certificate_ids=set(EXPECTED_SOURCE_CERTIFICATES),
                        )
                        witness["snapshot_sha256"] = EXPECTED_SNAPSHOT_SHA256
                        witness["database_transaction_read_only"] = True
                        review = plan_historical_gmp_case_rebind_readonly(
                            session, witness=witness, decision=decision,
                        )
        finally:
            engine.dispose()

        _write_private_json(args.private_output, review)
        print(json.dumps({
            "status": review["status"],
            "schema": review["schema"],
            "expected_business_rows_to_change": review["expected_business_rows_to_change"],
            "database_writes": 0,
            "database_write_authorized": False,
            "private_plan_created": True,
        }, sort_keys=True))
        return 0
    except Exception as exc:
        # Never leak a private database DSN, source scope, UUID or operator ID.
        print("HISTORICAL_GMP_CASE_PLAN_BLOCKED: " + type(exc).__name__, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
