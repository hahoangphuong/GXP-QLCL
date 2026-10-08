"""Build B6C certificate-linkage evidence; optional database mode is read-only."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from backend.app.db.models.phase1 import Case, Certificate, Site
from backend.app.domain.legacy_certificate_linkage import (
    build_canonical_certificate_linkage_comparison,
    build_certificate_linkage_source_plan,
)
from tools.reconcile_db_ktra_repeatable_v2 import REHEARSAL_DATABASE, REQUIRED_REVISION


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "artifacts" / "phase3c" / "legacy_snapshot_v2.json"
OUTPUT_DIR = ROOT / "artifacts" / "phase3c"


def _load_snapshot(path: Path) -> tuple[dict[str, Any], str]:
    payload = path.read_bytes()
    return json.loads(payload), sha256(payload).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.write_bytes((json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8"))


def _validate_database_url(value: str) -> None:
    url = make_url(value)
    if url.get_backend_name() != "postgresql" or url.database != REHEARSAL_DATABASE:
        raise ValueError("B6C comparison requires the exact rehearsal PostgreSQL database")


def compare_rehearsal_read_only(database_url: str, source_plan: dict[str, Any]) -> dict[str, Any]:
    """Read canonical certificate/case rows inside a verified read-only transaction."""
    _validate_database_url(database_url)
    engine = create_engine(database_url, future=True)
    try:
        with Session(engine) as session:
            transaction = session.begin()
            try:
                session.execute(text("SET TRANSACTION READ ONLY"))
                if session.execute(text("SHOW transaction_read_only")).scalar_one() != "on":
                    raise ValueError("B6C comparison transaction is not read-only")
                if session.execute(text("SELECT current_database()")).scalar_one() != REHEARSAL_DATABASE:
                    raise ValueError("B6C comparison connected to an unexpected database")
                if session.execute(text("SELECT version_num FROM alembic_version")).scalar_one() != REQUIRED_REVISION:
                    raise ValueError("B6C comparison requires the current exact Alembic revision")
                cases = [{"id": row.id, "legacy_inspection_id": row.legacy_inspection_id, "site_id": row.site_id, "gxp_type": row.gxp_type} for row in session.scalars(select(Case))]
                sites = [{"id": row.id, "legacy_site_id": row.legacy_site_id} for row in session.scalars(select(Site))]
                certificates = [{"id": row.id, "legacy_certificate_id": row.legacy_certificate_id, "case_id": row.case_id, "site_id": row.site_id, "certificate_type": row.certificate_type} for row in session.scalars(select(Certificate))]
                comparison = build_canonical_certificate_linkage_comparison(source_plan, cases=cases, sites=sites, certificates=certificates)
                return {"provenance": {"database": REHEARSAL_DATABASE, "alembic_revision": REQUIRED_REVISION, "transaction_read_only": True, "database_mutated": False}, **comparison}
            finally:
                transaction.rollback()
    finally:
        engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only B6C legacy certificate linkage discovery.")
    parser.add_argument("--snapshot", type=Path, default=SNAPSHOT)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--database-url")
    args = parser.parse_args(argv)
    snapshot, snapshot_sha256 = _load_snapshot(args.snapshot.resolve())
    source = build_certificate_linkage_source_plan(snapshot, snapshot_sha256=snapshot_sha256)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(args.output_dir / "b6c_certificate_linkage_source_morphology.json", source["source_morphology"])
    _write_json(args.output_dir / "b6c_certificate_linkage_cross_source.json", source)
    source_blocked = [
        item for item in source["records"]
        if item["classification"] != "EXACT_SOURCE_MATCH" or item["duplicate_source_certificate_reference"]
    ]
    _write_json(args.output_dir / "b6c_certificate_linkage_blocked.json", {"records": source_blocked})
    summary: dict[str, Any] = {
        "source": source["source_morphology"],
        "cross_source": source["cross_source_classification_counts"],
        "blocked_source_record_count": len(source_blocked),
        "rehearsal_comparison": "NOT_RUN",
    }
    if args.database_url:
        comparison = compare_rehearsal_read_only(args.database_url, source)
        _write_json(args.output_dir / "b6c_certificate_linkage_rehearsal_comparison.json", comparison)
        _write_json(args.output_dir / "b6c_certificate_linkage_rehearsal_blocked.json", {"records": [item for item in comparison["records"] if item["classification"] != "EXACT_MATCH"]})
        summary["rehearsal_comparison"] = comparison["classification_counts"]
        summary["writability"] = comparison["writability_counts"]
    _write_json(args.output_dir / "b6c_certificate_linkage_summary.json", summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
