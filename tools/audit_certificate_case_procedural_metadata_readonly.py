"""Source-bound inspection procedural metadata (no file lookup, no adjudication).

Standalone read-only follow-up to V5/V6: checks original and reverse source
Cases, then reports whether rehearsal contains inspection timeline, plan,
decisions, approval rounds, archive-year anchor, or storage binding METADATA.
None of these establish originating issuance or per-Site GMP certification.
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
    Case, Certificate, CertificateRelationship, CaseApplication,
    InspectionApprovalSubmission, InspectionDecision, InspectionOutcome,
    InspectionPlan, LegacyInspectionStorageAnchor, StorageBinding,
)
from backend.app.domain.legacy_certificate_case_source_audit import (
    audit_certificate_case_source_links,
)
from backend.app.domain.phase2_import import load_confirmed_blanked_row_keys
from tools.apply_ddk_gxp_provenance_rehearsal import checked_rehearsal_url
from tools.audit_certificate_case_site_owners_rehearsal_readonly import (
    EXPECTED_SNAPSHOT_SHA256, EXPECTED_SOURCE_CERTIFICATES, SCHEMA as ANCHOR_SCHEMA,
    compare_source_to_rehearsal,
)
from tools.audit_certificate_case_issuance_document_metadata_readonly import (
    SCHEMA as DOCUMENT_SCHEMA, scan_issuance_document_metadata,
    _validate_private_output,
)
from tools.audit_ddk_gxp_canonical_candidates_readonly import _write_private_json
from tools.env_utils import parse_env_file
from tools.preflight_ddk_gxp_rehearsal import EXPECTED_DB, EXPECTED_REVISION

SCHEMA = "GXP_CERTIFICATE_CASE_PROCEDURAL_METADATA_V1"
STATUS = "PROCEDURAL_METADATA_ONLY_ISSUANCE_NOT_ADJUDICATED"


class ProceduralMetadataBlocked(ValueError):
    pass


def _require(test: bool, msg: str) -> None:
    if not test:
        raise ProceduralMetadataBlocked(msg)


def scan_procedural_metadata(
    session: Session, anchor: dict[str, Any], *,
    expected_certificate_ids: frozenset[int] = EXPECTED_SOURCE_CERTIFICATES,
) -> dict[str, Any]:
    """Pure SELECT classification with source-bound Case identities and no paths."""
    details = anchor.get("details_private")
    _require(
        anchor.get("schema") == ANCHOR_SCHEMA
        and anchor.get("database") == EXPECTED_DB
        and anchor.get("status") == "SOURCE_AND_CANONICAL_ANCHORS_VERIFIED_COVERAGE_NOT_APPROVED"
        and anchor.get("case_rebinding_authorized") is False
        and anchor.get("site_specific_scope_coverage_approved") is False
        and anchor.get("database_writes") == 0
        and anchor.get("nas_reads") == 0
        and isinstance(details, list)
        and len(details) == len(expected_certificate_ids),
        "Anchor witness not suitable for procedural metadata review",
    )
    _require(
        len({x["legacy_certificate_id"] for x in details}) == len(details)
        and {x["legacy_certificate_id"] for x in details} == expected_certificate_ids
        and anchor.get("counts", {}).get("source_certificate_version_fidelity_verified")
            == len(expected_certificate_ids),
        "Unexpected source Certificate set or unverified import values",
    )

    case_roles: dict[str, list[dict[str, Any]]] = defaultdict(list)
    cert_ids: dict[str, int] = {}
    for cert in details:
        cert_uuid = cert.get("certificate_id")
        source_cert_id = cert["legacy_certificate_id"]
        _require(isinstance(cert_uuid, str) and bool(cert_uuid),
                 "Missing canonical Certificate")
        cert_ids[cert_uuid] = source_cert_id
        original_uuid = cert["original_linked_case_id"]
        _require(isinstance(original_uuid, str) and original_uuid,
                 "Missing original Case")
        case_roles[original_uuid].append({
            "legacy_certificate_id": source_cert_id,
            "role": "ORIGINAL_LINKED_CASE",
            "legacy_case_id": cert["original_case_legacy_id"],
        })
        for candidate in cert["reverse_case_review_candidates"]:
            _require(candidate.get("remediation_authorized") is False
                     and candidate.get("primary_signed_issuance_case_link_verified") is False,
                     "Reverse Case marked as verified or approved")
            case_uuid = candidate["case_id"]
            _require(isinstance(case_uuid, str) and case_uuid,
                     "Missing reverse Case UUID")
            case_roles[case_uuid].append({
                "legacy_certificate_id": source_cert_id,
                "role": "REVERSE_CASE_CANDIDATE",
                "legacy_case_id": candidate["legacy_case_id"],
            })
    _require(len(cert_ids) == len(details), "Duplicate canonical Certificate mapping")
    for uuid, roles in case_roles.items():
        observed = {r["legacy_case_id"] for r in roles}
        _require(len(observed) == 1, "One Case UUID has contradictory legacy identities")
        case = session.get(Case, uuid)
        _require(
            case is not None and case.legacy_inspection_id in observed,
            "Case source/canonical identity changed",
        )

    case_uuids = set(case_roles)
    applications = list(session.scalars(
        select(CaseApplication).where(CaseApplication.case_id.in_(case_uuids))
    ))
    plans = list(session.scalars(
        select(InspectionPlan).where(InspectionPlan.case_id.in_(case_uuids))
    ))
    outcomes = list(session.scalars(
        select(InspectionOutcome).where(InspectionOutcome.case_id.in_(case_uuids))
    ))
    anchors = list(session.scalars(
        select(LegacyInspectionStorageAnchor).where(
            LegacyInspectionStorageAnchor.case_id.in_(case_uuids)
        )
    ))
    submissions = list(session.scalars(select(InspectionApprovalSubmission).where(
        InspectionApprovalSubmission.case_id.in_(case_uuids)
    )))
    bindings = list(session.scalars(select(StorageBinding).where(
        StorageBinding.case_id.in_(case_uuids)
    )))
    decisions = list(session.scalars(select(InspectionDecision).where(
        InspectionDecision.inspection_plan_id.in_({p.id for p in plans})
    ))) if plans else []
    relationships = list(session.scalars(select(CertificateRelationship).where(
        or_(
            CertificateRelationship.source_certificate_id.in_(set(cert_ids)),
            CertificateRelationship.target_certificate_id.in_(set(cert_ids)),
        )
    )))
    # Related external Certificates are context, not automatically part of
    # these three approved review identities. Do not emit them as linked.
    _require(
        len({r.id for r in relationships}) == len(relationships),
        "Duplicate Certificate relationship row",
    )

    def _unique_by_case(rows: list[Any], label: str) -> dict[str, Any]:
        lookup = {row.case_id: row for row in rows}
        _require(len(lookup) == len(rows), f"Duplicate {label} for Case")
        return lookup

    app_by_case = _unique_by_case(applications, "CaseApplication")
    plan_by_case = _unique_by_case(plans, "InspectionPlan")
    outcome_by_case = _unique_by_case(outcomes, "InspectionOutcome")
    anchor_by_case = _unique_by_case(anchors, "StorageAnchor")
    decisions_by_plan: dict[str, list[InspectionDecision]] = defaultdict(list)
    for decision in decisions:
        decisions_by_plan[decision.inspection_plan_id].append(decision)
    submissions_by_case: dict[str, list[InspectionApprovalSubmission]] = defaultdict(list)
    for submission in submissions:
        submissions_by_case[submission.case_id].append(submission)
    bindings_by_case: dict[str, list[StorageBinding]] = defaultdict(list)
    for binding in bindings:
        bindings_by_case[binding.case_id].append(binding)

    counts: Counter[str] = Counter()
    private = []
    for case_uuid, roles in sorted(
        case_roles.items(), key=lambda item: min(r["legacy_case_id"] for r in item[1])
    ):
        case = session.get(Case, case_uuid)
        application = app_by_case.get(case_uuid)
        plan = plan_by_case.get(case_uuid)
        outcome = outcome_by_case.get(case_uuid)
        storage_anchor = anchor_by_case.get(case_uuid)
        decisions_for_case = decisions_by_plan[plan.id] if plan else []
        submission_rows = submissions_by_case[case_uuid]
        binding_rows = bindings_by_case[case_uuid]
        if application: counts["case_applications_recorded"] += 1
        if plan: counts["inspection_plans_recorded"] += 1
        if outcome: counts["inspection_outcomes_recorded"] += 1
        if storage_anchor: counts["legacy_year_anchors_recorded"] += 1
        if binding_rows: counts["cases_with_storage_binding_metadata"] += 1
        counts["inspection_decision_rows"] += len(decisions_for_case)
        counts["approval_submission_rows"] += len(submission_rows)
        counts["storage_binding_rows"] += len(binding_rows)
        if plan and (plan.decision_reference or decisions_for_case):
            counts["cases_with_inspection_decision_references"] += 1
        if outcome and (outcome.decision_reference or outcome.bbkt_reference):
            counts["cases_with_outcome_or_minutes_reference"] += 1
        private.append({
            "case_uuid": case_uuid,
            "source_legacy_case_id": case.legacy_inspection_id,
            "source_certificate_roles": sorted(roles, key=lambda r: (r["legacy_certificate_id"], r["role"])),
            "application_present": bool(application),
            "application_dossier_reference_recorded": bool(application and application.dossier_reference),
            "inspection_plan_present": bool(plan),
            "plan_decision_reference_recorded": bool(plan and plan.decision_reference),
            "inspection_decisions": [{
                "ordinal": decision.ordinal,
                "decision_date": decision.decision_on.isoformat(),
                "reference_sha256": sha256(decision.reference.encode("utf-8")).hexdigest(),
                "relation_type_recorded": decision.relation_type is not None,
            } for decision in sorted(decisions_for_case, key=lambda x: x.ordinal)],
            "inspection_outcome_present": bool(outcome),
            "inspection_period_state": outcome.inspection_period_state if outcome else None,
            "inspection_start": outcome.inspected_on.isoformat() if outcome and outcome.inspected_on else None,
            "inspection_end": outcome.inspected_to_on.isoformat() if outcome and outcome.inspected_to_on else None,
            "outcome_decision_reference_recorded": bool(outcome and outcome.decision_reference),
            "minutes_reference_recorded": bool(outcome and outcome.bbkt_reference),
            "approval_submissions": {
                "PCT": sum(x.stage == "PCT" for x in submission_rows),
                "CT": sum(x.stage == "CT" for x in submission_rows),
            },
            "legacy_archive_year_anchor": {
                "present": bool(storage_anchor),
                "registration_year_status": storage_anchor.registration_submission_status if storage_anchor else None,
                "inspection_year_status": storage_anchor.inspection_year_status if storage_anchor else None,
                "registration_year": storage_anchor.registration_submission_year if storage_anchor else None,
                "inspection_year": storage_anchor.inspection_year if storage_anchor else None,
                "source_hash_recorded_not_reverified": bool(storage_anchor and storage_anchor.source_hash),
                "not_a_storage_locator": True,
            },
            "storage_binding_metadata_count_not_validated": len(binding_rows),
            "archive_content_verified": False,
            "originating_issuance_case_verified": False,
            "site_scope_grant_verified": False,
        })
    rel_private = []
    for relation in relationships:
        rel_private.append({
            "source_certificate_legacy_id": cert_ids.get(relation.source_certificate_id),
            "target_certificate_legacy_id": cert_ids.get(relation.target_certificate_id),
            "one_endpoint_outside_review_corpus": (
                relation.source_certificate_id not in cert_ids
                or relation.target_certificate_id not in cert_ids
            ),
            "recorded_relation_type": relation.relation_type,
            "recorded_effective_on": relation.effective_on.isoformat(),
            "recorded_not_adjudicated": True,
        })
    return {
        "schema": SCHEMA,
        "status": STATUS,
        "database": EXPECTED_DB,
        "source_certificate_count": len(details),
        "distinct_canonical_case_count": len(case_roles),
        "counts": dict(sorted(counts.items())),
        "certificate_relationship_metadata_rows": len(relationships),
        "private_case_procedural_metadata": private,
        "private_certificate_relation_metadata": rel_private,
        "primary_issuance_document_verified": False,
        "case_rebinding_authorized": False,
        "site_specific_scope_coverage_approved": False,
        "archive_year_is_file_location": False,
        "storage_binding_metadata_is_binary_proof": False,
        "database_writes": 0,
        "nas_reads": 0,
        "storage_binding_writes": 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-env", type=Path, default=Path("/etc/gxp/runtime.env"))
    parser.add_argument("--snapshot", type=Path, default=Path("artifacts/phase3c/legacy_snapshot.json"))
    parser.add_argument("--private-output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        _validate_private_output(args.private_output)
        raw = args.snapshot.read_bytes()
        _require(sha256(raw).hexdigest() == EXPECTED_SNAPSHOT_SHA256,
                 "Original source snapshot bytes changed")
        source = json.loads(raw)
        snapshot = source.get("sheets", source)
        excluded = {key for sheet, key in load_confirmed_blanked_row_keys() if sheet == "db.cc"}
        audit = audit_certificate_case_source_links(
            snapshot, excluded_certificate_row_keys=excluded
        )
        _require(
            audit.get("effective_certificate_source_rows") == 1601
            and {x["certificate_legacy_id"] for x in audit.get("effective_anomalies", [])}
                == EXPECTED_SOURCE_CERTIFICATES,
            "Original Certificate source exception population changed",
        )
        url = checked_rehearsal_url(parse_env_file(args.runtime_env))
        engine = create_engine(url, poolclass=NullPool, connect_args={
            "options": "-c default_transaction_read_only=on -c statement_timeout=30000",
        })
        try:
            with engine.connect() as connection, connection.begin():
                connection.exec_driver_sql(
                    "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
                )
                _require(
                    connection.execute(text("SELECT current_database()")).scalar_one() == EXPECTED_DB
                    and connection.execute(text("SHOW transaction_read_only")).scalar_one() == "on"
                    and connection.execute(text("SHOW transaction_isolation")).scalar_one() == "repeatable read"
                    and list(connection.execute(text(
                        "SELECT version_num FROM public.alembic_version"
                    )).scalars()) == [EXPECTED_REVISION],
                    "Unexpected rehearsal, revision or transaction mode",
                )
                with Session(bind=connection) as session:
                    anchor = compare_source_to_rehearsal(
                        session, audit, expected_certificate_ids=set(EXPECTED_SOURCE_CERTIFICATES)
                    )
                    documents = scan_issuance_document_metadata(session, anchor)
                    _require(
                        documents.get("schema") == DOCUMENT_SCHEMA
                        and documents.get("database_writes") == 0
                        and documents.get("binary_content_verified") is False
                        and documents.get("case_rebinding_authorized") is False,
                        "Document inventory gate does not permit review",
                    )
                    report = scan_procedural_metadata(session, anchor)
                    report["document_metadata_count"] = documents["document_rows_distinct"]
                    report["document_binary_verified"] = False
                    report["source_snapshot_sha256"] = EXPECTED_SNAPSHOT_SHA256
                    report["database_transaction_read_only"] = True
                    report["database_transaction_isolation"] = "repeatable read"
        finally:
            engine.dispose()
        _write_private_json(args.private_output, report)
        safe = {key: value for key, value in report.items() if not key.startswith("private_")}
        print(json.dumps(safe, ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as exc:
        print("PROCEDURAL_METADATA_READONLY_BLOCKED: " + type(exc).__name__,
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
