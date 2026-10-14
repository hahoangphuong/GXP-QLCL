"""Source-bound inspection-code-only folder Site crosswalk (no SMB/mutation).

This diagnostic compares a single NAS *name token* to the imported Site and
Case projection in rehearsal.  Imported site rows are NOT independent physical
db.cso source evidence; no source Site reassignment or link is authorized.
"""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models.phase1 import Case, LegacyInspectionStorageAnchor, Site
from tools.audit_ddk_gxp_case_year_transitions_readonly import compare_private_case_observations
from tools.audit_ddk_gxp_smb_readonly_folder_pilot import verified_lookup_targets
from tools.audit_ddk_gxp_storage_identity_readiness import profile_storage_lookup_inputs
from tools.build_ddk_gxp_manual_review_queue import build_review_queue

SCHEMA = "GXP_DDK_CODE_ONLY_INSPECTION_SITE_SOURCE_CROSSWALK_READONLY_V1"


class InspectionSiteCrosswalkBlocked(ValueError):
    pass


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise InspectionSiteCrosswalkBlocked(reason)


def extract_source_bound_marker(
    dossier: dict[str, Any],
    queue: dict[str, Any],
    readiness_bytes: bytes,
    full_bytes: bytes,
    dual_bytes: bytes,
    prior_bytes: bytes,
    marker_bytes: bytes,
) -> dict[str, Any]:
    """Fail closed on the *entire* original 6-Case lineage before taking 1 ID."""
    ready = json.loads(readiness_bytes)
    full = json.loads(full_bytes)
    dual = json.loads(dual_bytes)
    prior = json.loads(prior_bytes)
    marker = json.loads(marker_bytes)
    rhash = sha256(readiness_bytes).hexdigest()
    fhash = sha256(full_bytes).hexdigest()
    dhash = sha256(dual_bytes).hexdigest()
    phash = sha256(prior_bytes).hexdigest()
    _require(queue == build_review_queue(dossier), "Original source queue changed")
    transitions = compare_private_case_observations(full, dual, queue, ready, rhash)
    _require(
        transitions["case_parents_compared"] == 6
        and transitions["resolved_case_regressions"] == 0
        and transitions["year_specific_observations_checked"] == 9,
        "Protected original Case/year report changed",
    )
    ddks, cases = verified_lookup_targets(queue, ready)
    _require(len(ddks) == 8 and len(cases) == 6, "Source parent population drifted")
    _require(
        prior.get("schema") == "GXP_DDK_MISSING_CASE_YEAR_ROOT_SHAPE_READONLY_V1"
        and prior.get("status") == "ORIGINAL_NOT_FOUND_YEAR_ROOT_METADATA_CLASSIFIED"
        and prior.get("approval_status") == "NOT_APPROVED"
        and prior.get("source_readiness_sha256") == rhash
        and prior.get("source_full_smb_sha256") == fhash
        and prior.get("source_dual_year_smb_sha256") == dhash
        and prior.get("missing_case_parents_checked") == 3
        and prior.get("source_year_observations_checked") == 4
        and prior.get("classification_counts") ==
            {"NO_EXACT_TOKEN": 3, "INSPECTION_CODE_ONLY": 1}
        and prior.get("database_connected") is False
        and prior.get("database_writes") == 0
        and prior.get("storage_writes") == 0
        and prior.get("canonical_links_created") == 0,
        "Prior code-only classification not source-bound",
    )
    _require(
        marker.get("schema") == "GXP_DDK_CODE_ONLY_INSPECTION_SITE_MARKER_READONLY_V1"
        and marker.get("status") == "ONE_SOURCE_BOUND_CASE_YEAR_CODE_ONLY_METADATA_CLASSIFIED"
        and marker.get("approval_status") == "NOT_APPROVED"
        and marker.get("source_readiness_sha256") == rhash
        and marker.get("source_full_smb_sha256") == fhash
        and marker.get("source_dual_year_smb_sha256") == dhash
        and marker.get("source_prior_metadata_sha256") == phash
        and marker.get("source_case_year_observations_checked") == 1
        and marker.get("source_year_roots_checked") == 1
        and marker.get("code_matching_directories_checked") == 1
        and marker.get("classification_counts") == {"OTHER_NUMERIC_ID_TOKEN": 1}
        and marker.get("database_connected") is False
        and marker.get("database_writes") == 0
        and marker.get("storage_writes") == 0
        and marker.get("canonical_links_created") == 0,
        "Observed Site token metadata not source-bound",
    )
    obs = prior.get("private_case_year_metadata_observations")
    rows = dual.get("private_case_observations")
    _require(
        isinstance(obs, list) and len(obs) == 4
        and isinstance(rows, list) and len(rows) == 6,
        "Missing original Case/year observations",
    )
    source_missing = {
        (row["originating_case_id"], year["source_year"])
        for row in rows if row["final_status"] == "NOT_FOUND"
        for year in row["year_specific_observations"]
    }
    _require(len(source_missing) == 4
             and {(r["originating_case_id"], r["source_year"]) for r in obs} == source_missing,
             "Changed Case/year identity set")
    code_only = [r for r in obs if r.get("classification") == "INSPECTION_CODE_ONLY"]
    _require(len(code_only) == 1, "No unique code-only source Case/year")
    case_id = code_only[0]["originating_case_id"]
    year = code_only[0]["source_year"]
    source = {row["parent_id"]: row for row in cases}.get(case_id)
    _require(source is not None, "Original Case identity missing")
    original = {row["originating_case_id"]: row for row in rows}[case_id]
    _require(original["final_status"] == "NOT_FOUND"
             and any(
                 item.get("source_year") == year and item.get("status") == "not_found"
                 and item.get("candidate_count") == 0
                 for item in original["year_specific_observations"]),
             "Case/year no longer source-verified NOT_FOUND")
    _require(
        marker.get("source_case_parent_id_private") == case_id
        and marker.get("source_year_private") == year
        and marker.get("source_site_legacy_id_private") == source["site_legacy_id"],
        "Site marker belongs to different Case/year",
    )
    private = marker.get("private_folder_token_observations")
    _require(isinstance(private, list) and len(private) == 1,
             "Unexpected observed folder population")
    item = private[0]
    observed = item.get("observed_numeric_site_ids_unverified")
    _require(
        item.get("classification") == "OTHER_NUMERIC_ID_TOKEN"
        and isinstance(observed, list) and len(observed) == 1
        and type(observed[0]) is int and observed[0] > 0
        and type(source["site_legacy_id"]) is int
        and source["site_legacy_id"] > 0
        and observed[0] != source["site_legacy_id"],
        "No independently distinct observed numeric Site ID",
    )
    # No folder names, UNC strings or IDs may enter stdout.
    return {
        "case_id": case_id,
        "source_site_legacy_id": source["site_legacy_id"],
        "observed_site_legacy_id_unverified": observed[0],
        "inspection_code": source["inspection_legacy_code"],
        "source_year": year,
        "readiness": ready,
        "readiness_sha256": rhash,
        "marker_sha256": sha256(marker_bytes).hexdigest(),
    }


