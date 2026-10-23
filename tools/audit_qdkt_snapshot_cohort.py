"""Offline, source-guarded QĐKT Case-to-db.ktra cohort audit.

Never connects to PostgreSQL, never loads business-text columns, never authorizes
QĐKT rendering. Input cohort is a read-only export of case_id/legacy ID pairs.
"""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from backend.app.document.inspection_qd_kt_snapshot_case_link_audit import (
    QdKtCaseLegacyId, audit_qdkt_case_dbktra_links_with_header_proof,
    QdKtSnapshotLinkBlocked,
)


class QdKtCohortAuditBlocked(ValueError):
    pass


def _checked_cohort(value: Any) -> tuple[QdKtCaseLegacyId, ...]:
    if not isinstance(value, list):
        raise QdKtCohortAuditBlocked("CASE_COHORT_ARRAY_REQUIRED")
    rows: list[QdKtCaseLegacyId] = []
    for row in value:
        if not isinstance(row, dict) or set(row) != {"case_id", "legacy_inspection_id"}:
            raise QdKtCohortAuditBlocked("CASE_COHORT_EXACT_KEYS_REQUIRED")
        case_id = row["case_id"]
        legacy_id = row["legacy_inspection_id"]
        if not isinstance(case_id, str) or not case_id.strip() or case_id != case_id.strip():
            raise QdKtCohortAuditBlocked("CASE_COHORT_CASE_ID_INVALID")
        if legacy_id is not None and (type(legacy_id) is not int or legacy_id <= 0):
            raise QdKtCohortAuditBlocked("CASE_COHORT_LEGACY_ID_INVALID")
        rows.append(QdKtCaseLegacyId(case_id=case_id, legacy_inspection_id=legacy_id))
    if not rows:
        raise QdKtCohortAuditBlocked("CASE_COHORT_EMPTY")
    if len({r.case_id for r in rows}) != len(rows):
        raise QdKtCohortAuditBlocked("CASE_COHORT_DUPLICATE_CASE_ID")
    return tuple(rows)


def build_qdkt_cohort_report(
    *, snapshot: dict[str, Any], cohort: Any,
    header_row_number: int, source_header_row_attested: bool,
    snapshot_sha256: str, cohort_sha256: str,
) -> dict[str, Any]:
    """Return aggregate-only proof: no names, raw source cells or Case IDs."""
    cases = _checked_cohort(cohort)
    results = audit_qdkt_case_dbktra_links_with_header_proof(
        snapshot=snapshot, cases=cases, header_row_number=header_row_number,
        source_header_row_attested=source_header_row_attested,
    )
    counts = Counter(row.status for row in results)
    if sum(counts.values()) != len(cases):
        raise QdKtCohortAuditBlocked("CASE_COHORT_COUNT_MISMATCH")
    return {
        "schema_version": "qdkt-case-db-ktra-cohort-audit/v1",
        "source_snapshot_sha256": snapshot_sha256,
        "case_cohort_sha256": cohort_sha256,
        "source_workbook_sha256": snapshot["workbook"]["sha256"],
        "source_header_row_number": header_row_number,
        "case_count": len(cases),
        "status_counts": dict(sorted(counts.items())),
        "planning_row_proven": False,
        "qdkt_business_atoms_proven": False,
        "ready_to_render": False,
        "no_case_or_person_identifiers_exported": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--cases-json", type=Path, required=True,
                        help="Read-only exported list of {case_id, legacy_inspection_id}")
    parser.add_argument("--attested-header-row", type=int, required=True)
    parser.add_argument("--confirm-header-provenance", action="store_true",
                        help="Operator independently verified header-row coordinate in original workbook")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    # Explicit flag is not an attestation record; report describes the asserted
    # provenance only, never declares the underlying historical mapping proven.
    if not args.confirm_header_provenance:
        parser.error("header-row provenance confirmation required")
    try:
        snapshot_bytes = args.snapshot.read_bytes()
        cases_bytes = args.cases_json.read_bytes()
        snapshot = json.loads(snapshot_bytes)
        cohort = json.loads(cases_bytes)
        report = build_qdkt_cohort_report(
            snapshot=snapshot, cohort=cohort,
            header_row_number=args.attested_header_row,
            source_header_row_attested=True,
            snapshot_sha256=sha256(snapshot_bytes).hexdigest(),
            cohort_sha256=sha256(cases_bytes).hexdigest(),
        )
    except (OSError, ValueError, TypeError, KeyError, QdKtSnapshotLinkBlocked) as exc:
        parser.error(f"QDKT_SOURCE_AUDIT_BLOCKED: {exc}")
    # Only publish after every source and cohort guard passes.
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
