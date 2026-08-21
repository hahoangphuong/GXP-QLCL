from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.db.models import Base
from backend.app.db.session import build_engine, session_scope
from backend.app.document.seed_runtime import seed_default_template_metadata


DEFAULT_DATABASE_URL = "sqlite:///artifacts/phase5/template_seed.db"


def _sqlite_path_from_url(database_url: str) -> Path | None:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        return None
    raw_path = database_url[len(prefix) :]
    if not raw_path:
        return None
    return (ROOT / raw_path).resolve() if not Path(raw_path).is_absolute() else Path(raw_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed curated Phase 5 template metadata into a database.")
    parser.add_argument("database_url", nargs="?", default=DEFAULT_DATABASE_URL)
    parser.add_argument(
        "--fresh-sqlite",
        action="store_true",
        help="Delete and recreate the target SQLite file before seeding.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    database_url = args.database_url
    sqlite_path = _sqlite_path_from_url(database_url)
    should_reset_sqlite = args.fresh_sqlite or database_url == DEFAULT_DATABASE_URL
    if should_reset_sqlite and sqlite_path is not None and sqlite_path.exists():
        sqlite_path.unlink()
    engine = build_engine(database_url)
    Base.metadata.create_all(engine)
    with session_scope(database_url) as session:
        summary = seed_default_template_metadata(session)
    print(
        json.dumps(
            {
                "database_url": database_url,
                "fresh_sqlite": bool(should_reset_sqlite and sqlite_path is not None),
                "template_definitions_created": summary.template_definitions_created,
                "template_definitions_updated": summary.template_definitions_updated,
                "template_bindings_created": summary.template_bindings_created,
                "template_bindings_updated": summary.template_bindings_updated,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
