"""Read-only source integrity audit for legacy Certificate -> Case references.

This module compares only explicit db.cc / db.ktra source keys and contexts.
It does not infer replacements, rewrite source rows, or change runtime link rules.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

from backend.app.domain.phase2_import import (
    normalize_inspection_gxp_type,
    normalize_row,
    parse_int,
    source_row_key,
    source_row_number,
)


def audit_certificate_case_source_links(snapshot: dict[str, list[dict[str, str]]]) -> dict[str, Any]:
    """Classify every db.cc reference using the same normalization as Phase 2.

    A nonblank Case reference to a different Site is never considered valid
    merely because the two Sites share a company or a line code.
    """
    case_rows: dict[int, list[dict[str, str]]] = {}
    for source_row in snapshot["db.ktra"]:
        row = normalize_row(source_row)
        case_legacy_id = parse_int(row.get("ID"))
        if case_legacy_id is not None:
            case_rows.setdefault(case_legacy_id, []).append(row)

    counts: Counter[str] = Counter()
    anomalies: list[dict[str, Any]] = []

    for source_row in snapshot["db.cc"]:
        certificate = normalize_row(source_row)
        case_ref = str(certificate.get("inspection_case_legacy_id_ref") or "").strip()
        certificate_site = parse_int(certificate.get("site_legacy_id_ref"))
        certificate_gxp = certificate.get("certificate_type") or "UNKNOWN"
        case_legacy_id = parse_int(case_ref)
        linked_case_site: int | None = None
        linked_case_gxp: str | None = None

        if not case_ref:
            classification = "ADMINISTRATIVE_NO_CASE_REFERENCE"
        elif case_legacy_id is None:
            classification = "UNPARSEABLE_CASE_REFERENCE"
        elif case_legacy_id not in case_rows:
            classification = "CASE_SOURCE_NOT_FOUND"
        elif len(case_rows[case_legacy_id]) != 1:
            classification = "DUPLICATE_CASE_SOURCE_ID"
        else:
            linked_case = case_rows[case_legacy_id][0]
            linked_case_site = parse_int(linked_case.get("site_legacy_id_ref"))
            raw_case_gxp = str(linked_case.get("inspection_gxp_type") or "").strip()
            linked_case_gxp = normalize_inspection_gxp_type(raw_case_gxp) or raw_case_gxp or "UNKNOWN"
            if certificate_site is None or linked_case_site is None:
                classification = "SITE_CONTEXT_INCOMPLETE"
            else:
                site_mismatch = certificate_site != linked_case_site
                gxp_mismatch = certificate_gxp != linked_case_gxp
                if site_mismatch and gxp_mismatch:
                    classification = "SITE_AND_GXP_MISMATCH"
                elif site_mismatch:
                    classification = "SITE_MISMATCH"
                elif gxp_mismatch:
                    classification = "GXP_MISMATCH"
                else:
                    classification = "EXACT_SOURCE_CONTEXT"

        counts[classification] += 1
        if classification not in {"EXACT_SOURCE_CONTEXT", "ADMINISTRATIVE_NO_CASE_REFERENCE"}:
            certificate_legacy_id = parse_int(certificate.get("ID"))
            anomalies.append({
                "classification": classification,
                "certificate_source_row_key": source_row_key(
                    legacy_row_id=certificate_legacy_id,
                    source_row_number_value=source_row_number(certificate),
                ),
                "certificate_legacy_id": certificate_legacy_id,
                "linked_case_legacy_id": case_legacy_id,
                "raw_case_reference": case_ref,
                "certificate_site_legacy_id": certificate_site,
                "linked_case_site_legacy_id": linked_case_site,
                "certificate_gxp_type": certificate_gxp,
                "linked_case_gxp_type": linked_case_gxp,
            })

    return {
        "schema_version": "certificate-case-source-integrity/v1",
        "source_sheet": "db.cc",
        "total_certificate_source_rows": sum(counts.values()),
        "classification_counts": dict(sorted(counts.items())),
        "anomalies": anomalies,
        "database_mutated": False,
        "source_modified": False,
    }
