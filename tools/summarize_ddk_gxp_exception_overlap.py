"""Aggregate overlap analysis of an existing private DDK GxP exception dossier.

Reads a local JSON only. No database, network, files written or approvals.
Never prints source IDs, row/Case/Certificate UUIDs, or original source text.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from typing import Any

from tools.ddk_gxp_exception_dossier import DOSSIER_SCHEMA


class OverlapAuditBlocked(ValueError):
    """Refuse a partial, invalid or promoted source dossier."""


def _require(ok: bool, reason: str) -> None:
    if not ok:
        raise OverlapAuditBlocked(reason)


def summarize_dossier(dossier: dict[str, Any]) -> dict[str, Any]:
    _require(
        isinstance(dossier, dict)
        and dossier.get("schema") == DOSSIER_SCHEMA
        and dossier.get("status") == "READ_ONLY_EXCEPTION_EVIDENCE_NOT_APPROVED"
        and dossier.get("approval_status") == "NOT_APPROVED"
        and dossier.get("database_writes") == 0
        and dossier.get("canonical_links_created") == 0,
        "Not an unapproved, read-only exception dossier",
    )
    total = dossier.get("source_tokens_checked")
    rows = dossier.get("exception_token_details")
    company = dossier.get("ddk_company_exception_details")
    repeated = dossier.get("repeated_candidate_id_details")
    _require(type(total) is int and total > 0
             and isinstance(rows, list) and len(rows) <= total
             and isinstance(company, list) and isinstance(repeated, list),
             "Missing source rows or invalid cardinalities")
    counted: Counter[str] = Counter()
    source_refs: set[str] = set()
    cross_ddks: set[int] = set()
    case_ddks: set[int] = set()
    both = cross_only = case_only = case_at_ddk = 0
    cross_without_case = versionless = zero_scopes = null_lifecycle = 0
    for item in rows:
        _require(isinstance(item, dict)
                 and item.get("link_approval") == "NOT_APPROVED"
                 and item.get("review_status") == "REQUIRES_INDEPENDENT_ADJUDICATION",
                 "Unexpected approval status on candidate")
        ref = item.get("source_reference_id")
        flags = item.get("flags")
        _require(isinstance(ref, str) and ref and ref not in source_refs
                 and isinstance(flags, list) and len(flags) == len(set(flags))
                 and all(isinstance(flag, str) for flag in flags),
                 "Duplicate reference UUID or invalid flags")
        source_refs.add(ref)
        fs = set(flags)
        counted.update(fs)
        cross = "CERTIFICATE_SITE_DIFFERENT" in fs
        case = "CERTIFICATE_CASE_SITE_DIFFERENT" in fs
        if cross:
            cross_ddks.add(item["legacy_dkkd_id"])
        if case:
            case_ddks.add(item["legacy_dkkd_id"])
            case_at_ddk += item.get("case_site_id") == item.get("ddk_site_id")
        if cross and case:
            both += 1
        elif cross:
            cross_only += 1
        elif case:
            case_only += 1
        if cross and item.get("certificate_case_id") is None:
            cross_without_case += 1
        if cross or case:
            versions = item.get("certificate_versions")
            _require(isinstance(versions, list), "Missing CertificateVersion evidence")
            versionless += not bool(versions)
            if versions:
                zero_scopes += not any(v.get("scope_evidence") for v in versions)
                null_lifecycle += all(v.get("lifecycle_state") is None for v in versions)
    cross_total = both + cross_only
    case_total = both + case_only
    _require(cross_total == dossier.get("cross_site_occurrences")
             and case_total == dossier.get("other_case_site_or_type_observations", {}).get(
                 "CERTIFICATE_CASE_SITE_DIFFERENT"),
             "Mismatch with parent exception counts")
    company_ids = set()
    for item in company:
        _require(isinstance(item, dict) and item.get("link_approval") == "NOT_APPROVED"
                 and type(item.get("legacy_dkkd_id")) is int,
                 "Malformed DDK Company exception")
        company_ids.add(item["legacy_dkkd_id"])
    _require(len(company_ids) == len(company) == dossier.get("ddk_site_company_mismatches"),
             "DDK Company mismatch cardinality changed")

    legacy_ids: set[int] = set()
    repeated_extra = repeated_in_cell = repeated_multi_ddk = 0
    for item in repeated:
        _require(isinstance(item, dict) and item.get("link_approval") == "NOT_APPROVED",
                 "Unexpected repeated source approval")
        source_id = item.get("parsed_legacy_certificate_id")
        observations = item.get("observations")
        _require(type(source_id) is int and source_id > 0 and source_id not in legacy_ids
                 and isinstance(observations, list) and len(observations) >= 2
                 and len(observations) == item.get("occurrence_count"),
                 "Malformed repeated ID/occurrences")
        legacy_ids.add(source_id)
        observed_keys = set()
        cells: Counter[tuple] = Counter()
        ddks = set()
        for position in observations:
            _require(isinstance(position, dict)
                     and position.get("parsed_legacy_certificate_id") == source_id
                     and isinstance(position.get("source_reference_id"), str),
                     "Malformed repeated reference position")
            ref = position["source_reference_id"]
            _require(ref not in observed_keys, "Duplicate source token in repeated ID")
            observed_keys.add(ref)
            ddks.add(position["legacy_dkkd_id"])
            cells[(position["legacy_dkkd_id"], position["source_row_number"],
                   position["source_group"], position["id_cc_excel_column"])] += 1
        _require(len(ddks) == item.get("distinct_source_ddk_count")
                 and (len(ddks) > 1) == item.get("observed_in_multiple_ddk"),
                 "DDK distinct count differs from repeated evidence")
        repeated_multi_ddk += len(ddks) > 1
        repeated_in_cell += sum(n - 1 for n in cells.values() if n > 1)
        repeated_extra += len(observations) - 1
    _require(len(legacy_ids) == dossier.get("candidate_repeated_id_count")
             and repeated_extra == dossier.get("repeated_candidate_extra_occurrences")
             and repeated_in_cell == dossier.get("within_one_source_cell_repeat_extras")
             and repeated_multi_ddk == dossier.get("candidate_ids_observed_in_multiple_ddk")
             and total == dossier.get("distinct_observed_certificate_legacy_ids") + repeated_extra,
             "Source reference cardinality conservation failed")
    return {
        "schema": "GXP_DDK_EXCEPTION_OVERLAP_AGGREGATE_V1",
        "status": "AGGREGATE_READ_ONLY_NOT_APPROVED",
        "source_tokens_checked": total,
        "cross_site_occurrences": cross_total,
        "case_site_mismatch_occurrences": case_total,
        "cross_site_and_case_site_overlap": both,
        "cross_site_only": cross_only,
        "case_site_only": case_only,
        "case_site_equals_ddk_site_when_case_differs_from_certificate": case_at_ddk,
        "cross_site_without_case_fk": cross_without_case,
        "distinct_ddk_with_cross_site_tokens": len(cross_ddks),
        "distinct_ddk_with_case_site_discrepancies": len(case_ddks),
        "distinct_ddk_with_both_discrepancies": len(cross_ddks & case_ddks),
        "ddk_company_mismatch_count": len(company_ids),
        "company_mismatch_intersects_cross_site_ddk": len(company_ids & cross_ddks),
        "company_mismatch_intersects_case_site_ddk": len(company_ids & case_ddks),
        "other_exception_token_rows": len(rows) - (both + cross_only + case_only),
        "flag_counts": dict(sorted(counted.items())),
        "site_discrepancy_token_rows_without_versions": versionless,
        "site_discrepancy_token_rows_with_no_scopes": zero_scopes,
        "site_discrepancy_token_rows_only_null_lifecycle": null_lifecycle,
        "repeated_id_count": len(legacy_ids),
        "repeated_extra_occurrences": repeated_extra,
        "repeated_within_one_cell_extras": repeated_in_cell,
        "repeated_id_multi_ddk_count": repeated_multi_ddk,
        "recorded_canonical_link_rows_before": dossier.get("recorded_canonical_link_rows_before"),
        "canonical_links_created": 0,
        "database_writes": 0,
        "approval_status": "NOT_APPROVED",
        "limitations": [
            "Token-level overlap, not certificate approval, scope coverage or grant",
            "Counts are token occurrences, not distinct Certificate/Case identities",
            "Stored CertificateVersion scope and lifecycle are not legal evidence of Site coverage",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dossier-json", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = summarize_dossier(json.loads(args.dossier_json.read_text(encoding="utf-8")))
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print("DDK_EXCEPTION_OVERLAP_BLOCKED: " + type(exc).__name__, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
