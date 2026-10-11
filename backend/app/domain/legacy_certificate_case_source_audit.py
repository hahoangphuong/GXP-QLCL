"""Read-only source integrity audit for legacy Certificate -> Case references.

Compare literal db.cc / db.ktra ownership. Back-references provide review evidence
only: they never authorize changing an originating Case or merging Sites.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import re
from typing import Any

from backend.app.domain.phase2_import import (
    normalize_inspection_gxp_type,
    normalize_row,
    parse_int,
    source_row_key,
    source_row_number,
)


def _literal_legacy_int(value: object) -> int | None:
    """Source IDs are integers, never rounded/truncated decimal or prose IDs."""
    raw = str(value or "").strip()
    if not re.fullmatch(r"[0-9]+(?:\.0+)?", raw):
        return None
    return int(raw.split(".", 1)[0])


def audit_certificate_case_source_links(
    snapshot: dict[str, list[dict[str, str]]],
    *,
    excluded_certificate_row_keys: set[str] | None = None,
) -> dict[str, Any]:
    """Audit full source and optionally a confirmed-blanked-excluded import population.

    Exclusions must come from independently approved source-row contracts, not from
    this audit's classification. A shared company, line code, or certificate
    number never makes a cross-Site Case link valid.
    """
    excluded = excluded_certificate_row_keys or set()
    case_rows: dict[int, list[dict[str, str]]] = {}
    reverse_case_references: dict[int, list[dict[str, str]]] = defaultdict(list)
    for source_row in snapshot["db.ktra"]:
        row = normalize_row(source_row)
        legacy_case_id = _literal_legacy_int(row.get("ID"))
        if legacy_case_id is not None:
            case_rows.setdefault(legacy_case_id, []).append(row)
        reverse_certificate_id = _literal_legacy_int(row.get("ID CC GPs"))
        if reverse_certificate_id is not None and legacy_case_id is not None:
            reverse_case_references[reverse_certificate_id].append(row)

    # _validate_snapshot_source_keys rejects duplicates across *every* source
    # sheet before schema creation, not merely db.cc. Mirror that structural
    # preflight so a standalone --strict source audit cannot report false-clean
    # input when an unrelated parent sheet is not importable. Keep certificate
    # link classifications independent of source-key validity.
    source_identity_anomalies: list[dict[str, Any]] = []
    for source_sheet, source_rows in sorted(snapshot.items()):
        identity_counts: Counter[str] = Counter()
        for source_row in source_rows:
            row = normalize_row(source_row)
            row_key = source_row_key(
                legacy_row_id=parse_int(row.get("ID")),
                source_row_number_value=source_row_number(row),
            )
            if row_key is not None:
                identity_counts[row_key] += 1
        for key, count in sorted(identity_counts.items()):
            if count > 1:
                source_identity_anomalies.append({
                    "classification": (
                        "DUPLICATE_CERTIFICATE_SOURCE_ROW_KEY"
                        if source_sheet == "db.cc"
                        else "DUPLICATE_SOURCE_ROW_KEY"
                    ),
                    "source_sheet": source_sheet,
                    "source_row_key": key,
                    "occurrences": count,
                })

    # A matching Case/Site value is not proof that Phase 2 can actually
    # materialize its parent chain. The importer creates a Site only when its
    # Company FK resolves, and a Case only when its Site FK resolves. This is a
    # distinct source-importability check, not a change to regulatory link
    # classification or authority to remediate any association.
    parent_check_available = {"db.cty", "db.cso", "db.ktra", "db.cc"}.issubset(snapshot)
    source_parent_anomalies: list[dict[str, Any]] = []
    effective_parent_anomalies: list[dict[str, Any]] = []
    excluded_importable_certificate_rows: list[dict[str, Any]] = []
    if parent_check_available:
        company_ids = {
            parsed for source in snapshot["db.cty"]
            if (parsed := parse_int(normalize_row(source).get("ID"))) is not None
        }
        importable_site_ids: set[int] = set()
        for source in snapshot["db.cso"]:
            row = normalize_row(source)
            site_id = parse_int(row.get("ID"))
            company_id = parse_int(row.get("company_legacy_id_ref"))
            if site_id is not None and company_id in company_ids:
                importable_site_ids.add(site_id)

        all_case_ids: set[int] = set()
        importable_case_ids: set[int] = set()
        for source in snapshot["db.ktra"]:
            row = normalize_row(source)
            case_id = parse_int(row.get("ID"))
            case_site = parse_int(row.get("site_legacy_id_ref"))
            if case_id is None:
                continue
            all_case_ids.add(case_id)
            if case_site in importable_site_ids:
                importable_case_ids.add(case_id)

        for source in snapshot["db.cc"]:
            row = normalize_row(source)
            certificate_id = parse_int(row.get("ID"))
            row_key = source_row_key(
                legacy_row_id=certificate_id,
                source_row_number_value=source_row_number(row),
            )
            is_excluded = row_key in excluded
            certificate_site = parse_int(row.get("site_legacy_id_ref"))
            case_reference = str(row.get("inspection_case_legacy_id_ref") or "").strip()
            linked_case = parse_int(case_reference)
            # Confirmed-blanked exclusion must not hide source drift that
            # makes an excluded Certificate materializable by Phase 2.
            # Compare only literal source dependencies; never select a Case.
            if (
                is_excluded
                and certificate_site in importable_site_ids
                and (not case_reference or linked_case in importable_case_ids)
            ):
                excluded_importable_certificate_rows.append({
                    "classification": "CONFIRMED_BLANKED_CERTIFICATE_IMPORTABLE",
                    "certificate_legacy_id": certificate_id,
                    "certificate_source_row_key": row_key,
                    "linked_case_legacy_id": linked_case,
                    "certificate_site_legacy_id": certificate_site,
                    "remediation_authorized": False,
                })
            parent_problems: list[dict[str, Any]] = []
            if certificate_site not in importable_site_ids:
                parent_problems.append({
                    "classification": "CERTIFICATE_SITE_PARENT_NOT_IMPORTABLE",
                    "parent_source_sheet": "db.cso",
                    "parent_legacy_id": certificate_site,
                })
            # Missing/unparseable Case references are already classified by the
            # link audit; here we only flag a *present* Case source row whose
            # own Site parent cannot materialize under default import mapping.
            if case_reference and linked_case in all_case_ids and linked_case not in importable_case_ids:
                parent_problems.append({
                    "classification": "LINKED_CASE_PARENT_NOT_IMPORTABLE",
                    "parent_source_sheet": "db.ktra",
                    "parent_legacy_id": linked_case,
                })
            for problem in parent_problems:
                item = {
                    **problem,
                    "certificate_legacy_id": certificate_id,
                    "certificate_source_row_key": row_key,
                    "excluded_confirmed_blanked": is_excluded,
                    "remediation_authorized": False,
                }
                source_parent_anomalies.append(item)
                if not is_excluded:
                    effective_parent_anomalies.append(item)

    raw_counts: Counter[str] = Counter()
    effective_counts: Counter[str] = Counter()
    anomalies: list[dict[str, Any]] = []
    effective_anomalies: list[dict[str, Any]] = []
    excluded_count = 0

    for source_row in snapshot["db.cc"]:
        certificate = normalize_row(source_row)
        certificate_legacy_id = _literal_legacy_int(certificate.get("ID"))
        row_key = source_row_key(
            legacy_row_id=certificate_legacy_id,
            source_row_number_value=source_row_number(certificate),
        )
        is_excluded = row_key in excluded
        if is_excluded:
            excluded_count += 1

        case_ref = str(certificate.get("inspection_case_legacy_id_ref") or "").strip()
        certificate_site = _literal_legacy_int(certificate.get("site_legacy_id_ref"))
        certificate_gxp = certificate.get("certificate_type") or "UNKNOWN"
        certificate_number = str(certificate.get("certificate_number") or "").strip()
        certificate_scope = str(certificate.get("certificate_scope_text") or "").strip()
        case_legacy_id = _literal_legacy_int(case_ref)
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
            linked_case_site = _literal_legacy_int(linked_case.get("site_legacy_id_ref"))
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

        raw_counts[classification] += 1
        if not is_excluded:
            effective_counts[classification] += 1
        if classification in {"EXACT_SOURCE_CONTEXT", "ADMINISTRATIVE_NO_CASE_REFERENCE"}:
            continue

        reverse_evidence = []
        for row in reverse_case_references.get(certificate_legacy_id, []):
            reverse_case_gxp_raw = str(row.get("inspection_gxp_type") or "").strip()
            reverse_case_gxp = normalize_inspection_gxp_type(reverse_case_gxp_raw) or reverse_case_gxp_raw or "UNKNOWN"
            reverse_site = _literal_legacy_int(row.get("site_legacy_id_ref"))
            reverse_number = str(row.get("certificate_number") or "").strip()
            reverse_scope = str(row.get("evaluation_scope_raw") or "").strip()
            reverse_evidence.append({
                "case_legacy_id": _literal_legacy_int(row.get("ID")),
                "site_legacy_id": reverse_site,
                "gxp_type": reverse_case_gxp,
                "inspection_period_source": str(row.get("inspected_at") or "").strip() or None,
                "same_certificate_site_and_type": (
                    certificate_site is not None
                    and reverse_site == certificate_site
                    and reverse_case_gxp == certificate_gxp
                ),
                "same_nonblank_certificate_number": bool(
                    certificate_number and reverse_number and certificate_number == reverse_number
                ),
                # Exact lexical evidence only (after outer whitespace removal).
                # This never assigns or recommends a replacement Case FK.
                "same_nonblank_scope_text": bool(
                    certificate_scope and reverse_scope and certificate_scope == reverse_scope
                ),
            })
        item = {
            "classification": classification,
            "certificate_source_row_key": row_key,
            "certificate_legacy_id": certificate_legacy_id,
            "linked_case_legacy_id": case_legacy_id,
            "raw_case_reference": case_ref,
            "certificate_issued_at_source": str(certificate.get("certificate_issue_date") or "").strip() or None,
            "linked_case_inspection_period_source": (
                str(case_rows[case_legacy_id][0].get("inspected_at") or "").strip() or None
                if case_legacy_id is not None and len(case_rows.get(case_legacy_id, [])) == 1
                else None
            ),
            "certificate_site_legacy_id": certificate_site,
            "linked_case_site_legacy_id": linked_case_site,
            "certificate_gxp_type": certificate_gxp,
            "linked_case_gxp_type": linked_case_gxp,
            "excluded_confirmed_blanked": is_excluded,
            "reverse_case_reference_evidence": sorted(
                reverse_evidence, key=lambda item: item["case_legacy_id"]
            ),
            "remediation_authorized": False,
        }
        anomalies.append(item)
        if not is_excluded:
            effective_anomalies.append(item)

    return {
        "schema_version": "certificate-case-source-integrity/v2",
        "source_sheet": "db.cc",
        "total_certificate_source_rows": sum(raw_counts.values()),
        "classification_counts": dict(sorted(raw_counts.items())),
        "anomalies": anomalies,
        "excluded_confirmed_blanked_certificate_count": excluded_count,
        "effective_certificate_source_rows": sum(effective_counts.values()),
        "effective_classification_counts": dict(sorted(effective_counts.items())),
        "effective_anomalies": effective_anomalies,
        "source_identity_anomalies": source_identity_anomalies,
        "source_parent_check_available": parent_check_available,
        "source_parent_anomalies": source_parent_anomalies,
        "effective_parent_anomalies": effective_parent_anomalies,
        "excluded_importable_certificate_rows": excluded_importable_certificate_rows,
        "database_mutated": False,
        "source_modified": False,
    }
