"""Read-only diagnostic for Phase 2 legacy Certificate -> Case source links."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.app.domain.legacy_certificate_case_source_audit import audit_certificate_case_source_links
from backend.app.domain.phase2_import import load_confirmed_blanked_row_keys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=Path("artifacts/phase3c/legacy_snapshot.json"))
    parser.add_argument("--output", type=Path, help="Optional JSON report path (never a database write)")
    parser.add_argument("--strict", action="store_true", help="Return code 2 when any source anomaly remains")
    args = parser.parse_args(argv)
    payload = json.loads(args.snapshot.read_text(encoding="utf-8-sig"))
    snapshot = payload.get("sheets", payload)
    reviewed_keys = {
        key for sheet, key in load_confirmed_blanked_row_keys() if sheet == "db.cc"
    }
    report = audit_certificate_case_source_links(
        snapshot, excluded_certificate_row_keys=reviewed_keys
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "total_certificate_source_rows": report["total_certificate_source_rows"],
        "classification_counts": report["classification_counts"],
        "raw_anomaly_count": len(report["anomalies"]),
        "effective_source_rows": report["effective_certificate_source_rows"],
        "effective_classification_counts": report["effective_classification_counts"],
        "effective_anomaly_count": len(report["effective_anomalies"]),
        "source_identity_anomaly_count": len(report["source_identity_anomalies"]),
        "source_parent_check_available": report["source_parent_check_available"],
        "source_parent_anomaly_count": len(report["source_parent_anomalies"]),
        "effective_parent_anomaly_count": len(report["effective_parent_anomalies"]),
        "database_mutated": False,
    }, ensure_ascii=False, sort_keys=True))
    return 2 if args.strict and (
        report["effective_anomalies"]
        or report["source_identity_anomalies"]
        or report["effective_parent_anomalies"]
    ) else 0


if __name__ == "__main__":
    raise SystemExit(main())
