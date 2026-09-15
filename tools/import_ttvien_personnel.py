"""Operational entry point for the guarded TTviên personnel importer."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from backend.app.config import load_app_config
from backend.app.db.session import build_session_factory
from backend.app.services.legacy_ttvien_personnel_import import guarded_apply, guarded_preflight


def main() -> int:
    parser = argparse.ArgumentParser(description="Guarded TTviên personnel importer.")
    parser.add_argument("--source-plan", type=Path, required=True)
    parser.add_argument("--expected-database-name", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    source_plan_bytes = args.source_plan.read_bytes()
    database_url = load_app_config(dict(os.environ)).database_url
    factory = build_session_factory(database_url)
    with factory() as session:
        try:
            if args.dry_run:
                result = guarded_preflight(session, source_plan_bytes, expected_database_name=args.expected_database_name)
                session.rollback()
            else:
                result = guarded_apply(session, source_plan_bytes, expected_database_name=args.expected_database_name)
                session.commit()
        except Exception:
            session.rollback()
            raise
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
