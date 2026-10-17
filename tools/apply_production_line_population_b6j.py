"""Explicit guarded B6J writer.  It never reads database URLs implicitly."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.domain.production_line_population_writer_b6j import guarded_apply


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply one sealed B6J ProductionLine plan.")
    parser.add_argument("--database-url", required=True, help="Explicit PostgreSQL URL; never serialized in output.")
    parser.add_argument("--expected-database-name", required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--apply", action="store_true", help="Commit only after all B6J fences pass.")
    parser.add_argument("--allow-rehearsal-dry-run", action="store_true", help="Permit only a rollback dry-run against the exact rehearsal database.")
    parser.add_argument("--allow-rehearsal-apply", action="store_true", help="Permit only the exact sealed rehearsal apply.")
    parser.add_argument("--expected-plan-sha256")
    parser.add_argument("--expected-plan-file-sha256")
    args = parser.parse_args(argv)
    plan_bytes = args.plan.read_bytes()
    # Every execution must match two hashes retained independently at review
    # time. The plan's own digest can otherwise be recomputed after editing.
    if not args.expected_plan_sha256 or not args.expected_plan_file_sha256:
        parser.error("B6J requires independently recorded --expected-plan-sha256 and --expected-plan-file-sha256")
    if args.allow_rehearsal_apply and (not args.apply or args.allow_rehearsal_dry_run):
        parser.error("protected rehearsal apply requires --apply without a dry-run override")
    if sha256(plan_bytes).hexdigest() != args.expected_plan_file_sha256:
        parser.error("expected plan file SHA256 does not match exact plan bytes")
    plan = json.loads(plan_bytes)
    if plan.get("plan_sha256") != args.expected_plan_sha256:
        parser.error("expected semantic plan SHA256 does not match sealed plan")
    engine = create_engine(args.database_url, future=True)
    try:
        with Session(engine) as session:
            result = guarded_apply(session, plan, expected_database_name=args.expected_database_name, apply=args.apply, allow_rehearsal_dry_run=args.allow_rehearsal_dry_run, allow_rehearsal_apply=args.allow_rehearsal_apply)
            if args.apply and not args.allow_rehearsal_apply:
                session.commit()
            else:
                session.rollback()
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
