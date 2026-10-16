"""Certificate↔Case source/target witness, read-only and never a repair plan.

The original db.cso Site→Company pair controls Company ownership.  The
certificate's Site FK and Case's Site FK are distinct source anchors.
Stored CertificateVersion and CertificateScope records are *not*
version-and-Site-specific regulatory evidence.  Output is confidential.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from backend.app.db.models.phase1 import (
    Case, Certificate, CertificateScope, CertificateVersion, Company, Site,
)
from backend.app.domain.legacy_certificate_case_source_audit import (
    audit_certificate_case_source_links,
)
from backend.app.domain.phase2_import import load_confirmed_blanked_row_keys
from tools.apply_ddk_gxp_provenance_rehearsal import checked_rehearsal_url
from tools.audit_ddk_gxp_canonical_candidates_readonly import _write_private_json
from tools.env_utils import parse_env_file
from tools.preflight_ddk_gxp_rehearsal import EXPECTED_DB, EXPECTED_REVISION

SCHEMA = "GXP_CERTIFICATE_CASE_SOURCE_SITE_REHEARSAL_WITNESS_V1"
EXPECTED_SOURCE_CERTIFICATES = frozenset((376, 1037, 1180))
# Pinned snapshot bytes witnessed independently on gxp-web-prod (2026-10-16).
# Snapshot export SHA is not the physical original XLSB SHA.
EXPECTED_SNAPSHOT_SHA256 = "b3bde05963e4e4d14d5b244e7c62b0f810f1cbbe206750574def6a366bdf7296"


class CertificateCaseWitnessBlocked(ValueError):
    pass


def _check(ok: bool, message: str) -> None:
    if not ok:
        raise CertificateCaseWitnessBlocked(message)


def compare_source_to_rehearsal(
    session: Session, source_report: dict[str, Any],
    *, expected_certificate_ids: set[int],
) -> dict[str, Any]:
    """Pure SQL SELECT witness; fail on unexpected canonical/source identity."""
    _check(
        source_report.get("schema_version") == "certificate-case-source-integrity/v2"
        and source_report.get("source_parent_check_available") is True
        and not source_report.get("source_identity_anomalies")
        and not source_report.get("effective_parent_anomalies")
        and not source_report.get("excluded_importable_certificate_rows")
        and source_report.get("database_mutated") is False,
        "Original source context is not complete/clean enough to compare",
    )
    anomalies = source_report.get("effective_anomalies")
    _check(isinstance(anomalies, list) and bool(anomalies),
           "No complete original source anomalies")
    by_legacy_id = {item["certificate_legacy_id"]: item for item in anomalies}
    _check(
        len(by_legacy_id) == len(anomalies)
        and set(by_legacy_id) == expected_certificate_ids
        and all(item.get("classification") == "SITE_MISMATCH"
                and item.get("remediation_authorized") is False
                and item.get("excluded_confirmed_blanked") is False
                for item in anomalies),
        "Certificate source mismatch population changed",
    )
    certificates = list(session.scalars(
        select(Certificate).where(Certificate.legacy_certificate_id.in_(expected_certificate_ids))
    ))
    certs_by_legacy = {c.legacy_certificate_id: c for c in certificates}
    _check(len(certificates) == len(expected_certificate_ids)
           and set(certs_by_legacy) == expected_certificate_ids,
           "Canonical Certificate identity missing/duplicated")

    source_case_ids = set()
    source_site_ids = set()
    for item in anomalies:
        source_case_ids.add(item["linked_case_legacy_id"])
        source_site_ids.add(item["certificate_site_legacy_id"])
        source_site_ids.add(item["linked_case_site_legacy_id"])
        own = item.get("site_master_company_evidence")
        _check(isinstance(own, dict)
               and own.get("site_owner_is_authoritative_source") == "db.cso"
               and own.get("case_rebinding_authorized") is False,
               "Missing physically grounded db.cso ownership witness")
        for rev in own.get("reverse_source_cases", []):
            source_case_ids.add(rev["case_legacy_id"])
    _check(None not in source_case_ids and None not in source_site_ids,
           "Source Case/Site identity incomplete")
    cases = list(session.scalars(
        select(Case).where(Case.legacy_inspection_id.in_(source_case_ids))
    ))
    by_case = {c.legacy_inspection_id: c for c in cases}
    _check(len(cases) == len(source_case_ids)
           and set(by_case) == source_case_ids,
           "Canonical original or reverse Case identity missing")
    sites = list(session.scalars(
        select(Site).where(Site.legacy_site_id.in_(source_site_ids))
    ))
    by_site = {s.legacy_site_id: s for s in sites}
    _check(len(sites) == len(source_site_ids) and set(by_site) == source_site_ids,
           "Source db.cso Site identity missing/duplicated")
    companies = {c.id: c for c in session.scalars(
        select(Company).where(Company.id.in_({site.company_id for site in sites}))
    )}
    _check(all(site.company_id in companies
               and companies[site.company_id].legacy_company_id is not None
               for site in sites), "Canonical db.cso Site→Company owner incomplete")

    version_rows = list(session.scalars(select(CertificateVersion).where(
        CertificateVersion.certificate_id.in_({cert.id for cert in certificates})
    )))
    version_by_cert: dict[str, list[CertificateVersion]] = defaultdict(list)
    for version in version_rows:
        version_by_cert[version.certificate_id].append(version)
    _check(len({v.id for v in version_rows}) == len(version_rows),
           "Duplicate CertificateVersion identity")
    scopes = list(session.scalars(select(CertificateScope).where(
        CertificateScope.certificate_version_id.in_({v.id for v in version_rows})
    ))) if version_rows else []
    scope_by_version: dict[str, list[CertificateScope]] = defaultdict(list)
    for scope in scopes:
        scope_by_version[scope.certificate_version_id].append(scope)

    details = []
    counters: Counter[str] = Counter()
    for legacy_id, item in sorted(by_legacy_id.items()):
        cert = certs_by_legacy[legacy_id]
        source_case = by_case[item["linked_case_legacy_id"]]
        cs = by_site[item["certificate_site_legacy_id"]]
        ks = by_site[item["linked_case_site_legacy_id"]]
        owners = item["site_master_company_evidence"]
        _check(
            cert.site_id == cs.id
            and cert.case_id == source_case.id
            and cert.certificate_type == item["certificate_gxp_type"]
            and cert.issuance_basis == "inspection_case"
            and source_case.site_id == ks.id
            and source_case.gxp_type == item["linked_case_gxp_type"],
            "Canonical Certificate or linked Case differs from original source",
        )
        _check(
            companies[cs.company_id].legacy_company_id ==
                owners["certificate_site_owner_legacy_company_id"]
            and companies[ks.company_id].legacy_company_id ==
                owners["linked_case_site_owner_legacy_company_id"],
            "Canonical Site ownership contradicts db.cso original identity",
        )
        distinct = cs.id != ks.id
        _check(distinct, "Original mismatched source Sites unexpectedly coalesced")
        same_company = cs.company_id == ks.company_id
        expected_relation = ("DISTINCT_SITES_SAME_SOURCE_COMPANY"
                             if same_company else "DISTINCT_SITES_DIFFERENT_SOURCE_COMPANIES")
        _check(owners["source_owner_relationship"] == expected_relation,
               "Source-to-canonical Site owner relationship changed")
        counters[expected_relation] += 1
        # Both reverse-reference projections originate at db.ktra, but serve
        # independent purposes: Site-master ownership vs literal issuance
        # corroboration. Bind them one-to-one, not just by a common Case ID.
        source_reverses = owners.get("reverse_source_cases")
        original_reverses = item.get("reverse_case_reference_evidence")
        _check(isinstance(source_reverses, list)
               and isinstance(original_reverses, list),
               "Missing original reverse-case evidence")
        reverse_evidence_by_id = {
            row.get("case_legacy_id"): row for row in original_reverses
        }
        _check(
            len(reverse_evidence_by_id) == len(original_reverses)
            and all(type(x) is int for x in reverse_evidence_by_id)
            and {x.get("case_legacy_id") for x in source_reverses} ==
                set(reverse_evidence_by_id)
            and len(source_reverses) == len(reverse_evidence_by_id),
            "Reverse Case source projections are inconsistent/duplicated",
        )
        alt_cases = []
        for reverse in source_reverses:
            literal = reverse_evidence_by_id[reverse["case_legacy_id"]]
            reverse_case = by_case[reverse["case_legacy_id"]]
            reverse_site = next(
                (s for s in sites if s.id == reverse_case.site_id), None
            )
            _check(reverse_site is not None
                   and companies[reverse_site.company_id].legacy_company_id ==
                       reverse["source_site_owner_legacy_company_id"],
                   "Reverse-source Case now points to different Site owner")
            reverse_relation = (
                "SAME_SOURCE_SITE" if reverse_site.id == cs.id
                else "DISTINCT_SITES_SAME_SOURCE_COMPANY" if reverse_site.company_id == cs.company_id
                else "DISTINCT_SITES_DIFFERENT_SOURCE_COMPANIES"
            )
            _check(reverse["source_owner_relationship_to_certificate"] == reverse_relation,
                   "Reverse-source Case Site changed")
            _check(
                literal.get("site_legacy_id") == reverse_site.legacy_site_id
                and literal.get("gxp_type") == reverse_case.gxp_type
                and type(literal.get("same_certificate_site_and_type")) is bool
                and type(literal.get("same_nonblank_certificate_number")) is bool
                and type(literal.get("same_nonblank_scope_text")) is bool
                and literal["same_certificate_site_and_type"] ==
                    (reverse_site.id == cs.id and reverse_case.gxp_type == cert.certificate_type),
                "Reverse Case literal GxP/Site or scope/number evidence changed",
            )
            source_corrob = (
                literal["same_certificate_site_and_type"]
                and literal["same_nonblank_certificate_number"]
                and literal["same_nonblank_scope_text"]
            )
            if source_corrob:
                counters["reverse_case_triple_literal_corroboration_only"] += 1
            alt_cases.append({
                "source_site_gxp_correspondence": literal["same_certificate_site_and_type"],
                "source_certificate_number_correspondence": literal["same_nonblank_certificate_number"],
                "source_full_scope_lexical_correspondence": literal["same_nonblank_scope_text"],
                "source_inspection_period_recorded": literal.get("inspection_period_source") is not None,
                "all_three_source_signals": source_corrob,
                "primary_signed_issuance_case_link_verified": False,
                "source_literal_correspondence_is_approval": False,
                "case_id": reverse_case.id,
                "legacy_case_id": reverse_case.legacy_inspection_id,
                "site_id": reverse_case.site_id,
                "gxp_type": reverse_case.gxp_type,
                "source_reverse_reference_only": True,
                "remediation_authorized": False,
            })
        # Legacy Phase-2 import creates exactly one version per source
        # Certificate. Validate its actual number/date/scope against the
        # original db.cc source projection BEFORE considering it evidence.
        # This does not attest a signed regulatory grant or Site coverage.
        expected = item.get("source_version_fidelity_evidence")
        _check(isinstance(expected, dict)
               and expected.get("version_no") == 1
               and expected.get("site_specific_scope_coverage_approved") is False
               and type(expected.get("certificate_scope_source_is_nonblank")) is bool,
               "Original source CertificateVersion value evidence absent")
        actual_versions = version_by_cert[cert.id]
        _check(len(actual_versions) == 1 and actual_versions[0].version_no == 1,
               "Historical CertificateVersion count/order changed")
        version = actual_versions[0]
        number = str(version.certificate_number or "").strip()
        expected_number_hash = (
            sha256(number.encode("utf-8")).hexdigest() if number else None
        )
        _check(expected_number_hash == expected.get("certificate_number_sha256"),
               "Canonical CertificateVersion number does not match source")
        _check(
            (version.issue_date.isoformat() if version.issue_date else None)
                == expected.get("issue_date"),
            "Canonical CertificateVersion issuance date does not match source",
        )
        imported_scopes = scope_by_version[version.id]
        expected_scope_hash = expected.get("certificate_scope_sha256")
        if expected["certificate_scope_source_is_nonblank"]:
            _check(
                len(imported_scopes) == 1
                and imported_scopes[0].scope_key is None
                and imported_scopes[0].language_code == "vi"
                and imported_scopes[0].sort_order == 0
                and sha256(imported_scopes[0].scope_text.encode("utf-8")).hexdigest()
                    == expected_scope_hash,
                "Canonical CertificateVersion scope differs from source import",
            )
        else:
            _check(len(imported_scopes) == 0 and expected_scope_hash is None,
                   "Unexpected certificate scope not present in original source")
        counters["source_certificate_version_fidelity_verified"] += 1
        versions = []
        for version in sorted(actual_versions, key=lambda v: (v.version_no, v.id)):
            local_scopes = sorted(scope_by_version[version.id], key=lambda x: (x.sort_order, x.id))
            versions.append({
                "version_id": version.id,
                "version_no": version.version_no,
                "issue_date": version.issue_date.isoformat() if version.issue_date else None,
                "expiry_date": version.expiry_date.isoformat() if version.expiry_date else None,
                "lifecycle_state": version.lifecycle_state,
                "scope_evidence": [
                    {"scope_id": scope.id, "sort_order": scope.sort_order,
                     "language_code": scope.language_code,
                     "scope_sha256": sha256(scope.scope_text.encode("utf-8")).hexdigest()}
                    for scope in local_scopes
                ],
                "original_import_value_fidelity_verified": True,
                "site_specific_scope_coverage_verified": False,
            })
            counters["stored_certificate_versions"] += 1
            counters["stored_version_scope_rows"] += len(local_scopes)
        details.append({
            "legacy_certificate_id": legacy_id,
            "certificate_id": cert.id,
            "certificate_site_id": cert.site_id,
            "original_linked_case_id": cert.case_id,
            "original_case_legacy_id": source_case.legacy_inspection_id,
            "original_case_site_id": source_case.site_id,
            "source_site_company_relation": expected_relation,
            "original_certificate_site_company_id": cs.company_id,
            "original_case_site_company_id": ks.company_id,
            "reverse_case_review_candidates": alt_cases,
            "certificate_versions": versions,
            "decision_gate": (
                "ORIGINAL_ISSUANCE_CASE_AND_OWNER_SIGNOFF_REQUIRED"
                if not same_company else
                "REVIEWED_CASE_AND_VERSION_SITE_COVERAGE_REQUIRED"
            ),
            "legal_coverage_approved": False,
            "case_rebinding_authorized": False,
        })
    return {
        "schema": SCHEMA,
        "status": "SOURCE_AND_CANONICAL_ANCHORS_VERIFIED_COVERAGE_NOT_APPROVED",
        "database": EXPECTED_DB,
        "certificate_count": len(details),
        "original_source_mismatch_count": len(anomalies),
        "reverse_case_candidate_count": sum(len(x["reverse_case_review_candidates"]) for x in details),
        "counts": dict(sorted(counters.items())),
        "details_private": details,
        "site_specific_scope_coverage_approved": False,
        "case_rebinding_authorized": False,
        "canonical_ddk_gxp_links_approved": False,
        "database_writes": 0,
        "nas_reads": 0,
        "storage_binding_writes": 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-env", type=Path, default=Path("/etc/gxp/runtime.env"))
    parser.add_argument("--snapshot", type=Path, default=Path(
        "artifacts/phase3c/legacy_snapshot.json"))
    parser.add_argument("--private-output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        # Source snapshot is an independently versioned legacy export; its
        # digest is printed but NOT falsely claimed to equal workbook SHA256.
        raw = args.snapshot.read_bytes()
        source_sha256 = sha256(raw).hexdigest()
        _check(source_sha256 == EXPECTED_SNAPSHOT_SHA256,
               "Source snapshot SHA256 differs from independently witnessed bytes")
        payload = json.loads(raw)
        snapshot = payload.get("sheets", payload)
        excluded = {key for sheet, key in load_confirmed_blanked_row_keys()
                    if sheet == "db.cc"}
        source_report = audit_certificate_case_source_links(
            snapshot, excluded_certificate_row_keys=excluded
        )
        _check(source_report.get("effective_certificate_source_rows") == 1601,
               "Original accepted effective Certificate population changed")
        _check({x["certificate_legacy_id"] for x in source_report["effective_anomalies"]}
               == EXPECTED_SOURCE_CERTIFICATES,
               "Original physical source exception set changed")
        url = checked_rehearsal_url(parse_env_file(args.runtime_env))
        engine = create_engine(url, poolclass=NullPool, connect_args={
            "options": "-c default_transaction_read_only=on -c statement_timeout=30000",
        })
        try:
            with engine.connect() as conn:
                with conn.begin():
                    conn.exec_driver_sql("SET TRANSACTION READ ONLY")
                    _check(conn.execute(text("SELECT current_database()")).scalar_one() == EXPECTED_DB
                           and conn.execute(text("SHOW transaction_read_only")).scalar_one() == "on",
                           "Not the isolated read-only rehearsal transaction")
                    revisions = list(conn.execute(text(
                        "SELECT version_num FROM public.alembic_version"
                    )).scalars())
                    _check(revisions == [EXPECTED_REVISION], "Unexpected rehearsal schema revision")
                    with Session(bind=conn) as session:
                        report = compare_source_to_rehearsal(
                            session, source_report,
                            expected_certificate_ids=set(EXPECTED_SOURCE_CERTIFICATES),
                        )
                    report["snapshot_sha256"] = source_sha256
                    report["database_transaction_read_only"] = True
        finally:
            engine.dispose()
        _write_private_json(args.private_output, report)
        print(json.dumps({
            k: v for k, v in report.items() if k != "details_private"
        }, ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as exc:
        # Fail closed; never emit private Case/Certificate UUIDs or DSN.
        print("CERTIFICATE_CASE_TARGET_WITNESS_BLOCKED: " +
              type(exc).__name__, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
