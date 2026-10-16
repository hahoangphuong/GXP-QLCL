"""Read-only primary-document metadata inventory for unresolved Certificate→Case anchors.

Revalidates sealed source snapshot against canonical rehearsal under the SAME
read-only DB transaction before reading Document/Variant/Version metadata.
A recorded document, locator or checksum is NOT an inspected issuance decision,
not proven storage/binary content and never Site/Cases coverage approval.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any

from sqlalchemy import create_engine, or_, select, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from backend.app.db.models.phase1 import Document, DocumentVariant, DocumentVersion
from backend.app.domain.legacy_certificate_case_source_audit import (
    audit_certificate_case_source_links,
)
from backend.app.domain.phase2_import import load_confirmed_blanked_row_keys
from tools.apply_ddk_gxp_provenance_rehearsal import checked_rehearsal_url
from tools.audit_certificate_case_site_owners_rehearsal_readonly import (
    EXPECTED_SNAPSHOT_SHA256, EXPECTED_SOURCE_CERTIFICATES, SCHEMA as ANCHOR_SCHEMA,
    compare_source_to_rehearsal,
)
from tools.audit_ddk_gxp_canonical_candidates_readonly import _write_private_json
from tools.env_utils import parse_env_file
from tools.preflight_ddk_gxp_rehearsal import EXPECTED_DB, EXPECTED_REVISION

SCHEMA = "GXP_CERTIFICATE_CASE_ISSUANCE_DOCUMENT_METADATA_V1"
STATUS = "METADATA_ONLY_PRIMARY_DOCUMENT_NOT_VERIFIED"


class IssuanceEvidenceMetadataBlocked(ValueError):
    pass


def _require(value: bool, reason: str) -> None:
    if not value:
        raise IssuanceEvidenceMetadataBlocked(reason)


def scan_issuance_document_metadata(
    session: Session, anchor: dict[str, Any],
) -> dict[str, Any]:
    """Pure read projection: source Cases are separate evidence owners, not substitute Cases."""
    _require(
        anchor.get("schema") == ANCHOR_SCHEMA
        and anchor.get("status") == "SOURCE_AND_CANONICAL_ANCHORS_VERIFIED_COVERAGE_NOT_APPROVED"
        and anchor.get("database") == EXPECTED_DB
        and anchor.get("database_writes") == 0
        and anchor.get("nas_reads") == 0
        and anchor.get("case_rebinding_authorized") is False
        and anchor.get("canonical_ddk_gxp_links_approved") is False
        and anchor.get("site_specific_scope_coverage_approved") is False,
        "Unverified or already-approved Certificate/Case anchor",
    )
    details = anchor.get("details_private")
    _require(isinstance(details, list) and len(details) == len(EXPECTED_SOURCE_CERTIFICATES),
             "Incomplete private anchor set")
    ids = [x.get("legacy_certificate_id") for x in details]
    _require(set(ids) == EXPECTED_SOURCE_CERTIFICATES and len(set(ids)) == len(ids),
             "Different source Certificate set")
    _require(
        anchor.get("counts", {}).get("source_certificate_version_fidelity_verified")
        == len(EXPECTED_SOURCE_CERTIFICATES)
        and anchor.get("counts", {}).get("stored_certificate_versions")
        == len(EXPECTED_SOURCE_CERTIFICATES),
        "Certificate import-value provenance not verified",
    )

    cert_ids: set[str] = set()
    case_ids: set[str] = set()
    target_rows: list[dict[str, Any]] = []
    for item in sorted(details, key=lambda x: x["legacy_certificate_id"]):
        cert_id = item.get("certificate_id")
        original_case_id = item.get("original_linked_case_id")
        reverse = item.get("reverse_case_review_candidates")
        versions = item.get("certificate_versions")
        _require(
            isinstance(cert_id, str) and bool(cert_id)
            and isinstance(original_case_id, str) and bool(original_case_id)
            and item.get("legal_coverage_approved") is False
            and item.get("case_rebinding_authorized") is False
            and isinstance(reverse, list) and isinstance(versions, list)
            and len(versions) == 1
            and versions[0].get("original_import_value_fidelity_verified") is True
            and versions[0].get("site_specific_scope_coverage_verified") is False,
            "Incomplete or approved Certificate target",
        )
        cases = [("ORIGINAL_CASE", original_case_id)]
        for alternate in reverse:
            _require(
                isinstance(alternate.get("case_id"), str)
                and bool(alternate["case_id"])
                and alternate.get("remediation_authorized") is False
                and alternate.get("primary_signed_issuance_case_link_verified") is False,
                "Invalid reverse-Case review candidate",
            )
            cases.append(("REVERSE_CASE_CANDIDATE", alternate["case_id"]))
        _require(len({(kind, id_) for kind, id_ in cases}) == len(cases),
                 "Duplicate source Case review target")
        cert_ids.add(cert_id)
        case_ids.update(id_ for _, id_ in cases)
        target_rows.append({
            "legacy_certificate_id": item["legacy_certificate_id"],
            "certificate_uuid": cert_id,
            "original_case_legacy_id": item["original_case_legacy_id"],
            "cases": cases,
        })
    _require(len(cert_ids) == len(target_rows),
             "Two legacy Certificates share one canonical identity")

    clauses = [Document.certificate_id.in_(cert_ids), Document.case_id.in_(case_ids)]
    documents = list(session.scalars(select(Document).where(or_(*clauses))))
    _require(len({d.id for d in documents}) == len(documents),
             "Duplicate Document primary identity")
    doc_ids = {d.id for d in documents}
    variants = list(session.scalars(
        select(DocumentVariant).where(DocumentVariant.document_id.in_(doc_ids))
    )) if doc_ids else []
    _require(len({v.id for v in variants}) == len(variants),
             "Duplicate DocumentVariant primary identity")
    by_document: dict[str, list[DocumentVariant]] = defaultdict(list)
    for variant in variants:
        by_document[variant.document_id].append(variant)
    version_rows = list(session.scalars(select(DocumentVersion).where(
        DocumentVersion.document_variant_id.in_({v.id for v in variants})
    ))) if variants else []
    _require(len({v.id for v in version_rows}) == len(version_rows),
             "Duplicate DocumentVersion primary identity")
    by_variant: dict[str, list[DocumentVersion]] = defaultdict(list)
    for version in version_rows:
        by_variant[version.document_variant_id].append(version)

    docs_for_cert: dict[str, list[Document]] = defaultdict(list)
    docs_for_case: dict[str, list[Document]] = defaultdict(list)
    for doc in documents:
        if doc.certificate_id in cert_ids:
            docs_for_cert[doc.certificate_id].append(doc)
        if doc.case_id in case_ids:
            docs_for_case[doc.case_id].append(doc)

    counts: Counter[str] = Counter()
    private_targets: list[dict[str, Any]] = []
    unique_docs_by_role: dict[str, set[str]] = defaultdict(set)
    for target in target_rows:
        requested = [("CERTIFICATE", target["certificate_uuid"])] + target["cases"]
        for role, parent_uuid in requested:
            chosen = docs_for_cert[parent_uuid] if role == "CERTIFICATE" else docs_for_case[parent_uuid]
            inventory = []
            for doc in sorted(chosen, key=lambda x: x.id):
                unique_docs_by_role[role].add(doc.id)
                variants_private = []
                for variant in sorted(by_document[doc.id], key=lambda x: x.id):
                    versions_private = []
                    for doc_version in sorted(
                        by_variant[variant.id], key=lambda x: (x.version_no, x.id)
                    ):
                        locator = (doc_version.storage_root is not None
                                   and doc_version.storage_relative_path is not None)
                        checksum = bool(doc_version.checksum_sha256)
                        counts["document_version_rows"] += 1
                        if locator:
                            counts["recorded_locator_not_verified"] += 1
                        if checksum:
                            counts["recorded_checksum_not_verified"] += 1
                        versions_private.append({
                            "document_version_uuid": doc_version.id,
                            "version_no": doc_version.version_no,
                            "storage_binding_uuid_recorded": doc_version.storage_binding_id is not None,
                            "locator_recorded_not_probed": locator,
                            "checksum_recorded_not_verified": checksum,
                            "binary_verified": False,
                        })
                    variants_private.append({
                        "document_variant_uuid": variant.id,
                        "variant_type": variant.variant_type.value,
                        "versions": versions_private,
                    })
                inventory.append({
                    "document_uuid": doc.id,
                    "family_code": doc.family_code,
                    "document_type_code": doc.document_type_code,
                    "also_points_to_certificate_and_case": (
                        doc.certificate_id is not None and doc.case_id is not None
                    ),
                    "variants": variants_private,
                })
            counts[f"{role}_target_records"] += 1
            counts[f"{role}_attached_document_rows"] += len(inventory)
            if not inventory:
                counts[f"{role}_without_document_metadata"] += 1
            private_targets.append({
                "legacy_certificate_id": target["legacy_certificate_id"],
                "role": role,
                "parent_uuid": parent_uuid,
                "documents": inventory,
                "primary_issuance_provenance_verified": False,
                "legal_site_coverage_verified": False,
            })

    return {
        "schema": SCHEMA,
        "status": STATUS,
        "database": EXPECTED_DB,
        "source_certificate_count": len(target_rows),
        "distinct_canonical_certificate_count": len(cert_ids),
        "distinct_canonical_case_count": len(case_ids),
        "document_rows_distinct": len(doc_ids),
        "variant_rows_distinct": len(variants),
        "version_rows_distinct": len(version_rows),
        "per_role_unique_document_counts": {
            role: len(unique_docs_by_role[role])
            for role in ("CERTIFICATE", "ORIGINAL_CASE", "REVERSE_CASE_CANDIDATE")
        },
        "counts": dict(sorted(counts.items())),
        "private_document_evidence_queue": private_targets,
        "binary_content_verified": False,
        "recorded_locator_is_verified": False,
        "recorded_checksum_is_verified": False,
        "original_signed_issuance_verified": False,
        "primary_issuance_case_link_verified": False,
        "case_rebinding_authorized": False,
        "site_specific_scope_coverage_approved": False,
        "ddk_gxp_links_approved": False,
        "database_writes": 0,
        "nas_reads": 0,
        "storage_binding_writes": 0,
    }


def _validate_private_output(path: Path) -> None:
    _require(not path.is_symlink() and not path.exists(),
             "Private report destination already exists")
    directory = path.parent
    _require(directory.is_dir() and not directory.is_symlink(),
             "Private report directory must already exist")
    info = directory.stat()
    _require(info.st_uid == os.geteuid()
             and stat.S_IMODE(info.st_mode) & 0o077 == 0,
             "Private report directory must be owned by operator and private")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-env", type=Path, default=Path("/etc/gxp/runtime.env"))
    parser.add_argument("--snapshot", type=Path, default=Path(
        "artifacts/phase3c/legacy_snapshot.json"))
    parser.add_argument("--private-output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        _validate_private_output(args.private_output)
        source_bytes = args.snapshot.read_bytes()
        _require(sha256(source_bytes).hexdigest() == EXPECTED_SNAPSHOT_SHA256,
                 "Original source snapshot changed")
        source = json.loads(source_bytes)
        snapshot = source.get("sheets", source)
        excluded = {key for sheet, key in load_confirmed_blanked_row_keys()
                    if sheet == "db.cc"}
        source_report = audit_certificate_case_source_links(
            snapshot, excluded_certificate_row_keys=excluded
        )
        _require(source_report.get("effective_certificate_source_rows") == 1601
                 and {x["certificate_legacy_id"] for x in
                      source_report.get("effective_anomalies", [])}
                    == EXPECTED_SOURCE_CERTIFICATES,
                 "Certificate source exception set drifted")
        url = checked_rehearsal_url(parse_env_file(args.runtime_env))
        engine = create_engine(url, poolclass=NullPool, connect_args={
            "options": "-c default_transaction_read_only=on -c statement_timeout=30000",
        })
        try:
            with engine.connect() as connection, connection.begin():
                connection.exec_driver_sql("SET TRANSACTION READ ONLY")
                _require(
                    connection.execute(text("SELECT current_database()")).scalar_one() == EXPECTED_DB
                    and connection.execute(text("SHOW transaction_read_only")).scalar_one() == "on"
                    and list(connection.execute(text(
                        "SELECT version_num FROM public.alembic_version"
                    )).scalars()) == [EXPECTED_REVISION],
                    "Unexpected database, transaction mode or revision",
                )
                with Session(bind=connection) as session:
                    anchor = compare_source_to_rehearsal(
                        session, source_report,
                        expected_certificate_ids=set(EXPECTED_SOURCE_CERTIFICATES),
                    )
                    report = scan_issuance_document_metadata(session, anchor)
                    report["original_source_snapshot_sha256"] = EXPECTED_SNAPSHOT_SHA256
                    report["database_transaction_read_only"] = True
        finally:
            engine.dispose()
        _write_private_json(args.private_output, report)
        safe = {
            k: v for k, v in report.items()
            if k not in {"private_document_evidence_queue"}
        }
        print(json.dumps(safe, ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as exc:
        # Never expose DB URL, protected document IDs, filenames or private paths.
        print("ISSUANCE_DOCUMENT_METADATA_WITNESS_BLOCKED: "
              + type(exc).__name__, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
