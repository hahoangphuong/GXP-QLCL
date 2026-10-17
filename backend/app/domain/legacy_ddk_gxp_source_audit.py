"""Independent read-only audit of legacy ĐĐK/GxP source references.

Never projects reverse references into canonical BusinessEligibilityCertificateLink
rows. A source reference is review evidence only, not linkage approval.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

from backend.app.domain.phase2_import import normalize_row, parse_int, source_row_key, source_row_number


def _identity(sheet: str, row: dict[str, str]) -> tuple[str, str]:
    source_key = source_row_key(
        legacy_row_id=parse_int(row.get("ID")),
        source_row_number_value=source_row_number(row),
    )
    return sheet, source_key or "row:unknown"


def audit_ddk_gxp_source_links(
    snapshot: dict[str, list[dict[str, str]]],
    *,
    confirmed_blanked_row_keys: set[tuple[str, str]],
) -> dict[str, Any]:
    """Classify both source-reference directions without changing import semantics.

    The legacy importer reads db.dkkd.ID CC to materialize a version-specific
    GxP basis. db.cc.ID DDK is a separate, reverse source reference whose
    regulatory ownership has not been adjudicated. Never infer a link from it.
    """
    ddk_by_id: dict[int, dict[str, str]] = {}
    for source in snapshot["db.dkkd"]:
        row = normalize_row(source)
        legacy_id = parse_int(row.get("ID"))
        if legacy_id is not None:
            ddk_by_id[legacy_id] = row

    counts: Counter[str] = Counter()
    cross_site_candidates: list[dict[str, Any]] = []
    excluded_confirmed_blanked: list[dict[str, Any]] = []
    missing_targets: list[dict[str, Any]] = []
    unknown_sites: list[dict[str, Any]] = []
    company_mismatch_candidates: list[dict[str, Any]] = []
    effective_ddk_ids: set[int] = set()

    for source in snapshot["db.dkkd"]:
        row = normalize_row(source)
        raw_forward_ref = str(row.get("linked_certificate_ids") or "").strip()
        # This is the exact forward field consumed by Phase-2 import.
        if raw_forward_ref:
            counts["forward_nonblank_ddk_id_cc"] += 1

    for source in snapshot["db.cc"]:
        row = normalize_row(source)
        counts["certificate_rows"] += 1
        raw_ref = str(row.get("ID DDK") or "").strip()
        if not raw_ref:
            continue
        counts["reverse_nonblank_cert_id_ddk"] += 1
        target_id = parse_int(raw_ref)
        if target_id is None:
            counts["reverse_nonliteral"] += 1
            if raw_ref == "-":
                counts["reverse_placeholder"] += 1
            else:
                counts["reverse_other_nonliteral"] += 1
            continue
        counts["reverse_literal"] += 1
        origin_id = parse_int(row.get("ID"))
        target_row = ddk_by_id.get(target_id)
        origin_identity = _identity("db.cc", row)
        record = {
            "legacy_certificate_id": origin_id,
            "legacy_ddk_id": target_id,
            "certificate_source_key": origin_identity[1],
        }
        if target_row is None:
            counts["reverse_missing_target"] += 1
            missing_targets.append(record)
            continue
        target_identity = _identity("db.dkkd", target_row)
        if origin_identity in confirmed_blanked_row_keys or target_identity in confirmed_blanked_row_keys:
            counts["reverse_excluded_confirmed_blanked"] += 1
            excluded_confirmed_blanked.append({
                **record,
                "certificate_blanked": origin_identity in confirmed_blanked_row_keys,
                "ddk_blanked": target_identity in confirmed_blanked_row_keys,
            })
            continue

        counts["reverse_effective_candidates"] += 1
        effective_ddk_ids.add(target_id)
        cert_site = parse_int(row.get("site_legacy_id_ref"))
        ddk_site = parse_int(target_row.get("site_legacy_id_ref"))
        cert_company = parse_int(row.get("company_legacy_id_ref"))
        ddk_company = parse_int(target_row.get("company_legacy_id_ref"))
        evidence = {
            **record,
            "certificate_site_legacy_id": cert_site,
            "ddk_site_legacy_id": ddk_site,
            "certificate_company_legacy_id": cert_company,
            "ddk_company_legacy_id": ddk_company,
        }
        if cert_site is None or ddk_site is None:
            counts["reverse_missing_site_value"] += 1
            unknown_sites.append(evidence)
        elif cert_site != ddk_site:
            counts["reverse_cross_site"] += 1
            cross_site_candidates.append(evidence)
        else:
            counts["reverse_same_site"] += 1
        if cert_company is not None and ddk_company is not None and cert_company != ddk_company:
            counts["reverse_company_mismatch"] += 1
            company_mismatch_candidates.append(evidence)

    summary = {
        "ddk_source_rows": len(snapshot["db.dkkd"]),
        "certificate_source_rows": counts["certificate_rows"],
        "forward_nonblank_ddk_id_cc": counts["forward_nonblank_ddk_id_cc"],
        "reverse_nonblank_cert_id_ddk": counts["reverse_nonblank_cert_id_ddk"],
        "reverse_literal": counts["reverse_literal"],
        "reverse_nonliteral": counts["reverse_nonliteral"],
        "reverse_placeholder": counts["reverse_placeholder"],
        "reverse_other_nonliteral": counts["reverse_other_nonliteral"],
        "reverse_missing_target": counts["reverse_missing_target"],
        "reverse_excluded_confirmed_blanked": counts["reverse_excluded_confirmed_blanked"],
        "reverse_effective_candidates": counts["reverse_effective_candidates"],
        "reverse_same_site": counts["reverse_same_site"],
        "reverse_cross_site": counts["reverse_cross_site"],
        "reverse_missing_site_value": counts["reverse_missing_site_value"],
        "reverse_company_mismatch": counts["reverse_company_mismatch"],
        "reverse_unique_effective_ddk": len(effective_ddk_ids),
    }
    # Include only literal source IDs and numeric ownership evidence, not
    # organization names, addresses, personnel details or raw free-text.
    return {
        "summary": summary,
        "cross_site_candidates": sorted(cross_site_candidates, key=lambda r: (r["legacy_certificate_id"] or -1, r["legacy_ddk_id"])),
        "company_mismatch_candidates": sorted(company_mismatch_candidates, key=lambda r: (r["legacy_certificate_id"] or -1, r["legacy_ddk_id"])),
        "excluded_confirmed_blanked": sorted(excluded_confirmed_blanked, key=lambda r: (r["legacy_certificate_id"] or -1, r["legacy_ddk_id"])),
        "missing_targets": sorted(missing_targets, key=lambda r: (r["legacy_certificate_id"] or -1, r["legacy_ddk_id"])),
        "unknown_sites": sorted(unknown_sites, key=lambda r: (r["legacy_certificate_id"] or -1, r["legacy_ddk_id"])),
    }
