"""Explicitly guarded DDK Company correction using db.cso Site ownership.

Default mode is READ-ONLY. --apply touches only the DDK aggregate's
company_id; the original workbook, source reference groups and raw
company identity remain unchanged. Does not establish GxP certification
coverage or create a DDK-to-GxP link.

Only gxp_legacy_rehearsal with an independently protected source dossier
is accepted. No production endpoint or generic database URL.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
from typing import Any

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from backend.app.db.models.phase1 import (
    BusinessEligibilityCertificate, BusinessEligibilityCertificateLink,
    BusinessEligibilityGxpSourceGroup, Company, Site,
)
from tools.apply_ddk_gxp_provenance_rehearsal import checked_rehearsal_url
from tools.audit_ddk_gxp_canonical_candidates_readonly import EXPECTED_WORKBOOK_SHA256
from tools.build_ddk_gxp_manual_review_queue import _private_input, build_review_queue
from tools.env_utils import parse_env_file
from tools.preflight_ddk_gxp_rehearsal import EXPECTED_DB, EXPECTED_REVISION

SCHEMA = "GXP_DDK_SITE_OWNER_CANONICAL_COMPANY_RECONCILIATION_V1"


class SiteOwnerCorrectionBlocked(ValueError):
    pass


def _check(test: bool, message: str) -> None:
    if not test:
        raise SiteOwnerCorrectionBlocked(message)


def classify_source_ddk_company_vs_site_owner(
    *,
    ddk_id: str,
    ddk_legacy_id: int,
    ddk_site_id: str,
    canonical_company_id: str,
    source_company_id: str,
    source_site_id: str,
    site_owner_company_id: str,
    company_review: dict[str, Any] | None,
) -> str:
    """Source/company mismatch is preserved while canonical ownership transitions.

    Only an independently recorded original Company exception may carry both
    pre-correction and Site-authoritative post-correction states. All other
    records MUST already agree with the db.cso Site -> Company relation.
    """
    _check(ddk_site_id == source_site_id, "DDK original Site identity changed")
    if source_company_id == site_owner_company_id:
        _check(canonical_company_id == site_owner_company_id,
               "Canonical DDK Company differs from authoritative Site owner")
        _check(company_review is None, "Unexpected Company discrepancy record")
        return "SOURCE_AND_CANONICAL_SITE_OWNER_AGREE"
    _check(
        isinstance(company_review, dict)
        and company_review.get("legacy_dkkd_id") == ddk_legacy_id
        and company_review.get("canonical_business_eligibility_certificate_id") == ddk_id
        and company_review.get("ddk_site_id") == ddk_site_id
        and company_review.get("ddk_company_id") == source_company_id
        and company_review.get("site_owning_company_id") == site_owner_company_id
        and company_review.get("link_approval") == "NOT_APPROVED"
        and canonical_company_id in (source_company_id, site_owner_company_id),
        "Unattested Site/Company inconsistency or changed canonical DDK",
    )
    return ("SOURCE_DISCREPANCY_CANONICAL_SITE_OWNER_ALIGNED"
            if canonical_company_id == site_owner_company_id
            else "SOURCE_DISCREPANCY_CANONICAL_NOT_YET_ALIGNED")


def plan_site_owner_correction(
    session: Session, dossier: dict[str, Any],
) -> dict[str, Any]:
    """Prepare one original-source-attested Company-only correction.

    Uses only actual Site.company_id (db.cso owner), not a Certificate or
    another DDK's site, to choose a canonical Company. This function
    never changes database records. An unexpected mismatch blocks all.
    """
    queue = build_review_queue(dossier)
    _check(
        dossier.get("source_workbook_sha256") == EXPECTED_WORKBOOK_SHA256
        and queue.get("source_tokens_checked") == 861
        and queue.get("source_exception_token_records") == 8
        and queue.get("ddk_company_review_records") == 1
        and queue.get("link_approval") == "NOT_APPROVED",
        "Pinned physical source/exception population changed",
    )
    reviews = queue["ddk_company_reviews"]
    _check(len(reviews) == 1, "Expected one independently source-attested Company discrepancy")
    original = reviews[0]["original_company_exception_evidence"]
    _check(
        original.get("link_approval") == "NOT_APPROVED"
        and original.get("review_status") == "REQUIRES_INDEPENDENT_ADJUDICATION"
        and type(original.get("legacy_dkkd_id")) is int
        and isinstance(original.get("ddk_site_id"), str)
        and isinstance(original.get("ddk_company_id"), str)
        and isinstance(original.get("site_owning_company_id"), str)
        and original["ddk_company_id"] != original["site_owning_company_id"],
        "Source Company conflict identity missing",
    )
    ddks = list(session.scalars(select(BusinessEligibilityCertificate)))
    _check(len(ddks) == 780, "Unexpected rehearsal DDK population")
    sites = {site.id: site for site in session.scalars(select(Site))}
    _check(len(sites) == len(set(sites)), "Duplicate canonical Site UUIDs")
    companies = {company.id: company for company in session.scalars(select(Company))}
    mismatches = []
    for ddk in ddks:
        site = sites.get(ddk.site_id)
        _check(
            site is not None and site.company_id in companies
            and site.legacy_site_id is not None,
            "DDK points to an absent/non-source canonical Site owner",
        )
        if ddk.company_id != site.company_id:
            mismatches.append((ddk, site))
    _check(len(mismatches) <= 1, "More than the approved source discrepancy was found")
    target = next((d for d in ddks if d.legacy_dkkd_id == original["legacy_dkkd_id"]), None)
    _check(
        target is not None
        and target.id == original["canonical_business_eligibility_certificate_id"]
        and target.site_id == original["ddk_site_id"]
        and target.site_id in sites,
        "Original DDK identity is not the imported one",
    )
    site = sites[target.site_id]
    _check(
        site.company_id == original["site_owning_company_id"]
        and type(companies[site.company_id].legacy_company_id) is int,
        "Source Site-to-Company owner changed",
    )
    _check(
        target.company_id in {original["ddk_company_id"], site.company_id},
        "DDK company unexpectedly changed since dossier was captured",
    )
    if mismatches:
        _check(
            len(mismatches) == 1 and mismatches[0][0].id == target.id
            and mismatches[0][1].id == site.id
            and target.company_id == original["ddk_company_id"],
            "Unexpected Company mismatch outside original source record",
        )
    _check(
        session.scalar(select(func.count()).select_from(
            BusinessEligibilityCertificateLink)) == 0,
        "Canonical DDK/GxP links are no longer empty",
    )
    _check(
        session.scalar(select(func.count()).select_from(
            BusinessEligibilityGxpSourceGroup)) == 3120,
        "Pinned four-group original reference evidence changed",
    )
    return {
        "schema": SCHEMA,
        "database": EXPECTED_DB,
        "source_workbook_sha256": EXPECTED_WORKBOOK_SHA256,
        "ddk_rows_checked": len(ddks),
        "source_company_conflicts": 1,
        "canonical_company_mismatches": len(mismatches),
        "status": "NEEDS_ONE_CANONICAL_COMPANY_CORRECTION" if mismatches
                  else "ALREADY_ALIGNED_SOURCE_CONFLICT_RETAINED",
        "approval_status_for_ddk_gxp_links": "NOT_APPROVED",
        "source_workbook_changed": False,
        "site_owner_changed": False,
        "case_site_changed": False,
        "certificate_site_changed": False,
        "canonical_links_created": 0,
        "private_target_ddk_id": target.id,
        "private_target_legacy_ddk_id": target.legacy_dkkd_id,
        "private_previous_company_id": target.company_id,
        "private_correct_company_id": site.company_id,
    }


def run(database_url: str, dossier: dict[str, Any], *, apply: bool) -> dict[str, Any]:
    # Python library callers cannot bypass checked local rehearsal DB identity
    # or explicit transaction mode.
    from sqlalchemy.engine import make_url
    u = make_url(database_url)
    _check(
        u.get_backend_name() == "postgresql"
        and u.database == EXPECTED_DB and u.username == "gxp_app"
        and u.host in ("127.0.0.1", "localhost", "::1") and not u.query,
        "Expected strict local rehearsal target",
    )
    options = {
        "options": "-c statement_timeout=30000 -c lock_timeout=5000" +
                   ("" if apply else " -c default_transaction_read_only=on"),
    }
    engine = create_engine(database_url, poolclass=NullPool, connect_args=options)
    try:
        with engine.begin() as conn:
            db = conn.execute(text("SELECT current_database()")).scalar_one()
            rev = conn.execute(text("SELECT version_num FROM public.alembic_version")).scalar_one()
            ro = conn.execute(text("SELECT current_setting('transaction_read_only')")).scalar_one()
            _check(db == EXPECTED_DB and rev == EXPECTED_REVISION
                   and ro == ("off" if apply else "on"),
                   "Wrong DB/revision or transaction mode")
            with Session(bind=conn, autoflush=False) as session:
                report = plan_site_owner_correction(session, dossier)
                if apply and report["canonical_company_mismatches"] == 1:
                    ddk = session.get(
                        BusinessEligibilityCertificate,
                        report["private_target_ddk_id"],
                        with_for_update=True,
                    )
                    _check(
                        ddk is not None
                        and ddk.company_id == report["private_previous_company_id"]
                        and ddk.site_id == session.get(Site, ddk.site_id).id
                        and session.get(Site, ddk.site_id).company_id ==
                            report["private_correct_company_id"],
                        "Target changed after locked preflight",
                    )
                    ddk.company_id = report["private_correct_company_id"]
                    session.flush()
                    _check(
                        ddk.company_id == session.get(Site, ddk.site_id).company_id
                        and session.scalar(select(func.count()).select_from(
                            BusinessEligibilityCertificateLink)) == 0,
                        "Post-correction Site ownership or link-count drift",
                    )
                report["applied_company_updates"] = (
                    1 if apply and report["canonical_company_mismatches"] == 1 else 0
                )
                report["mode"] = "REHEARSAL_APPLY" if apply else "READ_ONLY_PLAN"
                return report
    finally:
        engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-env", type=Path, default=Path("/etc/gxp/runtime.env"))
    parser.add_argument("--dossier-json", type=Path, required=True)
    parser.add_argument("--expected-dossier-sha256", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-target")
    args = parser.parse_args(argv)
    try:
        if args.apply:
            _check(args.confirm_target == EXPECTED_DB,
                   "Explicit rehearsal apply confirmation missing")
        elif args.confirm_target is not None:
            raise SiteOwnerCorrectionBlocked("Confirmation flag is apply-only")
        original = _private_input(args.dossier_json)
        _check(
            bool(re.fullmatch(r"[0-9a-f]{64}", args.expected_dossier_sha256))
            and sha256(original).hexdigest() == args.expected_dossier_sha256,
            "Private dossier SHA changed",
        )
        url = checked_rehearsal_url(parse_env_file(args.runtime_env))
        result = run(url, json.loads(original), apply=args.apply)
        public = {k: v for k, v in result.items() if not k.startswith("private_")}
        print(json.dumps(public, ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as exc:
        # Even a database driver/permission error must never print a DSN,
        # original Company IDs or private source values on stdout/stderr.
        print("DDK_SITE_OWNER_COMPANY_RECONCILIATION_BLOCKED: " +
              type(exc).__name__, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
