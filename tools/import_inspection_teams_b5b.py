"""Operational entry point for the guarded B5B team importer."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from backend.app.config import load_app_config
from backend.app.db.session import build_session_factory
from backend.app.services.legacy_inspection_team_import import guarded_apply, guarded_preflight


def main() -> int:
    parser = argparse.ArgumentParser(description="Guarded B5B inspection-team importer.")
    parser.add_argument("--source-plan", type=Path, required=True)
    parser.add_argument("--expected-database-name", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    source = args.source_plan.read_bytes()
    config = load_app_config(dict(os.environ))
    with build_session_factory(config.database_url)() as session:
        try:
            result = guarded_preflight(session, source, expected_database_name=args.expected_database_name) if args.dry_run else guarded_apply(session, source, expected_database_name=args.expected_database_name)
            if args.dry_run:
                session.rollback()
            else:
                session.commit()
        except Exception:
            session.rollback()
            raise
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
