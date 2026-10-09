"""Export B6H canonical state through one explicit PostgreSQL READ ONLY transaction."""
from __future__ import annotations

import argparse
from hashlib import sha256
from pathlib import Path
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.domain.production_line_canonical_state import canonical_state_digest_pair, export_canonical_state
from backend.app.domain.production_line_population import canonical_artifact_bytes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only B6H canonical-state exporter.")
    parser.add_argument("--database-url", required=True, help="Explicit PostgreSQL URL; never serialized.")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    # Canonical export bytes are source provenance; never replace a previous
    # snapshot even before opening a READ ONLY PostgreSQL connection.
    if args.output.exists() or args.output.is_symlink():
        parser.error("B6H canonical-state output already exists; select a fresh path")
    url = make_url(args.database_url)
    if url.get_backend_name() != "postgresql":
        parser.error("B6H exporter requires PostgreSQL")
    engine = create_engine(args.database_url, future=True)
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                connection.execute(text("SET TRANSACTION READ ONLY"))
                state = export_canonical_state(Session(bind=connection, autoflush=False))
                transaction.rollback()
            except Exception:
                transaction.rollback()
                raise
    finally:
        engine.dispose()
    payload = canonical_artifact_bytes(state)
    semantic_sha256, file_sha256 = canonical_state_digest_pair(state)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with args.output.open("xb") as handle:
            handle.write(payload)
    except FileExistsError:
        parser.error("B6H canonical-state output already exists; select a fresh path")
    print(f"CANONICAL_STATE_SHA256={semantic_sha256}")
    print(f"CANONICAL_STATE_FILE_SHA256={file_sha256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
