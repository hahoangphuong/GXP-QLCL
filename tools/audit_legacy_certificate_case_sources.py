"""Read-only diagnostic for Phase 2 legacy Certificate -> Case source links."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.app.domain.legacy_certificate_case_source_audit import audit_certificate_case_source_links


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=Path("artifacts/phase3c/legacy_snapshot.json"))
    parser.add_argument("--output", type=Path, help="Optional JSON report path (never a database write)")
    parser.add_argument("--strict", action="store_true", help="Return code 2 when any source anomaly remains")
    args = parser.parse_args(argv)
    payload = json.loads(args.snapshot.read_text(encoding="utf-8-sig"))
    snapshot = payload.get("sheets", payload)
    report = audit_certificate_case_source_links(snapshot)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "total_certificate_source_rows": report["total_certificate_source_rows"],
        "classification_counts": report["classification_counts"],
        "anomaly_count": len(report["anomalies"]),
        "database_mutated": False,
    }, ensure_ascii=False, sort_keys=True))
    return 2 if args.strict and report["anomalies"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
