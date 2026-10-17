"""Exception-only private review dossier for original DDK GxP ID CC observations.

No legal/canonical link approval. Call only from the guarded read-only
rehearsal transaction, after classify_candidates validates the entire
source workbook and reference-token population. Never send dossier rows to
stdout or a frontend API.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from hashlib import sha256
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models.phase1 import (
    BusinessEligibilityCertificate, BusinessEligibilityGxpSourceGroup,
    Case, Certificate, CertificateScope, CertificateVersion, Site,
)
from tools.audit_ddk_gxp_canonical_candidates_readonly import (
    CandidateAuditBlocked, REPORT_SCHEMA,
)


DOSSIER_SCHEMA = "GXP_DDK_IDCC_EXCEPTION_EVIDENCE_DOSSIER_V1"


def build_exception_dossier(session: Session, audit: dict[str, Any]) -> dict[str, Any]:
    if (
        audit.get("schema") != REPORT_SCHEMA
        or audit.get("approval_status") != "NOT_APPROVED"
        or audit.get("database_writes") != 0
        or audit.get("canonical_links_created") != 0
    ):
        raise CandidateAuditBlocked("Refuse dossier from unvalidated source-token audit")
    observations = audit["candidate_observations"]
    if len(observations) != audit["source_tokens"]:
        raise CandidateAuditBlocked("Incomplete source-token evidence in audit")

    group_rows = list(session.scalars(select(BusinessEligibilityGxpSourceGroup)))
    groups_by_key = {
        (g.legacy_dkkd_id, g.source_row_number, g.source_group): g
        for g in group_rows
    }
    if len(groups_by_key) != audit["source_groups"]:
        raise CandidateAuditBlocked("Duplicate or missing physical original source group keys")
    ddks = {
        x.legacy_dkkd_id: x for x in session.scalars(select(BusinessEligibilityCertificate))
        if x.legacy_dkkd_id is not None
    }
    certs = {
        x.legacy_certificate_id: x for x in session.scalars(select(Certificate))
        if x.legacy_certificate_id is not None
    }
    sites = {x.id: x for x in session.scalars(select(Site))}
    cases = {x.id: x for x in session.scalars(select(Case))}
    versions: dict[str, list[CertificateVersion]] = defaultdict(list)
    for v in session.scalars(select(CertificateVersion)):
        versions[v.certificate_id].append(v)
    scopes: dict[str, list[CertificateScope]] = defaultdict(list)
    for scope in session.scalars(select(CertificateScope)):
        scopes[scope.certificate_version_id].append(scope)

    def version_evidence(certificate_id: str) -> list[dict[str, Any]]:
        result = []
        for v in sorted(versions[certificate_id], key=lambda x: (x.version_no, x.id)):
            result.append({
                "certificate_version_id": v.id,
                "version_no": v.version_no,
                "is_latest_version": v.is_latest_version,
                "lifecycle_state": v.lifecycle_state,
                "issue_date": v.issue_date.isoformat() if v.issue_date else None,
                "expiry_date": v.expiry_date.isoformat() if v.expiry_date else None,
                # Scope owner and content fingerprints, NEVER another
                # version's scope, nor an inferred coverage/grant decision.
                "scope_evidence": [
                    {
                        "scope_id": s.id,
                        "language_code": s.language_code,
                        "sort_order": s.sort_order,
                        "scope_text_sha256": sha256(s.scope_text.encode("utf-8")).hexdigest(),
                    }
                    for s in sorted(scopes[v.id], key=lambda s: (s.sort_order, s.id))
                ],
            })
        return result

    repeated: dict[int, list[dict[str, Any]]] = defaultdict(list)
    exception_rows = []
    extra_flags: Counter[str] = Counter()
    for item in observations:
        ddk_id = item["legacy_dkkd_id"]
        certificate_legacy_id = item["parsed_legacy_certificate_id"]
        g = groups_by_key.get((ddk_id, item["source_row_number"], item["source_role"]))
        if g is None or g.id_cc_excel_column != item["id_cc_excel_column"]:
            raise CandidateAuditBlocked("Candidate references changed physical workbook source")
        ddk = ddks.get(ddk_id)
        cert = certs.get(certificate_legacy_id)
        source_position = {
            "legacy_dkkd_id": ddk_id,
            "source_row_number": g.source_row_number,
            "source_group": g.source_group,
            "id_cc_excel_column": g.id_cc_excel_column,
            "token_index": item["token_index"],
            "source_reference_id": item["source_reference_id"],
            "parsed_legacy_certificate_id": certificate_legacy_id,
        }
        if certificate_legacy_id is not None:
            repeated[certificate_legacy_id].append(source_position)
        flags = [x for x in item["flags"] if x != "SOURCE_OBSERVATION_NOT_APPROVED"]
        if cert is not None:
            case = cases.get(cert.case_id) if cert.case_id else None
            if cert.case_id is not None and case is None:
                flags.append("CERTIFICATE_ORIGIN_CASE_MISSING")
            if case is not None:
                if case.site_id != cert.site_id:
                    flags.append("CERTIFICATE_CASE_SITE_DIFFERENT")
                if case.gxp_type != cert.certificate_type:
                    flags.append("CERTIFICATE_CASE_GXP_TYPE_DIFFERENT")
            # Missing Case for an administrative issue is NOT automatically an error.
        else:
            case = None
        for f in set(flags):
            extra_flags[f] += 1
        if flags:
            report_item = {
                **source_position,
                "flags": sorted(set(flags)),
                "review_status": "REQUIRES_INDEPENDENT_ADJUDICATION",
                "link_approval": "NOT_APPROVED",
                "original_source": {
                    "id_cc_raw": g.id_cc_raw,
                    "certificate_scope_raw": g.certificate_scope_raw,
                    "applicable_standard_raw": g.applicable_standard_raw,
                    "business_activity_raw": g.business_activity_raw,
                    "source_values_sha256": g.source_values_sha256,
                },
                "ddk_site_id": ddk.site_id if ddk else None,
                "ddk_company_id": ddk.company_id if ddk else None,
                "observed_certificate_id": cert.id if cert else None,
                "certificate_site_id": cert.site_id if cert else None,
                "certificate_type": cert.certificate_type if cert else None,
                "certificate_issuance_basis": cert.issuance_basis if cert else None,
                "certificate_case_id": cert.case_id if cert else None,
                "case_site_id": case.site_id if case else None,
                "case_gxp_type": case.gxp_type if case else None,
                "case_legacy_inspection_id": case.legacy_inspection_id if case else None,
                "certificate_versions": version_evidence(cert.id) if cert else [],
            }
            exception_rows.append(report_item)

    company_rows = []
    for ddk_id in sorted({item["legacy_dkkd_id"] for item in observations}
                         | {g.legacy_dkkd_id for g in group_rows}):
        ddk = ddks.get(ddk_id)
        if ddk is None:
            continue
        site = sites.get(ddk.site_id)
        if site is None or site.company_id != ddk.company_id:
            positions = sorted({g.source_row_number for g in group_rows
                                if g.legacy_dkkd_id == ddk_id})
            company_rows.append({
                "legacy_dkkd_id": ddk_id,
                "source_row_numbers": positions,
                "canonical_business_eligibility_certificate_id": ddk.id,
                "ddk_site_id": ddk.site_id,
                "ddk_company_id": ddk.company_id,
                "site_owning_company_id": site.company_id if site else None,
                "review_status": "REQUIRES_INDEPENDENT_ADJUDICATION",
                "link_approval": "NOT_APPROVED",
                "flags": ["DDK_SITE_COMPANY_MISMATCH" if site else "DDK_SITE_MISSING"],
            })

    repeat_items = []
    within_cell_extras = 0
    multiple_ddk_ids = 0
    for legacy_id, positions in sorted(repeated.items()):
        if len(positions) < 2:
            continue
        cells = Counter(
            (p["legacy_dkkd_id"], p["source_row_number"], p["source_group"],
             p["id_cc_excel_column"]) for p in positions
        )
        within_cell_extras += sum(count - 1 for count in cells.values() if count > 1)
        across_ddk = len({p["legacy_dkkd_id"] for p in positions}) > 1
        if across_ddk:
            multiple_ddk_ids += 1
        repeat_items.append({
            "parsed_legacy_certificate_id": legacy_id,
            "occurrence_count": len(positions),
            "distinct_source_ddk_count": len({p["legacy_dkkd_id"] for p in positions}),
            "repeated_within_same_original_cell": any(n > 1 for n in cells.values()),
            "observed_in_multiple_ddk": across_ddk,
            "observations": positions,
            "link_approval": "NOT_APPROVED",
        })
    extra_occurrences = sum(x["occurrence_count"] - 1 for x in repeat_items)
    if extra_occurrences != audit["repeated_candidate_id_extra_occurrences"]:
        raise CandidateAuditBlocked("Duplicate reference cardinality changed")
    actual_cross_site = sum("CERTIFICATE_SITE_DIFFERENT" in x["flags"]
                            for x in exception_rows)
    actual_company = len(company_rows)
    if (actual_cross_site != audit["counts"].get("candidate_different_site", 0)
            or actual_company != audit["counts"].get("ddk_site_company_mismatch", 0)):
        raise CandidateAuditBlocked("Exception counts disagree with original source audit")

    return {
        "schema": DOSSIER_SCHEMA,
        "status": "READ_ONLY_EXCEPTION_EVIDENCE_NOT_APPROVED",
        "source_workbook_sha256": audit["source_workbook_sha256"],
        "source_tokens_checked": len(observations),
        "distinct_observed_certificate_legacy_ids": len(repeated),
        "candidate_repeated_id_count": len(repeat_items),
        "repeated_candidate_extra_occurrences": extra_occurrences,
        "within_one_source_cell_repeat_extras": within_cell_extras,
        "candidate_ids_observed_in_multiple_ddk": multiple_ddk_ids,
        "cross_site_occurrences": actual_cross_site,
        "ddk_site_company_mismatches": actual_company,
        "recorded_canonical_link_rows_before": audit["recorded_canonical_gxp_link_rows_before"],
        "database_writes": 0,
        "canonical_links_created": 0,
        "approval_status": "NOT_APPROVED",
        "other_case_site_or_type_observations": {
            key: extra_flags.get(key, 0) for key in (
                "CERTIFICATE_ORIGIN_CASE_MISSING",
                "CERTIFICATE_CASE_SITE_DIFFERENT",
                "CERTIFICATE_CASE_GXP_TYPE_DIFFERENT",
            )
        },
        "exception_token_details": exception_rows,
        "ddk_company_exception_details": company_rows,
        "repeated_candidate_id_details": repeat_items,
        "limitations": [
            "A same-company cross-Site observation does not establish site coverage",
            "Case association and stored CertificateVersion scopes do not approve DDK linkage",
            "Same type, same Site and matching legacy IDs do not prove historical validity",
            "Repeat references are preserved; not merged or deduplicated",
            "Original source values are confidential; keep dossier only in private 0600 file",
        ],
    }