def evaluate_canonical_projection(
    *,
    target: dict[str, Any],
    source_site: Site | None,
    observed_site: Site | None,
    source_case: Case | None,
    source_anchor: LegacyInspectionStorageAnchor | None,
    same_code_cases: list[Case],
) -> dict[str, Any]:
    """Classify imported database rows, without adjudicating original db.cso."""
    _require(
        source_site is not None
        and source_site.legacy_site_id == target["source_site_legacy_id"]
        and source_case is not None
        and source_case.id == target["case_id"]
        and source_case.site_id == source_site.id
        and source_case.legacy_inspection_code == target["inspection_code"]
        and source_anchor is not None
        and source_anchor.case_id == source_case.id
        and source_anchor.source_sheet == "db.ktra"
        and type(source_anchor.source_row) is int
        and source_anchor.source_row > 0
        and isinstance(source_anchor.source_hash, str)
        and len(source_anchor.source_hash) == 64
        and isinstance(source_anchor.source_version, str)
        and len(source_anchor.source_version) == 64,
        "Original canonical Site/Case/db.ktra anchor drifted",
    )
    _require(
        isinstance(same_code_cases, list)
        and 1 <= len(same_code_cases) <= 100
        and len({row.id for row in same_code_cases}) == len(same_code_cases)
        and any(row.id == source_case.id for row in same_code_cases)
        and all(row.legacy_inspection_code == target["inspection_code"] for row in same_code_cases),
        "Case code identity population malformed or unbounded",
    )
    if observed_site is None:
        classification = "OBSERVED_ID_ABSENT_IN_IMPORTED_SITE_DIRECTORY"
    else:
        _require(
            observed_site.legacy_site_id == target["observed_site_legacy_id_unverified"]
            and observed_site.id != source_site.id,
            "Observed numeric Site ID ambiguous or source identity changed",
        )
        classification = "OBSERVED_ID_EXISTS_AS_DIFFERENT_IMPORTED_SITE"
    same_code_other = [
        row for row in same_code_cases
        if row.id != source_case.id
    ]
    other_site_code = [
        row for row in same_code_other
        if observed_site is not None and row.site_id == observed_site.id
    ]
    return {
        "schema": SCHEMA,
        "status": "IMPORT_PROJECTION_SITE_CODE_CROSSWALK_ONLY",
        "approval_status": "NOT_APPROVED",
        "observed_site_classification": classification,
        "source_site_case_anchor_unchanged": True,
        "observed_site_same_company_as_source": (
            None if observed_site is None
            else observed_site.company_id == source_site.company_id
        ),
        "matching_inspection_code_case_count": len(same_code_cases),
        "other_case_with_same_code_count": len(same_code_other),
        "other_case_with_observed_site_and_same_code_count": len(other_site_code),
        "observed_id_physically_verified_in_db_cso": False,
        "source_case_physically_reverified_in_db_ktra": False,
        "database_access": "REHEARSAL_READ_ONLY",
        "database_writes": 0,
        "storage_connected": False,
        "storage_writes": 0,
        "canonical_links_created": 0,
        "private_identity_observations": {
            "source_case_id": source_case.id,
            "source_site_canonical_id": source_site.id,
            "observed_site_canonical_id_unverified": (
                observed_site.id if observed_site is not None else None
            ),
            "same_inspection_code_other_case_ids_unverified": [
                row.id for row in same_code_other
            ],
        },
        "limitations": [
            "Site rows are IMPORTED db.cso projections, not verified physical workbook evidence",
            "db.ktra row/hash is an imported anchor, not a re-read workbook cell",
            "A NAS filename Site marker cannot supersede source Case.site_id",
            "No transfer of ownership, binder repair, Certificate/DDK linking or migration",
        ],
    }


def read_imported_site_case_crosswalk(
    session: Session, queue: dict[str, Any], target: dict[str, Any],
) -> dict[str, Any]:
    """DB read only; caller MUST open a guarded read-only rehearsal transaction."""
    _require(
        profile_storage_lookup_inputs(session, queue) == target["readiness"],
        "Whole original source-readiness population drifted",
    )
    source_site = session.scalar(
        select(Site).where(Site.legacy_site_id == target["source_site_legacy_id"])
    )
    observed_site = session.scalar(
        select(Site).where(Site.legacy_site_id == target["observed_site_legacy_id_unverified"])
    )
    source_case = session.get(Case, target["case_id"])
    anchor = session.scalar(
        select(LegacyInspectionStorageAnchor).where(
            LegacyInspectionStorageAnchor.case_id == target["case_id"]
        )
    )
    cases = list(session.scalars(select(Case).where(
        Case.legacy_inspection_code == target["inspection_code"]
    ).limit(101)))
    _require(len(cases) <= 100, "Case code collision population budget exceeded")
    return evaluate_canonical_projection(
        target=target, source_site=source_site, observed_site=observed_site,
        source_case=source_case, source_anchor=anchor, same_code_cases=cases,
    )
