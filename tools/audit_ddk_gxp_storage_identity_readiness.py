"""Guarded storage lookup-input readiness for existing private DDK/GxP reviews.

Reads canonical Site/Case identity and immutable db.ktra year anchors.
Does not resolve folders, list NAS, read binaries, or approve DDK links.
"""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
from typing import Any

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from backend.app.db.models.phase1 import (
    BusinessEligibilityCertificate, Case, Certificate,
    LegacyInspectionStorageAnchor, Site, StorageBinding,
)
from tools.apply_ddk_gxp_provenance_rehearsal import checked_rehearsal_url
from tools.audit_ddk_gxp_canonical_candidates_readonly import _write_private_json
from tools.build_ddk_gxp_manual_review_queue import (
    _private_input, build_review_queue,
)
from tools.reconcile_ddk_site_owner_company_rehearsal import (
    classify_source_ddk_company_vs_site_owner,
)
from tools.env_utils import parse_env_file
from tools.preflight_ddk_gxp_rehearsal import EXPECTED_DB, EXPECTED_REVISION


SCHEMA = "GXP_DDK_EXCEPTION_STORAGE_IDENTITY_READINESS_V1"
_HASH = re.compile(r"^[0-9a-f]{64}$")


class StorageReadinessBlocked(ValueError):
    """Cannot attest lookup inputs from these observed records."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise StorageReadinessBlocked(message)


def classify_anchor(anchor: LegacyInspectionStorageAnchor | None) -> tuple[str, int | None]:
    """Classify the physical db.ktra year evidence; no date inference."""
    if anchor is None:
        return ("CASE_ANCHOR_METADATA_MISSING", None)
    _require(
        anchor.source_sheet == "db.ktra"
        and type(anchor.source_row) is int and anchor.source_row > 0
        and bool(_HASH.fullmatch(anchor.source_hash))
        and bool(_HASH.fullmatch(anchor.source_version)),
        "Source case anchor identity or integrity stamp malformed",
    )
    valid_statuses = {"usable", "unavailable", "conflict"}
    for status, year in (
        (anchor.registration_submission_status, anchor.registration_submission_year),
        (anchor.inspection_year_status, anchor.inspection_year),
    ):
        _require(status in valid_statuses
                 and ((status == "usable") == (
                     type(year) is int and 1900 <= year <= 2100
                 )) and (status == "usable" or year is None),
                 "Malformed recorded source-year status/value",
        )
    if anchor.registration_submission_status == "usable":
        return ("REGISTRATION_SOURCE_YEAR_USABLE", anchor.registration_submission_year)
    if anchor.registration_submission_status == "conflict":
        return ("REGISTRATION_SOURCE_YEAR_CONFLICT_NOT_RESOLVED", None)
    if anchor.inspection_year_status == "usable":
        return ("INSPECTION_SOURCE_YEAR_PRESENT_REGISTRATION_UNAVAILABLE",
                anchor.inspection_year)
    if anchor.inspection_year_status == "conflict":
        return ("INSPECTION_SOURCE_YEAR_CONFLICT_NOT_RESOLVED", None)
    return ("SOURCE_YEAR_UNAVAILABLE", None)


def profile_storage_lookup_inputs(session: Session, queue: dict[str, Any]) -> dict[str, Any]:
    """Read stable source identity fields only, never translate them to paths."""
    _require(
        queue.get("schema") == "GXP_DDK_EXCEPTION_MANUAL_REVIEW_QUEUE_V1"
        and queue.get("status") == "PRIVATE_REVIEW_ONLY_NOT_APPROVED"
        and queue.get("link_approval") == "NOT_APPROVED"
        and queue.get("manual_review_status") == "PENDING_INDEPENDENT_EVIDENCE"
        and queue.get("database_writes") == 0
        and queue.get("canonical_links_created") == 0,
        "Unexpected private queue contract",
    )
    tokens = queue.get("source_token_reviews")
    companies = queue.get("ddk_company_reviews")
    _require(isinstance(tokens, list) and isinstance(companies, list)
             and len(tokens) == queue.get("source_exception_token_records")
             and len(companies) == queue.get("ddk_company_review_records"),
             "Private review queue cardinality changed")
    company_source_reviews = {
        item["original_company_exception_evidence"]["legacy_dkkd_id"]:
            item["original_company_exception_evidence"]
        for item in companies
    }
    ddks = {
        x.legacy_dkkd_id: x for x in session.scalars(
            select(BusinessEligibilityCertificate)
        ) if x.legacy_dkkd_id is not None
    }
    certificates = {x.id: x for x in session.scalars(select(Certificate))}
    cases = {x.id: x for x in session.scalars(select(Case))}
    sites = {x.id: x for x in session.scalars(select(Site))}
    anchors = {x.case_id: x for x in session.scalars(
        select(LegacyInspectionStorageAnchor)
    )}
    bindings: dict[str, list[StorageBinding]] = {}
    for binding in session.scalars(select(StorageBinding)):
        if binding.case_id is not None:
            bindings.setdefault(binding.case_id, []).append(binding)

    counts: Counter[str] = Counter()
    private = []
    unique_ddk: set[str] = set()
    unique_certificate: set[str] = set()
    unique_case: set[str] = set()
    records = tokens + companies
    keys: set[str] = set()
    for item in records:
        key = item.get("review_key")
        _require(isinstance(key, str) and bool(key) and key not in keys
                 and item.get("review_status") == "PENDING_INDEPENDENT_EVIDENCE"
                 and item.get("link_approval") == "NOT_APPROVED",
                 "Missing or unapproved review identity")
        keys.add(key)
        source = item.get("original_exception_evidence")
        company = item.get("original_company_exception_evidence")
        _require((source is None) != (company is None),
                 "Review has ambiguous source ownership")
        original = source if source is not None else company
        legacy_ddk_id = original.get("legacy_dkkd_id")
        _require(type(legacy_ddk_id) is int, "Missing original DDK ID")
        ddk = ddks.get(legacy_ddk_id)
        _require(ddk is not None, "Canonical DDK original identity missing")
        ddk_site = sites.get(ddk.site_id)
        _require(ddk_site is not None, "DDK site canonical identity missing")
        company_state = classify_source_ddk_company_vs_site_owner(
            ddk_id=ddk.id, ddk_legacy_id=legacy_ddk_id,
            ddk_site_id=ddk.site_id,
            canonical_company_id=ddk.company_id,
            source_company_id=original.get("ddk_company_id"),
            source_site_id=original.get("ddk_site_id"),
            site_owner_company_id=ddk_site.company_id,
            company_review=company_source_reviews.get(legacy_ddk_id),
        )
        counts["DDK_COMPANY_" + company_state] += 1
        unique_ddk.add(ddk.id)
        ddk_site_key = ddk_site.legacy_site_id
        ddk_class = (
            "DDK_SITE_IDENTITY_INPUT_AVAILABLE_UNPROBED"
            if type(ddk_site_key) is int and ddk_site_key > 0
            else "DDK_LEGACY_SITE_ID_MISSING"
        )
        counts[ddk_class] += 1

        cert_record: dict[str, Any] | None = None
        case_record: dict[str, Any] | None = None
        if source is not None:
            cert_id = source.get("observed_certificate_id")
            _require(isinstance(cert_id, str) and bool(cert_id),
                     "Flagged token lacks the formerly identified canonical Certificate")
            cert = certificates.get(cert_id)
            _require(cert is not None
                     and cert.legacy_certificate_id == source.get("parsed_legacy_certificate_id")
                     and cert.site_id == source.get("certificate_site_id")
                     and cert.case_id == source.get("certificate_case_id")
                     and cert.certificate_type == source.get("certificate_type"),
                     "Observed canonical Certificate identity changed")
            unique_certificate.add(cert.id)
            cert_site = sites.get(cert.site_id)
            _require(cert_site is not None, "Certificate Site identity missing")
            cert_key = cert_site.legacy_site_id
            cert_class = (
                "CERTIFICATE_SITE_ID_AVAILABLE_REFERENCE_ONLY"
                if type(cert_key) is int and cert_key > 0
                else "CERTIFICATE_SITE_LEGACY_ID_MISSING"
            )
            counts[cert_class] += 1
            cert_record = {
                "certificate_id": cert.id,
                "certificate_site_id": cert.site_id,
                "certificate_site_legacy_id": cert_key,
                "status": cert_class,
                "folder_resolution_contract": "NOT_ASSIGNED_TO_CERTIFICATE",
            }
            if cert.case_id is not None:
                case = cases.get(cert.case_id)
                _require(case is not None and case.site_id == source.get("case_site_id")
                         and case.gxp_type == source.get("case_gxp_type"),
                         "Source Case and current Case identity disagree")
                unique_case.add(case.id)
                case_site = sites.get(case.site_id)
                _require(case_site is not None, "Originating Case Site missing")
                anchor_status, selected_year = classify_anchor(anchors.get(case.id))
                case_site_key = case_site.legacy_site_id
                key_ready = (
                    type(case_site_key) is int and case_site_key > 0
                    and isinstance(case.legacy_inspection_code, str)
                    and bool(case.legacy_inspection_code.strip())
                )
                case_class = (
                    "CASE_LOOKUP_INPUT_AVAILABLE_UNPROBED"
                    if key_ready and selected_year is not None
                    else "CASE_LOOKUP_INPUT_INCOMPLETE"
                )
                counts[case_class] += 1
                counts["CASE_ANCHOR_" + anchor_status] += 1
                observed_bindings = bindings.get(case.id, [])
                counts["CASE_BINDING_ROWS_PRESENT_UNVERIFIED" if observed_bindings else
                       "CASE_BINDING_ROWS_ABSENT"] += 1
                case_record = {
                    "case_id": case.id,
                    "case_site_id": case.site_id,
                    "case_site_legacy_id": case_site_key,
                    "case_legacy_inspection_code": case.legacy_inspection_code,
                    "anchor_classification": anchor_status,
                    "source_year_observed": selected_year,
                    "lookup_input_classification": case_class,
                    "recorded_storage_binding_ids_unverified": [
                        x.id for x in observed_bindings
                    ],
                }
            else:
                counts["CERTIFICATE_WITHOUT_CASE_NO_INSPECTION_FOLDER_INFERENCE"] += 1
        else:
            counts["COMPANY_REVIEW_HAS_NO_CERTIFICATE_OR_CASE_TARGET"] += 1

        private.append({
            "review_key": key,
            "review_status": "PENDING_INDEPENDENT_EVIDENCE",
            "link_approval": "NOT_APPROVED",
            "ddk": {
                "canonical_id": ddk.id, "site_id": ddk.site_id,
                "site_legacy_id": ddk_site_key,
                "lookup_input_classification": ddk_class,
            },
            "certificate_reference": cert_record,
            "originating_case_reference": case_record,
        })

    return {
        "schema": SCHEMA,
        "status": "INPUT_IDENTITIES_ONLY_NO_STORAGE_PROBE",
        "approval_status": "NOT_APPROVED",
        "review_records": len(records),
        "source_token_review_records": len(tokens),
        "ddk_company_review_records": len(companies),
        "unique_ddk_count": len(unique_ddk),
        "unique_certificate_count": len(unique_certificate),
        "unique_originating_case_count": len(unique_case),
        "lookup_input_classification_counts": dict(sorted(counts.items())),
        "storage_roots_accessed": False,
        "storage_folders_enumerated": False,
        "storage_binaries_verified": False,
        "canonical_links_created": 0,
        "database_writes": 0,
        "private_lookup_input_evidence": private,
        "limitations": [
            "Lookup inputs are source keys, not proven filesystem folder locations",
            "Case folder lookup belongs to Case Site, not Certificate or DDK Site",
            "A recorded storage binding may be stale and is not verified by this audit",
            "No Certificate-folder mapping can be inferred from Site legacy ID",
            "No stored input or scope justifies a canonical DDK-to-Certificate link",
        ],
    }


def scan_rehearsal(database_url: str, queue: dict[str, Any]) -> dict[str, Any]:
    engine = create_engine(database_url, poolclass=NullPool, connect_args={
        "options": "-c default_transaction_read_only=on -c statement_timeout=30000",
    })
    try:
        with engine.connect() as conn:
            with conn.begin():
                conn.exec_driver_sql("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
                _require(conn.execute(text("SELECT current_database()")).scalar_one() == EXPECTED_DB
                         and conn.execute(text("SHOW transaction_read_only")).scalar_one() == "on"
                         and conn.execute(text("SHOW transaction_isolation")).scalar_one() == "repeatable read",
                         "Not a stable read-only rehearsal transaction")
                _require(list(conn.execute(text("SELECT version_num FROM public.alembic_version")).scalars()) == [
                    EXPECTED_REVISION
                ], "Unexpected schema revision")
                with Session(bind=conn, autoflush=False) as session:
                    return profile_storage_lookup_inputs(session, queue)
    finally:
        engine.dispose()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dossier-json", type=Path, required=True)
    ap.add_argument("--queue-json", type=Path, required=True)
    ap.add_argument("--runtime-env", type=Path, default=Path("/etc/gxp/runtime.env"))
    ap.add_argument("--details-json", type=Path)
    args = ap.parse_args(argv)
    try:
        _require(args.queue_json.parent.resolve() == args.dossier_json.parent.resolve()
                 and (args.details_json is None
                      or args.details_json.parent.resolve() == args.dossier_json.parent.resolve()),
                 "Private inputs/output must share their protected directory")
        dossier_bytes = _private_input(args.dossier_json)
        queue_bytes = _private_input(args.queue_json)
        dossier = json.loads(dossier_bytes)
        queue = json.loads(queue_bytes)
        _require(queue == build_review_queue(dossier),
                 "Queue differs from original validated source evidence")
        _require(queue.get("source_tokens_checked") == 861
                 and queue.get("source_exception_token_records") == 8
                 and queue.get("ddk_company_review_records") == 1,
                 "Unexpected observed corpus/review population")
        database_url = checked_rehearsal_url(parse_env_file(args.runtime_env))
        report = scan_rehearsal(database_url, queue)
        if args.details_json is not None:
            _require(not args.details_json.exists() and not args.details_json.is_symlink(),
                     "Refuse to overwrite private report")
            _write_private_json(args.details_json, report)
        safe = {k: v for k, v in report.items()
                if k not in {"private_lookup_input_evidence", "limitations"}}
        safe["input_queue_sha256"] = sha256(queue_bytes).hexdigest()
        print(json.dumps(safe, ensure_ascii=False, sort_keys=True))
        return 0
    except (ValueError, OSError, KeyError, TypeError):
        print("DDK_STORAGE_IDENTITY_READINESS_BLOCKED", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
