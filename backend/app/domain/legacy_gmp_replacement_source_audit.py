"""Read-only GMP replacement evidence from legacy db.cc MÃ DC.

This is source chronology and identity review, NOT CertificateRelationship
creation or permission to modify canonical data. The owner must review each
source group and its issuance evidence before approving any relationship.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from hashlib import sha256
from typing import Any, Mapping

from backend.app.domain.phase2_import import (
    normalize_row,
    parse_date,
    parse_int,
    source_row_key,
    source_row_number,
)


def audit_gmp_replacement_sources(
    snapshot: Mapping[str, list[dict[str, str]]],
    *,
    excluded_certificate_row_keys: set[str] | None = None,
) -> dict[str, Any]:
    """Audit exact shared MÃ DC among GMP issuance identities, without writes.

    Cert number, matching business name, "MỚI NHẤT", and latest_legacy_id
    are deliberately not used as replacement or identity keys.
    A source-order pair is REVIEW_ONLY even when all structural gates pass.
    """
    excluded = excluded_certificate_row_keys or set()

    owners_by_site: dict[int, list[int | None]] = defaultdict(list)
    for raw in snapshot.get("db.cso", []):
        site = normalize_row(raw)
        site_id = parse_int(site.get("ID"))
        if site_id is not None:
            owners_by_site[site_id].append(parse_int(site.get("company_legacy_id_ref")))
    site_owner = {
        site_id: values[0] if len(values) == 1 else None
        for site_id, values in owners_by_site.items()
    }

    by_code: dict[str, list[dict[str, Any]]] = defaultdict(list)
    counts = Counter()
    for raw in snapshot.get("db.cc", []):
        certificate = normalize_row(raw)
        if str(certificate.get("certificate_type") or "").strip().upper() != "GMP":
            continue
        legacy_id = parse_int(certificate.get("ID"))
        row_key = source_row_key(
            legacy_row_id=legacy_id,
            source_row_number_value=source_row_number(certificate),
        )
        if row_key in excluded:
            counts["EXCLUDED_APPROVED_SOURCE_ROW"] += 1
            continue
        raw_code = str(certificate.get("scope_code") or "").strip()
        if raw_code in {"", "-", "???"}:
            counts["GMP_MISSING_MA_DC"] += 1
            continue
        site_id = parse_int(certificate.get("site_legacy_id_ref"))
        raw_date = str(certificate.get("certificate_issue_date") or "").strip()
        issued = parse_date(raw_date)
        by_code[raw_code].append({
            "legacy_certificate_id": legacy_id,
            "source_row_key": row_key,
            "site_legacy_id": site_id,
            "company_legacy_id": site_owner.get(site_id),
            "issued_on": issued.isoformat() if issued else None,
        })
        counts["GMP_WITH_MA_DC"] += 1

    groups: list[dict[str, Any]] = []
    for code, members in sorted(by_code.items()):
        if len(members) < 2:
            continue
        legacy_ids = [item["legacy_certificate_id"] for item in members]
        companies = [item["company_legacy_id"] for item in members]
        dates = [item["issued_on"] for item in members]

        # A repeated source code is evidence to review, not automatic proof
        # of common regulatory identity or of the order of replacement.
        if any(value is None for value in legacy_ids) or len(set(legacy_ids)) != len(members):
            state = "BLOCKED_SOURCE_CERTIFICATE_IDENTITY"
        elif any(value is None for value in companies):
            state = "BLOCKED_SITE_COMPANY_OWNER"
        elif len(set(companies)) != 1:
            state = "BLOCKED_CROSS_COMPANY_MA_DC"
        elif any(value is None for value in dates) or len(set(dates)) != len(members):
            state = "BLOCKED_MISSING_OR_EQUAL_ISSUE_DATE"
        else:
            state = "SOURCE_CHRONOLOGY_FOR_REVIEW"
        ordered = sorted(
            members,
            key=lambda item: (
                item["issued_on"] is None,
                item["issued_on"] or "",
                item["legacy_certificate_id"] is None,
                item["legacy_certificate_id"] or 0,
            ),
        )
        pairs = [
            {
                "older_legacy_certificate_id": previous["legacy_certificate_id"],
                "newer_legacy_certificate_id": next_item["legacy_certificate_id"],
                "authorization": "REVIEW_ONLY",
            }
            for previous, next_item in zip(ordered, ordered[1:])
        ] if state == "SOURCE_CHRONOLOGY_FOR_REVIEW" else []
        groups.append({
            "ma_dc_sha256": sha256(code.encode("utf-8")).hexdigest(),
            "certificate_count": len(members),
            "source_state": state,
            "certificates": ordered,
            "chronological_adjacent_pairs_for_review": pairs,
            "replacement_authorized": False,
        })
        counts[state] += 1

    groups.sort(key=lambda item: item["ma_dc_sha256"])
    return {
        "schema_version": "legacy-gmp-replacement-source-audit/v1",
        "source_sheet": "db.cc",
        "source_key": "MÃ DC",
        "group_count": len(groups),
        "counts": dict(sorted(counts.items())),
        "groups": groups,
        "database_mutated": False,
        "source_modified": False,
        "replacement_authorized": False,
    }
