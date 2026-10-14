"""Read-only document-metadata coverage for private ĐĐK/GxP review queue.

A document row or locator is NOT evidence of verified binary content,
Site coverage, lifecycle GRANTED, or authority for a canonical link.
No document downloads, storage probes, writes to PostgreSQL, or source import.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any

from sqlalchemy import create_engine, or_, select, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from backend.app.db.models.phase1 import (
    BusinessEligibilityCertificate, Case, Certificate,
    Document, DocumentVariant, DocumentVersion,
)
from tools.apply_ddk_gxp_provenance_rehearsal import checked_rehearsal_url
from tools.audit_ddk_gxp_canonical_candidates_readonly import _write_private_json
from tools.build_ddk_gxp_manual_review_queue import (
    _private_input, build_review_queue, SCHEMA as QUEUE_SCHEMA,
)
from tools.env_utils import parse_env_file
from tools.preflight_ddk_gxp_rehearsal import EXPECTED_DB, EXPECTED_REVISION


SCHEMA = "GXP_DDK_REVIEW_DOCUMENT_METADATA_COVERAGE_V1"
ROLES = ("DDK", "CERTIFICATE", "ORIGINATING_CASE")


class DocumentCoverageBlocked(ValueError):
    """Incomplete queue, unexpected source identity or non-rehearsal DB."""


def scan_document_metadata(session: Session, queue: dict[str, Any]) -> dict[str, Any]:
    """Inspect only stored parent/variant/version metadata for flagged reviews."""
    if (
        queue.get("schema") != QUEUE_SCHEMA
        or queue.get("link_approval") != "NOT_APPROVED"
        or queue.get("manual_review_status") != "PENDING_INDEPENDENT_EVIDENCE"
        or queue.get("database_writes") != 0
        or queue.get("canonical_links_created") != 0
    ):
        raise DocumentCoverageBlocked("Private review queue is not an unapproved source")
    originals = queue.get("source_token_reviews")
    company_reviews = queue.get("ddk_company_reviews")
    if not isinstance(originals, list) or not isinstance(company_reviews, list):
        raise DocumentCoverageBlocked("Missing review records")
    if len(originals) != queue.get("source_exception_token_records") or len(
        company_reviews
    ) != queue.get("ddk_company_review_records"):
        raise DocumentCoverageBlocked("Review cardinality drift")

    all_reviews = originals + company_reviews
    keys = [entry.get("review_key") for entry in all_reviews]
    if (any(not isinstance(k, str) or not k for k in keys)
            or len(keys) != len(set(keys))):
        raise DocumentCoverageBlocked("Duplicate or invalid review identity")
    legacy_ddk_ids = {
        x["original_exception_evidence"]["legacy_dkkd_id"] for x in originals
    } | {
        x["original_company_exception_evidence"]["legacy_dkkd_id"]
        for x in company_reviews
    }
    canonical_ddks = {
        x.legacy_dkkd_id: x for x in session.scalars(
            select(BusinessEligibilityCertificate).where(
                BusinessEligibilityCertificate.legacy_dkkd_id.in_(legacy_ddk_ids)
            )
        )
    }
    candidate_certificate_ids = {
        x["original_exception_evidence"]["observed_certificate_id"]
        for x in originals
        if x["original_exception_evidence"].get("observed_certificate_id")
    }
    case_ids = {
        x["original_exception_evidence"]["certificate_case_id"]
        for x in originals
        if x["original_exception_evidence"].get("certificate_case_id")
    }
    certificates = {
        x.id: x for x in session.scalars(
            select(Certificate).where(Certificate.id.in_(candidate_certificate_ids))
        )
    }
    cases = {
        x.id: x for x in session.scalars(select(Case).where(Case.id.in_(case_ids)))
    }
    ddk_ids = {x.id for x in canonical_ddks.values()}
    conditions = []
    if ddk_ids:
        conditions.append(Document.business_eligibility_certificate_id.in_(ddk_ids))
    if candidate_certificate_ids:
        conditions.append(Document.certificate_id.in_(candidate_certificate_ids))
    if case_ids:
        conditions.append(Document.case_id.in_(case_ids))
    docs = list(session.scalars(select(Document).where(or_(*conditions)))) if conditions else []
    doc_ids = [x.id for x in docs]
    variants = list(session.scalars(
        select(DocumentVariant).where(DocumentVariant.document_id.in_(doc_ids))
    )) if doc_ids else []
    variant_ids = [x.id for x in variants]
    versions = list(session.scalars(
        select(DocumentVersion).where(
            DocumentVersion.document_variant_id.in_(variant_ids)
        )
    )) if variant_ids else []

    variants_by_doc = defaultdict(list)
    versions_by_variant = defaultdict(list)
    docs_by_parent: dict[tuple[str, str], list[Document]] = defaultdict(list)
    for v in variants:
        variants_by_doc[v.document_id].append(v)
    for v in versions:
        versions_by_variant[v.document_variant_id].append(v)
    for doc in docs:
        if doc.business_eligibility_certificate_id in ddk_ids:
            docs_by_parent[("DDK", doc.business_eligibility_certificate_id)].append(doc)
        if doc.certificate_id in candidate_certificate_ids:
            docs_by_parent[("CERTIFICATE", doc.certificate_id)].append(doc)
        if doc.case_id in case_ids:
            docs_by_parent[("ORIGINATING_CASE", doc.case_id)].append(doc)

    counts = Counter()
    private_rows = []
    unique_targets: dict[str, set[str]] = {r: set() for r in ROLES}
    for item in all_reviews:
        token = item.get("original_exception_evidence")
        if token is not None:
            legacy_id = token["legacy_dkkd_id"]
            ddk = canonical_ddks.get(legacy_id)
            if (ddk is None or ddk.site_id != token.get("ddk_site_id")
                    or ddk.company_id != token.get("ddk_company_id")):
                raise DocumentCoverageBlocked("Canonical DDK source identity changed")
            cert_id = token.get("observed_certificate_id")
            if cert_id is not None:
                cert = certificates.get(cert_id)
                if cert is None or cert.legacy_certificate_id != token.get(
                    "parsed_legacy_certificate_id"
                ) or cert.site_id != token.get("certificate_site_id"):
                    raise DocumentCoverageBlocked("Certificate source identity no longer matches")
            case_id = token.get("certificate_case_id")
            if case_id is not None:
                case = cases.get(case_id)
                if case is None or case.site_id != token.get("case_site_id"):
                    raise DocumentCoverageBlocked("Originating Case identity no longer matches")
                if cert_id and certificates[cert_id].case_id != case_id:
                    raise DocumentCoverageBlocked("Certificate no longer points to source Case")
            if cert_id is not None and certificates[cert_id].case_id != case_id:
                raise DocumentCoverageBlocked("Certificate Case linkage changed")
            targets = {
                "DDK": ddk.id,
                "CERTIFICATE": cert_id,
                "ORIGINATING_CASE": case_id,
            }
        else:
            company = item.get("original_company_exception_evidence")
            if not isinstance(company, dict):
                raise DocumentCoverageBlocked("Unknown private review kind")
            ddk = canonical_ddks.get(company["legacy_dkkd_id"])
            if (ddk is None
                    or ddk.id != company["canonical_business_eligibility_certificate_id"]
                    or ddk.company_id != company["ddk_company_id"]
                    or ddk.site_id != company["ddk_site_id"]):
                raise DocumentCoverageBlocked("DDK owning-company review identity changed")
            targets = {"DDK": ddk.id, "CERTIFICATE": None, "ORIGINATING_CASE": None}

        row = {
            "review_key": item["review_key"],
            "review_status": "PENDING_INDEPENDENT_EVIDENCE",
            "link_approval": "NOT_APPROVED",
            "targets": [],
        }
        for role in ROLES:
            target_id = targets[role]
            if target_id is None:
                counts[f"{role}_not_linked"] += 1
                row["targets"].append({"role": role, "parent_id": None,
                                       "metadata_classification": "NOT_LINKED",
                                       "documents": []})
                continue
            unique_targets[role].add(target_id)
            matching = sorted(docs_by_parent.get((role, target_id), []), key=lambda x: x.id)
            doc_records = []
            has_locator = False
            for doc in matching:
                var_records = []
                for variant in sorted(variants_by_doc[doc.id], key=lambda x: x.id):
                    vers = []
                    for version in sorted(versions_by_variant[variant.id],
                                          key=lambda x: (x.version_no, x.id)):
                        locator = version.storage_root is not None and version.storage_relative_path is not None
                        has_locator |= locator
                        vers.append({
                            "document_version_id": version.id,
                            "version_no": version.version_no,
                            "storage_locator_recorded_not_verified": locator,
                            "checksum_metadata_present": bool(version.checksum_sha256),
                        })
                    var_records.append({
                        "document_variant_id": variant.id,
                        "variant_type": variant.variant_type.value,
                        "stored_version_metadata": vers,
                    })
                doc_records.append({
                    "document_id": doc.id,
                    "family_code": doc.family_code,
                    "document_type_code": doc.document_type_code,
                    "variants": var_records,
                })
            if not matching:
                classification = "NO_DOCUMENT_METADATA"
            elif has_locator:
                classification = "STORAGE_LOCATOR_RECORDED_UNVERIFIED"
            else:
                classification = "DOCUMENT_METADATA_WITHOUT_STORAGE_LOCATOR"
            counts[f"{role}_{classification}"] += 1
            row["targets"].append({
                "role": role, "parent_id": target_id,
                "metadata_classification": classification,
                "documents": doc_records,
            })
        private_rows.append(row)

    return {
        "schema": SCHEMA,
        "status": "METADATA_ONLY_NOT_REGULATORY_EVIDENCE",
        "approval_status": "NOT_APPROVED",
        "review_records": len(all_reviews),
        "source_token_review_records": len(originals),
        "ddk_company_review_records": len(company_reviews),
        "unique_parent_counts": {x: len(unique_targets[x]) for x in ROLES},
        "parent_review_classification_counts": dict(sorted(counts.items())),
        "database_writes": 0,
        "canonical_links_created": 0,
        "binary_content_verified": False,
        "storage_paths_probed": False,
        "private_review_document_metadata": private_rows,
        "limitations": [
            "Document/variant/version metadata is not proof that a binary exists",
            "A recorded locator and checksum do not prove legal or technical authenticity",
            "No document coverage count proves GxP grant or Site/Case scope",
            "Source ID CC and recorded canonical FK identities remain unapproved",
        ],
    }


def audit_rehearsal(database_url: str, queue: dict[str, Any]) -> dict[str, Any]:
    engine = create_engine(
        database_url, poolclass=NullPool,
        connect_args={
            "options": "-c default_transaction_read_only=on -c statement_timeout=30000"
        },
    )
    try:
        with engine.connect() as conn, conn.begin():
            conn.exec_driver_sql("SET TRANSACTION READ ONLY")
            if (conn.execute(text("SELECT current_database()")).scalar_one() != EXPECTED_DB
                    or conn.execute(text("SHOW transaction_read_only")).scalar_one() != "on"):
                raise DocumentCoverageBlocked("Not the guarded read-only rehearsal database")
            if list(conn.execute(text("SELECT version_num FROM public.alembic_version")).scalars()) != [
                EXPECTED_REVISION
            ]:
                raise DocumentCoverageBlocked("Unexpected rehearsal migration revision")
            with Session(bind=conn) as session:
                return scan_document_metadata(session, queue)
    finally:
        engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dossier-json", type=Path, required=True)
    parser.add_argument("--queue-json", type=Path, required=True)
    parser.add_argument("--runtime-env", type=Path, default=Path("/etc/gxp/runtime.env"))
    parser.add_argument("--details-json", type=Path)
    args = parser.parse_args(argv)
    try:
        if (args.dossier_json.parent.resolve() != args.queue_json.parent.resolve()
                or (args.details_json is not None
                    and args.details_json.parent.resolve() != args.queue_json.parent.resolve())):
            raise DocumentCoverageBlocked("All private source/output must be in same directory")
        dossier_bytes = _private_input(args.dossier_json)
        queue_bytes = _private_input(args.queue_json)
        dossier = json.loads(dossier_bytes)
        queue = json.loads(queue_bytes)
        if queue != build_review_queue(dossier):
            raise DocumentCoverageBlocked("Private queue does not equal validated source dossier")
        if queue["source_tokens_checked"] != 861 or len(queue["source_token_reviews"]) != 8 or len(
            queue["ddk_company_reviews"]
        ) != 1:
            raise DocumentCoverageBlocked("Unexpected accepted corpus/review population")
        url = checked_rehearsal_url(parse_env_file(args.runtime_env))
        result = audit_rehearsal(url, queue)
        if args.details_json is not None:
            if args.details_json.exists() or args.details_json.is_symlink():
                raise DocumentCoverageBlocked("Private details already exist")
            _write_private_json(args.details_json, result)
        safe = {
            key: value for key, value in result.items()
            if key not in {"private_review_document_metadata", "limitations"}
        }
        safe["input_queue_sha256"] = sha256(queue_bytes).hexdigest()
        print(json.dumps(safe, ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, ValueError, TypeError, KeyError):
        print("DDK_DOCUMENT_METADATA_AUDIT_BLOCKED", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
