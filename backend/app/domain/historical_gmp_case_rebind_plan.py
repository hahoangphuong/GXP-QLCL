"""Exact-row, read-only historical GMP Case-origin reconciliation plan.

The data owner's confirmation of the original issuing Case is distinct from
authorization to mutate the rehearsal database. This module only reads state;
it cannot generate/apply SQL changes or relax any issuance validation.
"""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models.phase1 import Case, Certificate
from tools.audit_certificate_case_site_owners_rehearsal_readonly import (
    SCHEMA as WITNESS_SCHEMA, EXPECTED_DB, EXPECTED_SNAPSHOT_SHA256,
)


class HistoricalGmpRebindBlocked(ValueError):
    """Fail closed on missing, ambiguous, stale or unconfirmed provenance."""


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise HistoricalGmpRebindBlocked(reason)


def plan_historical_gmp_case_rebind_readonly(
    session: Session,
    *,
    witness: Mapping[str, Any],
    decision: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a *non-executable* exact-row proposal from pinned source and DB.

    Caller must enforce a read-only database transaction. Even a complete plan
    is NOT authorization for a later update, migration, or scope backfill.
    """
    _require(
        witness.get("schema") == WITNESS_SCHEMA
        and witness.get("status") == "SOURCE_AND_CANONICAL_ANCHORS_VERIFIED_COVERAGE_NOT_APPROVED"
        and witness.get("database") == EXPECTED_DB
        and witness.get("database_transaction_read_only") is True
        and witness.get("snapshot_sha256") == EXPECTED_SNAPSHOT_SHA256
        and witness.get("database_writes") == 0
        and witness.get("case_rebinding_authorized") is False
        and witness.get("site_specific_scope_coverage_approved") is False,
        "UNTRUSTED_SOURCE_OR_NON_READ_ONLY_WITNESS",
    )
    _require(
        decision.get("schema") == "gmp-owner-confirmed-issuing-case/v1"
        and decision.get("source_snapshot_sha256") == EXPECTED_SNAPSHOT_SHA256
        and decision.get("owner_confirmed_issuing_case") is True
        and decision.get("database_write_authorized") is False
        and isinstance(decision.get("owner_decision_reference"), str)
        and bool(decision["owner_decision_reference"].strip()),
        "OWNER_OR_SOURCE_DECISION_INCOMPLETE",
    )
    legacy_certificate_id = decision.get("certificate_legacy_id")
    prior_case_id = decision.get("incorrect_imported_case_legacy_id")
    replacement_case_id = decision.get("confirmed_issuing_case_legacy_id")
    _require(
        all(type(item) is int and item > 0 for item in (
            legacy_certificate_id, prior_case_id, replacement_case_id
        )) and prior_case_id != replacement_case_id,
        "SOURCE_IDENTITIES_MISSING_OR_EQUAL",
    )

    details = witness.get("details_private")
    _require(isinstance(details, list) and bool(details), "WITNESS_DETAILS_ABSENT")
    matched = [row for row in details if row.get("legacy_certificate_id") == legacy_certificate_id]
    _require(len(matched) == 1, "SOURCE_CERTIFICATE_NOT_UNIQUE")
    detail = matched[0]
    _require(
        detail.get("original_case_legacy_id") == prior_case_id
        and detail.get("original_linked_case_id")
        and detail.get("source_site_company_relation") ==
            "DISTINCT_SITES_DIFFERENT_SOURCE_COMPANIES"
        and detail.get("case_rebinding_authorized") is False
        and detail.get("legal_coverage_approved") is False
        and detail.get("decision_gate") ==
            "ORIGINAL_ISSUANCE_CASE_AND_OWNER_SIGNOFF_REQUIRED",
        "UNEXPECTED_ORIGINAL_LINK_OR_SOURCE_CONTEXT",
    )
    candidates = detail.get("reverse_case_review_candidates")
    _require(isinstance(candidates, list), "REVERSE_CASE_WITNESS_ABSENT")
    chosen = [row for row in candidates if row.get("legacy_case_id") == replacement_case_id]
    _require(
        len(chosen) == 1
        and chosen[0].get("all_three_source_signals") is True
        and chosen[0].get("source_reverse_reference_only") is True
        and chosen[0].get("remediation_authorized") is False
        and chosen[0].get("source_site_gxp_correspondence") is True
        and chosen[0].get("source_certificate_number_correspondence") is True
        and chosen[0].get("source_full_scope_lexical_correspondence") is True
        and chosen[0].get("site_id") == detail.get("certificate_site_id")
        and chosen[0].get("gxp_type") == "GMP",
        "ORIGINATING_CASE_REVERSE_EVIDENCE_NOT_UNIQUE",
    )
    versions = detail.get("certificate_versions")
    _require(
        isinstance(versions, list) and len(versions) == 1
        and versions[0].get("version_no") == 1
        and versions[0].get("original_import_value_fidelity_verified") is True
        and versions[0].get("site_specific_scope_coverage_verified") is False,
        "HISTORICAL_CERTIFICATE_VERSION_NOT_EXACT",
    )

    # Independently compare the latest selected canonical state to the witness:
    # never derive a write plan from stale or simply self-reported UUIDs.
    certificate_rows = list(session.scalars(
        select(Certificate).where(Certificate.legacy_certificate_id == legacy_certificate_id)
    ))
    _require(len(certificate_rows) == 1, "TARGET_CERTIFICATE_NOT_UNIQUE")
    certificate = certificate_rows[0]
    _require(
        certificate.id == detail.get("certificate_id")
        and certificate.case_id == detail.get("original_linked_case_id")
        and certificate.site_id == detail.get("certificate_site_id")
        and certificate.certificate_type == "GMP"
        and certificate.issuance_basis == "inspection_case",
        "CANONICAL_CERTIFICATE_CHANGED_SINCE_WITNESS",
    )

    original = session.get(Case, certificate.case_id)
    _require(
        original is not None and original.legacy_inspection_id == prior_case_id
        and original.site_id == detail.get("original_case_site_id")
        and original.gxp_type == "GMP",
        "CANONICAL_ORIGINAL_CASE_CHANGED",
    )
    target = session.get(Case, chosen[0]["case_id"])
    _require(
        target is not None and target.legacy_inspection_id == replacement_case_id
        and target.site_id == certificate.site_id
        and target.gxp_type == "GMP",
        "CANONICAL_ISSUING_CASE_CHANGED",
    )
    other_certificates = list(session.scalars(
        select(Certificate.id).where(
            Certificate.case_id == target.id,
            Certificate.id != certificate.id,
            Certificate.certificate_type == "GMP",
        )
    ))
    _require(not other_certificates, "ISSUING_CASE_ALREADY_LINKED_TO_OTHER_GMP")

    # The plan stores only the before/after value of ONE FK. The inverse is
    # reviewable but no executable SQL or "approved" flag can be emitted here.
    proposed = {
        "certificate_id": certificate.id,
        "legacy_certificate_id": legacy_certificate_id,
        "field": "certificate.case_id",
        "expected_before_case_id": original.id,
        "expected_before_case_legacy_id": prior_case_id,
        "proposed_after_case_id": target.id,
        "proposed_after_case_legacy_id": replacement_case_id,
        "certificate_site_id_unchanged": certificate.site_id,
        "certificate_type_unchanged": certificate.certificate_type,
        "issuance_basis_unchanged": certificate.issuance_basis,
        "inverse_rollback_case_id": original.id,
    }
    return {
        "schema": "gxp-historical-gmp-case-rebind-exact-row-review/v1",
        "status": "OWNER_CONFIRMED_SOURCE_ORIGIN_TARGET_VERIFIED_WRITE_NOT_AUTHORIZED",
        "decision_reference": decision["owner_decision_reference"],
        "source_snapshot_sha256": EXPECTED_SNAPSHOT_SHA256,
        "target_database": EXPECTED_DB,
        "expected_business_rows_to_change": 1,
        "proposed_change": proposed,
        "plan_sha256": sha256(
            json.dumps(proposed, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "document_binary_verified": False,
        "database_writes": 0,
        "database_write_authorized": False,
        "deployment_authorized": False,
        "backup_performed": False,
    }
