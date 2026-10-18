"""Read-only GMP MÃ DC replacement chronology review from a source snapshot."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.app.domain.legacy_gmp_replacement_source_audit import (
    audit_gmp_replacement_sources,
)
from backend.app.domain.phase2_import import load_confirmed_blanked_row_keys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=Path("artifacts/phase3c/legacy_snapshot.json"))
    parser.add_argument("--output", type=Path, help="Optional review-only JSON. No database connection is made.")
    args = parser.parse_args(argv)

    payload = json.loads(args.snapshot.read_text(encoding="utf-8-sig"))
    snapshot = payload.get("sheets", payload)
    excluded = {
        key for sheet, key in load_confirmed_blanked_row_keys() if sheet == "db.cc"
    }
    report = audit_gmp_replacement_sources(
        snapshot, excluded_certificate_row_keys=excluded
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(json.dumps({
        "schema_version": report["schema_version"],
        "group_count": report["group_count"],
        "counts": report["counts"],
        "replacement_authorized": False,
        "database_mutated": False,
        "source_modified": False,
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
